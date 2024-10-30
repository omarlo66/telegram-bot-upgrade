from django.db import models
from pendulum import DateTime, Duration

from src.common import pendulum


class OfferMessage(models.Model):
    content = models.TextField()
    interval = models.PositiveSmallIntegerField()

    def get_sending_times(self, db) -> list[DateTime]:
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

        period_start = db.get_offer_message_start_time()
        sending_times: list[DateTime] = []

        for index in range(1, self.interval + 1):
            sending_time = period_start + (index * daily_interval) - sending_period_half
            sending_time = sending_time.replace(minute=0)
            sending_times.append(sending_time)
        return sending_times

    def get_formatted_sending_times(self, db) -> str:
        message = ''
        now = pendulum.now()

        for index, sending_time in enumerate(self.get_sending_times(db), 1):
            status = 'passed' if now > sending_time else 'upcoming'
            formatted_time = sending_time.strftime('%A, %d/%m/%Y at %I:%M %p')
            message += f'{index}. {formatted_time} ({status})\n'

        return message

    @classmethod
    def from_json(cls, data: dict) -> tuple['OfferMessage', bool]:
        return cls.objects.get_or_create(**data)
