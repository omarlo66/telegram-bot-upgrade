import pendulum
from django.conf import settings


def now():
    return pendulum.now(tz=settings.TIME_ZONE)


def from_timestamp(timestamp):
    return pendulum.from_timestamp(timestamp, tz=settings.TIME_ZONE)


def from_format(string: str, fmt: str):
    return pendulum.from_format(string, fmt, tz=settings.TIME_ZONE)
