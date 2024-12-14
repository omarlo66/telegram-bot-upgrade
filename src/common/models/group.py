from django.db import models


class Group(models.Model):
    telegram_id = models.IntegerField(null=True, unique=True)
    title = models.CharField(max_length=255, default='')
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, to_field='telegram_id')

    @classmethod
    def from_json(cls, data: dict) -> tuple['Group', bool]:
        data['telegram_id'] = data.pop('id')
        return cls.objects.get_or_create(**data)
