import datetime
import json

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButtonRequestChat,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, ChatMember, ChatMemberUpdated, SharedUser,
)
from telegram.constants import ParseMode, ChatType, ChatMemberStatus
from telegram.ext import ContextTypes, CallbackContext, filters, Application
from telegram.ext.filters import StatusUpdate
from telethon import TelegramClient
from telethon.hints import TotalList

from src.admin_bot.cache import Cache
from src.admin_bot.choices import EmployeeRole
from src.admin_bot.enums import BotStep, InlineButtonCallbackType
from src.admin_bot.excel_writer import ExcelWriter
from src.admin_bot.utils import is_bot_owner, get_request_user_reply_markup, is_normal_chat_member_telethon, \
    ban_chat_member, is_normal_chat_member_ptb
from src.common import pendulum
from src.common.choices import PaymentMethod
from src.common.db import Database
from src.common.exceptions import EmployeeAlreadyExists, SubgroupAlreadyExists, SubgroupIsMainGroup
from src.common.formatters import format_date
from src.common.models import Employee, Group, User, SenderEntity, Subscription, OfferMessage, GroupFamily, \
    SubscriptionRequest
from src.common.utils import format_nullable_string, format_message, get_display_name, get_payment_method_keyboard, \
    aenumerate, aget_inline_keyboard
from src.common.validators import get_date, get_int, ErrorMessages


# noinspection PyUnusedLocal,PyMethodMayBeStatic
class Commands:
    def __init__(self):
        self.db: Database | None = None
        self.caches: dict[int, Cache] = {}
        self.client: TelegramClient | None = None
        self._client: TelegramClient | None = None
        self.application: Application | None = None

    @property
    def command_mapping(self):
        return {
            'login': self.login,
            'start': self.start,
            'help': self.help,
            'renew': self.renew_user_subscription,
            'info': self.info,
            'welcome': self.welcome_message,
            'salla_link': self.salla_link,
            'employee': self.add_employee,
            'employees': self.employees,
            'offer_message': self.offer_message,
            'offer_messages': self.offer_messages,
            'group_family': self.group_family,
            'edit': self.edit_user_subscription
        }

    @property
    def status_update_mapping(self):
        return {
            StatusUpdate.CHAT_SHARED: self.chat_shared,
            StatusUpdate.USERS_SHARED: self.user_shared,
            filters.TEXT: self.message_received,
            filters.CONTACT: self.contact_shared
        }

    @property
    def callback_query_mapping(self):
        return [
            self.button_callback
        ]

    def get_current_cache(self, user_id: int) -> Cache:
        if user_id in self.caches:
            cache = self.caches[user_id]

        else:
            cache = self.caches[user_id] = Cache()

        return cache

        # ---------- Permission decorators ---------- #

    @staticmethod
    def admin_command(func):
        async def wrapper(self: 'Commands', update: Update, context: ContextTypes.DEFAULT_TYPE):
            sender_id = update.effective_sender.id
            admin = await Employee.objects.filter(id=sender_id, role=EmployeeRole.ADMIN).afirst()
            bot_owner = is_bot_owner(sender_id)

            if admin or bot_owner:
                return await func(self, update, context)

            await update.effective_message.reply_text(
                'Permission denied. You must be an admin to do this action'
            )

        return wrapper

    @staticmethod
    def employee_command(func):
        async def wrapper(self: 'Commands', update: Update, context: ContextTypes.DEFAULT_TYPE):
            sender_id = update.effective_sender.id
            employee = await Employee.objects.filter(telegram_id=sender_id).afirst()
            bot_owner = is_bot_owner(sender_id)

            if employee or bot_owner:
                return await func(self, update, context)

            await update.effective_message.reply_text(
                'Permission denied. You must be an employee to do this action'
            )

        return wrapper

    @staticmethod
    def telethon_client_required(func):
        async def wrapper(self: 'Commands', update: Update, context: ContextTypes.DEFAULT_TYPE):
            if self.client:
                return await func(self, update, context)

            await update.effective_message.reply_text(
                'Sender not found. Use /login command to add a sender and try again'
            )

        return wrapper

    @staticmethod
    def private_chat_only(func):
        async def wrapper(self: 'Commands', update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.effective_chat.type is not ChatType.PRIVATE:
                return
            return await func(self, update, context)

        return wrapper

    # ---------- Commands ---------- #

    @telethon_client_required
    @employee_command
    @private_chat_only
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.NEW_USER_CHAT
        keyboard = [
            [
                KeyboardButton("Select Channel", request_chat=KeyboardButtonRequestChat(
                    request_id=1,
                    chat_is_channel=True
                )),
                KeyboardButton("Select Group", request_chat=KeyboardButtonRequestChat(
                    request_id=2,
                    chat_is_channel=False
                ))
            ]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        await update.message.reply_text("Select a channel/group:", reply_markup=reply_markup)

    @employee_command
    @private_chat_only
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        commands = [
            {
                'name': 'login',
                'description': 'Log in as a sender'
            },
            {
                'name': 'start',
                'description': 'Add user subscription'
            },
            {
                'name': 'renew',
                'description': 'Renew user subscription'
            },
            {
                'name': 'edit',
                'description': 'Edit user subscription'
            },
            {
                'name': 'info',
                'description': 'Get all subscribers as Excel file'
            },
            {
                'name': 'employee',
                'description': 'Add or update employee'
            },
            {
                'name': 'employees',
                'description': 'Get info about all employees'
            },
            {
                'name': 'offer_message',
                'description': 'Add new offer message'
            },
            {
                'name': 'offer_messages',
                'description': 'View all offer messages'
            },
            {
                'name': 'welcome',
                'description': 'Set welcome message'
            },
            {
                'name': 'salla_link',
                'description': 'Add or update Salla link for renewing subscriptions'
            },
            {
                'name': 'group_family',
                'description': 'Add a new family group (main group and sub-groups)'
            }
        ]

        message = 'Here are the available commands:\n\n'

        for command in commands:
            message += f'/{command["name"]}:  {command["description"]}\n'

        await update.message.reply_text(message)

    @employee_command
    @private_chat_only
    async def login(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sender_entity = await SenderEntity.objects.filter(user_id=update.effective_sender.id).afirst()

        if sender_entity:
            await update.message.reply_text("You're already added as a sender.")
            return

        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.API_ID

        message = (
            '1. Visit this link: https://my.telegram.org/apps\n'
            '2. Log in\n'
            '3. Create a new app. Name can be anything you want. "Channel Manager" is a good name.\n'
            '4. Enter App api_id\n'
            '5. Enter App api_hash\n'
            '6. Share phone number\n'
            '7. Share confirmation code with the developer\n\n'
            'Enter App api_id:'
        )
        await update.message.reply_text(message)

    @employee_command
    @telethon_client_required
    @private_chat_only
    async def info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.INFO_CHAT

        keyboard = [
            [
                KeyboardButton("Select Channel", request_chat=KeyboardButtonRequestChat(
                    request_id=1,
                    chat_is_channel=True,
                    request_title=True
                )),
                KeyboardButton("Select Group", request_chat=KeyboardButtonRequestChat(
                    request_id=2,
                    chat_is_channel=False,
                    request_title=True
                ))
            ]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        await update.message.reply_text("Select a channel/group:", reply_markup=reply_markup)

    @employee_command
    @private_chat_only
    async def welcome_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.WELCOME_MESSAGE
        await update.message.reply_text(
            f"Current message: {format_nullable_string(self.db.welcome_message)}\n\n"
            f"You can enter a new message:"
        )

    @employee_command
    @private_chat_only
    async def salla_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.SALLA_LINK
        await update.message.reply_text(
            f"Current Salla link: {format_nullable_string(self.db.salla_link)}\n\n"
            f"You can enter a new link:"
        )

    @employee_command
    @private_chat_only
    async def renew_user_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.RENEW_USER_ID
        await update.message.reply_text('Enter user\'s Telegram ID to renew subscription:')

    @employee_command
    @private_chat_only
    async def offer_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.OFFER_MESSAGE_CONTENT
        await update.message.reply_text('Enter message:')

    @employee_command
    @private_chat_only
    async def offer_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = ''

        async for index, offer_message in aenumerate(OfferMessage.objects.all(), 1):
            formatted_sending_times = offer_message.get_formatted_sending_times(self.db)

            message += (
                f'*{index}. Content*: {format_nullable_string(offer_message.content)}\n\n'
                f'*Sending times*:\n{formatted_sending_times}\n'
            )

        if message:
            message = format_message(message)
            await update.message.reply_markdown_v2(message)

        else:
            await update.message.reply_text('No offer messages found. Use /offer_message to create a new message')

    @admin_command
    @private_chat_only
    async def add_employee(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.SELECT_EMPLOYEE
        reply_markup = get_request_user_reply_markup()
        await update.message.reply_text("Select user:", reply_markup=reply_markup)

    @admin_command
    @private_chat_only
    async def employees(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = ''

        async for index, employee in aenumerate(Employee.objects.all(), 1):
            username = f'@{employee.telegram_username}' if employee.telegram_username else None

            message += (
                f'{index}. {format_nullable_string(employee.full_name)} '
                f'({format_nullable_string(username)}, {employee.get_role_display()})\n'
            )

        if not message:
            message = 'No employees found. Add employees via /employee command and try again.'

        message = format_message(message)
        await update.message.reply_markdown_v2(message)

    @admin_command
    @private_chat_only
    async def group_family(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.clear()
        cache.current_step = BotStep.GROUP_FAMILY_MAIN_GROUP

        keyboard = [
            [
                KeyboardButton("Select Main Group", request_chat=KeyboardButtonRequestChat(
                    request_id=1,
                    chat_is_channel=False,
                    request_title=True
                ))
            ]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard)
        await update.message.reply_text('Select main group:', reply_markup=reply_markup)

    @employee_command
    @telethon_client_required
    @private_chat_only
    async def cleanup_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.clear()
        cache.current_step = BotStep.SELECT_CLEANUP_GROUP

        keyboard = [
            [
                KeyboardButton("Select Group", request_chat=KeyboardButtonRequestChat(
                    request_id=1,
                    chat_is_channel=False,
                    request_title=True
                ))
            ]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard)
        await update.message.reply_text('Select group:', reply_markup=reply_markup)

    @employee_command
    @private_chat_only
    async def edit_user_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.EDIT_USER_ID
        await update.message.reply_text('Enter user\'s Telegram ID to edit subscription:')

    # ---------- Status Updates ---------- #
    async def chat_shared(self, update: Update, context: CallbackContext):
        cache = self.get_current_cache(update.effective_sender.id)
        shared_chat = update.message.chat_shared

        match cache.current_step:
            case BotStep.NEW_USER_CHAT:
                cache.current_step = BotStep.NEW_USER
                cache.chat_id = shared_chat.chat_id
                reply_markup = get_request_user_reply_markup()
                await update.message.reply_text("Select user:", reply_markup=reply_markup)

            case BotStep.GROUP_FAMILY_MAIN_GROUP:
                cache.group_family_main_group, _ = await Group.objects.aget_or_create(
                    telegram_id=shared_chat.chat_id,
                    defaults=dict(title=shared_chat.title)
                )
                cache.current_step = BotStep.GROUP_FAMILY_SUBGROUPS
                cache.group_family_subgroups.clear()

                keyboard = [
                    [
                        KeyboardButton("Select subgroup", request_chat=KeyboardButtonRequestChat(
                            request_id=1,
                            chat_is_channel=False,
                            request_title=True
                        ))
                    ]
                ]

                reply_markup = ReplyKeyboardMarkup(keyboard)
                await update.message.reply_text('Select subgroups:', reply_markup=reply_markup)

            case BotStep.GROUP_FAMILY_SUBGROUPS:
                subgroup, _ = await Group.objects.aget_or_create(
                    telegram_id=shared_chat.chat_id,
                    defaults=dict(title=shared_chat.title)
                )

                try:
                    cache.add_group_family_subgroup(subgroup)

                    keyboard = [
                        [
                            InlineKeyboardButton('Finish', callback_data=1)
                        ]
                    ]

                    reply_markup = InlineKeyboardMarkup(keyboard)

                    message_text = (
                        f'Subgroup selected. You now have {len(cache.group_family_subgroups)} subgroups selected.\n'
                        f'You can continue adding more subgroups. Once you\'re done, click "Finish".'
                    )

                    if cache.subgroup_message:
                        await cache.subgroup_message.edit_text(message_text, reply_markup=reply_markup)

                    else:
                        cache.subgroup_message = await update.message.reply_text(
                            message_text,
                            reply_markup=reply_markup
                        )

                except SubgroupAlreadyExists:
                    await update.message.reply_text('This subgroup already exists. Please select another subgroup.')

                except SubgroupIsMainGroup:
                    await update.message.reply_text(
                        'Subgroup is the same as main group. Please select another subgroup.'
                    )

            case BotStep.INFO_CHAT:
                async with self.client:
                    rows = []

                    async for user in self.client.iter_participants(shared_chat.chat_id):
                        row = []
                        bot_user: User = await User.objects.filter(telegram_id=user.id).afirst()

                        if not user.deleted:
                            row.append(user.id)
                            row.append(user.username)
                            row.append(get_display_name(user))

                            if bot_user:
                                latest_subscription = await bot_user.latest_subscription

                                if latest_subscription:
                                    row.append(latest_subscription.get_payment_method_display())
                                    row.append(latest_subscription.invoice_number)
                                    row.append(format_date(latest_subscription.created_at))
                                    row.append(format_date(latest_subscription.end_date))
                                else:
                                    row.append('')
                                    row.append('')
                                    row.append('')
                                    row.append('')

                                row.append('Yes')

                            else:
                                row.append('')
                                row.append('')
                                row.append('')
                                row.append('')
                                row.append('No')

                        rows.append(row)

                    filename = f'{shared_chat.title} users.xlsx'

                    excel_writer = ExcelWriter(filename)

                    headers = [
                        'Telegram ID',
                        'Username',
                        'Full Name',
                        'Payment Method',
                        'Invoice Number',
                        'Created at',
                        'Subscription end date',
                        'Added to bot'
                    ]

                    if rows:
                        excel_writer.write(headers, rows)
                        await update.message.reply_document(document=open(filename, 'rb'))

                    else:
                        message = 'No users found. Add users via /start and try again.'
                        await update.message.reply_text(message)

            case BotStep.SELECT_CLEANUP_GROUP:
                cache.current_step = BotStep.CONFIRM_CLEANUP_GROUP
                cache.cleanup_group_id = shared_chat.chat_id
                subscribed_user_ids = []

                for user in User.objects.all():
                    if user.has_active_subscription_for_chat(shared_chat.chat_id):
                        subscribed_user_ids.append(user.id)

                async with self.client:
                    chat_members: TotalList = await self.client.get_participants(shared_chat.chat_id)

                    for chat_user in chat_members:
                        if (
                                chat_user.id not in subscribed_user_ids and
                                is_normal_chat_member_telethon(chat_user)
                        ):
                            cache.cleanup_group_users.append(chat_user)

                unsubscribed_user_names = '\n'.join(
                    f'{index}. {get_display_name(user)}' for index, user in enumerate(cache.cleanup_group_users, 1)
                )

                if cache.cleanup_group_users:
                    message = (
                        f'The following users will be removed from the group "{shared_chat.title}"\n'
                        f'Click "Confirm" to remove them or click "Cancel" to cancel the process.\n\n'
                        f'{unsubscribed_user_names}'
                    )

                    keyboard = [
                        [
                            InlineKeyboardButton('Confirm', callback_data='confirm_cleanup_group'),
                            InlineKeyboardButton('Cancel', callback_data='cancel_cleanup_group')
                        ]
                    ]

                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(message, reply_markup=reply_markup)

                else:
                    await update.message.reply_text('All users in this group are subscribed.')

    async def user_shared(self, update: Update, context: CallbackContext):
        user = update.message.users_shared.users[0]
        cache = self.get_current_cache(update.effective_sender.id)
        cache.shared_user = user

        match cache.current_step:
            case BotStep.NEW_USER:
                existing_user = await User.objects.filter(telegram_id=user.user_id).afirst()

                if existing_user:
                    existing_subscription = await existing_user.subscriptions.filter(
                        chat_id=cache.chat_id,
                        is_active=True,
                    ).afirst()

                    if existing_subscription:
                        formatted_subscription = existing_subscription.format(separator='\n')

                        message = format_message(
                            f"This user has the following active subscription for this group:\n"
                            f"{formatted_subscription}\n\n"
                            f" To renew subscriptions, use /renew command instead."
                        )
                        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
                        cache.current_step = BotStep.IDLE
                        return

                cache.current_step = BotStep.NEW_USER_PAYMENT_METHOD
                keyboard = get_payment_method_keyboard()
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("Enter subscription method:", reply_markup=reply_markup)

            case BotStep.SELECT_EMPLOYEE:
                cache.current_step = BotStep.EMPLOYEE_ROLE

                keyboard = [
                    [
                        InlineKeyboardButton('Admin', callback_data='admin'),
                        InlineKeyboardButton('Employee', callback_data='employee')
                    ]
                ]

                inline_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text('Select employee role:', reply_markup=inline_markup)

    async def contact_shared(self, update: Update, context: CallbackContext):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.login_phone_number = update.message.contact.phone_number
        cache.current_step = BotStep.TWO_FACTOR_AUTH_PASSWORD

        keyboard = [
            [
                InlineKeyboardButton('Skip', callback_data=1)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            'Enter your 2fa password, or click the skip button if you don\'t have one.',
            reply_markup=reply_markup
        )

    async def _log_in(self, update: Update, password: str | None = None):
        cache = self.get_current_cache(update.effective_sender.id)

        self._client = TelegramClient(
            api_id=cache.api_id,
            api_hash=cache.api_hash,
            session=str(update.effective_sender.id)
        )

        password = password if password else lambda: input('Enter 2fa password:')
        await self._client.start(phone=cache.login_phone_number, password=password)
        user = await self._client.get_me()

        await SenderEntity.objects.aupdate(commit=False, is_active=False)

        sender_entity = await SenderEntity.objects.acreate(
            user_id=update.effective_sender.id,
            api_id=cache.api_id,
            api_hash=cache.api_hash,
            phone_number=cache.login_phone_number,
            is_active=True
        )

        self.client = self._client

        await update.message.reply_text(
            f"Logged in successfully. You can now send messages as @{user.username}",
            reply_markup=ReplyKeyboardRemove()
        )

    @private_chat_only
    async def message_received(self, update: Update, context: CallbackContext):
        cache = self.get_current_cache(update.effective_sender.id)

        match cache.current_step:
            case BotStep.NEW_USER_INVOICE_NUMBER:
                cache.invoice_number = update.message.text
                cache.current_step = BotStep.NEW_USER_SUBSCRIPTION_END_DATE
                await update.message.reply_text("Enter subscription end date (dd/mm/yyyy):")

            case BotStep.NEW_USER_SUBSCRIPTION_END_DATE:
                subscription_end_date, valid = get_date(update.message.text)

                if not valid:
                    await update.message.reply_text(ErrorMessages.INVALID_DATE)
                    return

                cache.subscription_end_date = subscription_end_date

                async with self.client:
                    await self._add_user_subscription(update, context)
                    await update.message.reply_text("User added successfully!")

            case BotStep.WELCOME_MESSAGE:
                self.db.welcome_message = update.message.text
                self.db.save()
                await update.message.reply_text("Welcome message saved successfully!")

            case BotStep.SALLA_LINK:
                self.db.salla_link = update.message.text
                self.db.save()
                await update.message.reply_text("Salla link saved successfully!")

            case BotStep.RENEW_USER_ID:
                renew_user_id, valid = get_int(update.message.text)

                if not valid:
                    await update.message.reply_text(ErrorMessages.INVALID_INT)
                    return

                cache.renew_user_id = renew_user_id
                existing_user: User | None = await User.objects.filter(telegram_id=cache.renew_user_id).afirst()

                if existing_user:
                    cache.current_step = BotStep.RENEW_SUBSCRIPTION
                    active_subscriptions = existing_user.get_active_subscriptions()

                    keyboard = await aget_inline_keyboard(
                        active_subscriptions,
                        value_field='id',
                        label_field='chat_name',
                        items_per_row=1
                    )

                    await update.message.reply_markdown_v2(
                        'Select subscription to renew:',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )

                else:
                    await update.message.reply_text("User not found")
                    return

            case BotStep.RENEW_END_DATE:
                subscription_end_date, valid = get_date(update.message.text)

                if not valid:
                    await update.message.reply_text(ErrorMessages.INVALID_DATE)
                    return

                cache.renew_end_date = subscription_end_date
                cache.current_step = BotStep.RENEW_PAYMENT_METHOD
                keyboard = get_payment_method_keyboard()
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("Enter subscription method:", reply_markup=reply_markup)

            case BotStep.RENEW_INVOICE_NUMBER:
                invoice_number = update.message.text
                user = await User.objects.filter(telegram_id=cache.renew_user_id).afirst()

                existing_subscription: Subscription | None = await Subscription.objects.filter(
                    id=cache.renew_subscription_id
                ).afirst()

                await existing_subscription.renew(
                    invoice_number=invoice_number,
                    end_date=cache.renew_end_date,
                    payment_method=cache.payment_method
                )

                await update.effective_message.reply_text(
                    "Subscription renewed successfully",
                    reply_markup=ReplyKeyboardRemove()
                )

            case BotStep.OFFER_MESSAGE_CONTENT:
                cache.offer_message_content = update.message.text
                cache.current_step = BotStep.OFFER_MESSAGE_INTERVAL
                await update.message.reply_text('How many times per 2 weeks do you want to send this message?')

            case BotStep.OFFER_MESSAGE_INTERVAL:
                offer_message_interval, valid = get_int(update.message.text)

                if not valid:
                    await update.message.reply_text(ErrorMessages.INVALID_INT)
                    return

                cache.offer_message_interval = offer_message_interval

                offer_message = await OfferMessage.objects.acreate(
                    content=cache.offer_message_content,
                    interval=cache.offer_message_interval
                )

                formatted_sending_times = offer_message.get_formatted_sending_times(self.db)

                message = (
                    f'Message added successfully. Here are the scheduled sending times:\n\n{formatted_sending_times}'
                )

                message = format_message(message)
                await update.message.reply_markdown_v2(message)

            case BotStep.API_ID:
                api_id, valid = get_int(update.message.text)

                if not valid:
                    await update.message.reply_text(ErrorMessages.INVALID_INT)
                cache.api_id = api_id
                cache.current_step = BotStep.API_HASH
                await update.message.reply_text('Enter api_hash:')

            case BotStep.API_HASH:
                cache.api_hash = update.message.text

                keyboard = [
                    [
                        KeyboardButton('Share phone number', request_contact=True)
                    ]
                ]

                reply_markup = ReplyKeyboardMarkup(keyboard)
                await update.message.reply_text("Share phone number:", reply_markup=reply_markup)

            case BotStep.TWO_FACTOR_AUTH_PASSWORD:
                password = update.message.text
                await self._log_in(update, password)

            case BotStep.APPROVED_SUBSCRIPTION_END_DATE:
                end_date, valid = get_date(update.message.text)

                if not valid:
                    await update.message.reply_text(ErrorMessages.INVALID_DATE)
                    return

                request = cache.approved_subscription_request
                await request.arefresh_from_db()
                request.end_date = end_date
                await request.mark_as_approved()
                user = await User.objects.filter(telegram_id=request.user_telegram_id).afirst()

                if user:
                    user.last_added_to_group_at = pendulum.now()
                    await user.asave()

                await update.message.reply_text("Request approved successfully.")

            case BotStep.EDIT_USER_ID:
                edit_user_id, valid = get_int(update.message.text)

                if not valid:
                    await update.message.reply_text(ErrorMessages.INVALID_INT)
                    return

                cache.edit_user_id = edit_user_id
                existing_user: User | None = await User.objects.filter(telegram_id=cache.edit_user_id).afirst()

                if existing_user:
                    cache.current_step = BotStep.EDIT_SUBSCRIPTION
                    active_subscriptions = existing_user.get_active_subscriptions()

                    keyboard = await aget_inline_keyboard(
                        active_subscriptions,
                        value_field='id',
                        label_field='chat_name',
                        items_per_row=1
                    )

                    await update.message.reply_markdown_v2(
                        'Select subscription to edit:',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )

                else:
                    await update.message.reply_text("User not found")
                    return

            case BotStep.EDIT_PAYMENT_METHOD:
                payment_method = update.message.text
                subscription: Subscription | None = await Subscription.objects.filter(
                    id=cache.edit_subscription_id
                ).afirst()

                if subscription:
                    subscription.payment_method = payment_method
                    await subscription.asave()
                    await update.message.reply_text("Payment method updated successfully!")
                    cache.current_step = BotStep.EDIT_SUBSCRIPTION_FIELDS

            case BotStep.EDIT_INVOICE_NUMBER:
                invoice_number = update.message.text
                subscription: Subscription | None = await Subscription.objects.filter(
                    id=cache.edit_subscription_id).afirst()

                if subscription:
                    subscription.invoice_number = invoice_number
                    await subscription.asave()
                    await update.message.reply_text("Invoice number updated successfully!")
                    cache.current_step = BotStep.EDIT_SUBSCRIPTION_FIELDS

            case BotStep.EDIT_TRADINGVIEW_ID:
                tradingview_id = update.message.text
                subscription: Subscription | None = await Subscription.objects.filter(
                    id=cache.edit_subscription_id).afirst()

                if subscription:
                    subscription.tradingview_id = tradingview_id
                    await subscription.asave()
                    await update.message.reply_text("TradingView ID updated successfully!")
                    cache.current_step = BotStep.EDIT_SUBSCRIPTION_FIELDS

            case BotStep.EDIT_END_DATE:
                end_date, valid = get_date(update.message.text)

                if not valid:
                    await update.message.reply_text(ErrorMessages.INVALID_DATE)
                    return

                subscription: Subscription | None = await Subscription.objects.filter(
                    id=cache.edit_subscription_id).afirst()

                if subscription:
                    subscription.end_date = end_date
                    await subscription.asave()
                    await update.message.reply_text("End date updated successfully!")
                    cache.current_step = BotStep.EDIT_SUBSCRIPTION_FIELDS

    async def _add_user_subscription(self, update: Update, context: CallbackContext):
        cache = self.get_current_cache(update.effective_sender.id)
        user_entity = await self.client.get_entity(cache.shared_user.user_id)
        chat = await self.client.get_entity(cache.chat_id)
        user = await User.objects.filter(telegram_id=cache.shared_user.user_id).afirst()

        if not user:
            user = await User.objects.acreate(
                telegram_id=cache.shared_user.user_id,
                first_name=user_entity.first_name,
                last_name=user_entity.last_name,
                telegram_username=user_entity.username,
            )

        subscription = await user.subscriptions.acreate(
            chat_id=cache.chat_id,
            chat_name=chat.title,
            invoice_number=cache.invoice_number,
            end_date=cache.subscription_end_date,
            payment_method=cache.payment_method
        )

        # participants = await self.client(GetParticipantsRequest(
        #     cache.chat_id,
        #     ChannelParticipantsSearch(str(user_entity.username)),
        #     offset=0,
        #     limit=1,
        #     hash=0
        # ))

        # if not participants.participants:

        chat_member = await context.bot.get_chat_member(chat_id=cache.chat_id, user_id=cache.shared_user.user_id)

        if chat_member.status == ChatMemberStatus.LEFT:
            subscription_end_date = datetime.datetime.strptime(subscription.end_date.isoformat(), '%Y-%m-%d')
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=cache.chat_id,
                member_limit=1,
                expire_date=subscription_end_date,
                creates_join_request=False
            )
            welcome_message = self.db.welcome_message or 'مرحبا بك في قناتنا الخاصة'
            welcome_message += '\n\n' + invite_link.invite_link
            await self.client.send_message(entity=user_entity, message=welcome_message)
            # await self.client(InviteToChannelRequest(cache.chat_id, [cache.shared_user.user_id]))

    def extract_status_change(self, chat_member_update: ChatMemberUpdated) -> tuple[bool, bool] | None:
        """Takes a ChatMemberUpdated instance and extracts whether the 'old_chat_member' was a member
        of the chat and whether the 'new_chat_member' is a member of the chat. Returns None, if
        the status didn't change.
        """
        status_change = chat_member_update.difference().get("status")
        old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

        if status_change is None:
            return None

        old_status, new_status = status_change
        was_member = old_status in [
            ChatMember.MEMBER,
            ChatMember.OWNER,
            ChatMember.ADMINISTRATOR,
        ] or (old_status == ChatMember.RESTRICTED and old_is_member is True)

        is_member = new_status in [
            ChatMember.MEMBER,
            ChatMember.OWNER,
            ChatMember.ADMINISTRATOR,
        ] or (new_status == ChatMember.RESTRICTED and new_is_member is True)

        return was_member, is_member

    async def chat_member_updated(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        result = self.extract_status_change(update.chat_member)

        if result is None:
            return

        was_member, is_member = result

        if was_member and not is_member:
            await self.chat_member_left(update.chat_member, context)

        elif is_member and not was_member:
            await self.chat_member_joined(update.chat_member, context)

    async def chat_member_left(self, chat_member: ChatMemberUpdated, context: ContextTypes.DEFAULT_TYPE):
        chat_id = chat_member.chat.id

        group_family = await GroupFamily.aget_by_main_group(group_id=chat_id)
        removed_from_subgroups: list[Group] = []

        if group_family:
            async for subgroup in group_family.subgroups.all():
                banned = await ban_chat_member(
                    chat_id=subgroup.telegram_id,
                    user=chat_member.new_chat_member.user,
                    context=context
                )

                if banned:
                    removed_from_subgroups.append(subgroup)

            removed_subgroup_titles = ', '.join([subgroup.title for subgroup in removed_from_subgroups])
            print(f'User removed from {len(removed_from_subgroups)} subgroups: {removed_subgroup_titles}')

    async def chat_member_joined(self, chat_member: ChatMemberUpdated, context: ContextTypes.DEFAULT_TYPE):
        chat_id = chat_member.chat.id
        user_id = chat_member.new_chat_member.user.id
        user: User | None = await User.objects.filter(telegram_id=user_id).afirst()
        active_subscription_groups = []

        if user:
            active_subscriptions = user.get_active_subscriptions()
            active_subscription_groups = [subscription.chat_id async for subscription in active_subscriptions]

        async for group_family in GroupFamily.objects.all():
            async for subgroup in group_family.subgroups.all():
                main_group = await Group.objects.aget(id=group_family.main_group_id)
                if (
                        subgroup.telegram_id == chat_id and
                        ((not user) or main_group.telegram_id not in active_subscription_groups) and
                        is_normal_chat_member_ptb(chat_member.new_chat_member)
                ):
                    await ban_chat_member(
                        chat_id=subgroup.telegram_id,
                        user=chat_member.new_chat_member.user,
                        context=context
                    )

                    try:
                        async with self.client:
                            user_entity = await self.client.get_entity(user_id)
                            await self.client.send_message(
                                entity=user_entity,
                                message='يرجى الاشتراك في القناة الرئيسية.'
                            )

                    except Exception as error:
                        print(error, flush=True)

    # ---------- Callback Query Handlers ---------- #
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Parses the CallbackQuery and updates the message text."""
        query = update.callback_query
        cache = self.get_current_cache(update.effective_sender.id)

        # CallbackQueries need to be answered, even if no notification to the user is needed
        # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
        await query.answer()

        data = query.data

        try:
            data = json.loads(data)

        except json.JSONDecodeError as error:
            print(error, flush=True)

        if isinstance(data, dict):
            event_type = InlineButtonCallbackType(data.get('type'))

            match event_type:
                case InlineButtonCallbackType.SUBSCRIPTION_REQUEST_APPROVED:
                    request: SubscriptionRequest | None = await SubscriptionRequest.objects.filter(
                        id=data.get('id')
                    ).afirst()

                    if request:
                        if request.is_resolved:
                            await update.effective_message.reply_text('Request is already resolved.')

                        else:
                            cache.current_step = BotStep.APPROVED_SUBSCRIPTION_END_DATE
                            cache.approved_subscription_request = request
                            await query.edit_message_reply_markup(None)
                            await update.effective_message.reply_text("Enter subscription end date (dd/mm/yyyy):")

                    else:
                        await update.effective_message.reply_text('Request not found')

                case InlineButtonCallbackType.SUBSCRIPTION_REQUEST_DECLINED:
                    request: SubscriptionRequest | None = await SubscriptionRequest.objects.filter(
                        id=data.get('id')
                    ).afirst()

                    if request:
                        if request.is_resolved:
                            await update.effective_message.reply_text('Request is already resolved.')

                        else:
                            await request.mark_as_declined()
                            await query.edit_message_text("Request declined successfully.")

                    else:
                        await update.effective_message.reply_text('Request not found')

            return

        match cache.current_step:
            case BotStep.NEW_USER_PAYMENT_METHOD:
                try:
                    payment_method = cache.payment_method = PaymentMethod(data)

                except ValueError:
                    await update.message.reply_text('Invalid payment method. Try again.')
                    return

                await query.edit_message_text(text=f"Subscription method selected: {payment_method.label}")
                cache.current_step = BotStep.NEW_USER_INVOICE_NUMBER
                await update.effective_message.reply_text("Enter invoice number:", reply_markup=ReplyKeyboardRemove())

            case BotStep.RENEW_SUBSCRIPTION:
                cache.renew_subscription_id = data
                subscription: Subscription | None = await Subscription.objects.filter(id=data).afirst()

                if not subscription:
                    await update.effective_message.reply_text('Subscription not found.')
                    return

                cache.current_step = BotStep.RENEW_END_DATE
                await query.edit_message_text('Subscription selected.')
                await update.effective_message.reply_text("Enter subscription end date (dd/mm/yyyy):")

            case BotStep.RENEW_PAYMENT_METHOD:
                try:
                    payment_method = cache.payment_method = PaymentMethod(data)

                except ValueError:
                    await update.message.reply_text('Invalid payment method. Try again.')
                    return

                await query.edit_message_text(text=f"Subscription method selected: {payment_method.label}")
                cache.current_step = BotStep.RENEW_INVOICE_NUMBER
                await update.effective_message.reply_text('Enter invoice number:')

            case BotStep.EMPLOYEE_ROLE:
                try:
                    role = EmployeeRole(data)

                except ValueError:
                    await update.message.reply_text('Invalid role. Try again.')
                    return

                await query.edit_message_text(text=f"Selected role: {role.label}")
                user: SharedUser = cache.shared_user

                employee = Employee(
                    telegram_id=user.user_id,
                    telegram_username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name or '',
                    role=role
                )

                try:
                    created = await self.db.add_employee(employee)
                    verb = 'added' if created else 'updated'

                    await update.effective_message.reply_text(
                        f'Employee {verb} successfully.', reply_markup=ReplyKeyboardRemove()
                    )

                except EmployeeAlreadyExists:
                    await update.effective_message.reply_text(
                        'Employee already exists.',
                        reply_markup=ReplyKeyboardRemove()
                    )

            case BotStep.GROUP_FAMILY_SUBGROUPS:
                await query.delete_message()

                group_family = await GroupFamily.objects.acreate(
                    main_group=cache.group_family_main_group
                )
                await group_family.subgroups.aset(cache.group_family_subgroups)

                message = format_message(
                    f'Group family added successfully:\n'
                    f'*Main group*: {group_family.main_group.title}\n'
                    f'*subgroups*: {await group_family.subgroup_titles}'
                )

                await update.effective_message.reply_markdown_v2(message, reply_markup=ReplyKeyboardRemove())

            case BotStep.TWO_FACTOR_AUTH_PASSWORD:
                await query.edit_message_text(f'2FA password skipped.')
                await self._log_in(update)

            case BotStep.CONFIRM_CLEANUP_GROUP:
                if data == 'confirm_cleanup_group':
                    banned_count = 0

                    for user_to_ban in cache.cleanup_group_users:
                        banned = await ban_chat_member(
                            chat_id=cache.cleanup_group_id,
                            user=user_to_ban,
                            context=context
                        )

                        if banned:
                            banned_count += 1

                    await update.effective_message.reply_text(
                        f'{banned_count} users removed successfully.', reply_markup=ReplyKeyboardRemove()
                    )

                else:
                    await query.edit_message_text('Cleanup process cancelled.')

            case BotStep.EDIT_SUBSCRIPTION:
                cache.edit_subscription_id = data
                subscription: Subscription | None = await Subscription.objects.filter(id=data).afirst()

                if not subscription:
                    await update.effective_message.reply_text('Subscription not found.')
                    return

                cache.current_step = BotStep.EDIT_SUBSCRIPTION_FIELDS
                keyboard = [
                    [InlineKeyboardButton('Payment Method', callback_data='edit_payment_method')],
                    [InlineKeyboardButton('Invoice Number', callback_data='edit_invoice_number')],
                    [InlineKeyboardButton('TradingView ID', callback_data='edit_tradingview_id')],
                    [InlineKeyboardButton('End Date', callback_data='edit_end_date')],
                    [InlineKeyboardButton('Finish', callback_data='edit_finish')]
                ]

                await query.edit_message_text('Select field to edit:', reply_markup=InlineKeyboardMarkup(keyboard))

            case BotStep.EDIT_SUBSCRIPTION_FIELDS:
                match data:
                    case 'edit_payment_method':
                        subscription: Subscription | None = await Subscription.objects.filter(
                            id=cache.edit_subscription_id).afirst()
                        keyboard = get_payment_method_keyboard()
                        await update.effective_message.reply_text(
                            f"Current payment method: {subscription.get_payment_method_display()}\nSelect new payment method:",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        cache.current_step = BotStep.EDIT_PAYMENT_METHOD

                    case 'edit_invoice_number':
                        subscription: Subscription | None = await Subscription.objects.filter(
                            id=cache.edit_subscription_id).afirst()
                        await update.effective_message.reply_text(
                            f"Current invoice number: {subscription.invoice_number}\nEnter new invoice number:")
                        cache.current_step = BotStep.EDIT_INVOICE_NUMBER

                    case 'edit_tradingview_id':
                        subscription: Subscription | None = await Subscription.objects.filter(
                            id=cache.edit_subscription_id).afirst()
                        await update.effective_message.reply_text(
                            f"Current TradingView ID: {format_nullable_string(subscription.tradingview_id)}\nEnter new TradingView ID:")
                        cache.current_step = BotStep.EDIT_TRADINGVIEW_ID

                    case 'edit_end_date':
                        subscription: Subscription | None = await Subscription.objects.filter(
                            id=cache.edit_subscription_id).afirst()
                        await update.effective_message.reply_text(
                            f"Current end date: {format_date(subscription.end_date)}\nEnter new end date (dd/mm/yyyy):")
                        cache.current_step = BotStep.EDIT_END_DATE

                    case 'edit_finish':
                        await query.delete_message()
                        await update.effective_message.reply_text(
                            'Edit process finished.'
                        )
                        cache.current_step = BotStep.IDLE

            case BotStep.EDIT_PAYMENT_METHOD:
                subscription: Subscription | None = await Subscription.objects.filter(
                    id=cache.edit_subscription_id
                ).afirst()

                if subscription:
                    subscription.payment_method = data
                    await subscription.asave()
                    await query.delete_message()
                    await update.effective_message.reply_text("Payment method updated successfully!")
                    cache.current_step = BotStep.EDIT_SUBSCRIPTION_FIELDS
                else:
                    await update.effective_message.reply_text("Subscription not found.")
