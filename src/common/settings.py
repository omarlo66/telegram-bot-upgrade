BOT_OWNERS = [
    {
        'id': 451990780,
        'name': 'Mr. Yousef'
    }
]

PROJECT_ROOT = '/home/ociecharts1000/OcieChartBot'

GROUPS = [
    {
        'id': -1002177990335,
        'title': 'مؤشرات أوسي',
        'subgroups': [
            {
                'id': -1002178518740,
                'title': 'مجانين سباكس لايف الساعه الثالثه عصر'
            },
            {
                'id': -1002101211795,
                'title': 'مجانين سباكس ocie📉'
            }
        ]
    }
]

SUPPORT_CHAT_ID = -4545167654
DEVELOPER_CHAT_ID = 2054027110

try:
    from .local_settings import *

except ImportError:
    ...
