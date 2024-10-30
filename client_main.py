import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OciechartBotDjango.settings')
django.setup()

import logging

from src.client_bot.bot_manager import BotManager
from src.common.utils import get_credentials

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


if __name__ == '__main__':
    credentials = get_credentials('client')

    bot_manager = BotManager(
        token=credentials['bot_token']
    )
    
    bot_manager.run()
