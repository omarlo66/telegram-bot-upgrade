import enum


class BotStep:
    IDLE = 0

    # /start
    NEW_USER_CHAT = 1
    NEW_USER = 2
    NEW_USER_PAYMENT_METHOD = 3
    NEW_USER_INVOICE_NUMBER = 4
    NEW_USER_SUBSCRIPTION_END_DATE = 5

    # /salla_link
    SALLA_LINK = 6

    # /welcome
    WELCOME_MESSAGE = 7

    # /info
    INFO_CHAT = 8

    # /renew
    RENEW_USER_ID = 10
    RENEW_SUBSCRIPTION = 11
    RENEW_END_DATE = 12
    RENEW_PAYMENT_METHOD = 13
    RENEW_INVOICE_NUMBER = 14

    # /offer_message
    OFFER_MESSAGE_CONTENT = 20
    OFFER_MESSAGE_INTERVAL = 21

    # /employee
    SELECT_EMPLOYEE = 30
    EMPLOYEE_ROLE = 31

    # / login
    API_ID = 40
    API_HASH = 41
    TWO_FACTOR_AUTH_PASSWORD = 42

    # /group_family
    GROUP_FAMILY_MAIN_GROUP = 50
    GROUP_FAMILY_SUBGROUPS = 51

    # /cleanup_group
    SELECT_CLEANUP_GROUP = 60
    CONFIRM_CLEANUP_GROUP = 61

    # Client bot events
    APPROVED_SUBSCRIPTION_END_DATE = 70

    # /edit
    EDIT_USER_ID = 80
    EDIT_SUBSCRIPTION = 81
    EDIT_END_DATE = 82
    EDIT_PAYMENT_METHOD = 83
    EDIT_INVOICE_NUMBER = 84
    EDIT_TRADINGVIEW_ID = 85
    EDIT_SUBSCRIPTION_FIELDS = 86


class InlineButtonCallbackType(enum.Enum):
    # SubscriptionRequest
    SUBSCRIPTION_REQUEST_APPROVED = 1
    SUBSCRIPTION_REQUEST_DECLINED = 2

    # Support
    SUPPORT_RESPONSE = 3
    CONFIRM_SUPPORT_RESPONSE = 4
