import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OciechartBotDjango.settings')
django.setup()

import logging

from src.admin_bot.bot_manager import BotManager
from src.common.models import Employee, User
from src.common.utils import get_credentials




logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


if __name__ == '__main__':
    credentials = get_credentials('admin')
    
    bot_manager = BotManager(
        token=credentials
    )
    bot_manager.run()