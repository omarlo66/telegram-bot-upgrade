from django.db import models


class PaymentMethod(models.TextChoices):
    SALLA = 'salla', 'سلة'
    STC = 'stc', 'STC'
    TRIAL = 'trial', 'تجربة مجانيه'
    OTHER = 'other', 'أخرى'


class SubscriptionRequestStatus(models.IntegerChoices):
    PENDING = 1, 'Pending'
    APPROVED = 2, 'Approved'
    DECLINED = 3, 'Declined'
    COMPLETED = 4, 'Completed'
