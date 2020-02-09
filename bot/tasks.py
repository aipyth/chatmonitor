from __future__ import absolute_import, unicode_literals

import logging
import os

from celery import shared_task

from django.core.cache import cache
from .models import Chat, Keyword, NegativeKeyword
from . import utils


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')

import requests

def forward_message(chat_id, from_chat_id, message_id):
    METHOD = 'forwardMessage'
    url = "https://api.telegram.org/bot{}/{}".format(TOKEN, METHOD)
    body = {
        'chat_id': chat_id,
        'from_chat_id': from_chat_id,
        'message_id': message_id,
    }

    requests.post(url, json=body)


@shared_task
def check_message_for_keywords(chat_id, message_id, text, user_id, time):
    logger.debug("Processing message \"{}\" from {}".format(text, chat_id))
    chat = Chat.objects.get(chat_id=chat_id)

    # Define a list where keywords that occur in message will be stored
    keywords = []
    # Try to find them, man!
    # logger.debug("message - {}".format(update.message.text))
    for keyword in chat.keywords.filter(state=True):
        state = True
        if not keyword.key: continue
        # logger.debug("key {} - {}".format(keyword.key.lower(), keyword.key.lower() in text.lower()))
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
        return False

    # Just logging stuff
    keys = ', '.join([kw.key for kw in keywords])
    logger.info("Found keywords ({}) in {}:{}".format(keys, message_id, text.replace('\n', ' ')))

    if not utils.check_for_uniqueness(user_id, time, text):
        logger.info("Skipped message {} due repeating".format(message_id))
        return False

    # Resending messages to users
    users = list(set([kw.user for kw in keywords]))
    for user in users:
        logger.info("Sending message {} to {}".format(message_id, user.chat_id))
        # update.message.forward(user.chat_id)
        # bot.forwardMessage(user.chat_id, chat_id, message_id)
        forward_message(user.chat_id, chat_id, message_id)
    return True


@shared_task
def flush_cache():
    logger.info("Flushing Cache...")
    cache.clear()
