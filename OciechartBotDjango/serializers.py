from rest_framework import serializers
from src.common.models.subscription import Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    telegram_id = serializers.ReadOnlyField(source='user.telegram_id')
    telegram_username = serializers.ReadOnlyField(source='user.telegram_username')
    end_date = serializers.DateField(format='%d/%m/%Y')
    chat_name = serializers.ReadOnlyField()

    class Meta:
        model = Subscription
        fields = ['telegram_id', 'telegram_username', 'days_left', 'end_date','chat_name']
