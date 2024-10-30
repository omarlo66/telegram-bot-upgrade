from dataclasses import dataclass, field
from typing import Union, Type

from pendulum import Date, DateTime, Duration

from src.admin_bot.choices import EmployeeRole
from src.common import pendulum
from src.common.choices import PaymentMethod, SubscriptionRequestStatus
from src.common.exceptions import UserNotFound
from src.common.mixins import HumanEntityMixin
from src.common.utils import format_nullable_string, filter_list


class ModelManager:
    def __init__(self, table_name: str, db, model: Type['Model']):
        from src.common.db import Database

        self.table_name = table_name
        self.db: Database = db
        self.model = model

    def get(self, **kwargs) -> Union['Model', None]:
        return filter_list(getattr(self.db, self.table_name), one=True, **kwargs)

    def filter(self, **kwargs):
        return filter_list(getattr(self.db, self.table_name), **kwargs)

    def all(self):
        return getattr(self.db, self.table_name)

    def create(self, **kwargs) -> 'Model':
        entity = self.model(**kwargs)
        getattr(self.db, self.table_name).append(entity)
        self.db.save()
        return entity


class Model:
    objects: ModelManager = None

    def __init__(self, **kwargs):
        ...

    @classmethod
    def from_json(cls, data: dict) -> 'Model':
        return cls(**data)

    @classmethod
    def to_json(cls, data: dict):
        ...

    def save(self):
        self.objects.db.save()


@dataclass
class User(Model, HumanEntityMixin):
    table_name = 'users'

    id: int
    username: str
    first_name: str = ''
    last_name: str = ''

    subscriptions: list['Subscription'] = field(default_factory=list)

    def __eq__(self, other):
        return self.id == other.id

    def get_formatted_subscriptions(self, **kwargs):
        subscriptions = sorted(
            filter_list(self.subscriptions, **kwargs),
            key=lambda sub: sub.created_at
        )
        message = ''

        for index, subscription in enumerate(subscriptions, 1):
            message += f'{index}. {subscription.format()}\n\n'
        return message

    def add_subscription(self, subscription: 'Subscription'):
        self.subscriptions.append(subscription)

    def get_subscription(self, **kwargs) -> Union['Subscription', None]:
        return filter_list(self.subscriptions, one=True, **kwargs)

    @classmethod
    def from_json(cls, data: dict) -> 'User':
        subscriptions = []

        for subscription_data in data.get('subscriptions', []):
            subscriptions.append(Subscription.from_json(data=subscription_data))

        data['subscriptions'] = subscriptions
        return cls(**data)

    @classmethod
    def to_json(cls, data: dict):
        for subscription_data in data['subscriptions']:
            Subscription.to_json(subscription_data)

    def as_excel_rows(self) -> list[list]:
        return [
            [
                self.id,
                self.username,
                self.full_name,
                *subscription.as_excel_row()
            ]
            for subscription in self.get_active_subscriptions()
        ]

    @property
    def latest_subscription(self) -> Union['Subscription', None]:
        if self.subscriptions:
            sorted_subscriptions = self.get_active_subscriptions(sort_by='created_at')
            return sorted_subscriptions[-1]

    def get_active_subscriptions(self, sort_by: str = None):
        active_subscriptions = filter_list(self.subscriptions, is_active=True)

        if sort_by:
            active_subscriptions.sort(key=lambda subscription: getattr(subscription, sort_by))

        return active_subscriptions

    def has_active_subscription_for_chat(self, chat_id: int) -> bool:
        active_subscription = list(filter(lambda sub: sub.chat_id == chat_id, self.get_active_subscriptions()))
        return bool(active_subscription)

    def get_active_subscription_for_chat(self, chat_id: int) -> Union['Subscription', None]:
        active_subscriptions = self.get_active_subscriptions()
        active_chat_subscription = filter_list(active_subscriptions, one=True, chat_id=chat_id)
        return active_chat_subscription


@dataclass
class Subscription(Model):
    chat_id: int
    end_date: Date
    payment_method: PaymentMethod
    invoice_number: str
    user_notified_for_renewal_count: int = 0
    is_active: bool = True
    chat_name: str = ''
    created_at: DateTime | None = None

    @classmethod
    def create(
        cls,
        chat_id: int,
        end_date: Date,
        payment_method: PaymentMethod,
        invoice_number: str,
        user_notified_for_renewal_count: int = 0,
        is_active: bool = True,
        chat_name: str = ''
    ):
        return cls(
            chat_id=chat_id,
            end_date=end_date,
            payment_method=payment_method,
            invoice_number=invoice_number,
            user_notified_for_renewal_count=user_notified_for_renewal_count,
            is_active=is_active,
            chat_name=chat_name,
            created_at=pendulum.now()
        )

    @property
    def days_left(self) -> int:
        now = pendulum.now().date()

        if now > self.end_date:
            return 0
        return (self.end_date - now).days

    def format(self, separator: str = ' | '):
        created_at = self.created_at.strftime('%d/%m/%Y')
        subscription_end_date = self.end_date.strftime('%d/%m/%Y')

        return (
            f'*Channel/Group*: {format_nullable_string(self.chat_name)}{separator}'
            f'*Payment method*: {format_nullable_string(self.payment_method.label)}\n'
            f'*Created at*: {format_nullable_string(created_at)}{separator}'
            f'*End date*: {format_nullable_string(subscription_end_date)}\n'
            f'*Invoice number*: {format_nullable_string(self.invoice_number)}{separator}'
            f'*Days left*: {format_nullable_string(self.days_left)}'
        )

    def deactivate(self):
        self.is_active = False

    @classmethod
    def from_json(cls, data: dict) -> 'Subscription':
        data['created_at'] = DateTime.fromtimestamp(data['created_at'])
        data['end_date'] = Date.fromisoformat(data['end_date'])
        data['payment_method'] = PaymentMethod(data['payment_method'])
        return cls(**data)

    @classmethod
    def to_json(cls, data: dict):
        data['created_at'] = data['created_at'].timestamp()
        data['end_date'] = data['end_date'].isoformat()
        data['payment_method'] = data['payment_method'].value

    def as_excel_row(self) -> list:
        return [
            self.chat_name,
            self.payment_method.label,
            self.invoice_number,
            self.created_at.strftime('%d/%m/%Y'),
            self.end_date.strftime('%d/%m/%Y')
        ]

    def renew(
        self,
        invoice_number: str,
        end_date: Date,
        payment_method: PaymentMethod
    ) -> 'Subscription':

        self.deactivate()

        subscription = Subscription.create(
            chat_id=self.chat_id,
            chat_name=self.chat_name,
            invoice_number=invoice_number,
            end_date=end_date,
            payment_method=payment_method
        )

        return subscription


@dataclass
class OfferMessage(Model):
    content: str
    interval: int  # per 2 weeks

    @property
    def sending_times(self) -> list[DateTime]:
        """
        Schedules the message to be sent per "interval" every 2 weeks.
        E.g. interval = 3, the message will be sent 3 times every 2 weeks as follows:

        1. First we get the daily_interval. 14 (2 weekdays) is divided by interval. daily_interval = 14 / 3 = 4.66.
        A message will be sent every 4.66 days.

        2. sending_period_half = daily_interval / 2 = 4.66 / 2 = 2.33. This will be the sending time.

        A message will be sent at the 2.33rd day in each interval, meaning:
            a. First time = (index * daily_interval) - sending_period_half = (1 * 4.66) - 2.33 = 2.33
            b. Second time = (4.66 * 2) - 2.33 = 6.99
            c. Third time = (3 * 4.66) - 2.33 = 11.65
        :return: a list of sending times.
        """

        daily_interval = Duration(days=14) / self.interval
        sending_period_half = daily_interval / 2

        period_start = self.objects.db.get_offer_message_start_time()
        sending_times: list[DateTime] = []

        for index in range(1, self.interval + 1):
            sending_time: DateTime = period_start + (index * daily_interval) - sending_period_half
            sending_time = sending_time.replace(minute=0)
            sending_times.append(sending_time)

        return sending_times

    def get_formatted_sending_times(self):
        message = ''
        now = pendulum.now()

        for index, sending_time in enumerate(self.sending_times, 1):
            status = 'passed' if now > sending_time else 'upcoming'
            formatted_time = sending_time.strftime('%A, %d/%m/%Y at %I:%M %p')
            message += f'{index}. {formatted_time} ({status})\n'

        return message


@dataclass
class Employee(Model, HumanEntityMixin):
    id: int
    username: str
    first_name: str
    last_name: str
    role: EmployeeRole

    def __eq__(self, other):
        return self.id == other.id

    @classmethod
    def from_json(cls, data: dict) -> 'Employee':
        data['role'] = EmployeeRole(data['role'])
        return cls(**data)

    @classmethod
    def to_json(cls, data: dict):
        data['role'] = data['role'].value


@dataclass
class SenderEntity(Model):
    api_id: int
    api_hash: str
    user_id: int
    phone_number: str
    is_active: bool = False

    def update(self, api_id: int, api_hash: str, phone_number: str, is_active: bool = False):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.is_active = is_active


@dataclass
class Group(Model):
    id: int
    title: str

    def __eq__(self, other):
        return self.id == other.id


@dataclass
class GroupFamily(Model):
    main_group: Group
    subgroups: list[Group]

    @property
    def subgroup_titles(self):
        return ', '.join([subgroup.title for subgroup in self.subgroups])

    # @classmethod
    # def get_by_main_group(cls, group_id) -> Union['GroupFamily', None]:
    #     from src.common.db import Database
    #     db: Database = cls.objects.db
    #
    #     for group_family in db.group_families:
    #         if group_family.main_group.id == group_id:
    #             return group_family

    @classmethod
    def from_json(cls, data: dict) -> 'GroupFamily':
        subgroups = []

        for subgroup_data in data.get('subgroups', []):
            subgroups.append(Group.from_json(data=subgroup_data))

        data['main_group'] = Group.from_json(data=data['main_group'])
        data['subgroups'] = subgroups
        return cls(**data)


@dataclass
class SubscriptionRequest(Model):
    table_name = 'subscription_requests'

    user_id: int
    chat_id: int
    end_date: Date
    payment_method: PaymentMethod
    invoice_number: str
    status: SubscriptionRequestStatus
    chat_name: str = ''
    created_at: DateTime | None = None
    reported: bool = False

    @property
    def is_approved(self):
        return self.status == SubscriptionRequestStatus.APPROVED

    @property
    def is_declined(self):
        return self.status == SubscriptionRequestStatus.DECLINED

    @property
    def is_resolved(self):
        return self.is_approved or self.is_declined

    @classmethod
    def create(
        cls,
        user_id: int,
        chat_id: int,
        end_date: Date,
        payment_method: PaymentMethod,
        invoice_number: str,
        chat_name: str = ''
    ):
        request = cls.objects.create(
            user_id=user_id,
            chat_id=chat_id,
            end_date=end_date,
            payment_method=payment_method,
            invoice_number=invoice_number,
            status=SubscriptionRequestStatus.PENDING,
            chat_name=chat_name,
            created_at=pendulum.now()
        )
        return request

    @classmethod
    def from_json(cls, data: dict) -> 'SubscriptionRequest':
        data['created_at'] = DateTime.fromtimestamp(data['created_at'])
        data['end_date'] = Date.fromisoformat(data['end_date'])
        data['payment_method'] = PaymentMethod(data['payment_method'])
        data['status'] = SubscriptionRequestStatus(data['status'])
        return cls(**data)

    @classmethod
    def to_json(cls, data: dict):
        data['created_at'] = data['created_at'].timestamp()
        data['end_date'] = data['end_date'].isoformat()
        data['payment_method'] = data['payment_method'].value
        data['status'] = data['status'].value

    def format(self, separator: str = ' | '):
        created_at = self.created_at.strftime('%d/%m/%Y')
        subscription_end_date = self.end_date.strftime('%d/%m/%Y')

        return (
            f'*Channel/Group*: {format_nullable_string(self.chat_name)}{separator}'
            f'*Payment method*: {format_nullable_string(self.payment_method.label)}\n'
            f'*Created at*: {format_nullable_string(created_at)}{separator}'
            f'*End date*: {format_nullable_string(subscription_end_date)}\n'
            f'*Invoice number*: {format_nullable_string(self.invoice_number)}{separator}'
        )

    def mark_as_reported(self):
        self.reported = True
        self.save()

    def mark_as_approved(self):
        self.status = SubscriptionRequestStatus.APPROVED
        self.save()

    def mark_as_declined(self):
        self.status = SubscriptionRequestStatus.DECLINED
        self.save()

    def mark_as_completed(self):
        self.status = SubscriptionRequestStatus.COMPLETED
        self.save()

    def create_subscription(self):
        user: User | None = User.objects.get(id=self.user_id)

        if user:
            user.add_subscription(Subscription.create(
                chat_id=self.chat_id,
                chat_name=self.chat_name,
                payment_method=self.payment_method,
                invoice_number=self.invoice_number,
                end_date=self.end_date
            ))
            self.save()

        else:
            raise UserNotFound
