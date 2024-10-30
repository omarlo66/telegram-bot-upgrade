from django.db import models
from pendulum import Date, DateTime

from src.common.choices import PaymentMethod, SubscriptionRequestStatus
from src.common.utils import format_nullable_string


class SubscriptionRequest(models.Model):
    user_telegram_id = models.IntegerField()
    username = models.CharField(max_length=200, default='')
    chat_id = models.IntegerField()
    end_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, choices=PaymentMethod.choices)
    invoice_number = models.CharField(max_length=200)
    status = models.IntegerField(choices=SubscriptionRequestStatus.choices, default=SubscriptionRequestStatus.PENDING)
    chat_name = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    reported = models.BooleanField(default=False)

    tradingview_id = models.CharField(max_length=200, default='')

    # For renewing a subscription
    subscription = models.ForeignKey(
        'common.Subscription',
        related_name='subscription_requests',
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    @property
    def is_approved(self):
        return self.status == SubscriptionRequestStatus.APPROVED

    @property
    def is_declined(self):
        return self.status == SubscriptionRequestStatus.DECLINED

    @property
    def is_resolved(self):
        return self.is_approved or self.is_declined

    @classmethod
    def from_json(cls, data: dict) -> tuple['SubscriptionRequest', bool]:
        data['created_at'] = DateTime.fromtimestamp(data['created_at'])
        data['end_date'] = Date.fromisoformat(data['end_date'])
        data['payment_method'] = PaymentMethod(data['payment_method'])
        data['status'] = SubscriptionRequestStatus(data['status'])
        return cls.objects.get_or_create(**data)

    def format(self, separator: str = ' | '):
        created_at = self.created_at.strftime('%d/%m/%Y')

        if self.end_date:
            subscription_end_date = self.end_date.strftime('%d/%m/%Y')
        else:
            subscription_end_date = '-'

        return (
            f'*Username*: {format_nullable_string(self.username, prefix="@")}{separator}'
            f'*Channel/Group*: {format_nullable_string(self.chat_name)}{separator}'
            f'*Payment method*: {format_nullable_string(self.get_payment_method_display())}\n'
            f'*TradingView ID*: {format_nullable_string(self.tradingview_id)}{separator}'
            f'*Created at*: {format_nullable_string(created_at)}{separator}'
            f'*End date*: {format_nullable_string(subscription_end_date)}\n'
            f'*Invoice number*: {format_nullable_string(self.invoice_number)}{separator}'
        )

    async def mark_as_reported(self):
        self.reported = True
        await self.asave()

    async def mark_as_approved(self):
        self.status = SubscriptionRequestStatus.APPROVED
        await self.asave()

    async def mark_as_declined(self):
        self.status = SubscriptionRequestStatus.DECLINED
        await self.asave()

    async def mark_as_completed(self):
        self.status = SubscriptionRequestStatus.COMPLETED
        await self.asave()

    async def aget_or_create_subscription(self):
        from src.common.models import User

        user = await User.objects.aget(telegram_id=self.user_telegram_id)

        subscription = await user.subscriptions.filter(
            chat_id=self.chat_id
        ).alast()

        if subscription:
            subscription.chat_name = self.chat_name
            subscription.end_date = self.end_date
            subscription.is_active = True
            subscription.payment_method = self.payment_method
            subscription.invoice_number = self.invoice_number
            subscription.tradingview_id = self.tradingview_id
            await subscription.asave()

        else:
            subscription = await user.subscriptions.acreate(
                chat_id=self.chat_id,
                chat_name=self.chat_name,
                end_date=self.end_date,
                payment_method=self.payment_method,
                invoice_number=self.invoice_number,
                tradingview_id=self.tradingview_id
            )

        return subscription

    @property
    async def asubscription(self):
        from src.common.models import Subscription
        try:
            return await Subscription.objects.aget(id=self.subscription_id)
        except Subscription.DoesNotExist:
            ...
