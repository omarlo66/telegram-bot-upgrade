from django.db import models

from src.admin_bot.choices import EmployeeRole
from src.common.mixins import HumanEntityMixin


class Employee(models.Model, HumanEntityMixin):
    telegram_id = models.IntegerField(unique=True)
    telegram_username = models.CharField(max_length=255)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    role = models.CharField(max_length=30, choices=EmployeeRole.choices)
    have_task = models.BooleanField(default=False)

    @classmethod
    def from_json(cls, data: dict) -> tuple['Employee', bool]:
        data['telegram_id'] = data.pop('id')
        data['telegram_username'] = data.pop('username')
        data['last_name'] = data.pop('last_name', '') or ''
        data['role'] = EmployeeRole(data['role'])
        return cls.objects.get_or_create(**data)
