import datetime
import json
from types import SimpleNamespace
from django.conf import settings as django_settings
from django.db.models import Q
from pendulum import timezone
from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    ChatMemberHandler
)
from telethon import TelegramClient
from telethon.hints import TotalList

from src.admin_bot.choices import EmployeeRole
from src.admin_bot.commands import Commands
from src.admin_bot.enums import InlineButtonCallbackType
from src.admin_bot.excel_writer import ExcelWriter
from src.admin_bot.utils import is_normal_chat_member_telethon, ban_chat_member
from src.common import pendulum, settings
from src.common.choices import SubscriptionRequestStatus
from src.common.db import Database
from src.common.models import GroupFamily, Employee, User, Training, Feedback
from src.common.models import SubscriptionRequest
from src.common.utils import get_inline_keyboard, format_message, error_log
from asgiref.sync import sync_to_async

class GlobalCache(SimpleNamespace):
    last_error_message: str = None


# noinspection PyUnusedLocal
class BotManager(Commands):
    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def run(self):
        self._build_application()
        self._start_db()
        self._start_global_cache()
        self._start_telethon_client()
        self._map_commands()
        self._map_status_updates()
        self._map_callback_queries()
        self._add_error_handler()
        self._start_scheduler()
        self._run_application_polling()



    def _build_application(self):
        self.application = ApplicationBuilder().token(self.token).build()
        self.application.add_handler(ChatMemberHandler(self.chat_member_updated, ChatMemberHandler.CHAT_MEMBER))

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

    def _start_global_cache(self):
        self.global_cache = GlobalCache()

    def _add_error_handler(self):
        self.application.add_error_handler(self.error_handler)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(context.error) == self.global_cache.last_error_message:
            return

        self.global_cache.last_error_message = str(context.error)
        await context.bot.send_message(
            chat_id=settings.DEVELOPER_CHAT_ID,
            text=f'An error occurred: {context.error}\n'
        )

    def _start_scheduler(self):
        now = pendulum.now()
        one_hour = datetime.timedelta(hours=1)
        next_hour = now.start_of('hour') + one_hour

        minute_remainder = now.minute % 30

        if minute_remainder == 0:
            needed_minutes = 0

        else:
            needed_minutes = 30 - minute_remainder

        next_30_minutes = now + datetime.timedelta(minutes=needed_minutes)

        self.application.job_queue.run_repeating(
            self._resolve_training_requests,
            interval=datetime.timedelta(hours=1),
            first=0
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
            self._resolve_feedback,
            interval=datetime.timedelta(seconds=10),
            first=0
        )

        self.application.job_queue.run_daily(
            self._send_report_to_bot_owners,
            time=datetime.time(23, 45, tzinfo=timezone(django_settings.TIME_ZONE))
        )

    async def _kick_subgroup_users_not_in_main_group(self, context: ContextTypes.DEFAULT_TYPE):
        now = pendulum.now()
        group_families = GroupFamily.objects.all()

        async with self.client:
            async for group_family in group_families:
                main_group_members: TotalList = await self.client.get_participants(group_family.main_group.telegram_id)
                main_group_member_ids = [member.id for member in main_group_members]

                async for subgroup in group_family.subgroups.all():
                    subgroup_members: TotalList = await self.client.get_participants(subgroup.telegram_id)

                    for subgroup_member in subgroup_members:
                        if (
                            subgroup_member.id not in main_group_member_ids and
                            is_normal_chat_member_telethon(subgroup_member)
                        ):
                            try:
                                await ban_chat_member(
                                    chat_id=subgroup.telegram_id,
                                    user=subgroup_member,
                                    context=context
                                )

                            except BadRequest as error:
                                print(error, flush=True)
    
    async def send_messages_to_admins(self,message,context: ContextTypes.DEFAULT_TYPE,reply_markup=None):
        admins_and_employees = await sync_to_async(list)(
            Employee.objects.filter(Q(role=EmployeeRole.ADMIN) | Q(role=EmployeeRole.EMPLOYEE), have_task = False).all()
        )
        admins_and_employees = [i for i in admins_and_employees]
        sent = False
        for admin_id in admins_and_employees:
            try:
                # Send message to each admin
                if reply_markup:
                    await context.bot.send_message(chat_id=admin_id.telegram_id, text=message,reply_markup=reply_markup)
                    error_log().append(f'sending mmessage to:{admin_id.telegram_username}')
                else:
                    await context.bot.send_message(chat_id=admin_id.telegram_id, text=message)
                    error_log().append(f'sending mmessage to:{admin_id.telegram_username}')
                sent = True
            except Exception as e:
                error_log().append(f'cant send to admins here: {e}')
                print(f"Failed to send message to {admin_id}: {e}")
                sent = False
        return sent
    async def _resolve_subscription_requests(self, context: ContextTypes.DEFAULT_TYPE):
        async for request in SubscriptionRequest.objects.filter(status=SubscriptionRequestStatus.PENDING,reported=False).all():
            try:
                message = format_message(
                    'The following subscription has been requested:\n\n' +
                    request.format(separator='\n'),
                )

                keyboard = get_inline_keyboard(items=[
                    {
                        'value': json.dumps({
                            'type': InlineButtonCallbackType.SUBSCRIPTION_REQUEST_APPROVED.value,
                            'id': request.id,
                            'request': 'subscribtion'
                        }),
                        'label': 'Approve'
                    },
                    {
                        'value': json.dumps({
                            'type': InlineButtonCallbackType.SUBSCRIPTION_REQUEST_DECLINED.value,
                            'id': request.id,
                            'request': 'subscribtion'
                        }),
                        'label': 'Decline'
                    },
                ])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await self.send_messages_to_admins(message,context,reply_markup=reply_markup)
                await request.mark_as_reported()
            except Exception as error:
                print(f'Error: {error}', flush=True)
                raise error

    async def _resolve_feedback(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            # Fetch all feedback entries that are not notified
            reviews = Feedback.objects.filter(notified=False)
            reviews_count = await reviews.acount()

            if reviews_count > 0:
                async for review in reviews:
                    review_rate = {
                        0: 'لا تعليق',
                        1: 'ضعيف',
                        2: 'مقبول',
                        3: 'جيد',
                        4: 'جيد جداً',
                        5: 'ممتاز',
                    }
                    message = f'لقد حصلنا على تقييمات جديده من العملاء: @{review.telegram_username} => {review_rate[review.review]}'
                    
                    if review.message:
                        message += f"\n تعليق العميل:\n\n {review.message}"
                    
                    # Send message to admins
                    sent = await self.send_messages_to_admins(message, context, None)
                    if sent:
                        review.notified = True
                        await review.asave()

        except Exception as e:
            error_log().append(f"Error while sending feedback: {e}")


    async def _resolve_training_requests(self, context: ContextTypes.DEFAULT_TYPE):
        requests = Training.objects.filter(status=SubscriptionRequestStatus.PENDING,reported=False)
        requests_count = await requests.acount()

        if requests_count > 0:
            request = await requests.afirst()
            
            if request:
                # Create the inline keyboard
                keyboard = get_inline_keyboard(items=[
                    {
                        'value': json.dumps({
                            'type': InlineButtonCallbackType.SUBSCRIPTION_REQUEST_APPROVED.value,
                            'id': request.id,
                            'request': 'training'
                        }),
                        'label': 'Approve'
                    },
                    {
                        'value': json.dumps({
                            'type': InlineButtonCallbackType.SUBSCRIPTION_REQUEST_DECLINED.value,
                            'id': request.id,
                            'request': 'training'
                        }),
                        'label': 'Decline'
                    },
                ])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                try:
                    # Await the send_messages_to_admins call
                    await self.send_messages_to_admins(request.format('\n'), context, reply_markup=reply_markup)
                    request.reported = True
                    await request.asave()
                except Exception as e:
                    error_log().append(f'Error in training requests auto-send: {e}')

    async def _send_report_to_bot_owners(self, context: ContextTypes.DEFAULT_TYPE):
        """
        Send a daily report to bot owner for people who got added and people who got removed.
        """

        now = pendulum.now()
        today_start = now.start_of('day')

        users = User.objects.filter(
            Q(last_removed_from_group_at__gte=today_start) |
            Q(last_added_to_group_at__gte=today_start)
        )

        if not await users.aexists():
            for bot_owner in settings.BOT_OWNERS:
                chat_id = bot_owner['id']
                await context.bot.send_message(chat_id, "No users were added or removed today.")
            return

        report_users = []

        async for user in users:
            if user.last_removed_from_group_at and user.last_removed_from_group_at >= today_start:
                report_users.append((user, 'removed'))

            elif user.last_added_to_group_at and user.last_added_to_group_at >= today_start:
                report_users.append((user, 'added'))

        rows = []

        for user, status in report_users:
            row = [
                user.telegram_id,
                user.telegram_username,
                user.full_name,
                status
            ]

            rows.append(row)

        filename = f'User Report for {now.date().strftime("%d-%m-%Y")}.xlsx'

        excel_writer = ExcelWriter(filename)

        headers = [
            'Telegram ID',
            'Username',
            'Full Name',
            'Status'
        ]

        if rows:
            excel_writer.write(headers, rows)

            for bot_owner in settings.BOT_OWNERS:
                chat_id = bot_owner['id']
                await context.bot.send_message(chat_id, "Here is today's report:")
                await context.bot.send_document(chat_id, document=open(filename, 'rb'))

    def _run_application_polling(self):
        self.application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
