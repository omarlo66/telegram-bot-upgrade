from django.db import models


class SenderEntity(models.Model):
    api_id = models.IntegerField(unique=True)
    api_hash = models.CharField(max_length=255)
    user_id = models.IntegerField(unique=True)
    phone_number = models.CharField(max_length=20)
    is_active = models.BooleanField(default=False)

    def update(self, api_id: int, api_hash: str, phone_number: str, is_active: bool = False):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.is_active = is_active

    @classmethod
    def from_json(cls, data: dict) -> tuple['SenderEntity', bool]:
        return cls.objects.get_or_create(**data)
