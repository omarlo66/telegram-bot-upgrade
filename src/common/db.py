import json
import os
from dataclasses import dataclass, asdict

from pendulum import DateTime

from src.admin_bot import settings as admin_settings
from src.common import pendulum
from src.common.exceptions import EmployeeAlreadyExists
from src.common.models import User, OfferMessage, Employee, SenderEntity, GroupFamily, SubscriptionRequest
from src.common.utils import get_path


# noinspection PyMethodMayBeStatic
@dataclass
class Database:
    LOCATION = get_path('data/db.json')
    welcome_message: str = ''
    salla_link: str = ''
    offer_message_start_time: DateTime | None = None

    models = {
        'users': User,
        'offer_messages': OfferMessage,
        'employees': Employee,
        'sender_entities': SenderEntity,
        'group_families': GroupFamily,
        'subscription_requests': SubscriptionRequest
    }

    def start(self):
        self._ensure_data_folder_exists()
        self.load()

    async def add_employee(self, employee: Employee) -> bool:
        existing_employee: Employee = await Employee.objects.filter(
            telegram_id=employee.telegram_id
        ).afirst()

        created: bool = False

        if existing_employee:
            if existing_employee.role == employee.role:
                raise EmployeeAlreadyExists

            else:
                existing_employee.telegram_username = employee.telegram_username
                existing_employee.first_name = employee.first_name
                existing_employee.last_name = employee.last_name or ''
                existing_employee.role = employee.role
                await existing_employee.asave()

        else:
            await employee.asave()
            created = True
        return created

    def _ensure_data_folder_exists(self):
        os.makedirs(get_path('data'), exist_ok=True)

    def load(self, migrate_to_sql=False):
        if os.path.isfile(self.LOCATION):
            with open(self.LOCATION) as f:
                data = json.load(f)
                self._from_json(data, migrate_to_sql=migrate_to_sql)

    def save(self):
        data = asdict(self)
        self._to_json(data)
        json.dumps(data)

        with open(self.LOCATION, 'w') as f:
            json.dump(data, f, indent=4)

    def _from_json(self, data: dict, migrate_to_sql=False):
        offer_message_start_time: DateTime | None = data.get('offer_message_start_time')

        if offer_message_start_time:
            data['offer_message_start_time'] = pendulum.from_timestamp(offer_message_start_time)

        if migrate_to_sql:
            for table_name, model in self.models.items():
                json_items = data.get(table_name, [])
                json_item_count = len(json_items)
                model_instance_created_count = 0

                for row_data in json_items:
                    instance, created = model.from_json(data=row_data)
                    model_instance_created_count += created

                model_instance_count = model.objects.count()

                print(
                    f'Migrated "{model.__name__}" model.',
                    f"Json rows: {json_item_count}. SQL rows: {model_instance_count}.",
                    f'Created: {model_instance_created_count}',
                    flush=True
                )

        for dataclass_field in Database.__dataclass_fields__.values():
            if dataclass_field.name not in self.models:
                setattr(self, dataclass_field.name, data.get(dataclass_field.name, dataclass_field.default))

    def _to_json(self, data: dict):
        offer_message_start_time: DateTime | None = data.get('offer_message_start_time')

        if offer_message_start_time:
            data['offer_message_start_time'] = offer_message_start_time.timestamp()

        # for table_name, model in self.models.items():
        #     object_list: list = data[table_name]
        #
        #     for row_data in object_list:
        #         model.to_json(data=row_data)

    def get_active_sender(self) -> SenderEntity | None:
        try:
            return SenderEntity.objects.get(is_active=True)

        except SenderEntity.DoesNotExist:
            ...

    def get_offer_message_start_time(self) -> DateTime:
        now = pendulum.now()

        def reset_offer_message_start_time():
            self.offer_message_start_time = now.start_of('week')
            self.save()

        if self.offer_message_start_time:
            if now > self.offer_message_start_time + admin_settings.OFFER_MESSAGES_INTERVAL:
                reset_offer_message_start_time()

        else:
            reset_offer_message_start_time()

        return self.offer_message_start_time
