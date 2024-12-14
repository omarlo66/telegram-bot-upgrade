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
        # Parse the date string
        parsed_date = pendulum.from_format(string, 'DD/MM/YYYY').date()

        # Check if the date is in the future
        is_future = parsed_date > pendulum.now().date()

        return parsed_date, is_future

    except ValueError:
        # Return None and False if parsing fails
        return None, False