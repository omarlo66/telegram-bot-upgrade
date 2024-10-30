from django.db import models


class EmployeeRole(models.TextChoices):
    ADMIN = 'admin', 'Admin'
    EMPLOYEE = 'employee', 'Employee'
