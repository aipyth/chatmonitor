from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django_telegrambot.apps import DjangoTelegramBot
from .models import Chat, Keyword, NegativeKeyword, User

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chatmonitor.settings')
#
# broker = os.environ.get('REDIS_URL', 'redis://')
#
# app = Celery('tasks', broker=broker)
# app.conf.update(
#     task_serializer='json',
#     accept_content=['json'],  # Ignore other content
#     result_serializer='json',
#     enable_utc=True,
# )
import logging
logger = logging.getLogger(__name__)

bot = DjangoTelegramBot.get_bot()

@shared_task
def check_message_for_keywords(chat_id, message_id, text):

    chat = Chat.objects.get(chat_id=chat_id)

    # Define a list where keywords that occur in message will be stored
    keywords = []
    # Try to find them, man!
    # logger.debug("message - {}".format(update.message.text))
    for keyword in chat.keywords.all():
        state = True
        if not keyword.key: continue
        # logger.debug("key {} - {}".format(keyword.key.lower(), keyword.key.lower() in update.message.text.lower()))
        if keyword.key.lower() in text.lower():
            # Also don't forget about negative keywords
            for nkey in keyword.negativekeyword.all():
                if nkey.key in text:
                    state = False
            if state:
                relation = keyword.user.relation_set.filter(chat=chat)[0]
                if relation.active:
                    keywords.append(keyword)

    # If theres no keywords - skip
    if not keywords:
        logger.info("Skipped message {}:{}:[{}]".format(message_id, text, keywords))
        return

    # Just logging stuff
    keys = ', '.join([kw.key for kw in keywords])
    logger.info("Found keywords ({}) in {}:{}".format(keys, message_id, text.replace('\n', ' ')))

    # Resending messages to users
    users = list(set([kw.user for kw in keywords]))
    for user in users:
        logger.info("Sending message {} to {}".format(message_id, user.chat_id))
        # update.message.forward(user.chat_id)
        bot.forwardMessage(user.chat_id, chat_id, message_id)
