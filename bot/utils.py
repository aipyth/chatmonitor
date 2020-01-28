from threading import Thread

from .models import User, Chat, Keyword, NegativeKeyword

import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def threaded(func):
    def wrapper(*args, **kwargs):
        thread = Thread(target=func, args=args, kwargs=kwargs)
        thread.start()
    return wrapper


@threaded
def pin_all_to_chat(user, chat):
    logger.debug("(pin_all_to_chat) started")
    for kw in user.keywords.all():
        chat.keywords.add(kw)
    logger.debug("(pin_all_to_chat) finished")


@threaded
def unpin_all_from_chat(user, chat):
    logger.debug("(unpin_all_from_chat) started")
    for kw in chat.keywords.filter(user=user):
        chat.keywords.remove(kw)
    logger.debug("(unpin_all_from_chat) finished")


@threaded
def pin_all_negative_to_all(user):
    logger.debug("(pin_all_negative_to_all) started")
    for key in user.keywords.all():
        for kw in user.negativekeyword.all():
            key.negativekeyword.add(kw)
    logger.debug("(pin_all_negative_to_all) finished")


@threaded
def pin_all_negative_to_one(user, key):
    logger.debug("(pin_all_negative_to_one) started")
    for kw in user.negativekeyword.all():
        key.negativekeyword.add(kw)
    logger.debug("(pin_all_negative_to_one) finished")


@threaded
def pin_one_negative_to_all(user, nkw):
    logger.debug("(pin_one_negative_to_all) started")
    for key in user.keywords.all():
        key.negativekeyword.add(nkw)
    logger.debug("(pin_one_negative_to_all) finished")


@threaded
def unpin_all_negative_from_one(user, key):
    logger.debug("(unpin_all_negative_from_one) started")
    for kw in key.negativekeyword.filter(user=user):
        key.negativekeyword.remove(kw)
    logger.debug("(unpin_all_negative_from_one) finished")


@threaded
def switch_group_on(group):
    logger.debug("(switch_group_on) started")
    for key in group.keys.all():
        key.state = True
        key.save()
    logger.debug("(switch_group_on) finished")


@threaded
def switch_group_off(group):
    logger.debug("(switch_group_off) started")
    for key in group.keys.all():
        key.state = False
        key.save()
    logger.debug("(switch_group_off) finished")