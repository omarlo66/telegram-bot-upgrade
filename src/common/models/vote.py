from django.db import models


class Feedback(models.Model):
    telegram_id = models.IntegerField(unique=False)
    telegram_username = models.CharField(max_length=255,unique=False)
    review = models.IntegerField(choices=[
            (0, "Very Bad"),
            (1, "Bad"),
            (2, "Okay"),
            (3, "Good"),
            (4, "Very Good"),
            (5, "Excellent")
        ],unique=False)
    message = models.CharField(max_length=255,default=False,unique=False)
    notified = models.BooleanField(default=False,unique=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    @classmethod
    def from_json(cls, data: dict):
        data['telegram_id'] = data.pop('id')
        data['telegram_username'] = data.pop('username')
        data['last_name'] = data.pop('last_name', '') or ''
        data['review'] = data.pop('review')
        data['message'] = data.pop('message',' ')

        return cls.objects.get_or_create(**data)