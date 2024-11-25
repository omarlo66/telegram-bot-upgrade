import json
import os.path
from pathlib import Path
from types import FunctionType
from typing import Iterable, Union, Any, Callable

from telegram import InlineKeyboardButton

from src.common import settings
from src.common.choices import PaymentMethod


def format_nullable_string(string, prefix=None):
    xmark = '❌'

    if string not in (None, ''):
        if prefix:
            return f'{prefix}{string}'
        return string
    return xmark


def filter_list(iterable: Iterable, one: bool = False, **kwargs) -> Union[Union[list, None], Union[Any, None]]:
    def filter_func(item):
        for key, value in kwargs.items():
            if '__isnull' in key:
                actual_key = key.replace('__isnull', '')
                if (actual_key is None) is not value:
                    return False

            elif '__in' in key:
                actual_key = key.replace('__in', '')
                if getattr(item, actual_key) not in value:
                    return False

            elif getattr(item, key) != value:
                return False
        return True

    filtered_items = list(filter(filter_func, iterable))

    if one:
        if filtered_items:
            return filtered_items[0]
        else:
            return
    else:
        return filtered_items


def format_message(message: str) -> str:
    chars = "\_[]()~`>#+-=|{}.!"

    for char in chars:
        message = message.replace(char, f'\\{char}')

    return message

    # return (
    #     message
    #     .replace('.', '\\.')
    #     .replace('-', '\\-')
    #     .replace('|', '\\|')
    #     .replace('(', '\\(')
    #     .replace(')', '\\)')
    #     .replace('=', '\\=')
    #     .replace('>', '\\>')
    #     .replace('<', '\\<')
    #     .replace('!', '\\!')
    #     .replace('#', '\\#')
    #     .replace('#\\', '\\')
    #     .replace('#\\', '\\')
    # )


def get_payment_method_keyboard():
    items_per_row = 2
    keyboard = []
    current_row = []

    for item in PaymentMethod:
        button = InlineKeyboardButton(item.label, callback_data=item.value)

        current_row.append(button)

        if len(current_row) == items_per_row:
            keyboard.append(current_row)
            current_row = []

    return keyboard


def get_inline_keyboard_button(
    index: int,
    item: dict | object,
    label_field: str | Callable,
    value_field: str,
    keyboard: list,
    current_row: list,
    items_per_row: int,
    item_count: int
):
    if isinstance(label_field, FunctionType):
        label = label_field(item)

    elif isinstance(item, dict):
        label = item.get(label_field)

    else:
        label = getattr(item, label_field)

    if isinstance(item, dict):
        value = item.get(value_field)

    else:
        value = getattr(item, value_field)

    button = InlineKeyboardButton(label, callback_data=value)

    current_row.append(button)

    if len(current_row) == items_per_row:
        keyboard.append(current_row.copy())
        current_row.clear()

    elif index == item_count:
        keyboard.append(current_row)


def get_inline_keyboard(
    items: list[dict] | list[object],
    label_field: str = 'label',
    value_field: str = 'value',
    items_per_row: int = 2
):
    keyboard = []
    current_row = []

    for index, item in enumerate(items, 1):
        get_inline_keyboard_button(
            index,
            item,
            label_field,
            value_field,
            keyboard,
            current_row,
            items_per_row,
            item_count=len(items)
        )

    return keyboard


async def aget_inline_keyboard(
    items,
    label_field: str | Callable = 'label',
    value_field: str = 'value',
    items_per_row: int = 2
):
    keyboard = []
    current_row = []

    async for index, item in aenumerate(items, 1):
        get_inline_keyboard_button(
            index,
            item,
            label_field,
            value_field,
            keyboard,
            current_row,
            items_per_row,
            item_count=len(items)
        )

    return keyboard







def get_path(path: str) -> Path:
    if not settings.PROJECT_ROOT:
        raise ValueError('"PROJECT_ROOT" is required in settings.')

    return Path(settings.PROJECT_ROOT, path)

def get_credentials(bot_type: str):
    filename = get_path('credentials.json')

    if os.path.isfile(filename):
        with open(filename) as f:
            return json.load(f).get(bot_type)

    raise FileNotFoundError('Credentials file not found.')

def set_credintials(name:str,value):
    filename = get_path('credentials.json')
    if os.path.isfile(filename):
        with open(filename) as f:
            data = json.load(f)
            data[name] = value
            with open(filename,'w') as s:
                json.dump(data,s)

def get_display_name(user):
    if user.first_name:
        if user.last_name:
            display_name = f'{user.first_name} {user.last_name}'
        else:
            display_name = user.first_name

    elif user.last_name:
        display_name = user.last_name
    else:
        display_name = ''

    return display_name
set_credintials('token_auth','101020')

def get_mentionable_display_name(user):
    if user.username:
        return f'@{user.username}'
    else:
        return get_display_name(user)


async def aenumerate(async_sequence, start=0):
    """Asynchronously enumerate an async iterator from a given start value"""
    n = start
    async for elem in async_sequence:
        yield n, elem
        n += 1


def get_group_display_name_by_id(chat_id: str) -> str | None:
    DISPLAY_NAMES = {
        group['id']: group['title']
        for group in settings.GROUPS
    }

    return DISPLAY_NAMES.get(chat_id)


async def get_staff_ids(employee_role: str = None):
    from src.common.models import Employee
    employees = Employee.objects.all()

    if employee_role:
        employees = employees.filter(role=employee_role)

    employee_ids = set(employee.id async for employee in employees)
    bot_owner_ids = set(user['id'] for user in settings.BOT_OWNERS)
    return employee_ids | bot_owner_ids
