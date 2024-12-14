# Generated by Django 5.1 on 2024-11-15 13:30

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0017_training_anounced'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionrequest',
            name='anounced',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='training',
            name='reported',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='training',
            name='created_at',
            field=models.DateField(default=datetime.date(2024, 11, 15)),
        ),
    ]
