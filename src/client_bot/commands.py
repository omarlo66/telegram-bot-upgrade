import json

from telegram import (
    Update,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.constants import ChatType
from telegram.ext import ContextTypes, CallbackContext, filters, Application
from telethon import TelegramClient

from src.admin_bot.enums import InlineButtonCallbackType
from src.client_bot.cache import Cache
from src.client_bot.constants import Messages
from src.client_bot.enums import BotStep
from src.client_bot.interfaces import SupportResponse, TelegramPhoto
from src.common import settings
from src.common.choices import PaymentMethod
from src.common.db import Database
from src.common.formatters import format_date
from src.common.models import User, SubscriptionRequest, Subscription
from src.common.utils import (
    format_message,
    get_inline_keyboard,
    get_payment_method_keyboard,
    aget_inline_keyboard,
    aenumerate,
    get_group_display_name_by_id,
    get_mentionable_display_name
)


# noinspection PyUnusedLocal
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
            'start': self.start
        }

    @property
    def status_update_mapping(self):
        return {
            filters.TEXT | filters.Document.ALL | filters.PHOTO: self.message_received,
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

    @staticmethod
    def private_chat_and_support_chat_only(func):
        async def wrapper(self: 'Commands', update: Update, context: ContextTypes.DEFAULT_TYPE):
            if (
                update.effective_chat.type is not ChatType.PRIVATE and
                update.effective_chat.id != settings.SUPPORT_CHAT_ID
            ):
                return
            return await func(self, update, context)

        return wrapper

    # ---------- Commands ---------- #

    @private_chat_only
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.START

        keyboard = [
            [InlineKeyboardButton(text='تفعيل الخدمة', callback_data='subscribe')],
            [InlineKeyboardButton(text='استعلام عن الخدمات', callback_data='mysubscriptions')],
            [InlineKeyboardButton(text='تمديد العضوية', callback_data='renew')],
            [InlineKeyboardButton(text='مراسلة الدعم', callback_data='contact_support')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_markdown_v2(
            format_message(
                'مرحبا بك في بوت اوسي شارت. يرجى اختيار خدمة:' + '\n\n' +
                '١. للاشتراك في قناة جديدة اضغط على "اشتراك"' + '\n' +
                '٢. لعرض الاشتراكات الحالية اضغط على "عرض الاشتراكات"' + '\n' +
                '٣. لتجديد اشتراك اضغط على "تجديد"' + '\n' +
                '٤. لمراسلة الدعم اضغط على "مراسلة الدعم"'
            ),
            reply_markup=reply_markup
        )

    async def subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.SELECT_SUBSCRIPTION_GROUP

        keyboard = get_inline_keyboard(
            items=settings.GROUPS,
            label_field='title',
            value_field='id',
            items_per_row=1
        )

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.effective_message.reply_text("يرجى اختيار قناة للاشتراك:", reply_markup=reply_markup)

    async def my_subscriptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = 'هذه هي اشتراكاتك الحالية\n\n'
        empty_message = 'لا توجد اشتراكات حالية'

        try:
            user = await User.objects.aget(telegram_id=update.effective_sender.id)

        except User.DoesNotExist:
            await update.effective_message.reply_text(empty_message)
            return

        if not await user.get_active_subscriptions().aexists():
            await update.effective_message.reply_text(empty_message)
            return

        async for index, subscription in aenumerate(user.get_active_subscriptions(), 1):
            message += f'{index}. {subscription.chat_name}, ينتهي الاشتراك في {format_date(subscription.end_date)}\n'
        await update.effective_message.reply_text(message)

    async def renew_user_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        renew_user_id = update.effective_sender.id
        existing_user: User | None = await User.objects.filter(telegram_id=renew_user_id).afirst()

        if existing_user:
            cache.current_step = BotStep.RENEW_SUBSCRIPTION
            active_subscriptions = existing_user.get_active_subscriptions()

            if not await active_subscriptions.aexists():
                await update.effective_message.reply_text('لا يوجد اشتراكات حالية لتجديدها.')
                return

            keyboard = await aget_inline_keyboard(
                active_subscriptions,
                label_field=lambda subscription: get_group_display_name_by_id(subscription.chat_id) or subscription.chat_name,
                value_field='id'
            )

            message = format_message('يرجى اختيار اشتراك لتجديده:')
            await update.effective_message.reply_markdown_v2(message, reply_markup=InlineKeyboardMarkup(keyboard))

        else:
            await update.effective_message.reply_text('لا يوجد اشتراكات حالية لتجديدها.')

    async def contact_support(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.CONTACT_SUPPORT
        await update.effective_message.reply_text(Messages.CONTACT_SUPPORT)

    # ---------- Status Updates ---------- #
    @private_chat_and_support_chat_only
    async def message_received(self, update: Update, context: CallbackContext):
        cache = self.get_current_cache(update.effective_sender.id)

        match cache.current_step:
            case BotStep.SUBSCRIPTION_INVOICE_NUMBER:
                cache.invoice_number = update.message.text
                cache.current_step = BotStep.TRADINGVIEW_ID
                await update.message.reply_text(Messages.ENTER_TRADINGVIEW_ID)

            case BotStep.TRADINGVIEW_ID:
                cache.tradingview_id = update.message.text
                await self._add_user_subscription(update, context)

            case BotStep.RENEW_INVOICE_NUMBER:
                cache.invoice_number = update.message.text
                cache.current_step = BotStep.RENEW_TRADINGVIEW_ID
                await update.message.reply_text(Messages.ENTER_TRADINGVIEW_ID)

            case BotStep.RENEW_TRADINGVIEW_ID:
                tradingview_id = update.message.text
                user = await User.objects.filter(telegram_id=update.effective_sender.id).afirst()
                existing_subscription: Subscription = await user.subscriptions.aget(id=cache.renew_subscription_id)

                await SubscriptionRequest.objects.acreate(
                    user_telegram_id=user.telegram_id,
                    username=user.telegram_username or '',
                    chat_id=existing_subscription.chat_id,
                    chat_name=existing_subscription.chat_name,
                    invoice_number=cache.invoice_number,
                    payment_method=cache.renew_payment_method,
                    tradingview_id=tradingview_id,
                    subscription=existing_subscription
                )

                await update.message.reply_text(Messages.SUBSCRIPTION_REQUEST_SENT)

            case BotStep.CONTACT_SUPPORT:
                if update.effective_chat.type is not ChatType.PRIVATE:
                    return

                sender = update.effective_sender
                display_name = get_mentionable_display_name(sender)
                message = "رسالة من " + display_name + " (معرف: " + str(sender.id) + ")" + '\n\n' + update.message.text
                button = InlineKeyboardButton(
                    text='رد على الرسالة',
                    callback_data=json.dumps(dict(type=InlineButtonCallbackType.SUPPORT_RESPONSE.value, sender_id=sender.id))
                )
                reply_markup = InlineKeyboardMarkup([[button]])
                await update.message.reply_text(Messages.CONTACT_SUPPORT_SENT)

                await context.bot.send_message(
                    chat_id=settings.SUPPORT_CHAT_ID,
                    text=message,
                    reply_markup=reply_markup
                )

            case BotStep.RESPOND_TO_SUPPORT:
                if update.effective_chat.id != settings.SUPPORT_CHAT_ID:
                    return

                support_response = cache.support_response

                if update.message.text:
                    support_response.message = update.message.text

                if update.message.photo:
                    support_response.photos.append(
                        TelegramPhoto(photo_size=update.message.photo[-1], caption=update.message.caption)
                    )

                if update.message.document:
                    support_response.documents.append(update.message.document)

                message_text = (
                    support_response.formatted_message +
                    "يرجى التاكيد عند الانتهاء"
                )
                reply_markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text='تأكيد',
                                callback_data=json.dumps(dict(
                                    type=InlineButtonCallbackType.CONFIRM_SUPPORT_RESPONSE.value
                                ))
                            )
                        ]
                    ]
                )

                if support_response.message_id:
                    await context.bot.edit_message_text(
                        chat_id=settings.SUPPORT_CHAT_ID,
                        message_id=support_response.message_id,
                        text=message_text,
                        reply_markup=reply_markup
                    )

                else:
                    message = await context.bot.send_message(
                        chat_id=settings.SUPPORT_CHAT_ID,
                        text=message_text,
                        reply_markup=reply_markup
                    )
                    support_response.message_id = message.message_id

    async def _add_user_subscription(self, update: Update, context: CallbackContext):
        user = update.effective_sender
        cache = self.get_current_cache(user.id)
        chat = await context.bot.get_chat(cache.chat_id)
        existing_user = await User.objects.filter(telegram_id=user.id).afirst()

        if not existing_user:
            await User.objects.acreate(
                telegram_id=user.id,
                first_name=user.first_name or '',
                last_name=user.last_name or '',
                telegram_username=user.username or ''
            )

        await SubscriptionRequest.objects.acreate(
            user_telegram_id=user.id,
            username=user.username or '',
            chat_id=cache.chat_id,
            chat_name=chat.title,
            invoice_number=cache.invoice_number,
            payment_method=cache.payment_method,
            tradingview_id=cache.tradingview_id
        )

        await update.message.reply_text(Messages.SUBSCRIPTION_REQUEST_SENT)

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

        except json.JSONDecodeError:
            ...

        if isinstance(data, dict):
            event_type = InlineButtonCallbackType(data.get('type'))

            match event_type:
                case InlineButtonCallbackType.SUPPORT_RESPONSE:
                    cache.current_step = BotStep.RESPOND_TO_SUPPORT
                    cache.support_response = SupportResponse(asker_id=data['sender_id'])
                    message = await update.effective_message.reply_text(
                        "يرجى ادخال رسالتك. يمكنك ايضا ارفاق الصور والملفات"
                    )

                case InlineButtonCallbackType.CONFIRM_SUPPORT_RESPONSE:
                    support_response = cache.support_response

                    # Send the message to the asker privately
                    if support_response.message:
                        await context.bot.send_message(
                            chat_id=support_response.asker_id,
                            text="رد من فريق الدعم:\n" + support_response.message,
                        )

                    else:
                        await context.bot.send_message(
                            chat_id=support_response.asker_id,
                            text="رد من فريق الدعم:"
                        )

                    if support_response.documents:
                        for document in support_response.documents:
                            await context.bot.send_document(
                                chat_id=support_response.asker_id,
                                document=document
                            )

                    if support_response.photos:
                        for photo in support_response.photos:
                            await context.bot.send_photo(
                                chat_id=support_response.asker_id,
                                photo=photo.photo_size,
                                caption=photo.caption
                            )

                    await context.bot.edit_message_text(
                        chat_id=settings.SUPPORT_CHAT_ID,
                        message_id=support_response.message_id,
                        text=(
                            support_response.formatted_message +
                            "تم الرد بنجاح"
                        )
                    )

                    cache.current_step = BotStep.IDLE

            return

        match cache.current_step:
            case BotStep.SELECT_SUBSCRIPTION_GROUP:
                await query.delete_message()
                cache.chat_id = int(data)

                existing_user = await User.objects.filter(telegram_id=update.effective_sender.id).afirst()

                if existing_user:
                    existing_subscription = await existing_user.subscriptions.filter(
                        chat_id=cache.chat_id,
                        is_active=True
                    ).afirst()

                    if existing_subscription:
                        message = format_message(
                            f'لديك اشتراك نشط بالفعل في هذه القناة. ينتهي في {format_date(existing_subscription.end_date)}'
                        )
                        await update.effective_message.reply_markdown_v2(message)
                        cache.current_step = BotStep.IDLE
                        return

                cache.current_step = BotStep.SUBSCRIPTION_PAYMENT_METHOD
                keyboard = get_payment_method_keyboard()
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.effective_message.reply_text(Messages.ENTER_SUBSCRIPTION_METHOD, reply_markup=reply_markup)

            case BotStep.SUBSCRIPTION_PAYMENT_METHOD:
                try:
                    payment_method = cache.payment_method = PaymentMethod(data)

                except ValueError:
                    await update.effective_message.reply_text(Messages.INVALID_PAYMENT_METHOD)
                    return

                await query.edit_message_text(text=f"وسيلة الدفع المختارة: {payment_method.label}")
                cache.current_step = BotStep.SUBSCRIPTION_INVOICE_NUMBER
                await update.effective_message.reply_text(Messages.ENTER_INVOICE_NUMBER, reply_markup=ReplyKeyboardRemove())

            case BotStep.RENEW_SUBSCRIPTION:
                await query.edit_message_text(text='تم اختيار الاشتراك')
                cache.renew_subscription_id = int(data)
                cache.current_step = BotStep.RENEW_PAYMENT_METHOD
                keyboard = get_payment_method_keyboard()
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.effective_message.reply_text(
                    Messages.ENTER_SUBSCRIPTION_METHOD,
                    reply_markup=reply_markup
                )

            case BotStep.RENEW_PAYMENT_METHOD:
                try:
                    payment_method = cache.renew_payment_method = PaymentMethod(data)

                except ValueError:
                    await update.effective_message.reply_text(Messages.INVALID_PAYMENT_METHOD)
                    return

                await query.edit_message_text(text=f"وسيلة الدفع المختارة: {payment_method.label}")
                cache.current_step = BotStep.RENEW_INVOICE_NUMBER
                await update.effective_message.reply_text(Messages.ENTER_INVOICE_NUMBER)

            case BotStep.START:
                await query.delete_message()
                match data:
                    case 'subscribe':
                        await self.subscribe(update, context)
                    case 'mysubscriptions':
                        await self.my_subscriptions(update, context)
                    case 'renew':
                        await self.renew_user_subscription(update, context)

                    case 'contact_support':
                        await self.contact_support(update, context)
