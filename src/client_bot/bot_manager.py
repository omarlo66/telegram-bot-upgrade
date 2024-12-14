import datetime

from django.conf import settings as django_settings
from pendulum import timezone
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler
)
from telethon import TelegramClient

from src.admin_bot.utils import ban_chat_member
from src.client_bot import settings
from src.client_bot.commands import Commands
from src.common import pendulum
from src.common.db import Database
from src.common.choices import SubscriptionRequestStatus, PaymentMethod
from src.common.formatters import format_date
from src.common.models import SubscriptionRequest, User, OfferMessage, Training
from src.common.models.group import Group
from asgiref.sync import sync_to_async

from src.common.utils import error_log

# noinspection PyMethodMayBeStatic
class BotManager(Commands):
    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def run(self):
        self._build_application()
        self._start_db()
        # self._start_telethon_client()
        self._map_commands()
        self._map_status_updates()
        self._map_callback_queries()
        self._add_error_handler()
        self._start_scheduler()
        self._run_application_polling()

    def _build_application(self):
        self.application = ApplicationBuilder().token(self.token).build()

    def _start_telethon_client(self):
        active_sender = self.db.get_active_sender()

        if active_sender:
            self.client = TelegramClient(
                api_id=active_sender.api_id,
                api_hash=active_sender.api_hash,
                session=str(active_sender.user_id)
            )

    def _map_commands(self):
        for command_name, command_func in self.command_mapping.items():
            handler = CommandHandler(command_name, command_func)
            self.application.add_handler(handler)

    def _map_status_updates(self):
        for status_update, status_update_func in self.status_update_mapping.items():
            self.application.add_handler(MessageHandler(status_update, status_update_func))

    def _map_callback_queries(self):
        for callback_query_func in self.callback_query_mapping:
            self.application.add_handler(CallbackQueryHandler(callback_query_func))

    def _start_db(self):
        self.db = Database()
        self.db.start()

    def _add_error_handler(self):
        self.application.add_error_handler(self.error_handler)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update == None:
            error_log().append(context.error)
            return
        await context.bot.send_message(
            chat_id=settings.DEVELOPER_CHAT_ID,
            text=(
                f'An error occurred: {context.error}\n'
                f'User: {update.effective_user.id}\n'
                f'Chat: {update.effective_chat.id}\n'
                f'Message: {update.effective_message.text}'
            )
        )

    def _start_scheduler(self):
        one_hour = datetime.timedelta(hours=1)
        next_hour = pendulum.now().start_of('hour') + one_hour

        self.application.job_queue.run_once(
            self._notify_users_with_ending_subscriptions,
            when=0
        )

        self.application.job_queue.run_daily(
            self._notify_users_with_ending_subscriptions,
            time=datetime.time(23, tzinfo=timezone(django_settings.TIME_ZONE))
        )

        self.application.job_queue.run_repeating(
            self._resolve_subscription_requests,
            interval=datetime.timedelta(seconds=10),
            first=0
        )

        self.application.job_queue.run_repeating(
            self._resolve_training_requests,
            interval=datetime.timedelta(seconds=10),
            first=0
        )

        self.application.job_queue.run_repeating(
            self._send_offer_messages,
            interval=one_hour,
            first=next_hour
        )

    async def _notify_users_with_ending_subscriptions(self, context: ContextTypes.DEFAULT_TYPE):
        notification_period = 7  # in days
        now = pendulum.now()

        async for user in User.objects.all():
            if not await user.subscriptions.filter(is_active=True).aexists():
                groups = await sync_to_async(lambda: list(Group.objects.filter(parent_id=None)))()
                for group in groups:
                    try:
                        await ban_chat_member(
                            chat_id=group['id'],
                            user=user,
                            context=context
                        )

                    except BadRequest:
                        ...
                continue

            async for subscription in user.get_active_subscriptions():
                remaining_subscription_days = subscription.days_left

                if (
                    remaining_subscription_days == notification_period and
                    subscription.user_notified_for_renewal_count == 0
                ):
                    subscription_end_date = subscription.end_date.strftime('%d/%m/%Y')
                    message = f'يرجى الانتباه. سيتم انتهاء اشتراكك في {subscription_end_date}.n\n {subscription.chat_name}\n\n'

                    if self.db.salla_link:
                        message += 'يمكنك اعادة الاشتراك عن طريق سلة: ' + self.db.salla_link

                    try:
                        await context.bot.send_message(chat_id=user.telegram_id, text=message)
                        subscription.user_notified_for_renewal_count += 1
                        await subscription.asave()

                    except BadRequest:
                        ...

                if (
                    remaining_subscription_days == 1 and
                    subscription.user_notified_for_renewal_count < 2
                ):
                    message = f'سيتم انتهاء اشتراكك اليوم. جدد اشتراكك الان للاستمتاع بمزايا قناتنا الخاصة. \n\n {subscription.chat_name}'

                    if self.db.salla_link:
                        message += 'يمكنك اعادة الاشتراك عن طريق سلة: ' + self.db.salla_link

                    try:
                        await context.bot.send_message(
                            chat_id=user.telegram_id,
                            text=message
                        )
                        subscription.user_notified_for_renewal_count += 1
                        await subscription.asave()

                    except BadRequest:
                        ...
                if (
                    remaining_subscription_days <= 0 and
                    subscription.is_active
                ):
                    try:
                        await ban_chat_member(
                            chat_id=subscription.chat_id,
                            user=user,
                            context=context
                        )
                        await subscription.deactivate()

                        try:
                            await context.bot.send_message(
                                chat_id=user.telegram_id,
                                text=f'لقد انتهى اشتراكك في قناة {subscription.chat_name}'
                                     f'. يمكنك تجديد الاشتراك '
                            )

                        except:
                            ...

                    except BadRequest:
                        ...

    async def _resolve_subscription_requests(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            requests = await sync_to_async(
                    lambda: list(SubscriptionRequest.objects.filter(
                        status__in=(SubscriptionRequestStatus.APPROVED, SubscriptionRequestStatus.DECLINED),
                        anounced=False
                    ))
                )()
            for request in requests:
                error_log().append(f'requests is pending: {request}')
                try:
                    if request.is_approved:
                        subscription = await request.asubscription
                        if subscription:
                            subscription.invoice_number = request.invoice_number
                            subscription.end_date = request.end_date
                            subscription.payment_method=PaymentMethod(request.payment_method)
                            subscription.tradingview_id=request.tradingview_id
                            await subscription.asave()

                            await self.approve_request_and_send_links_v2(
                                context,
                                request,
                                message_prefix=f"تمت الموافقة على طلب تجديد اشتراكك بنجاح.\n"
                            )

                        else:
                            try:
                                await request.aget_or_create_subscription()
                            except User.DoesNotExist:
                                error_log().append('user not exist')
                                continue
                            error_log().append('Generating user link')
                            await self.approve_request_and_send_links_v2(
                                context,
                                request,
                                message_prefix="تم الاشتراك بنجاح.\n"
                            )

                        await request.mark_as_completed()

                    elif request.is_declined:
                        await context.bot.send_message(
                            chat_id=request.user_telegram_id,
                            text=f"للأسف لم يتم قبول طلبك بالإنضمام للمجموعه لسبب التالي: \n\n {request.message} \n\n لا تقلق يمكنك طلب المساعده من الدعم نحن هما من أجل مساعدتك /start"
                        )
                        await request.mark_as_completed()
                except Exception as e:
                    error_log().append(f'error in request {request.username} {e}')
        except Exception as e:
            error_log().append(f'error in sub-requests: {e}')

    async def approve_request_and_send_links_v2(self, context, request, message_prefix: str):
        async def _debug_log(message, details=None):
            """
            Helper function to log detailed debug messages with optional context details.
            """
            if details:
                message += f" | Details: {details}"
            print(message, flush=True)
            error_log().append(message)

        try:
            # Format the subscription end date
            end_date_formatted = format_date(request.end_date)
            subscription_end_date = datetime.datetime.strptime(
                request.end_date.isoformat(),
                '%Y-%m-%d'
            )

            # Fetch main groups asynchronously
            groups = await sync_to_async(lambda: list(Group.objects.filter(parent_id=None)))()
            if not groups:
                await _debug_log("No main groups found.")
                return  # Exit early if no groups exist

            invite_links = []  # To store all generated invite links

            # Iterate through main groups
            for group in groups:
                try:
                    # Skip if the group does not match the request's chat ID
                    if group.telegram_id != request.chat_id:
                        continue

                    # Generate invite link for the main group
                    main_invite_link = await context.bot.create_chat_invite_link(
                        chat_id=request.chat_id,
                        creates_join_request=False,
                        member_limit=1,
                        expire_date=subscription_end_date
                    )
                    invite_links.append(main_invite_link.invite_link)
                    await _debug_log(
                        "Main group invite link generated.",
                        {"group_id": group.telegram_id, "invite_link": main_invite_link.invite_link}
                    )

                    # Fetch subgroups linked to the main group
                    subgroups = await sync_to_async(
                        lambda: list(Group.objects.filter(parent_id=group.telegram_id))
                    )()
                    if not subgroups:
                        await _debug_log(
                            f"No subgroups found for main group {group.telegram_id}."
                        )

                    # Iterate through subgroups and generate invite links
                    for subgroup in subgroups:
                        try:
                            subgroup_invite_link = await context.bot.create_chat_invite_link(
                                chat_id=subgroup.telegram_id,
                                creates_join_request=False,
                                member_limit=1,
                                expire_date=subscription_end_date
                            )
                            invite_links.append(subgroup_invite_link.invite_link)
                            await _debug_log(
                                "Subgroup invite link generated.",
                                {"subgroup_id": subgroup.telegram_id, "invite_link": subgroup_invite_link.invite_link}
                            )
                        except Exception as subgroup_error:
                            # Log specific errors with subgroups
                            await _debug_log(
                                f"Error generating invite link for subgroup {subgroup.telegram_id}.",
                                {"error": str(subgroup_error), "subgroup_id": subgroup.telegram_id}
                            )

                except Exception as main_group_error:
                    # Log specific errors with the main group
                    await _debug_log(
                        f"Error generating invite link for main group {group.telegram_id}.",
                        {"error": str(main_group_error), "group_id": group.telegram_id}
                    )

            # If invite links were successfully generated, send them to the user
            if invite_links:
                formatted_invite_links = '\n'.join(invite_links)
                await context.bot.send_message(
                    chat_id=request.user_telegram_id,
                    text=(
                        f"{message_prefix}يرجى الانضمام عبر الروابط التالية: \n"
                        f"{formatted_invite_links}\n"
                        f"ينتهي اشتراكك في {end_date_formatted}"
                    )
                )
                await _debug_log("Invite links sent to user.", {"user_id": request.user_telegram_id})
            else:
                # Log if no invite links were generated
                await _debug_log("No invite links generated for the request.")
                await context.bot.send_message(
                    chat_id=request.user_telegram_id,
                    text="لم نتمكن من إنشاء روابط الدعوة الخاصة بك. الرجاء المحاولة لاحقًا أو الاتصال بالدعم."
                )

        except Exception as error:
            # Catch and log unexpected errors
            error_message = f"Unexpected error in approve_request_and_send_links: {error}"
            await _debug_log(error_message, {"user_id": request.user_telegram_id, "request_id": request.id})
            await context.bot.send_message(
                chat_id=request.user_telegram_id,
                text="حدث خطأ غير متوقع أثناء معالجة طلبك. الرجاء المحاولة لاحقًا أو الاتصال بالدعم."
            )


    async def approve_request_and_send_links(self, context, request, message_prefix: str):
        try:
            # Format the end date
            end_date_formatted = format_date(request.end_date)
            subscription_end_date = datetime.datetime.strptime(
                request.end_date.isoformat(),
                '%Y-%m-%d'
            )

            # Retrieve main groups asynchronously
            groups = await sync_to_async(lambda: list(Group.objects.filter(parent_id=None)))()
            invite_links = []

            # Iterate through groups to create invite links
            for group in groups:
                if group.telegram_id == request.chat_id:
                    try:
                        # Create an invite link for the main group
                        main_invite_link = await context.bot.create_chat_invite_link(
                            chat_id=request.chat_id,
                            creates_join_request=False,
                            member_limit=1,
                            expire_date=subscription_end_date
                        )
                        invite_links.append(main_invite_link.invite_link)

                        # Retrieve and iterate through subgroups
                        subgroups = await sync_to_async(lambda: list(Group.objects.filter(parent_id=group.telegram_id)))()
                        for subgroup in subgroups:
                            try:
                                subgroup_invite_link = await context.bot.create_chat_invite_link(
                                    chat_id=subgroup.telegram_id,
                                    creates_join_request=False,
                                    member_limit=1,
                                    expire_date=subscription_end_date
                                )
                                invite_links.append(subgroup_invite_link.invite_link)
                            except Exception as subgroup_error:
                                # Handle potential `ChatNotFound` or other subgroup errors
                                print(f"Error with subgroup {subgroup.telegram_id}: {subgroup_error}", flush=True)
                                error_log().append(f"Error with subgroup {subgroup.telegram_id}: {subgroup_error}")

                    except Exception as main_group_error:
                        # Handle potential `ChatNotFound` or other main group errors
                        print(f"Error with main group {group.telegram_id}: {main_group_error}", flush=True)
                        error_log().append(f"Error with main group {group.telegram_id}: {main_group_error}")

            # Send message with formatted invite links if any links were generated
            if invite_links:
                formatted_invite_links = '\n'.join(invite_links) + '\n'
                await context.bot.send_message(
                    chat_id=request.user_telegram_id,
                    text=(
                        message_prefix +
                        'يرجى الانضمام عبر الروابط التالية: \n' +
                        formatted_invite_links +
                        f"ينتهي اشتراكك في {end_date_formatted}"
                    )
                )
            else:
                error_log().append("No invite links generated.")

        except Exception as error:
            # Handle any unexpected errors
            print(error, flush=True)
            error_log().append(f'Error in announcing client subscription update: {error}')

    async def training_reminder(self,context: ContextTypes.DEFAULT_TYPE):
        today = datetime.datetime.today()
        date = today.date()
        time = today.time()
        training_ = await Training.objects.filter(session_date=date,status=SubscriptionRequestStatus.APPROVED).all()
        for training in training_:
            if training.session_time > time:
                training.status = SubscriptionRequestStatus.COMPLETED
                await training.asave()

            if training.session_time == time:
                context.bot.send_message(training.telegram_id,'أقترب موعد التدريب كن على أستعداد')
                training.status = SubscriptionRequestStatus.COMPLETED
                await training.asave()

    async def _resolve_training_requests(self, context: ContextTypes.DEFAULT_TYPE):
        # Iterate over approved requests asynchronously
        async for request in Training.objects.filter(status=SubscriptionRequestStatus.APPROVED, anounced=False).all():
            try:
                await context.bot.send_message(request.telegram_id, request.message)
                request.anounced = True
                await request.asave()  # Await the save operation
            except Exception as e:
                error_log().append(f'Cannot announce user for their approved training due to: {e}')

        # Iterate over rejected requests asynchronously
        async for request in Training.objects.filter(status=SubscriptionRequestStatus.DECLINED, anounced=False).all():
            try:
                message = request.rejected_format()  # If this is not async, do not await
                await context.bot.send_message(request.telegram_id, message)
                request.anounced = True
                request.status = SubscriptionRequestStatus.COMPLETED
                await request.asave()  # Await the save operation
            except Exception as e:
                error_log().append(f'Cannot announce user for their rejected training due to: {e}')


    async def _send_offer_messages(self, context: ContextTypes.DEFAULT_TYPE):
        async for message in OfferMessage.objects.all():
            now = pendulum.now()

            for sending_time in message.get_sending_times(self.db):
                if (
                    sending_time.date() == now.date() and
                    sending_time.hour == now.hour
                ):
                    async for user in User.objects.all():
                        await context.bot.send_message(
                            chat_id=user.telegram_id,
                            text=message.content
                        )

    def _run_application_polling(self):
        self.application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
