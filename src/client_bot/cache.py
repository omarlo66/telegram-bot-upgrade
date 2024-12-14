from types import SimpleNamespace

from pendulum import Date

from src.client_bot.enums import BotStep
from src.client_bot.interfaces import SupportResponse
from src.common.choices import PaymentMethod

from src.common.models import Feedback

class Cache(SimpleNamespace):
    chat_id: int | None = None
    payment_method: PaymentMethod | None = None
    invoice_number: str | None = None
    subscription_end_date: Date | None
    current_step: BotStep | None = None
    tradingview_id: str | None = None

    renew_subscription_id: int | None = None
    renew_payment_method: PaymentMethod | None = None

    support_response: SupportResponse | None = None

    training_date: Date | None = None
    training_time: str | None = None

    free_trial: bool | None = False

    feedback: Feedback | None = None

    def clear(self):
        self.free_trial = False
        self.feedback = None
