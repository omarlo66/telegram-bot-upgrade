from typing import Union

from django.db import models

from src.common.mixins import HumanEntityMixin
import src.common.models
from src.common.utils import aenumerate


class User(models.Model, HumanEntityMixin):
    telegram_id = models.IntegerField(unique=True)
    telegram_username = models.CharField(max_length=255)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)

    last_removed_from_group_at = models.DateTimeField(null=True, blank=True)
    last_added_to_group_at = models.DateTimeField(null=True, blank=True)

    async def get_formatted_subscriptions(self, **kwargs):
        subscriptions = self.subscriptions.filter(**kwargs).order_by('created_at')
        message = ''

        async for index, subscription in aenumerate(subscriptions, 1):
            message += f'{index}. {subscription.format()}\n\n'
        return message

    @classmethod
    def from_json(cls, data: dict) -> tuple['User', bool]:
        from src.common.models import Subscription

        data['telegram_id'] = data.pop('id')
        data['telegram_username'] = data.pop('username')
        data['last_name'] = data.pop('last_name', '') or ''

        subscriptions_data = data.pop('subscriptions', [])
        user, created = cls.objects.get_or_create(**data)

        for subscription_data in subscriptions_data:
            subscription_data['user_id'] = user.id
            Subscription.from_json(data=subscription_data)
        return user, created

    def as_excel_rows(self) -> list[list]:
        return [
            [
                self.telegram_id,
                self.telegram_username,
                self.full_name,
                *subscription.as_excel_row()
            ]
            for subscription in self.get_active_subscriptions()
        ]

    @property
    async def latest_subscription(self) -> Union['src.common.models.Subscription', None]:
        if self.subscriptions:
            sorted_subscriptions = self.get_active_subscriptions(sort_by='created_at')
            return await sorted_subscriptions.alast()

    def get_active_subscriptions(self, sort_by: str = None):
        active_subscriptions = self.subscriptions.filter(is_active=True)

        if sort_by:
            active_subscriptions = active_subscriptions.order_by(sort_by)

        return active_subscriptions

    def has_active_subscription_for_chat(self, chat_id: int) -> bool:
        return self.get_active_subscriptions().filter(chat_id=chat_id).exists()

    async def get_active_subscription_for_chat(self, chat_id: int) -> Union['src.common.models.Subscription', None]:
        return await self.get_active_subscriptions().filter(chat_id=chat_id).afirst()
