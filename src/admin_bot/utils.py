import telegram
from telegram import KeyboardButton, KeyboardButtonRequestUsers, ReplyKeyboardMarkup, ChatMember
from telegram.constants import ChatMemberStatus
from telegram.error import ChatMigrated
from telegram.ext import ContextTypes
from telethon.tl.types import ChannelParticipantCreator, ChannelParticipantAdmin

from datetime import datetime

from src.common import settings, pendulum
from src.common.models import User

class error_log:
    def __init__(self):
        self.error_log_file = 'error_log'
        self.type = ''
        try:
            open(self.error_log_file,'r').read()
            self.type = 'a'
        except:
            self.type = 'w'
    def append(self,error):
        open(self.error_log_file,self.type).write(f'{error}\t{datetime.now()}\n')

    def show_all(self):
        return open(self.error_log_file,'r').read()
    
    
def get_request_user_reply_markup():
    keyboard = [
        [
            KeyboardButton("Select User", request_users=KeyboardButtonRequestUsers(
                request_id=1,
                request_name=True,
                request_username=True
            ))
        ]
    ]

    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)


def is_bot_owner(user_id: int) -> bool:
    owner_ids = [owner['id'] for owner in settings.BOT_OWNERS]
    return user_id in owner_ids


def is_normal_chat_member_telethon(chat_member) -> bool:
    return not (
        chat_member.bot or
        isinstance(chat_member.participant, ChannelParticipantCreator) or
        isinstance(chat_member.participant, ChannelParticipantAdmin)
    )


def is_normal_chat_member_ptb(chat_member: ChatMember) -> bool:
    return not chat_member.user.is_bot and chat_member.status == ChatMemberStatus.MEMBER


async def ban_chat_member(chat_id, user: [User, telegram.User], context: ContextTypes.DEFAULT_TYPE):
    is_django_user = isinstance(user, User)
    until_date = pendulum.now().add(minutes=1)

    async def update_django_user_removal_time():
        now = pendulum.now()

        if is_django_user:
            user.last_removed_from_group_at = now
            await user.asave()

        else:
            _user, created = await User.objects.aget_or_create(
                telegram_id=user.id,
                defaults=dict(
                    first_name=user.first_name,
                    last_name=user.last_name,
                    telegram_username=user.username,
                    last_removed_from_group_at=now
                )
            )

            if not created:
                _user.last_removed_from_group_at = now
                await _user.asave()

    user_id = user.telegram_id if is_django_user else user.id

    try:
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=until_date
        )
        await update_django_user_removal_time()
        return True

    except ChatMigrated as error:
        try:
            await context.bot.ban_chat_member(
                chat_id=error.new_chat_id,
                user_id=user_id,
                until_date=until_date
            )
            await update_django_user_removal_time()
            return True

        except Exception as error:
            print("Error:", error)
            return False

    except Exception as error:
        print("Error:", error)
        return False
