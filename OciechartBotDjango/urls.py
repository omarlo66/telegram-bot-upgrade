"""
URL configuration for OciechartBotDjango project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# from django.contrib import admin
from django.urls import path

from .views import SubscriberActivityView, SubscriberActivityAPIView2,SubscriberActivityAPIView, LoginAdmin ,save_cred, Dashboard_v2

urlpatterns = [
    #    path('admin/', admin.site.urls),
    path('',LoginAdmin.as_view(),name='login'),
    path('login',save_cred.as_view(),name="login"),
    path('subscriber-activity/', SubscriberActivityView.as_view(), name='dashboard'),
    path('dashboard/', Dashboard_v2.as_view(), name='dashboard'),
    path('api/subscriber-activity/', SubscriberActivityAPIView2.as_view())
]