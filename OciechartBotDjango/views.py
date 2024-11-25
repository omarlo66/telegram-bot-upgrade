from datetime import timedelta, datetime,time

from django.db.models import Q
from django.utils import timezone
from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import response
from OciechartBotDjango.serializers import SubscriptionSerializer
from src.common import settings
from src.common.models import Subscription
from src.common.utils import get_credentials

from .forms import LoginForm
from django.shortcuts import render
from django.http import HttpResponseRedirect


class loginAdmin(TemplateView):
    template_name = "login.html"    

class save_cred(APIView):
    auth_token = get_credentials('token_auth')
    def post(self,request):
        user_auth_ = False
        if request.POST:
            response = Response()
            password = request.POST['password']
            if password == self.auth_token:
                user_auth_ = True
                set_cookie(response,'auth',password,7)
        response.data = user_auth_
        response.status_code = 200
        return response
        
def set_cookie(response, key, value, days_expire=7):
    if days_expire is None:
        max_age = 365 * 24 * 60 * 60  # one year
    else:
        max_age = days_expire * 24 * 60 * 60
    expires = datetime.strftime(
        datetime.utcnow() + timedelta(seconds=max_age),
        "%a, %d-%b-%Y %H:%M:%S GMT"
    )
    response.set_cookie(
        key,
        value,
        max_age=max_age,
        expires=expires,
        domain='/',
        secure=False,
        httponly=True
    )

class SubscriberActivityView(TemplateView):
    template_name = "subscriber-activity.html"


class SubscriberActivityAPIView(APIView):
    def get(self, request, format=None):
        token = request.COOKIES.get('auth')
        print(token)
        if token != get_credentials('token_auth'):
            return Response(False,status=status.HTTP_401_UNAUTHORIZED)

        filter_param = request.query_params.get('filter', 'month')
        now = timezone.now()
        one_month_ago = now - timedelta(days=30)
        next_month = now + timedelta(days=30)
        subscriptions = Subscription.objects.all()

        if filter_param == 'day':
            start_date = now - timedelta(days=1)
            response_data = self.get_day_data(
                start_date=start_date,
                subscriptions=subscriptions
            )

        elif filter_param == 'week':
            start_date = now - timedelta(days=7)
            response_data = self.get_week_data(
                start_date=start_date,
                subscriptions=subscriptions
            )

        elif filter_param == 'month':
            start_date = now - timedelta(days=30)
            response_data = self.get_month_data(
                start_date=start_date,
                subscriptions=subscriptions
            )

        else:
            return Response({"error": "Invalid filter parameter"}, status=status.HTTP_400_BAD_REQUEST)

        subscription_count = subscriptions.count()
        joined_within_a_month = subscriptions.filter(created_at__gte=one_month_ago).count()
        joined_within_a_month_percentage = round((joined_within_a_month / (subscription_count or 1)) * 100, 2)
        leaving_within_a_month = subscriptions.filter(end_date__lte=next_month).count()
        leaving_within_a_month_percentage = round((leaving_within_a_month / (subscription_count or 1)) * 100, 2)

        monthly_growth_percentage = round(
            (joined_within_a_month - leaving_within_a_month) / (subscription_count or 1) * 100, 2
        )

        most_joins_in_a_day = max(response_data['joined'])

        data = {
            "total_members": Subscription.objects.filter(is_active=True).count(),
            "joined_within_a_month_percentage": joined_within_a_month_percentage,
            "leaving_within_a_month_percentage": leaving_within_a_month_percentage,
            "monthly_growth_percentage": monthly_growth_percentage,
            "most_joins_in_a_day": most_joins_in_a_day,
            "chart_data": response_data,
            "table_data": self.get_table_data()
        }

        return Response(data, status=status.HTTP_200_OK)

    def get_table_data(self):
        subscriptions = Subscription.objects.filter(is_active=True).order_by('end_date')
        serializer = SubscriptionSerializer(subscriptions, many=True)
        return serializer.data

    def get_day_data(self, start_date: datetime, subscriptions):
        dates = [start_date + timedelta(hours=i) for i in range(24)]
        labels = [date.strftime('%Y-%m-%d %H:00') for date in dates]

        joined_data = [
            subscriptions.filter(
                Q(created_at__date=start_date.date()),
                Q(created_at__hour=date.hour)).count()
            for date in dates
        ]

        left_data = [
            subscriptions.filter(
                Q(end_date=start_date.date()),
                Q(end_date__hour=date.hour)).count()
            for date in dates
        ]
        return {"labels": labels, "joined": joined_data, "left": left_data}

    def get_week_data(self, start_date: datetime, subscriptions):
        dates = [start_date + timedelta(days=i) for i in range(7)]
        labels = [date.strftime('%Y-%m-%d') for date in dates]
        joined_data = [
            subscriptions.filter(created_at__date=date.date()).count()
            for date in dates
        ]

        left_data = [
            subscriptions.filter(end_date=date.date()).count()
            for date in dates
        ]

        return {"labels": labels, "joined": joined_data, "left": left_data}

    def get_month_data(self, start_date: datetime, subscriptions):
        dates = [start_date + timedelta(days=i) for i in range(30)]
        labels = [date.strftime('%d/%m') for date in dates]

        joined_data = [
            subscriptions.filter(created_at__date=date.date()).count()
            for date in dates
        ]

        left_data = [
            subscriptions.filter(end_date=date.date()).count()
            for date in dates
        ]

        return {"labels": labels, "joined": joined_data, "left": left_data}
