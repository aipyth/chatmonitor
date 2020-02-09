import re
import datetime
import json
import hashlib
import base64
from threading import Thread

from django.core.cache import cache
from .models import User, Chat, Keyword, NegativeKeyword

import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)



def check_for_uniqueness(user:str, time:int, message:str):
    """Return True if there was such message from the user
    for 30 sec ago, otherwise -- return False"""
    # from datetime import datetime
    # from bot.utils import check_for_uniqueness
    # check_for_uniqueness('username', int(datetime.timestamp(datetime.now())), '12345')
    DELTA_SECONDS = 30
    # keys is a list of all keywords in cache
    keys_str = cache.get("keys")
    # check if keys if in cache
    if not keys_str:
        # if not - create it
        keys_str = json.dumps([])
        cache.set("keys", keys_str)
    # make a list of the string
    keys = json.loads(keys_str)
    # get short hash
    hashing_msg = (user + ' ' + message).encode("utf-8")
    # print(type(hashing_msg))
    hash = hashlib.sha1(hashing_msg)
    hash_str = base64.b64encode(hash.digest()).decode("utf-8")
    if hash_str in keys:
        record = cache.get(hash_str)
        # get username, time and text from record
        record_re = re.match("(\S+) ([0-9]+) (.+)", record)
        record_user = record_re.group(1)
        record_time = int(record_re.group(2))
        record_text = record_re.group(3)
        # if the message was sent longer, than DELTA_SECONDS --
        # delete it and accept the new message as unique
        # otherwise -- recheck the message
        time_delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(record_time)
        if time_delta.total_seconds() < DELTA_SECONDS:
            # additional check
            if user == record_user and message == record_text:
                record = user + ' ' + str(time) + ' ' + message
                cache.set(hash_str, record)
                return False
        else:
            # also update keys list
            record = user + ' ' + str(time) + ' ' + message
            cache.set(hash_str, record)
    else:
        # there was no such message before
        record = user + ' ' + str(time) + ' ' + message
        cache.set(hash_str, record)
        keys.append(hash_str)
        cache.set("keys", json.dumps(keys))
    return True


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
