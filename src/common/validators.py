from types import SimpleNamespace

import pendulum
from pendulum import Date


class ErrorMessages(SimpleNamespace):
    INVALID_INT = 'Invalid number. Please enter a numeric value.'
    INVALID_DATE = 'Invalid date. Please enter a correct date.'


def get_int(string: str) -> tuple[int | None, bool]:
    try:
        return int(string), True

    except ValueError:
        return None, False


def get_date(string: str) -> tuple[Date | None, bool]:
    try:
        return pendulum.from_format(string, 'DD/MM/YYYY').date(), True

    except ValueError:
        return None, False
