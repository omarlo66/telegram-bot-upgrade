import datetime
import json

from telegram import (
    ReplyKeyboardMarkup,
    Update,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.error import BadRequest
from telegram.constants import ChatType
from telegram.ext import ContextTypes, CallbackContext, filters, Application
from telethon import TelegramClient

from asgiref.sync import sync_to_async

from src.admin_bot.enums import InlineButtonCallbackType
from src.client_bot.cache import Cache
from src.client_bot.constants import Messages
from src.client_bot.enums import BotStep
from src.client_bot.interfaces import SupportResponse, TelegramPhoto
from src.common import settings
from src.common.choices import PaymentMethod, SubscriptionRequestStatus
from src.common.db import Database
from src.common.formatters import format_date
from src.common.models import User, SubscriptionRequest, Subscription, Group, Training, Feedback
from src.common.utils import (
    format_message,
    get_inline_keyboard,
    get_payment_method_keyboard,
    aget_inline_keyboard,
    aenumerate,
    get_group_display_name_by_id,
    get_mentionable_display_name,
    get_inline_keyboard_v2,
    get_inline_keyboard_with_argument,
    error_log
)
import calendar




# noinspection PyUnusedLocal
class Commands:
    def __init__(self):
        self.db: Database | None = None
        self.caches: dict[int, Cache] = {}
        self.client: TelegramClient | None = None
        self._client: TelegramClient | None = None
        self.application: Application | None = None
        self.groupSubscribtion = 0
        self.find_requests()
        self.training_requests()
        keyboard = [
            [InlineKeyboardButton("القائمه الرئيسيه", callback_data='start'),InlineKeyboardButton("الإشتراك", callback_data='subscribe')]
        ]
        self.static_keyoard = ReplyKeyboardMarkup(keyboard,resize_keyboard=True)


    async def find_requests(self):
        for i in SubscriptionRequest.objects.all():
                if i.status == SubscriptionRequestStatus.DECLINED:
                    message = i.message
                    user_id = i.user_telegram_id
                    await self.client.send_message(user_id, f'للأسف لم يتم قبول طلب الإنضمام للأسباب التاليه: \n \n {message} \n\n تواصل مع الدعم للمساعده /start' + message)
    
    async def training_requests(self):
        for i in Training.objects.filter(status=SubscriptionRequestStatus.DECLINED,anounced=False).all():
            self.client.send_message(i.telegram_id, message=f'لم يتم قبول طلب خدمة التدريب للأسباب التاليه: \n \n {i.message}')
            i.anounced = True
            await i.asave()
        for i in Training.objects.filter(status=SubscriptionRequestStatus.APPROVED,anounced=False).all():
            self.client.send_message(i.telegram_id, message=f'تم  قبول طلب خدمة التدريب: \n \n {i.message}')
            i.anounced = True
            await i.asave()

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
        async def wrapper(self: 'Commands', update: Update, context: ContextTypes.DEFAULT_TYPE,new=True):
            if update.effective_chat.type is not ChatType.PRIVATE:
                return
            return await func(self, update, context)

        return wrapper

    @staticmethod
    def private_chat_and_support_chat_only(func):
        async def wrapper(self: 'Commands', update: Update, context: ContextTypes.DEFAULT_TYPE,new=True):
            if (
                update.effective_chat.type is not ChatType.PRIVATE and
                update.effective_chat.id != settings.SUPPORT_CHAT_ID
            ):
                return
            return await func(self, update, context)

        return wrapper

    # ---------- Commands ---------- #
    async def update_db(self):
        settings_groups = settings.GROUPS
        for i in settings_groups:
            if not await Group.objects.filter(telegram_id=i['id']).afirst():
                await Group.objects.acreate(telegram_id=i['id'],title=i['title'])
            if i['subgroups'] and len(i['subgroups']) > 0:
                parent_id = await Group.objects.filter(telegram_id=i['id']).afirst()
                if parent_id:
                    parent_id = parent_id.telegram_id
                for sub in i['subgroups']:
                    if not await Group.objects.filter(telegram_id=sub['id']).afirst():
                        await Group.objects.acreate(telegram_id=sub['id'],title=sub['title'],parent_id=parent_id)

    @private_chat_only
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE,new=True):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.START
        keyboard = get_inline_keyboard([
            {'text':'انضمام للقنوات','callback':'subscribe'},
            {'text':'استعلام عن الخدمات','callback':'mysubscriptions'},
            {'text':'تمديد العضوية','callback':'renew'},
            {'text':'مراسلة الدعم','callback':'contact_support'},
            {'text':'أحصل على تجربه مجانيه','callback':'free_subscribe'},
            {'text':'خدمة التدريب','callback':'training_request'},
        ],label_field='text',value_field='callback',items_per_row=2)
        #keyboard = [
        #    [InlineKeyboardButton(text='تفعيل الخدمة', callback_data='subscribe')],
        #    [InlineKeyboardButton(text='استعلام عن الخدمات', callback_data='mysubscriptions')],
        #    [InlineKeyboardButton(text='تمديد العضوية', callback_data='renew')],
        #    [InlineKeyboardButton(text='مراسلة الدعم', callback_data='contact_support')]
        #]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.update_db()
        if new == True:
            await update.effective_message.reply_photo(open('welcome.png','rb'))
            await update.effective_message.reply_text(
                format_message('برجاء قراءة المرفق جيداً إذا كانت هذا أول  مره للتواصل \n الأستكمال يعني أنك توافق على الشروط'),
                reply_markup=reply_markup
            )
        else:
            await update.effective_message.reply_text(
                    format_message('كيف يمكنني مساعدتك؟'),
                reply_markup=reply_markup)

    async def get_groups(self, chat_id):
        groups = await sync_to_async(lambda: list(Group.objects.filter(parent_id=None)))()
        return groups
    
    async def subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.SELECT_SUBSCRIPTION_GROUP
        #keyboard = get_inline_keyboard(
        #    items=settings.GROUPS,
        #    label_field='title',
        #    value_field='id',
        #    items_per_row=1
        #)
        #groups = settings.GROUPS
        chat_id = cache.chat_id
        groups = await self.get_groups(chat_id)
        groups = [{'title': i.title, 'id': i.telegram_id} for i in groups]
        groups.append({'title':'العوده للقائمه','id':0})
        keyboard = get_inline_keyboard(groups,label_field='title',value_field='id',items_per_row=2)
        reply_markup = InlineKeyboardMarkup(keyboard)
        #await update.effective_message.reply_text(text = "يرجى اختيار قناة للاشتراك:" , reply_markup=reply_markup)
        await update.effective_message.reply_markdown_v2(text=format_message("يرجى اختيار قناة للاشتراك:"), reply_markup=reply_markup)
        #await update.effective_message.reply_markdown_v2(text='test',reply_markup=ReplyKeyboardMarkup(keyboard))

    @private_chat_only
    async def feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Collect feedback from the user.
        """
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.FEEDBACK  # Track feedback flow in cache

        # Feedback options
        feedback_options = [
            {'title': 'ممتاز', 'id': 5},
            {'title': 'جيد جداً', 'id': 4},
            {'title': 'جيد', 'id': 3},
            {'title': 'مقبول', 'id': 2},
            {'title': 'ضعيف', 'id': 1},
            {'title': 'لا تعليق','id':0},
        ]

        # Generate inline keyboard
        keyboard = get_inline_keyboard(
            items=feedback_options,
            label_field='title',
            value_field='id',
            items_per_row=2
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send feedback prompt
        await update.effective_message.reply_text(
            "برجاء تقييم تجربتك معنا:",
            reply_markup=reply_markup
        )

    async def free_subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.SELECT_SUBSCRIPTION_GROUP
        cache.free_trial = True
        groups = await self.get_groups(cache.chat_id)
        groups_inline = [{'title': i.title, 'id': i.telegram_id} for i in groups]
        groups_inline.append({'title':'خدمة التدريب','id':1})
        groups_inline.append({'title':'العوده للقائمه','id':0})
        
        keyboard = get_inline_keyboard(groups_inline,label_field='title',value_field='id',items_per_row=2)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.effective_message.reply_markdown_v2(text=format_message("يرجى اختيار قناة او خدمه للاشتراك:"), reply_markup=reply_markup)

    async def my_subscriptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = 'هذه هي اشتراكاتك الحالية\n\n'
        empty_message = 'لا توجد اشتراكات حالية'

        try:
            user = await User.objects.aget(telegram_id=update.effective_sender.id)

        except User.DoesNotExist:
            await update.effective_message.reply_text(empty_message)
            return

        if not await user.get_active_subscriptions().aexists():
            await update.effective_message.reply_text(empty_message,reply_markup=self.static_keyoard)
            return

        async for index, subscription in aenumerate(user.get_active_subscriptions(), 1):
            message += f'{index}. {subscription.chat_name}, ينتهي الاشتراك في {format_date(subscription.end_date)}\n'
        await update.effective_message.reply_text(message,reply_markup=self.static_keyoard)

    async def renew_user_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.free_trial = True
        renew_user_id = update.effective_sender.id
        existing_user: User | None = await User.objects.filter(telegram_id=renew_user_id).afirst()

        if existing_user:
            cache.current_step = BotStep.RENEW_SUBSCRIPTION
            active_subscriptions = existing_user.get_active_subscriptions()

            if not await active_subscriptions.aexists():
                await update.effective_message.reply_text('لا يوجد اشتراكات حالية لتجديدها.',reply_markup=self.static_keyoard)
                return

            keyboard = await aget_inline_keyboard(
                active_subscriptions,
                label_field=lambda subscription: get_group_display_name_by_id(subscription.chat_id) or subscription.chat_name,
                value_field='id'
            )

            message = format_message('يرجى اختيار اشتراك لتجديده:')
            await update.effective_message.reply_markdown_v2(message, reply_markup=InlineKeyboardMarkup(keyboard))

        else:
            await update.effective_message.reply_text('لا يوجد اشتراكات حالية لتجديدها.',reply_markup=self.static_keyoard)

    async def contact_support(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.CONTACT_SUPPORT
        await update.effective_message.reply_text(Messages.CONTACT_SUPPORT,reply_markup=self.static_keyoard)

    async def help_services(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.SELECT_SUBSCRIPTION_GROUP

        # Generate the inline keyboard for main groups and subgroups
        keyboard = get_inline_keyboard_v2(settings.GROUPS)
        
        # Wrap the keyboard in InlineKeyboardMarkup
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send the message with the inline keyboard
        await update.effective_message.reply_text(
            text=Messages.ABOUT_SERVICES,
            reply_markup=reply_markup
        )

    #training request functions
    async def training_request(self,update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        cache.current_step = BotStep.TRAINING_REQUEST
        now = datetime.datetime.now()
        calendar_markup = await self.create_calendar(now.year, now.month)
        await update.effective_message.reply_text("حدد التاريخ المناسب للتدريب:\n", reply_markup=calendar_markup)
        #await update.effective_message.reply_text(' \n\n YYYY-MM-DD \n\n مثال: 2023-01-01')
    
    async def create_calendar(self, year, month):
        keyboard = []
        cal = calendar.monthcalendar(year, month)
        month_name = calendar.month_name[month]

        # Add month and year at the top
        keyboard.append([InlineKeyboardButton(f"{month_name} {year}", callback_data="ignore")])

        # Add the day headers
        days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in days])

        # Add the days of the month
        for week in cal:
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(" ", callback_data="ignore"))
                else:
                    callback_data = json.dumps({"year": year, "month": month, "day": day})
                    row.append(InlineKeyboardButton(str(day), callback_data=callback_data))
            keyboard.append(row)

        # Add navigation buttons
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1

        keyboard.append([
            InlineKeyboardButton("<", callback_data=json.dumps({"year": prev_year, "month": prev_month, "action": "prev"})),
            InlineKeyboardButton("العوده للرئيسيه", callback_data="ignore"),
            InlineKeyboardButton(">", callback_data=json.dumps({"year": next_year, "month": next_month, "action": "next"}))
        ])

        return InlineKeyboardMarkup(keyboard)
    

    async def time_markup(self, date):
        # Fetch reserved training sessions for the given date asynchronously
        sessions = await sync_to_async(lambda: list(Training.objects.filter(session_date=date)))()

        times = ['00:30','16:30','18:00','19:30','20:30','21:30','22:30','23:30']  # Available time slots from 08:00 to 19:00

        # Extract reserved session times and format them as strings
        if sessions:    
            session_times = [f'{session.session_time}' for session in sessions]
        else:
            session_times = []

        # Filter out reserved times to get available time slots
        available_times = [time for time in times if time not in session_times]

        # Create the reply markup with available time slots
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(time, callback_data=time)] for time in available_times] +
            [[InlineKeyboardButton('العوده', callback_data='back')]]
        )
        return reply_markup

    async def confirm_training(self,update: Update, context: ContextTypes.DEFAULT_TYPE):
        cache = self.get_current_cache(update.effective_sender.id)
        try:
            await Training.objects.acreate(
                                telegram_id = update.effective_sender.id,
                                session_date = cache.training_date,
                                session_time = cache.training_time,
                                payment_method = cache.payment_method,
                                invoice_number = cache.invoice_number,
                                username = update.effective_user.username
                            )
            await update.message.reply_text(f'تم إرسال الطلب وسيتم الرد في أقرب وقت ممكن, شكراً لأختيارك Ocie Chart \n لقد حددت جلسة التدريب بتاريخ {cache.training_date} ووقت {cache.training_time}',reply_markup=self.static_keyoard)
            await self.feedback(update,context)
            #await cache.clear()
        except Exception as e:
            error_log().append(f'Confirm_traning function: {e}')

        
    # ---------- Status Updates ---------- #
    @private_chat_and_support_chat_only
    async def message_received(self, update: Update, context: CallbackContext):
        cache = self.get_current_cache(update.effective_sender.id)
        if update.message.text == 'الإشتراك':
            await update.effective_message.delete()
            cache.current_step = BotStep.SELECT_SUBSCRIPTION_GROUP
            await self.subscribe(update,context)
        elif update.message.text == 'القائمه الرئيسيه':
            await update.effective_message.delete()
            cache.current_step = BotStep.START
            await self.start(update,context,False)
            
        if not cache.current_step:
            await self.start(update,context,False)

        match cache.current_step:
            case BotStep.SUBSCRIPTION_INVOICE_NUMBER:
                cache.invoice_number = update.message.text
                cache.current_step = BotStep.TRADINGVIEW_ID
                try:
                    await update.message.reply_text(Messages.ENTER_TRADINGVIEW_ID)
                except:
                    await update.effective_message.reply_text(Messages.ENTER_TRADINGVIEW_ID)
            
            case BotStep.TRADINGVIEW_ID:
                cache.tradingview_id = update.message.text
                await self._add_user_subscription_2(update, context)
                await update.message.reply_text(Messages.SUBSCRIPTION_REQUEST_SENT,reply_markup=self.static_keyoard)
                await self.feedback(update,context)

            case BotStep.RENEW_INVOICE_NUMBER:
                cache.invoice_number = update.message.text
                cache.current_step = BotStep.RENEW_TRADINGVIEW_ID
                try:
                    await update.message.reply_text(Messages.ENTER_TRADINGVIEW_ID)
                except:
                    await update.effective_message.reply_text(Messages.ENTER_TRADINGVIEW_ID)

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
                    subscription=existing_subscription,
                    renew = True
                )
                cache.clear()
                await update.message.reply_text(Messages.SUBSCRIPTION_REQUEST_SENT,reply_markup=self.static_keyoard)
                await self.feedback(update,context)

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
                await update.message.reply_text(Messages.CONTACT_SUPPORT_SENT,reply_markup=self.static_keyoard)
                await self.feedback(update,context)

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

            case BotStep.TRAINING_INVOICE:
                if cache.free_trial == True:
                    cache.invoice_number = 'free trial'
                else:
                    cache.invoice_number = update.message.text

                cache.current_step = BotStep.TRAINING_REQUEST
                await self.confirm_training(update,context)
 
            case BotStep.FEEDBACK_MESSAGE:
                user_comment = update.message.text
                feedback = cache.feedback  # Retrieve the feedback from the cache

                try:
                    # Update the feedback record with the user's comment
                    await Feedback.objects.filter(id=feedback.id).aupdate(message=user_comment)

                    await update.message.reply_text(
                        "شكراً لتعليقك! نقدّر ملاحظاتك وسنعمل على تحسين خدماتنا."
                    )
                    cache.clear()  # Clear cache after feedback process is complete

                except Exception as e:
                    error_log().append(f"Error saving user feedback comment: {e}")
                    await update.message.reply_text(
                        "حدث خطأ أثناء حفظ تعليقك. الرجاء المحاولة مرة أخرى."
                    )

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
        cache.clear()
        await update.message.reply_text(Messages.SUBSCRIPTION_REQUEST_SENT,reply_markup=self.static_keyoard())
        await self.feedback(update,context)

    async def _add_user_subscription_2(self, update: Update, context: CallbackContext):
        user = update.effective_sender
        cache = self.get_current_cache(user.id)

        # Check if chat_id exists in cache and is valid
        if not cache.chat_id:
            #await update.message.reply_text("Error: No chat ID found in cache.")
            return

        chat_name = await Group.objects.filter(telegram_id=cache.chat_id).afirst()
        if chat_name:
            chat_name = chat_name.title

        # Retrieve or create user record
        existing_user = await User.objects.filter(telegram_id=user.id).afirst()
        if not existing_user:
            await User.objects.acreate(
                telegram_id=user.id,
                first_name=user.first_name or '',
                last_name=user.last_name or '',
                telegram_username=user.username or ''
            )

        # Create subscription request with the chat name (real or fallback)
        if cache.invoice_number == None:
            cache.invoice_number = 'trial'
        await SubscriptionRequest.objects.acreate(
            user_telegram_id=user.id,
            username=user.username or '',
            chat_id=cache.chat_id,
            chat_name=chat_name,  # Use chat_name here instead of chat.title
            invoice_number=cache.invoice_number,
            payment_method=cache.payment_method,
            tradingview_id=cache.tradingview_id
        )
        cache.clear()
        # Confirm subscription request
        #await update.message.reply_text(Messages.SUBSCRIPTION_REQUEST_SENT)

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
            if 'type' in data.keys():
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

                        await self.feedback(update,context)

                return

        if data == 'start':
            await self.start(update,context,False)
            return
        elif data == 'subscribe':
            await self.subscribe(update,context)
            return
        if cache.current_step == None:
            cache.current_step = BotStep.START

        print(cache.current_step,' *'*8)
        match cache.current_step:
            
            #ask for date
            case BotStep.TRAINING_REQUEST:
                

                # Handle navigation between months
                if "action" in data:
                    year, month = data["year"], data["month"]
                    new_calendar = await self.create_calendar(year, month)
                    await query.edit_message_reply_markup(reply_markup=new_calendar)

                # Handle date selection
                elif "year" in data and "month" in data and "day" in data:
                    selected_date = datetime.date(data["year"], data["month"], data["day"])
                    today = datetime.date.today()
                    if selected_date < today:
                        await update.effective_message.reply_text('برجاء أختيار تاريخ بعد اليوم')
                        await self.training_request(update, context)
                        return
                    elif selected_date == today:
                        await update.effective_message.reply_text('برجاء أختيار تاريخ بعد اليوم')
                        await self.training_request(update, context)
                        return
                    await query.delete_message()
                    cache.training_date = selected_date
                    cache.current_step = BotStep.TRAINING_TIME
                    time_markup = await self.time_markup(selected_date)
                    await update.effective_message.reply_text(f"لقد أخترت تاريخ: {selected_date} \n \n أختر الموعد المناسب للتدريب: (بتوقيت المملكه العربيه السعوديه) \n\n إذا لم يتوفر مواعيد في هذا اليوم يمكنك العوده وتحديد يوم أخر ** شكرأ لتفهمك",reply_markup=time_markup)

                else:
                    await self.start(update,context,False)
                    return
            #choose time or get back
            case BotStep.TRAINING_TIME:
                await query.delete_message()
                if data == "back":
                    await self.training_request(update,context)

                # Handle time slot selection
                else:
                    start_time = data
                    cache.training_time = start_time
                    if cache.free_trial == True:
                        cache.payment_method = PaymentMethod.TRIAL
                        cache.invoice_number = 'free trial'
                        cache.current_step = BotStep.SEND_TRAINING_REQUEST
                        await Training.objects.acreate(
                                telegram_id = update.effective_sender.id,
                                session_date = cache.training_date,
                                session_time = cache.training_time,
                                payment_method = cache.payment_method,
                                invoice_number = cache.invoice_number,
                                username = update.effective_user.username
                            )
                        await update.effective_message.reply_text(f'تم إرسال الطلب وسيتم الرد في أقرب وقت ممكن, شكراً لأختيارك Ocie Chart \n لقد حددت جلسة التدريب بتاريخ {cache.training_date} ووقت {cache.training_time}',reply_markup=self.static_keyoard)
                        await self.feedback(update,context)
                    else:
                        cache.current_step = BotStep.TRAINING_PAYMENT
                        payment_methods_keyborad = InlineKeyboardMarkup(get_payment_method_keyboard(False))
                        await update.effective_message.reply_text("لقد قمت بتحديد الموعد المناسب للتدريب. يرجى اختيار طريقة الدفع:",reply_markup=payment_methods_keyborad)
            
            case BotStep.TRAINING_PAYMENT:
                try:
                    payment_method = cache.payment_method = PaymentMethod(data)

                except ValueError:
                    await update.effective_message.reply_text(Messages.INVALID_PAYMENT_METHOD)
                    return
                await query.edit_message_text(text=f"وسيلة الدفع المختارة: {payment_method.label}")
                cache.current_step = BotStep.TRAINING_INVOICE
                await  update.effective_message.reply_text('يرجى ادخال رقم الفاتورة أو معرف التحويل', reply_markup=ReplyKeyboardRemove())

            case BotStep.TRAINING_REQUEST:
                await query.delete_message()
                match data:
                    case 'confirm_training':
                        self.confirm_training(update,context)
                        print('confirm')
                    case 'start':
                        self.start(update,context,False)

            case BotStep.SELECT_SUBSCRIPTION_GROUP:
                await query.delete_message()
                if data == 0:
                    await self.start(update,context,False)
                    return
                elif data == 1:
                    await self.training_request(update,context)
                    return
                
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
                        await update.effective_message.reply_markdown_v2(message,reply_markup=self.static_keyoard)
                        cache.current_step = BotStep.IDLE
                        return
                if cache.free_trial == True:
                    cache.current_step = BotStep.TRADINGVIEW_ID
                    cache.payment_method = PaymentMethod(PaymentMethod.TRIAL)
                    await update.effective_message.reply_text(Messages.ENTER_TRADINGVIEW_ID)
                else:
                    cache.current_step = BotStep.SUBSCRIPTION_PAYMENT_METHOD
                    keyboard = get_payment_method_keyboard(False)
                    reply_markup = InlineKeyboardMarkup(keyboard)
                
                    await update.effective_message.reply_text(Messages.ENTER_SUBSCRIPTION_METHOD, reply_markup=reply_markup)

            case BotStep.SUBSCRIPTION_PAYMENT_METHOD:
                try:
                    payment_method = cache.payment_method = PaymentMethod(data)

                except ValueError:
                    await update.effective_message.reply_text(Messages.INVALID_PAYMENT_METHOD)
                    return

                await query.edit_message_text(text=f"وسيلة الدفع المختارة: {payment_method.label}")

                if cache.free_trial == True:
                    cache.current_step = BotStep.TRADINGVIEW_ID
                    await  update.effective_message.reply_text(Messages.ENTER_TRADINGVIEW_ID, reply_markup=ReplyKeyboardRemove())
                else:
                    cache.current_step = BotStep.SUBSCRIPTION_INVOICE_NUMBER
                    await update.effective_message.reply_text(Messages.ENTER_INVOICE_NUMBER, reply_markup=ReplyKeyboardRemove())

            case BotStep.RENEW_SUBSCRIPTION:
                await query.edit_message_text(text='تم اختيار الاشتراك')
                cache.renew_subscription_id = int(data)
                cache.current_step = BotStep.RENEW_PAYMENT_METHOD
                keyboard = get_payment_method_keyboard(False)
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
                    case 'free_subscribe':
                        await self.free_subscribe(update,context)
                    case 'mysubscriptions':
                        await self.my_subscriptions(update, context)
                    case 'renew':
                        await self.renew_user_subscription(update, context)
                    case 'contact_support':
                        await self.contact_support(update, context)
                    case 'training_request':
                        await self.training_request(update, context)

            case BotStep.FEEDBACK:
                query = update.callback_query
                await query.answer()  # Acknowledge the callback

                # Extract feedback rating from callback data
                feedback_data = query.data
                user_id = update.effective_sender.id

                try:
                    feedback_rating = int(feedback_data)
                    # Store feedback in the database (example model required)
                    cache.feedback = await Feedback.objects.acreate(
                        telegram_id = user_id,
                        telegram_username=update.effective_sender.username ,
                        review=feedback_rating
                    )
                    if feedback_rating <= 3:
                        cache.current_step = BotStep.FEEDBACK_MESSAGE
                        await query.edit_message_text(" شكراً لتقييمك! نسعى دائماً لتقديم الأفضل. \n\n برجاء كتابة ما أعجبك وما لا يعجبك في خدماتنا \n\n /start او العوده للقائمه")
                        
                    else:
                        # Thank the user for their feedback
                        cache.current_step = BotStep.IDLE
                        await query.edit_message_text(" شكراً لتقييمك! نسعى دائماً لتقديم الأفضل.")
                        

                except Exception as e:
                    error_log().append(f"Error handling feedback callback: {e}")
                    await query.edit_message_text("حدث خطأ أثناء معالجة تقييمك. برجاء المحاولة مرة أخرى.")