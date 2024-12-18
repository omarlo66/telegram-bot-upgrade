from collections import defaultdict
from datetime import timedelta, datetime,time
from django.db.models.functions import TruncHour,TruncDate,ExtractHour
from django.db.models import Q,Count
from django.utils import timezone
from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import response
from OciechartBotDjango.serializers import SubscriptionSerializer
from src.common import settings
from src.common.choices import SubscriptionRequestStatus
from src.common.models import Subscription, Feedback, Group, Training, subscription
from src.common.utils import get_credentials
from .forms import LoginForm
from django.shortcuts import render
from django.http import HttpResponseRedirect, HttpResponse
from django.utils.timezone import make_aware

class LoginAdmin(TemplateView):
    template_name = "login.html"  # Setting the template directly

    def get(self, request, *args, **kwargs):
        auth_token = get_credentials('token_auth')  # Call function inside method

        # Check for the auth cookie
        if request.COOKIES.get('auth') == auth_token:
            return HttpResponseRedirect('/subscriber-activity')

        # Render the template if not authenticated
        return render(request, self.template_name)
    
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
        
from datetime import datetime, timedelta

def set_cookie(response, key, value, days_expire=7):
    max_age = days_expire * 24 * 60 * 60 if days_expire is not None else 365 * 24 * 60 * 60
    expires = datetime.strftime(datetime.utcnow() + timedelta(seconds=max_age), "%a, %d-%b-%Y %H:%M:%S GMT")

    # Set cookie with necessary parameters for localhost
    response.set_cookie(
        key=key,
        value=value,
        max_age=max_age,
        expires=expires,
        path='/',         # Allows cookie to be accessible site-wide
        secure=False,     # Set False for local HTTP; set True in production with HTTPS
        httponly=True     # Protects against JavaScript access
    )


class SubscriberActivityView(TemplateView):
    template_name = "dashboard.html"

class Dashboard_v2(TemplateView):
    template_name = "dashboard.html"

class SubscriberActivityAPIView2(APIView):
    def get(self, request, format=None,from_date=None,to_date=None):
        token = request.COOKIES.get('auth')

        from_date = request.query_params.get('from_date', None)
        to_date = request.query_params.get('to_date', None)
        
        if token != get_credentials('token_auth'):
            return Response(False,status=status.HTTP_401_UNAUTHORIZED)

        if from_date != None and to_date != None:
            from_date = datetime.strptime(from_date, "%Y-%m-%d")
            to_date = datetime.strptime(to_date, "%Y-%m-%d")
            subscriptions = Subscription.objects.filter(created_at__range=(from_date, to_date))
        else:
            subscriptions = Subscription.objects.all()
            to_date = datetime.now().date()
            year = to_date.year
            month = to_date.month - 1

            if month == 0:  # Handle January case
                month = 12
                year -= 1

            from_date = to_date.replace(year=year, month=month)

        one_month_ago = from_date
        next_month = to_date
        if not subscriptions.exists():
            print("No subscriptions found.")
            return Response({"error": "No subscriptions available"}, status=status.HTTP_204_NO_CONTENT)
        
        subscriptions_by_date = defaultdict(int)

        # Loop through the subscriptions and count the number per date
        for subscription in subscriptions:
            subscription_date = subscription.created_at.date()  # Extract the date part
            subscriptions_by_date[subscription_date] += 1

        # Find the top day with the maximum subscriptions
        top_day_subscriptions_date = max(subscriptions_by_date, key=subscriptions_by_date.get)
        top_day_subscriptions = subscriptions_by_date[top_day_subscriptions_date]

        subscription_count = subscriptions.count()
        joined_within_a_month = subscriptions.filter(created_at__range=(one_month_ago, next_month)).count()
        joined_within_a_month_percentage = round((joined_within_a_month / (subscription_count or 1)) * 100, 2)
        leaving_within_a_month = subscriptions.filter(end_date__lte=next_month).count()
        leaving_within_a_month_percentage = round((leaving_within_a_month / (subscription_count or 1)) * 100, 2)

        monthly_growth_percentage = round(
            (joined_within_a_month - leaving_within_a_month) / (subscription_count or 1) * 100, 2
        )

        return Response({
            "subscription_count": subscription_count,
            "joined_within_a_month": joined_within_a_month,
            "joined_within_a_month_percentage": joined_within_a_month_percentage,
            "leaving_within_a_month": leaving_within_a_month,
            "leaving_within_a_month_percentage": leaving_within_a_month_percentage,
            "monthly_growth_percentage": monthly_growth_percentage,
            "most_joins_in_a_day": top_day_subscriptions,
            "most_joins_in_a_day_date": top_day_subscriptions_date,
            "reviews":self.reviews(from_date,to_date),
            "groups":self.groups(),
            "training":self.training(from_date,to_date),
            "total_renewed":self.total_renewed(from_date,to_date),
            "total_lefted":self.total_lefted(from_date,to_date),
            "total_subscribers": self.total_subscribers(from_date,to_date),
            'subscriber_by_date': self.get_subscription_data(subscriptions),
            'parameters': [from_date,to_date]
        },status=status.HTTP_200_OK)
        

    def get_subscription_data(self, subscriptions):
        grouped_data = subscriptions.values(
        'created_at__date',
        'chat_name'
        ).annotate(
            count=Count('id')
        ).order_by('created_at__date', 'chat_name')

        # Group data by date and create a list of dictionaries
        result = []
        current_date = None
        current_group = None
        for item in grouped_data:
            date = item['created_at__date'].strftime('%Y-%m-%d')
            chat_name = item['chat_name']
            count = item['count']

            if date != current_date:
                current_date = date
                current_group = {'created_at': date, 'data': []}
                result.append(current_group)

            current_group['data'].append({'label': chat_name, 'value': count})

        return result
    
    def chart_2_data(self,start_date,end_date):
        reviews_dict = {
            0: 'لا تعليق',
            1: 'ضعيف',
            2: 'مقبول',
            3: 'جيد',
            4: 'جيد جداً',
            5: 'ممتاز'
        }
        if start_date == None and end_date == None:
            chart_labels = []
            chart_data = []
            reviews = self.reviews()
            for review in reviews:
                chart_labels.append(review['review'])
                chart_data.append(reviews_dict[review['review']])
            return chart_labels,chart_data
        
    def total_renewed(self,start_date,end_date):
        if start_date == None and end_date == None:
            return Subscription.objects.filter(renewed=True).count()
        else:
            return Subscription.objects.filter(renewed=True).filter(created_at__date__range=(start_date,end_date)).count()

    def total_lefted(self,start_date,end_date):
        if start_date == None and end_date == None:
            return Subscription.objects.filter(is_active=False).count()
        else:
            return Subscription.objects.filter(is_active=False).filter(created_at__date__range=(start_date,end_date)).count()
    
    def total_subscribers(self,from_date,to_date):
        if from_date == None and to_date == None:
            return Subscription.objects.all().count()
        else:
            return Subscription.objects.filter(created_at__date__range=(from_date,to_date)).count()

    def reviews(self,from_date,to_date):
        if from_date == None and to_date == None:
            reviews = [{'review':i.review,'date':i.created_at} for i in Feedback.objects.all()]
        else:
            reviews = [{'review':i.review,'date':i.created_at} for i in Feedback.objects.filter(created_at__date__range=(from_date,to_date))]
        return reviews

    def groups(self):
        groups = [{'title':i.title,'id':i.telegram_id,'subscribers':Subscription.objects.filter(chat_name=i.title,is_active=True).count(),'lefted':Subscription.objects.filter(chat_name=i.title,is_active=False).count(),'renew':Subscription.objects.filter(chat_name=i.title,renewed=True).count()} for i in Group.objects.all()]
        return groups

    def top_users(self,from_date,to_date):
        if from_date == None and to_date == None:
            top_users = [{'user':i.user_id,'subscribers':Subscription.objects.filter(user_id=i.user_id).count()} for i in Subscription.objects.all()]
        else:
            top_users = [{'user':i.user_id,'subscribers':Subscription.objects.filter(user_id=i.user_id).count()} for i in Subscription.objects.filter(created_at__date__range=(from_date,to_date))]
        return top_users

    def training(self, from_date, to_date):
        try:
            # Make sure `from_date` and `to_date` are timezone-aware if required
            if from_date is not None:
                from_date = make_aware(from_date)
            if to_date is not None:
                to_date = make_aware(to_date)

            # Filter the training queryset based on date range
            queryset = Training.objects.all()
            if from_date and to_date:
                queryset = queryset.filter(created_at__range=(from_date, to_date))

            # Process queryset to include required data
            training = []
            for i in queryset:
                couch_username = i.couch_telegram.telegram_username if i.couch_telegram else ""
                training.append({
                    "couch": couch_username,
                    "date": i.session_date,
                    "time": i.session_time,
                    "status": SubscriptionRequestStatus(i.status).name,
                    "created_at": i.created_at,
                })

            return training
        except Exception as e:
            print(f"Error in training function: {e}")
            return []


class SubscriberActivityAPIView(APIView):
    def get(self, request, format=None):
        token = request.COOKIES.get('auth')
        if token != get_credentials('token_auth'):
            return Response(False,status=status.HTTP_401_UNAUTHORIZED)

        
        try:
            if from_date != None:
                today = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                from_date =  today.month_delta
                date = datetime.strptime(date, "%d-%m-%Y")
                aware_datetime = make_aware(date)
                subscriptions = Subscription.objects.filter(created_at__date=aware_datetime)
                if not subscriptions.exists():
                    print("No subscriptions found for the selected date.")
            elif from_date != None and to_date != None:
                from_date = datetime.strptime(from_date, "%d-%m-%Y")
                to_date = datetime.strptime(to_date, "%d-%m-%Y")
                subscriptions = Subscription.objects.filter(created_at__range=(from_date, to_date))
            else:
                subscriptions = Subscription.objects.all()
            if not subscriptions.exists():
                print("No subscriptions found.")
                return Response({"error": "No subscriptions available"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            subscriptions = []
        #
        if filter_param == 'all':
            response_data = self.get_all_data()
        elif filter_param == 'day':
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
                start_date=start_date
            )
        else:
            return Response({"error": "Invalid filter parameter"}, status=status.HTTP_400_BAD_REQUEST)
        print(subscriptions)
        subscription_count = subscriptions.count()
        joined_within_a_month = subscriptions.filter(created_at__gte=one_month_ago).count()
        joined_within_a_month_percentage = round((joined_within_a_month / (subscription_count or 1)) * 100, 2)
        leaving_within_a_month = subscriptions.filter(end_date__lte=next_month).count()
        leaving_within_a_month_percentage = round((leaving_within_a_month / (subscription_count or 1)) * 100, 2)

        monthly_growth_percentage = round(
            (joined_within_a_month - leaving_within_a_month) / (subscription_count or 1) * 100, 2
        )

        most_joins_in_a_day = max(response_data['joined'])
        try:
            most_joins_in_a_day_date = max(response_data['labels'])
        except Exception as e:
            print('error: ',e,' Var: ',response_data)
            most_joins_in_a_day_date = 'date not found'
        

        data = {
            "total_members": subscription_count,
            "joined_within_a_month_percentage": joined_within_a_month_percentage,
            "leaving_within_a_month_percentage": leaving_within_a_month_percentage,
            "monthly_growth_percentage": monthly_growth_percentage,
            "most_joins_in_a_day": most_joins_in_a_day,
            "most_joins_in_a_day_date": most_joins_in_a_day_date,
            "chart_data": response_data,
            "total_renewed": self.total_renewed(date),
            "total_lefted": self.total_lefted(date),
            "table_data": self.get_table_data(),
            "reviews": self.reviews(),
            "groups" : self.groups(),
            "training": self.training(),
        }

        return Response(data, status=status.HTTP_200_OK)

    def total_renewed(self,date=None):
        if date == None:
            return Subscription.objects.filter(renewed=True).count()
        else:
            return Subscription.objects.filter(renewed=True).filter(created_at=date).count()

    def total_lefted(self,date=None):
        if date == None:
            return Subscription.objects.filter(is_active=False).count()
        else:
            return Subscription.objects.filter(is_active=False).filter(created_at=date).count()

    
    def get_table_data(self):
        subscriptions = Subscription.objects.filter(is_active=True).order_by('end_date')
        serializer = SubscriptionSerializer(subscriptions, many=True)
        return serializer.data

    def reviews(self):
        reviews = [{'review':i.review,'date':i.created_at} for i in Feedback.objects.all()]
        return reviews

    def groups(self):
        groups = [{'title':i.title,'id':i.telegram_id,'subscribers':Subscription.objects.filter(chat_name=i.title).count(),'lefted':Subscription.objects.filter(is_active=False).count(),'renew':Subscription.objects.filter(renewed=True).count()} for i in Group.objects.all()]
        return groups

    def training(self):
        training = [{"couch":i.couch_telegram.telegram_username if i.couch_telegram != None else "","date":i.session_date,"time":i.session_time,"status":SubscriptionRequestStatus(i.status).name,"created_at":i.created_at} for i in Training.objects.all()]
        return training

    def get_day_data(self, start_date: datetime, subscriptions):
        dates = [start_date + timedelta(hours=i) for i in range(24)]
        labels = [date.strftime('%Y-%m-%d %H:00') for date in dates]

        # Handle joined_data with ExtractHour
        joined_data = subscriptions.filter(created_at__date=start_date.date()) \
                                .annotate(hour=ExtractHour('created_at')) \
                                .values('hour') \
                                .annotate(count=Count('id')) \
                                .order_by('hour')
        
        # Manually extract hour for left_data from a DateField
        left_data = subscriptions.filter(end_date=start_date.date())
        
        left_counts = [0] * 24
        for sub in left_data:
            end_hour = sub.end_date.hour
            left_counts[end_hour] += 1
        
        joined_counts = {entry['hour']: entry['count'] for entry in joined_data}
        joined_result = [joined_counts.get(hour, 0) for hour in range(24)]

        return {"labels": labels, "joined": joined_result, "left": left_counts}

    def get_week_data(self, start_date: datetime, subscriptions):
        # Generate dates and labels for the week
        dates = [start_date + timedelta(days=i) for i in range(7)]
        labels = [date.strftime('%Y-%m-%d') for date in dates]

        try:
            # Query subscriptions created within the week
            joined_data = subscriptions.filter(created_at__date__range=(start_date, start_date + timedelta(days=6))) \
                                        .annotate(day=TruncDate('created_at')) \
                                        .values('day') \
                                        .annotate(count=Count('id')) \
                                        .order_by('day')

            # Query subscriptions ending within the week
            left_data = subscriptions.filter(end_date__range=(start_date, start_date + timedelta(days=6))) \
                                    .annotate(day=TruncDate('end_date')) \
                                    .values('day') \
                                    .annotate(count=Count('id')) \
                                    .order_by('day')

            # Debugging: Log raw query results
            print("Joined Data:", list(joined_data))
            print("Left Data:", list(left_data))

            # Handle query results and build counts
            joined_counts = {entry.get('day'): entry.get('count', 0) for entry in joined_data}
            left_counts = {entry.get('day'): entry.get('count', 0) for entry in left_data}

            # Generate results for each date in the week
            joined_result = [joined_counts.get(date.date(), 0) for date in dates]
            left_result = [left_counts.get(date.date(), 0) for date in dates]

            return {"labels": labels, "joined": joined_result, "left": left_result}

        except Exception as e:
            # Log the error and return default values
            print(f"Error in get_week_data: {e}")
            return {"labels": labels, "joined": [0] * 7, "left": [0] * 7}

    def get_month_data(self, start_date: datetime):
        dates = [start_date + timedelta(days=i) for i in range(30)]
        labels = [date.strftime('%d/%m') for date in dates]
        subscriptions = Subscription.objects
        joined_data = subscriptions.filter(created_at__date__range=(start_date, start_date + timedelta(days=29))) \
                                .annotate(day=TruncDate('created_at')) \
                                .values('day') \
                                .annotate(count=Count('id')) \
                                .order_by('day')
        
        left_data = subscriptions.filter(end_date__range=(start_date, start_date + timedelta(days=29))) \
                                .annotate(day=TruncDate('end_date')) \
                                .values('day') \
                                .annotate(count=Count('id')) \
                                .order_by('day')
        if not isinstance(left_data,list):
            left_data = []

        joined_counts = {entry['day']: entry['count'] for entry in joined_data}
        left_counts = {entry['day']: entry['count'] for entry in left_data}
        
        joined_result = [joined_counts.get(date.date(), 0) for date in dates]
        left_result = [left_counts.get(date.date(), 0) for date in dates]

        return {"labels": labels, "joined": joined_result, "left": left_result}
    
    def get_all_data(self):
        joined_result = []
        left_result = []
        labels = []
        subscribers = [i for i in Subscription.objects.filter(is_active=True).all()]
        for sub in subscribers:
            labels.append(sub.created_at)
            joined_result.append(1)
            left_result.append(0)
        return {"labels": labels, "joined": joined_result, "left": left_result}

