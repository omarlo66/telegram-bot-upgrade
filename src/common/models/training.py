from django.db import models  
from src.common.choices import SubscriptionRequestStatus, PaymentMethod
from src.common.utils import format_nullable_string
import datetime
from src.common.models.employee import Employee

class Training(models.Model):
    telegram_id = models.IntegerField(null=True)
    username = models.CharField(max_length=200, default='')
    session_date = models.CharField(max_length=255, default='')
    session_time = models.CharField(max_length=255, default='')
    couch_telegram = models.ForeignKey('common.Employee', on_delete=models.CASCADE,null=True,default=None)
    status = models.IntegerField(choices=SubscriptionRequestStatus.choices, default=SubscriptionRequestStatus.PENDING)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices,default='')
    invoice_number = models.CharField(max_length=300, default='free trial')
    message = models.CharField(max_length=300,default='')
    created_at = models.DateTimeField(auto_now_add=True)
    anounced = models.BooleanField(default=False)
    reported = models.BooleanField(default=False)

    @classmethod
    def from_json(cls, data: dict) -> tuple['Training', bool]:
        data['telegram_id'] = data.pop('id')
        return cls.objects.get_or_create(**data)

    def format(self, separator: str = ' | '):
        created_at = self.created_at.strftime('%d/%m/%Y')

        return (
            f'*Username*: {format_nullable_string(self.username, prefix="@")}{separator}'
            f'*Service*: training service'
            f'*Created at*: {format_nullable_string(self.created_at)}{separator}'
            f'*session date and time *: {format_nullable_string(self.session_date)} \t {format_nullable_string(self.session_time)}\n'
            f'*Invoice number*: {format_nullable_string(self.invoice_number)}{separator}'
            f'*Payment method*: {format_nullable_string(self.payment_method)}\n'
        )

    async def approved_format(self, spearator: str = '\n\n'):
       # This line is correct as `.afirst()` is an async method and should be awaited        
        # Check if couch_info was found
        if self.couch_telegram:
            coach_name = f"@{self.couch_telegram.telegram_username}"
        else:
             coach_name = ''
        return (
            f"تم الموافقه على طلب التدريب بتاريخ {self.session_date} \n في تمام الساعه {self.session_time}"
            f" بتوقيت المملكه العربيه السعوديه \n \n وسيقدم لك {coach_name} التدريب"
            f" شكراً لأختيارك Ocie Chart"
        )

    def rejected_format(self, spearator: str = '\n\n'):
            return (
                f"لم تتم الموافقه على التدريب للأسباب التاليه: {self.message} \n\n"
                f"برجاء تصحيح الخطأ وإعادة تقديم الطلب,\n\n"
                f"إذا كنت تحتاج للمساعده لا تتردد في التواصل مع الدعم /start"
            )
    