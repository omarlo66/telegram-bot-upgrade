from datetime import date

from django.db import models
from pendulum import DateTime, Date

from src.common import pendulum
from src.common.choices import PaymentMethod
from src.common.utils import format_nullable_string


class Subscription(models.Model):
    chat_id = models.IntegerField()
    chat_name = models.CharField(max_length=300)
    end_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    invoice_number = models.CharField(max_length=300)
    user_notified_for_renewal_count = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    tradingview_id = models.CharField(max_length=200, default='')

    user = models.ForeignKey('common.User', related_name='subscriptions', on_delete=models.CASCADE)

    @property
    def days_left(self) -> int:
        if not self.end_date:
            return 0

        now = pendulum.now().date()

        if now > self.end_date:
            return 0
        return (self.end_date - now).days

    def format(self, separator: str = ' | '):
        created_at = self.created_at.strftime('%d/%m/%Y')
        subscription_end_date = self.end_date.strftime('%d/%m/%Y')

        return (
            f'*Channel/Group*: {format_nullable_string(self.chat_name)}{separator}'
            f'*Payment method*: {format_nullable_string(self.get_payment_method_display())}\n'
            f'*Created at*: {format_nullable_string(created_at)}{separator}'
            f'*End date*: {format_nullable_string(subscription_end_date)}\n'
            f'*Invoice number*: {format_nullable_string(self.invoice_number)}{separator}'
            f'*Days left*: {format_nullable_string(self.days_left)}'
        )

    async def deactivate(self):
        self.is_active = False
        await self.asave()

    @classmethod
    def from_json(cls, data: dict) -> tuple['Subscription', bool]:
        data['created_at'] = DateTime.fromtimestamp(data['created_at'])
        data['end_date'] = Date.fromisoformat(data['end_date'])
        data['payment_method'] = PaymentMethod(data['payment_method'])
        return cls.objects.get_or_create(**data)

    @classmethod
    def to_json(cls, data: dict):
        data['created_at'] = data['created_at'].timestamp()
        data['end_date'] = data['end_date'].isoformat()
        data['payment_method'] = data['payment_method'].value

    def as_excel_row(self) -> list:
        return [
            self.chat_name,
            self.get_payment_method_display(),
            self.invoice_number,
            self.created_at.strftime('%d/%m/%Y'),
            self.end_date.strftime('%d/%m/%Y')
        ]

    async def renew(
        self,
        invoice_number: str,
        end_date: date,
        payment_method: PaymentMethod,
        tradingview_id: str = ''

    ) -> 'Subscription':

        await self.deactivate()

        subscription = await Subscription.objects.acreate(
            user_id=self.user_id,
            chat_id=self.chat_id,
            chat_name=self.chat_name,
            invoice_number=invoice_number,
            end_date=end_date,
            payment_method=payment_method,
            tradingview_id=tradingview_id
        )

        return subscription
