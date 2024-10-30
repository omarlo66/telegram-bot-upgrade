from src.common.settings import *  # noqa

from datetime import timedelta

OFFER_MESSAGES_INTERVAL = timedelta(days=14)


try:
    from .local_settings import *

except ImportError:
    ...
