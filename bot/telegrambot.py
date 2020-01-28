import json
import logging
import os
import random
import re
import uuid
from collections import namedtuple

from django.core.paginator import Paginator

import telegram
from django_telegrambot.apps import DjangoTelegramBot
from telegram.ext import (CallbackQueryHandler, CommandHandler,
                          ConversationHandler, Filters, InlineQueryHandler,
                          MessageHandler, RegexHandler)

from . import tasks, utils
from .bot_filters import GroupFilters
from .models import Chat, Keyword, NegativeKeyword, User, KeywordsGroup

# Config logging
debug = os.environ.get('DEBUG', 0)
level = logging.DEBUG if debug else logging.INFO
logging.basicConfig(level=level)
logger = logging.getLogger(__name__)

# Open text responses and other static stuff
with open('bot/text.json', encoding='utf8') as file:
    text_object = lambda d: namedtuple('text_object', d.keys())(*d.values())
    text = json.load(file, object_hook=text_object)



# Keyboards

menu_keyboard = telegram.InlineKeyboardMarkup([
        # Keywords
        [telegram.InlineKeyboardButton(text=text.buttons.menu.add_key, callback_data=text.buttons.menu.add_key)],

        [telegram.InlineKeyboardButton(text=text.buttons.menu.pin_key_to_chat, switch_inline_query_current_chat=text.buttons.menu.pin_key_to_chat[:-2])],

        [telegram.InlineKeyboardButton(text=text.buttons.menu.unpin_key_from_chat, switch_inline_query_current_chat=text.buttons.menu.unpin_key_from_chat[:-2])],

        [telegram.InlineKeyboardButton(text=text.buttons.menu.delete_key, switch_inline_query_current_chat=text.buttons.menu.delete_key[:-2])],

        # Negative Keywords
        [telegram.InlineKeyboardButton(text=text.buttons.menu.add_neg_key, callback_data=text.buttons.menu.add_neg_key)],

        [telegram.InlineKeyboardButton(text=text.buttons.menu.pin_neg_key, switch_inline_query_current_chat=text.buttons.menu.pin_neg_key[:-2])],

        [telegram.InlineKeyboardButton(text=text.buttons.menu.unpin_neg_key, switch_inline_query_current_chat=text.buttons.menu.unpin_neg_key[:-2])],

        [telegram.InlineKeyboardButton(text=text.buttons.menu.delete_neg_key, switch_inline_query_current_chat=text.buttons.menu.delete_neg_key[:-2])],

        # Keywords' Groups
        [telegram.InlineKeyboardButton(text=text.buttons.menu.create_group, callback_data=text.buttons.menu.create_group)],

        [telegram.InlineKeyboardButton(text=text.buttons.menu.add_key_to_group, switch_inline_query_current_chat=text.buttons.menu.add_key_to_group)],

        # Chat switcher
        [telegram.InlineKeyboardButton(text=text.buttons.menu.chat_monitor, callback_data=text.buttons.menu.chat_monitor)],
    ])



def start(bot, update):
    "Start conversation with bot"
    user = User.objects.get_or_none(chat_id=update.message.chat.id)
    if not user:
        username = update.message.from_user.username if update.message.from_user.username else ''
        user = User(chat_id=update.message.chat.id, name=update.message.from_user.full_name, username=username)
        user.save()
        logger.debug("New user created: `{}`".format(user))
    else:
        logger.debug("User `{}` already exist.".format(user))

    # Looking for common chats with the user
    for chat in Chat.objects.all():
        try:
            in_chat = bot.getChatMember(chat.chat_id, user.chat_id)
            if in_chat.status not in ('left', 'kicked'):
                logger.debug("{} in {}. Relating them.".format(user, chat))
                chat.user.add(user)
            else:
                logger.debug("{} not in {}. Skipping.".format(user, chat))
        except telegram.TelegramError:
            logger.debug("{} not in {}. Skipping.".format(user, chat))

    bot.sendMessage(update.message.chat_id, text=text.content.greeting, parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=menu_keyboard)


def menu(bot, update):
    "Show up the menu"
    bot.sendMessage(update.message.chat.id, text=text.content.menu, reply_markup=menu_keyboard)


def default_fallback(bot, update):
    "When no message passes"
    bot.sendMessage(update.effective_message.chat.id, text=text.context.dont_understand)



# Handle adding bot to chats

def chat_created(bot, update):
    "Handling chat creation with bot in it"
    # Bot shouldn't be in any of chats below
    if update.message.chat.type in ('private', 'channel'):
        return

    # Defining chat type
    for literal, ltype in Chat.CHATS:
        if update.message.chat.type == ltype:
            chat_type = literal

    chat = Chat(chat_id=update.message.chat.id, chat_type=chat_type, title=update.message.chat.title)
    chat.save()

    # Looking for users with common chat
    for user in User.objects.all():
        try:
            if bot.getChatMember(chat.chat_id, user.chat_id):
                logger.debug("{} in {}. Relating them...".format(user, chat))
                chat.user.add(user)
        except telegram.TelegramError:
            logger.debug("{} not in {}. Skipping...".format(user, chat))


def new_chat_members(bot, update):
    "Handling new chat members"
    # Bot shouldn't be in any of chats below
    if update.message.chat.type in ('private', 'channel'):
        return

    chat = Chat.objects.get_or_none(chat_id=update.message.chat.id)

    for member in update.message.new_chat_members:
        # If the bot is added to the chat, then...
        if member.username == bot.username:
            if chat:
                chat.bot_in_chat = True

            else:
                # Defining chat type
                for literal, ltype in Chat.CHATS:
                    if update.message.chat.type == ltype:
                        chat_type = literal

                chat = Chat(chat_id=update.message.chat.id, chat_type=chat_type, title=update.message.chat.title)

            chat.save()

            # Looking for users with common chat
            for user in User.objects.all():
                try:
                    in_chat = bot.getChatMember(chat.chat_id, user.chat_id)
                    if in_chat.status not in ('left', 'kicked'):
                        logger.debug("{} in {}. Relating them.".format(user, chat))
                        chat.user.add(user)
                    else:
                        logger.debug("{} not in {}. Skipping.".format(user, chat))
                except telegram.TelegramError:
                    logger.debug("{} not in {}. Skipping.".format(user, chat))
        else:
            # If the user is in db, add chat to his chats in bot's db
            user = User.objects.get_or_none(chat_id=member.id)
            if user:
                logger.debug("{} in {}. Relating them.".format(user, chat))
                chat.user.add(user)


def left_chat_member(bot, update):
    "Handling user_left"
    # We do not monitor these chats
    if update.message.chat.type in ('private', 'channel'):
        return

    chat = Chat.objects.get(chat_id=update.message.chat.id)
    # If bot was kicked or whatever!
    if update.message.left_chat_member.username == bot.username:

        chat.bot_in_chat = False
        chat.save()
    # If any other user was kicked delete this chat from his list
    else:
        user = User.objects.get_or_none(chat_id=update.message.left_chat_member.id)
        if user:
            user.chats.remove(chat)




# ACTIONS

# Add key

def ask_new_key(bot, update):
    bot.sendMessage(update.effective_message.chat.id, text=random.choice(text.actions.add_key.ask_new_key))
    return PROCESS_KEY


def add_key(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    # Store unique-in-user-scope keys
    keys = set(update.message.text.split('\n'))
    for k in keys:
        if not Keyword.objects.filter(key=k, user=user) and k:
            key = Keyword(key=k, user=user)
            key.save()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.menu.pin_key_to_chat, switch_inline_query_current_chat=text.buttons.menu.pin_key_to_chat[:-2])],
    ])
    bot.sendMessage(user.chat_id, text=text.actions.add_key.success, reply_markup=keyboard)
    return -1




# Add negative key

def ask_negative_key(bot, update):
    bot.sendMessage(update.effective_message.chat.id, text=random.choice(text.actions.add_neg_key.ask_new_key) + '\n\n' + text.actions.add_neg_key.warn)
    return PROCESS_NEG_KEY


def add_negative_key(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    # Store unique-in-user-scope keys
    keys = set(update.message.text.split('\n'))
    for k in keys:
        if not NegativeKeyword.objects.filter(key=k, user=user) and k:
            nkey = NegativeKeyword(key=k, user=user)
            nkey.save()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.menu.pin_neg_key, switch_inline_query_current_chat=text.buttons.menu.pin_neg_key[:-2])],
    ])
    bot.sendMessage(user.chat_id, text=text.actions.add_neg_key.success, reply_markup=keyboard)
    return -1




# Pin key

def get_keys_for_pinning(bot, update):
    "Shows all user's keys answering to inline query"
    logger.debug("Processing in function get_keys_for_pinning")
    user = User.objects.get(chat_id=update.effective_user.id)

    # Due to the restriction of number of objects we can send in response we need to paginate the data
    objects = user.keywords.all()
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    keywords = paginator.page(int(offset))
    next_offset = str(keywords.next_page_number()) if keywords.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title='Все ключи',
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.pin_key.choose_pin_key.format(text.actions.pin_key.all_keys)))
        ] + [
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=keyword.key,
                description=keyword.prepare_description(),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.pin_key.choose_pin_key.format(keyword.key))
            ) for keyword in keywords
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )
    logger.debug("Processing finished in function get_keys_for_pinning")


def get_chat_list_button_for_pinning_key(bot, update):
    "Shows a message with button to switch inline query with available chats on"
    user = User.objects.get(chat_id=update.effective_user.id)

    key = re.match(text.re.choose_pin_key, update.message.text).group(1)

    update.message.delete()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.pin_key_to_chat.pin_to_chat, switch_inline_query_current_chat=text.buttons.pin_key_to_chat.choose_chat_to_pin_pattern.format(key))]
    ])
    bot.sendMessage(user.chat_id, text=text.actions.pin_key.choose_chat, reply_markup=keyboard)


def get_chat_list_for_pinning_key(bot, update):
    "Shows all user's chats answering to inline query"
    user = User.objects.get(chat_id=update.effective_user.id)

    key = re.match(text.re.choose_chat_to_pin, update.inline_query.query).group(1)

    # Due to the restriction of number of objects we can send in response we need to paginate the data
    objects = user.chats.filter(bot_in_chat=True)
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    chats = paginator.page(int(offset))
    next_offset = str(chats.next_page_number()) if chats.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=chat.title,
                description=chat.get_keys(user),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.pin_key.pin_key_to_chat.format(chat=chat.id, key=key))
            ) for chat in chats
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def pin_key_to_chat(bot, update):
    "Pin key to chat, nothing more.."
    user = User.objects.get(chat_id=update.effective_user.id)

    match = re.match(text.re.pin_key_to_chat, update.message.text)
    chat_id = match.group(1)
    key = match.group(2)

    chat = Chat.objects.get(id=chat_id)
    if key == text.actions.pin_key.all_keys:
        utils.pin_all_to_chat(user, chat)
        # for kw in user.keywords.all():
        #     chat.keywords.add(kw)
    else:
        try:
            kw = user.keywords.filter(key=key)[0]
        except IndexError:
            logger.debug("Cannot pin key {} to chat {}. This key does not exist.".format(key, chat))
            return
        chat.keywords.add(kw)

    bot.sendMessage(user.chat_id, text=random.choice(text.actions.pin_key.success))




# Unpin key

def get_chat_list_for_unpinning_key(bot, update):
    "Show user's chats list answering to inline query"
    user = User.objects.get(chat_id=update.effective_user.id)

    objects = user.chats.filter(bot_in_chat=True)
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    chats = paginator.page(int(offset))
    next_offset = str(chats.next_page_number()) if chats.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=chat.title,
                description=chat.get_keys(user),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.unpin_key.select_chat.format(chat.id))
            ) for chat in chats
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def get_key_list_button_for_unpinning_key(bot, update):
    "Show message with button that switches inline mode on to show all keys for specified chat"
    user = User.objects.get(chat_id=update.effective_user.id)

    chat = re.match(text.re.unpin_key_select_chat, update.message.text).group(1)

    update.message.delete()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.unpin_key_from_chat.unpin_from_chat, switch_inline_query_current_chat=text.buttons.unpin_key_from_chat.choose_key_pattern.format(chat=chat))]
    ])
    bot.sendMessage(user.chat_id, text=text.actions.unpin_key.choose_key, reply_markup=keyboard)


def get_key_list_for_pinning_key(bot, update):
    "Show all keys for specified chat in inline mode"
    user = User.objects.get(chat_id=update.effective_user.id)

    chat_id = re.match(text.re.unpin_key_choose_key, update.inline_query.query).group(1)
    chat = Chat.objects.get(id=chat_id)

    objects = chat.keywords.filter(user=user)
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    keywords = paginator.page(int(offset))
    next_offset = str(keywords.next_page_number()) if keywords.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title='Все ключи',
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.unpin_key.unpin.format(chat=chat.id, key=text.actions.unpin_key.all_keys)))
        ] + [
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=kw.key,
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.unpin_key.unpin.format(chat=chat.id, key=kw.key))
            ) for kw in keywords
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def unpin_key_from_chat(bot, update):
    "Just unpin key from chat"
    user = User.objects.get(chat_id=update.effective_user.id)

    match = re.match(text.re.unpin_key_from_chat, update.message.text)
    chat_id = match.group(1)
    key = match.group(2)
    chat = Chat.objects.get(id=chat_id)
    if key == text.actions.unpin_key.all_keys:
        utils.unpin_all_from_chat(user, chat)
        # for kw in chat.keywords.filter(user=user):
        #     chat.keywords.remove(kw)
    else:
        try:
            kw = chat.keywords.filter(key=key, user=user)[0]
        except IndexError:
            logger.debug("Cannot unpin key {} from chat {}. This key does not exist.".format(key, chat))
            return
        chat.keywords.remove(kw)

    bot.sendMessage(user.chat_id, text=random.choice(text.actions.unpin_key.success))




# Delete Keywords

def get_keys_list_for_deletion(bot, update):
    "Shows all keys list in inline mode"
    user = User.objects.get(chat_id=update.effective_user.id)

    objects = user.keywords.all()
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    keywords = paginator.page(int(offset))
    next_offset = str(keywords.next_page_number()) if keywords.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=kw.key,
                description=kw.prepare_description(),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.key_deletion.delete.format(key=kw.key))
            ) for kw in keywords
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def delete_key(bot, update):
    "Key deletion"
    user = User.objects.get(chat_id=update.effective_user.id)

    key = re.match(text.re.delete_key, update.message.text).group(1)
    try:
        key = user.keywords.filter(key=key)[0]
    except IndexError:
        logger.debug("No match for {}. Deletion declined.".format(key))
        return

    key.delete()

    bot.sendMessage(user.chat_id, text=random.choice(text.actions.key_deletion.success))




# Pin negative key

def get_negative_keys_list_for_pinning(bot, update):
    "Show a list of negative keywords in inline mode"
    user = User.objects.get(chat_id=update.effective_user.id)

    objects = user.negativekeyword.all()
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    keywords = paginator.page(int(offset))
    next_offset = str(keywords.next_page_number()) if keywords.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title='Все ключи',
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.pin_neg_key.choose_pin_key.format(text.actions.pin_neg_key.all_keys)))
        ] + [
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=keyword.key,
                description=keyword.prepare_description(),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.pin_neg_key.choose_pin_key.format(keyword.key))
            ) for keyword in keywords
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def get_key_list_button_for_pinning_negative_key(bot, update):
    "Shows a message with button to switch to show keys list"
    user = User.objects.get(chat_id=update.effective_user.id)

    key = re.match(text.re.choose_pin_neg_key, update.message.text).group(1)

    update.message.delete()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.pin_neg_key.pin, switch_inline_query_current_chat=text.buttons.pin_neg_key.choose_key_to_pin_pattern.format(key))]
    ])
    bot.sendMessage(user.chat_id, text=text.actions.pin_neg_key.choose_key, reply_markup=keyboard)


def get_keys_list_for_pinning_negative_key(bot, update):
    "Shows a list of keys in inline mode"
    user = User.objects.get(chat_id=update.effective_user.id)

    keyword = re.match(text.re.choose_key_to_pin, update.inline_query.query).group(1)

    objects = user.keywords.all()
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    keywords = paginator.page(int(offset))
    next_offset = str(keywords.next_page_number()) if keywords.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title='Все ключи',
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.pin_neg_key.pin_key_to_key.format(key=0, nkey=keyword))
            )
        ] + [
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=key.key,
                description=key.prepare_description(),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.pin_neg_key.pin_key_to_key.format(key=key.id, nkey=keyword))
            ) for key in keywords
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def pin_negative_key_to_key(bot, update):
    "Pin negative key to key, that's all!"
    user = User.objects.get(chat_id=update.effective_user.id)

    match = re.match(text.re.pin_key_to_key, update.message.text)
    key_id = match.group(1)
    nkey = match.group(2)


    if nkey == text.actions.pin_neg_key.all_keys:
        if int(key_id) == 0:
            utils.pin_all_negative_to_all(user)
            # for key in user.keywords.all():
            #     for kw in user.negativekeyword.all():
            #         key.negativekeyword.add(kw)
        else:
            key = Keyword.objects.get(id=key_id)
            utils.pin_all_negative_to_one(user, key)
            # for kw in user.negativekeyword.all():
            #     key.negativekeyword.add(kw)
    else:
        try:
            kw = user.negativekeyword.filter(key=nkey)[0]
        except IndexError:
            logger.debug("No objects for negative key {}. Pinning declined.".format(nkey))
            return
        if int(key_id) == 0:
            utils.pin_one_negative_to_all(user, kw)
            # for key in user.keywords.all():
            #     key.negativekeyword.add(kw)
        else:
            key = Keyword.objects.get(id=key_id)
            key.negativekeyword.add(kw)

    bot.sendMessage(user.chat_id, text=random.choice(text.actions.pin_neg_key.success))



# Unpin negative key

def get_key_list_for_unpinning_negative_key(bot, update):
    "Shows a list of keywords in inline mode"
    user = User.objects.get(chat_id=update.effective_user.id)

    objects = user.keywords.all()
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    keywords = paginator.page(int(offset))
    next_offset = str(keywords.next_page_number()) if keywords.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=keyword.key,
                description=keyword.nkeys_description(),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.unpin_neg_key.select_key.format(keyword.id))
            ) for keyword in keywords
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def get_negative_key_list_button_for_unpinning_key(bot, update):
    "Shows message with the button to switch to inline query for negative key selection"
    user = User.objects.get(chat_id=update.effective_user.id)

    key = re.match(text.re.unpin_neg_key, update.message.text).group(1)

    update.message.delete()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.unpin_neg_key.unpin, switch_inline_query_current_chat=text.buttons.unpin_neg_key.choose_key.format(key=key))]
    ])
    bot.sendMessage(user.chat_id, text=text.actions.unpin_neg_key.choose_key, reply_markup=keyboard)


def get_negative_keys_for_unpinning_negative_key(bot, update):
    "Shows a list of negative keywords in inline mode"
    user = User.objects.get(chat_id=update.effective_user.id)

    key_id = re.match(text.re.unpin_neg_key_choose_key, update.inline_query.query).group(1)
    key = Keyword.objects.get(id=key_id)

    objects = key.negativekeyword.all()
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    keywords = paginator.page(int(offset))
    next_offset = str(keywords.next_page_number()) if keywords.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title='Все ключи',
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.unpin_neg_key.unpin.format(key=key_id, nkey=text.actions.unpin_key.all_keys)))
        ] + [
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=kw.key,
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.unpin_neg_key.unpin.format(key=key_id, nkey=kw.key))
            ) for kw in keywords
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def unpin_negative_key_from_key(bot, update):
    "Just unpin negative key from key"
    user = User.objects.get(chat_id=update.effective_user.id)

    match = re.match(text.re.unpin_neg_key_from_key, update.message.text)
    key_id = match.group(1)
    nkey = match.group(2)

    key = Keyword.objects.get(id=key_id)
    if nkey == text.actions.unpin_neg_key.all_keys:
        for kw in key.negativekeyword.filter(user=user):
            key.negativekeyword.remove(kw)
    else:
        try:
            kw = key.negativekeyword.filter(key=nkey, user=user)[0]
        except IndexError:
            logger.debug("No match for negative key {}. Unpinning declined.".format(key))
            return
        key.negativekeyword.remove(kw)

    bot.sendMessage(user.chat_id, text=random.choice(text.actions.unpin_neg_key.success))




# Delete negative Keywords

def negative_key_deletion_choose_keyword(bot, update):
    "Shows the list of negative keywords in inline mode"
    user = User.objects.get(chat_id=update.effective_user.id)

    objects = user.negativekeyword.all()
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    keywords = paginator.page(int(offset))
    next_offset = str(keywords.next_page_number()) if keywords.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=kw.key,
                description=kw.prepare_description(),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.negative_key_deletion.delete.format(key=kw.key))
            ) for kw in keywords
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def delete_neg_key(bot, update):
    "Hey, you! Delete a negative key for me!"
    user = User.objects.get(chat_id=update.effective_user.id)

    key = re.match(text.re.delete_neg_key, update.message.text).group(1)
    try:
        nkw = user.negativekeyword.filter(key=key)[0]
    except IndexError:
        logger.debug("No match for negative key {}. Deletion declined.".format(key))
        return

    nkw.delete()

    bot.sendMessage(user.chat_id, text=random.choice(text.actions.negative_key_deletion.success))



# Keywords' Groups

# Create group
def ask_keywords_group_name(bot, update):
    "Ask a name for the new group"
    bot.sendMessage(update.effective_message.chat.id, text=text.actions.create_group.ask_new_group)
    return PROCESS_GROUP


def create_new_group(bot, update):
    "Process given name of the group and create it"
    user = User.objects.get(chat_id=update.effective_user.id)

    group = KeywordsGroup.objects.create(name=update.message.text, user=user)

    bot.sendMessage(user.chat_id, text=text.actions.create_group.success)

# add key to group
def show_keys_list_for_adding_to_group(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    objects = user.keywords.all()
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    keywords = paginator.page(int(offset))
    next_offset = str(keywords.next_page_number()) if keywords.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=keyword.key,
                description=keyword.prepare_description(),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.add_key_to_group.choose_key.format(keyword.key))
            ) for keyword in keywords
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def get_button_to_show_keywords_groups(bot, update):
    "Shows a message with button to switch inline query for picking a group"
    user = User.objects.get(chat_id=update.effective_user.id)
    key = re.match(text.re.choose_key_for_group, update.message.text).group(1)
    update.message.delete()
    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.add_key_to_group.choose_group_button, switch_inline_query_current_chat=text.buttons.add_key_to_group.choose_group_pattern.format(key))]
    ])
    bot.sendMessage(user.chat_id, text=text.actions.add_key_to_group.choose_group, reply_markup=keyboard)


def show_groups_for_adding_key(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    keyword = re.match(text.re.choose_group_to_key, update.inline_query.query).group(1)

    objects = user.groups.all()
    offset = 1 if not update.inline_query.offset else update.inline_query.offset
    paginator = Paginator(objects, 40)
    groups = paginator.page(int(offset))
    next_offset = str(groups.next_page_number()) if groups.has_next() else ''

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=group.name,
                description=group.prepare_description(),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions.add_key_to_group.add_key_to_group.format(group_id=group.id, key=keyword))
            ) for group in groups
        ],
        cache_time=3,
        is_personal=True,
        next_offset=next_offset,
    )


def add_key_to_group(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    match = re.match(text.re.add_key_to_group, update.message.text)
    group_id = match.group(1)
    keyword = match.group(2)

    key = Keyword.objects.get(key=keyword, user=user)
    group = KeywordsGroup.objects.get(id=group_id)
    group.keys.add(key)

    update.message.delete()
    bot.sendMessage(user.chat_id, text=text.actions.add_key_to_group.success)


# Monitoring chat's activity

def show_all_chats(bot, update):
    "Show all possible common chats for user in a message using InlineKeyboard"
    user = User.objects.get(chat_id=update.effective_user.id)

    # Check whether a user has common chats
    if user.chats.count() == 0:
        bot.sendMessage(user.chat_id, text=text.actions.chats.no_chats)
        return

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=chat.represent(user), callback_data=text.buttons.chats.switch.format(chat=chat.id))] for chat in user.chats.all()[:99]
    ])
    bot.sendMessage(user.chat_id, text=text.actions.chats.show_all, reply_markup=keyboard)


def switch_chat(bot, update):
    "Switch chat activity"
    user = User.objects.get(chat_id=update.effective_user.id)

    chat_id = re.match(text.re.switch, update.callback_query.data).group(1)
    chat = Chat.objects.get(id=chat_id)

    if chat in user.chats.all():
        if chat.bot_in_chat:
            relation = chat.relation_set.filter(user=user)[0]
            relation.active = not relation.active
            relation.save()

            if relation.active:
                update.callback_query.answer(text=text.actions.chats.switch_success + ' ' + text.actions.chats.switch_unactive)
            else:
                update.callback_query.answer(text=text.actions.chats.switch_success + ' ' + text.actions.chats.switch_active)

            keyboard = telegram.InlineKeyboardMarkup([
                [telegram.InlineKeyboardButton(text=chat.represent(user), callback_data=text.buttons.chats.switch.format(chat=chat.id))] for chat in user.chats.all()
            ])
            update.callback_query.edit_message_reply_markup(reply_markup=keyboard)

        else:
            update.callback_query.answer(text=text.actions.chats.switch_fail, show_alert=True)




# Group messages

def handle_group_message(bot, update):
    "Handle group messages"
    if update.message.text:
        tasks.check_message_for_keywords.delay(
        update.message.chat.id,
        update.message.message_id,
        update.message.text,
        )
    elif update.message.caption:
        tasks.check_message_for_keywords.delay(
        update.message.chat.id,
        update.message.message_id,
        update.message.caption,
        )
    # chat_id = update.message.chat.id
    # chat = Chat.objects.get(chat_id=chat_id)
    #
    # # If there is no text - skip
    # if not update.message.text:
    #     return
    #
    # # Define a list where keywords that occur in message will be stored
    # keywords = []
    # # Try to find them, man!
    # # logger.debug("message - {}".format(update.message.text))
    # for keyword in chat.keywords.all():
    #     state = True
    #     if not keyword.key: continue
    #     # logger.debug("key {} - {}".format(keyword.key.lower(), keyword.key.lower() in update.message.text.lower()))
    #     if keyword.key.lower() in update.message.text.lower():
    #         # Also don't forget about negative keywords
    #         for nkey in keyword.negativekeyword.all():
    #             if nkey.key in update.message.text:
    #                 state = False
    #         if state:
    #             relation = keyword.user.relation_set.filter(chat=chat)[0]
    #             if relation.active:
    #                 keywords.append(keyword)
    #
    # # If theres no keywords - skip
    # if not keywords:
    #     logger.debug("Skipped message {}:{}:[{}]".format(update.message.message_id, update.message.text, keywords))
    #     return
    #
    # # Just logging stuff
    # keys = ', '.join([kw.key for kw in keywords])
    # logger.debug("Found keywords ({}) in {}:{}".format(keys, update.message.message_id, update.message.text.replace('\n', ' ')))
    #
    # # Resending messages to users
    # users = list(set([kw.user for kw in keywords]))
    # for user in users:
    #     logger.debug("Sending message {} to {}".format(update.message.message_id, user.chat_id))
    #     update.message.forward(user.chat_id)







PROCESS_KEY = range(1)
PROCESS_NEG_KEY = range(1)
PROCESS_GROUP = range(1)

def main():
    dp = DjangoTelegramBot.dispatcher

    logger.info("Loading handlers for telegram bot")

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("menu", menu))

    # Handling adding and deleteing bot to/from the chat

    dp.add_handler(MessageHandler(Filters.status_update.new_chat_members, new_chat_members))

    dp.add_handler(MessageHandler(Filters.status_update.chat_created, chat_created))

    dp.add_handler(MessageHandler(Filters.status_update.left_chat_member, left_chat_member))

    # Handle group messages

    dp.add_handler(MessageHandler(GroupFilters.allowed_groups, handle_group_message))

    # Add key handler
    dp.add_handler(ConversationHandler(
        allow_reentry=True,
        entry_points=[
            CommandHandler('addkey', ask_new_key),
            CallbackQueryHandler(callback=ask_new_key, pattern=text.buttons.menu.add_key)
        ],
        states={
            PROCESS_KEY: [MessageHandler(Filters.text, add_key)],
        },
        fallbacks=[
            MessageHandler(Filters.all, default_fallback)
        ]
    ))

    # Add negative key handler
    dp.add_handler(ConversationHandler(
        allow_reentry=True,
        entry_points=[
            CommandHandler('addnegkey', ask_negative_key),
            CallbackQueryHandler(callback=ask_negative_key, pattern=text.buttons.menu.add_neg_key)
        ],
        states={
            PROCESS_NEG_KEY: [MessageHandler(Filters.text, add_negative_key)],
        },
        fallbacks=[
            MessageHandler(Filters.all, default_fallback)
        ]
    ))

    # Create keywords' group
    dp.add_handler(ConversationHandler(
        allow_reentry=True,
        entry_points=[
            CommandHandler('creategroup', ask_keywords_group_name),
            CallbackQueryHandler(callback=ask_keywords_group_name, pattern=text.buttons.menu.create_group),
        ],
        states={
            PROCESS_GROUP: [MessageHandler(Filters.text, create_new_group)],
        },
        fallbacks=[MessageHandler(Filters.all, default_fallback)]
    ))

    # Pin key to the chat through inline query
    dp.add_handler(InlineQueryHandler(callback=get_keys_for_pinning,pattern=text.buttons.menu.pin_key_to_chat[:-2]))

    dp.add_handler(RegexHandler(callback=get_chat_list_button_for_pinning_key, pattern=text.re.choose_pin_key))

    dp.add_handler(InlineQueryHandler(callback=get_chat_list_for_pinning_key, pattern=text.re.choose_chat_to_pin))

    dp.add_handler(RegexHandler(callback=pin_key_to_chat, pattern=text.re.pin_key_to_chat))

    # Pin negative key through inline query
    dp.add_handler(InlineQueryHandler(callback=get_negative_keys_list_for_pinning,pattern=text.buttons.menu.pin_neg_key[:-2]))

    dp.add_handler(RegexHandler(callback=get_key_list_button_for_pinning_negative_key, pattern=text.re.choose_pin_neg_key))

    dp.add_handler(InlineQueryHandler(callback=get_keys_list_for_pinning_negative_key, pattern=text.re.choose_key_to_pin))

    dp.add_handler(RegexHandler(callback=pin_negative_key_to_key, pattern=text.re.pin_key_to_key))

    # Add keyword to group
    dp.add_handler(InlineQueryHandler(callback=show_keys_list_for_adding_to_group, pattern=text.buttons.menu.add_key_to_group))

    dp.add_handler(RegexHandler(callback=get_button_to_show_keywords_groups, pattern=text.re.choose_key_for_group))

    dp.add_handler(InlineQueryHandler(callback=show_groups_for_adding_key, pattern=text.re.choose_group_to_key))

    dp.add_handler(RegexHandler(callback=add_key_to_group, pattern=text.re.add_key_to_group))

    # Unpin key from the chat
    dp.add_handler(InlineQueryHandler(callback=get_chat_list_for_unpinning_key, pattern=text.buttons.menu.unpin_key_from_chat[:-2]))

    dp.add_handler(RegexHandler(callback=get_key_list_button_for_unpinning_key, pattern=text.re.unpin_key_select_chat))

    dp.add_handler(InlineQueryHandler(callback=get_key_list_for_pinning_key, pattern=text.re.unpin_key_choose_key))

    dp.add_handler(RegexHandler(callback=unpin_key_from_chat, pattern=text.re.unpin_key_from_chat))

    # Unpin neg key from the key
    dp.add_handler(InlineQueryHandler(callback=get_key_list_for_unpinning_negative_key, pattern=text.buttons.menu.unpin_neg_key[:-2]))

    dp.add_handler(RegexHandler(callback=get_negative_key_list_button_for_unpinning_key, pattern=text.re.unpin_neg_key))

    dp.add_handler(InlineQueryHandler(callback=get_negative_keys_for_unpinning_negative_key, pattern=text.re.unpin_neg_key_choose_key))

    dp.add_handler(RegexHandler(callback=unpin_negative_key_from_key, pattern=text.re.unpin_neg_key_from_key))

    # Delete key
    dp.add_handler(InlineQueryHandler(callback=get_keys_list_for_deletion, pattern=text.buttons.menu.delete_key[:-2]))

    dp.add_handler(RegexHandler(callback=delete_key, pattern=text.re.delete_key))

    # Delete negative key
    dp.add_handler(InlineQueryHandler(callback=negative_key_deletion_choose_keyword, pattern=text.buttons.menu.delete_neg_key[:-2]))

    dp.add_handler(RegexHandler(callback=delete_neg_key, pattern=text.re.delete_neg_key))

    # Chat monitoring
    dp.add_handler(CallbackQueryHandler(callback=show_all_chats , pattern=text.buttons.menu.chat_monitor))

    dp.add_handler(CallbackQueryHandler(callback=switch_chat, pattern=text.re.switch))
