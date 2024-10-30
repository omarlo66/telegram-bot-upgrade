# Generated by Django 5.1 on 2024-08-28 13:52

import django.db.models.deletion
import src.common.mixins
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telegram_id', models.IntegerField(unique=True)),
                ('telegram_username', models.CharField(max_length=255)),
                ('first_name', models.CharField(max_length=255)),
                ('last_name', models.CharField(max_length=255)),
                ('role', models.CharField(choices=[('admin', 'Admin'), ('employee', 'Employee')], max_length=30)),
            ],
            bases=(models.Model, src.common.mixins.HumanEntityMixin),
        ),
        migrations.CreateModel(
            name='Group',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
        ),
        migrations.CreateModel(
            name='OfferMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('interval', models.PositiveSmallIntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='SenderEntity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('api_id', models.IntegerField(unique=True)),
                ('api_hash', models.CharField(max_length=255)),
                ('user_id', models.IntegerField(unique=True)),
                ('phone_number', models.CharField(max_length=20)),
                ('is_active', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='SubscriptionRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_id', models.IntegerField()),
                ('chat_id', models.IntegerField()),
                ('end_date', models.DateField()),
                ('payment_method', models.CharField(choices=[('salla', 'سلة'), ('stc', 'STC'), ('trial', 'تجربة'), ('other', 'أخرى')], max_length=50)),
                ('invoice_number', models.CharField(max_length=200)),
                ('status', models.IntegerField(choices=[(1, 'Pending'), (2, 'Approved'), (3, 'Declined'), (4, 'Completed')])),
                ('chat_name', models.CharField(max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reported', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telegram_id', models.IntegerField(unique=True)),
                ('telegram_username', models.CharField(max_length=255)),
                ('first_name', models.CharField(max_length=255)),
                ('last_name', models.CharField(max_length=255)),
            ],
            bases=(models.Model, src.common.mixins.HumanEntityMixin),
        ),
        migrations.CreateModel(
            name='GroupFamily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('main_group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_families', to='common.group')),
                ('subgroups', models.ManyToManyField(blank=True, to='common.group')),
            ],
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chat_id', models.IntegerField()),
                ('end_date', models.DateField()),
                ('payment_method', models.CharField(choices=[('salla', 'سلة'), ('stc', 'STC'), ('trial', 'تجربة'), ('other', 'أخرى')], max_length=20)),
                ('invoice_number', models.CharField(max_length=300)),
                ('user_notified_for_renewal_count', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('chat_name', models.CharField(max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to='common.user')),
            ],
        ),
    ]
