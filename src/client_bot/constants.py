from types import SimpleNamespace


class Messages(SimpleNamespace):
    SUBSCRIPTION_REQUEST_SENT: str = (
        'تم ارسال الطلب بنجاح\n'
        'سيتم مراجعة الطلب من قبل فريق الدعم والرد عليك خلال ٢٤ ساعة.'
    )

    ENTER_SUBSCRIPTION_METHOD = 'يرجى اختيار وسيلة الدفع:'
    INVALID_PAYMENT_METHOD = 'وسيلة الدفع غير صالحة. يرجى المحاولة مرة أخرى'
    ENTER_INVOICE_NUMBER = 'يرجى ادخال رقم الفاتورة:'
    ENTER_TRADINGVIEW_ID = 'يرجى ادخال معرف تريدنج فيو الخاص بك:'

    CONTACT_SUPPORT = 'يرجى ادخال رسالتك:'
    CONTACT_SUPPORT_SENT = 'تم ارسال الرسالة بنجاح\nسيتم الرد عليك خلال ٢٤ ساعة.'
