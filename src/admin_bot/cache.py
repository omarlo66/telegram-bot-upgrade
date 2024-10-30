from types import SimpleNamespace
from typing import Union

from pendulum import Date
from telegram import SharedUser, Message
from telethon.tl.types import User as TelethonUser

from src.admin_bot.enums import BotStep

import src.common.models
from src.common.choices import PaymentMethod
from src.common.exceptions import SubgroupAlreadyExists, SubgroupIsMainGroup


class Cache(SimpleNamespace):
    chat_id: int | None = None
    shared_user: SharedUser | None = None
    payment_method: PaymentMethod | None = None
    invoice_number: str | None = None
    subscription_end_date: Date | None
    current_step: BotStep | None = None

    renew_user_id: str | None = None
    renew_subscription_id: int | None = None
    renew_end_date: Date | None = None
    renew_payment_method: PaymentMethod | None = None

    offer_message_content: str | None = None
    offer_message_interval: int | None = None

    api_id: int
    api_hash: str
    login_phone_number: str

    group_family_main_group: 'src.common.models.Group'
    group_family_subgroups: list['src.common.models.Group'] = []
    subgroup_message: Message | None = None

    cleanup_group_id: int | None = None
    cleanup_group_users: list[TelethonUser] = []

    approved_subscription_request: Union['src.common.models.SubscriptionRequest', None] = None

    def add_group_family_subgroup(self, subgroup: 'src.common.models.Group'):
        if subgroup == self.group_family_main_group:
            raise SubgroupIsMainGroup

        for _subgroup in self.group_family_subgroups:
            if _subgroup == subgroup:
                raise SubgroupAlreadyExists

        self.group_family_subgroups.append(subgroup)

    def clear(self):
        self.group_family_subgroups.clear()
        self.cleanup_group_users.clear()
