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
from src.common.models import SubscriptionRequest, User, OfferMessage


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
            self._send_offer_messages,
            interval=one_hour,
            first=next_hour
        )

    async def _notify_users_with_ending_subscriptions(self, context: ContextTypes.DEFAULT_TYPE):
        notification_period = 7  # in days
        now = pendulum.now()

        async for user in User.objects.all():
            if not await user.subscriptions.filter(is_active=True).aexists():
                for group in settings.GROUPS:
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
                    message = 'يرجى الانتباه. سيتم انتهاء اشتراكك في ' + subscription_end_date + '.'

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
                    message = 'سيتم انتهاء اشتراكك اليوم. جدد اشتراكك الان للاستمتاع بمزايا قناتنا الخاصة. '

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
                                     f'. يمكنك تجديد الاشتراك باستخدام subscribe/'
                            )

                        except:
                            ...

                    except BadRequest:
                        ...

    async def _resolve_subscription_requests(self, context: ContextTypes.DEFAULT_TYPE):
        requests = SubscriptionRequest.objects.filter(
            status__in=(
                SubscriptionRequestStatus.APPROVED,
                SubscriptionRequestStatus.DECLINED
            )
        )

        async for request in requests:
            if request.is_approved:
                subscription = await request.asubscription

                if subscription:
                    await subscription.renew(
                        invoice_number=request.invoice_number,
                        end_date=request.end_date,
                        payment_method=PaymentMethod(request.payment_method),
                        tradingview_id=request.tradingview_id
                    )

                    await self.approve_request_and_send_links(
                        context,
                        request,
                        message_prefix=f"تمت الموافقة على طلب تجديد اشتراكك بنجاح.\n"
                    )

                else:
                    try:
                        await request.aget_or_create_subscription()

                    except User.DoesNotExist:
                        continue

                    await self.approve_request_and_send_links(
                        context,
                        request,
                        message_prefix="تم الاشتراك بنجاح.\n"
                    )

                await request.mark_as_completed()

            elif request.is_declined:
                await context.bot.send_message(
                    chat_id=request.user_telegram_id,
                    text="Your request has been declined. Please contact support for more information."
                )
                await request.mark_as_completed()

    async def approve_request_and_send_links(self, context, request, message_prefix: str):
        end_date_formatted = format_date(request.end_date)

        try:
            subscription_end_date = datetime.datetime.strptime(
                request.end_date.isoformat(),
                '%Y-%m-%d'
            )

            invite_links: list[str] = []

            for group in settings.GROUPS:
                if group['id'] == request.chat_id:
                    main_invite_link = await context.bot.create_chat_invite_link(
                        chat_id=request.chat_id,
                        creates_join_request=False,
                        member_limit=1,
                        expire_date=subscription_end_date
                    )

                    invite_links.append(main_invite_link.invite_link)

                    for subgroup in group['subgroups']:
                        subgroup_invite_link = await context.bot.create_chat_invite_link(
                            chat_id=subgroup['id'],
                            creates_join_request=False,
                            member_limit=1,
                            expire_date=subscription_end_date
                        )

                        invite_links.append(subgroup_invite_link.invite_link)

            formatted_invite_links = '\n'.join(invite_links) + '\n'

            await context.bot.send_message(
                chat_id=request.user_telegram_id,
                text=(
                    message_prefix +
                    f'يرجى الانضمام عبر الروابط التالية: \n' +
                    formatted_invite_links +
                    f"ينتهي اشتراكك في {end_date_formatted}"
                )
            )

        except Exception as error:
            print(error, flush=True)

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
