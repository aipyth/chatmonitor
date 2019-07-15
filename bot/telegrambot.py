import json
from collections import namedtuple
import random
import re
import uuid

import telegram
from telegram.ext import CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler, InlineQueryHandler, RegexHandler, Filters
from django_telegrambot.apps import DjangoTelegramBot

from .models import User, Chat, Keyword
from .bot_filters import GroupFilters


import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


with open('bot/text.json', encoding='utf8') as file:
    text_object = lambda d: namedtuple('text_object', d.keys())(*d.values())
    text = json.load(file, object_hook=text_object)



def start(bot, update):
    user = User.objects.get_or_none(chat_id=update.message.chat.id)
    if not user:
        user = User(chat_id=update.message.chat.id, name=update.message.from_user.full_name, username=update.message.from_user.username)
        user.save()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.menu.add_key, callback_data=text.buttons.menu.add_key)],
        [telegram.InlineKeyboardButton(text=text.buttons.menu.pin_key_to_chat, switch_inline_query_current_chat=text.buttons.menu.pin_key_to_chat[:-2])],
        [telegram.InlineKeyboardButton(text=text.buttons.menu.unpin_key_from_chat, switch_inline_query_current_chat=text.buttons.menu.unpin_key_from_chat[:-2])],
        [telegram.InlineKeyboardButton(text=text.buttons.menu.delete_key, switch_inline_query_current_chat=text.buttons.menu.delete_key[:-2])],
        [telegram.InlineKeyboardButton(text=text.buttons.menu.chat_monitor, callback_data=text.buttons.menu.chat_monitor)],
    ])

    bot.sendMessage(update.message.chat_id, text=text.content.greeting, parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=keyboard)


def menu(bot, update):
    "Show up the menu"
    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.menu.add_key, callback_data=text.buttons.menu.add_key)],
        [telegram.InlineKeyboardButton(text=text.buttons.menu.pin_key_to_chat, switch_inline_query_current_chat=text.buttons.menu.pin_key_to_chat[:-2])],
        [telegram.InlineKeyboardButton(text=text.buttons.menu.unpin_key_from_chat, switch_inline_query_current_chat=text.buttons.menu.unpin_key_from_chat[:-2])],
        [telegram.InlineKeyboardButton(text=text.buttons.menu.delete_key, switch_inline_query_current_chat=text.buttons.menu.delete_key[:-2])],
        [telegram.InlineKeyboardButton(text=text.buttons.menu.chat_monitor, callback_data=text.buttons.menu.chat_monitor)],
    ])
    bot.sendMessage(update.message.chat.id, text=text.content.menu, reply_markup=keyboard)


def default_fallback(bot, update):
    bot.sendMessage(update.effective_message.chat.id, text=text.context.dont_understand)



# Handle adding bot to chats

def chat_created(bot, update):
    if update.message.chat.type in ('private', 'channel'):
        return

    for literal, ltype in Chat.CHATS:
        if update.message.chat.type == ltype:
            chat_type = literal

    chat = Chat(chat_id=update.message.chat.id, chat_type=chat_type, title=update.message.chat.title)
    chat.save()

    for user in User.objects.all():
        try:
            if bot.getChatMember(chat.chat_id, user.chat_id):
                logger.debug("{} in {}. Relating them...".format(user, chat))
                chat.user.add(user)
        except telegram.TelegramError:
            logger.debug("{} not in {}. Skipping...".format(user, chat))


def new_chat_members(bot, update):
    if update.message.chat.type in ('private', 'channel'):
        return

    chat = Chat.objects.get_or_none(chat_id=update.message.chat.id)
    
    for member in update.message.new_chat_members:
        if member.username == bot.username:
            if chat:
                chat.bot_in_chat = True

            else:
                for literal, ltype in Chat.CHATS:
                    if update.message.chat.type == ltype:
                        chat_type = literal

                chat = Chat(chat_id=update.message.chat.id, chat_type=chat_type, title=update.message.chat.title)

            chat.save()

            for user in User.objects.all():
                try:
                    if bot.getChatMember(chat.chat_id, user.chat_id):
                        logger.debug("{} in {}. Relating them...".format(user, chat))
                        chat.user.add(user)
                except telegram.TelegramError:
                    logger.debug("{} not in {}. Skipping...".format(user, chat))
        else:
            user = User.objects.get_or_none(chat_id=member.id)
            if user:
                logger.debug("{} in {}. Relating them...".format(user, chat))
                chat.user.add(user)


def left_chat_member(bot, update):
    if update.message.chat.type in ('private', 'channel'):
        return

    if update.message.left_chat_member.username == bot.username:
        chat = Chat.objects.get(chat_id=update.message.chat.id)
        chat.bot_in_chat = False
        chat.save()
    else:
        return
    
    bot.sendMessage(chat.user.chat_id, text=text.actions_text.chats.deleted_from.format(chat.title), parse_mode=telegram.ParseMode.MARKDOWN)




# Add key

def add_key(bot, update):
    bot.sendMessage(update.effective_message.chat.id, text=random.choice(text.actions_text.add_key.ask_new_key))
    return PROCESS_KEY


def process_key(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    key = Keyword(key=update.message.text, user=user)
    key.save()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.menu.pin_key_to_chat, switch_inline_query_current_chat=text.buttons.menu.pin_key_to_chat[:-2])],
    ])
    bot.sendMessage(user.chat_id, text=text.actions_text.add_key.success, reply_markup=keyboard)
    return -1



# Pin key

def pin_key_to_chat(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=keyword.get('title'),
                description=keyword.get('description'),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions_text.pin_key.choose_pin_key.format(keyword.get('title')))
            ) for keyword in user.get_keywords_info()
        ],
        cache_time=3,
        is_personal=True,
    )


def process_pinning_key(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    key = re.match(text.re.choose_pin_key, update.message.text).group(1)
    kw = user.keywords.filter(key=key)[0]

    update.message.delete()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.pin_key_to_chat.pin_to_chat, switch_inline_query_current_chat=text.buttons.pin_key_to_chat.choose_chat_to_pin_pattern.format(kw.key))]
    ])
    bot.sendMessage(user.chat_id, text=text.actions_text.pin_key.choose_chat, reply_markup=keyboard)


def process_pinning_chat(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    key = re.match(text.re.choose_chat_to_pin, update.inline_query.query).group(1)
    kw = user.keywords.filter(key=key)[0]

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=chat.get('title'),
                description=chat.get('keys'),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions_text.pin_key.pin_key_to_chat.format(chat=chat.get('id'), key=kw.key))
            ) for chat in user.get_chats_info(kw)
        ],
        cache_time=3,
        is_personal=True,
    )


def process_pinning(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    match = re.match(text.re.pin_key_to_chat, update.message.text)
    chat_id = match.group(1)
    key = match.group(2)
    try:
        kw = user.keywords.filter(key=key)[0]
    except IndexError: return
    chat = Chat.objects.get(id=chat_id)
    chat.keywords.add(kw)

    bot.sendMessage(user.chat_id, text=random.choice(text.actions_text.pin_key.success)) 



# Unpin key

def prepare_chat_selection(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=chat.get('title'),
                description=chat.get('keys'),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions_text.unpin_key.select_chat.format(chat.get('id')))
            ) for chat in user.get_chats_info()
        ],
        cache_time=3,
        is_personal=True,
    )


def prepare_key_selection(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    chat = re.match(text.re.unpin_key_select_chat, update.message.text).group(1)

    update.message.delete()

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=text.buttons.unpin_key_from_chat.unpin_from_chat, switch_inline_query_current_chat=text.buttons.unpin_key_from_chat.choose_key_pattern.format(chat=chat))]
    ])
    bot.sendMessage(user.chat_id, text=text.actions_text.unpin_key.choose_key, reply_markup=keyboard)


def prepare_key_list(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    chat_id = re.match(text.re.unpin_key_choose_key, update.inline_query.query).group(1)
    chat = Chat.objects.get(id=chat_id)

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=kw.key,
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions_text.unpin_key.unpin.format(chat=chat.id, key=kw.key))
            ) for kw in chat.keywords.filter(user=user)
        ],
        cache_time=3,
        is_personal=True,
    )


def unpin_key_from_chat(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    match = re.match(text.re.unpin_key_from_chat, update.message.text)
    chat_id = match.group(1)
    key = match.group(2)
    chat = Chat.objects.get(id=chat_id)
    try:
        kw = chat.keywords.filter(key=key, user=user)[0]
    except IndexError: return
    chat.keywords.remove(kw)

    bot.sendMessage(user.chat_id, text=random.choice(text.actions_text.unpin_key.success)) 




# Delete Keywords

def deletion_choose_keyword(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    update.inline_query.answer(
        results=[
            telegram.InlineQueryResultArticle(
                id=uuid.uuid4(),
                title=kw.key,
                description=kw.prepare_description_with_emoji(),
                input_message_content=telegram.InputTextMessageContent(message_text=text.actions_text.key_deletion.delete.format(key=kw.key))
            ) for kw in user.keywords.all()
        ],
        cache_time=3,
        is_personal=True,
    )


def delete_key(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    key = re.match(text.re.delete_key, update.message.text).group(1)
    try:
        key = user.keywords.filter(key=key)[0]
    except IndexError: return

    key.delete()

    bot.sendMessage(user.chat_id, text=random.choice(text.actions_text.key_deletion.success))



# Monitoring chat's activity

def show_all_chats(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    if user.chats.count() == 0:
        bot.sendMessage(user.chat_id, text=text.actions_text.chats.no_chats)
        return

    keyboard = telegram.InlineKeyboardMarkup([
        [telegram.InlineKeyboardButton(text=chat.represent(user), callback_data=text.buttons.chats.switch.format(chat=chat.id))] for chat in user.chats.all()
    ])
    bot.sendMessage(user.chat_id, text=text.actions_text.chats.show_all, reply_markup=keyboard)


def switch_chat(bot, update):
    user = User.objects.get(chat_id=update.effective_user.id)

    chat_id = re.match(text.re.switch, update.callback_query.data).group(1)
    chat = Chat.objects.get(id=chat_id)

    if chat in user.chats.all():
        if chat.bot_in_chat:
            relation = chat.relation_set.filter(user=user)[0]
            relation.active = not relation.active
            relation.save()

            update.callback_query.answer(text=text.actions_text.chats.switch_success)

            keyboard = telegram.InlineKeyboardMarkup([
                [telegram.InlineKeyboardButton(text=chat.represent(user), callback_data=text.buttons.chats.switch.format(chat=chat.id))] for chat in user.chats.all()
            ])
            update.callback_query.edit_message_reply_markup(reply_markup=keyboard)

        else:
            update.callback_query.answer(text=text.actions_text.chats.switch_fail, show_alert=True)




# Group messages

def handle_group_message(bot, update):
    # logger.debug("handled {}".format(update.message))
    chat_id = update.message.chat.id
    chat = Chat.objects.get(chat_id=chat_id)

    keywords = []
    for keyword in chat.keywords.all():
        if keyword.key.lower() in update.message.text.lower():
            keywords.append(keyword)
    if not keywords:
        logger.debug("Skipped message {}:{}".format(update.message.message_id, update.message.text))
        return
    keys = ', '.join([kw.key for kw in keywords])
    logger.debug("Found keywords ({}) in {}:{}".format(keys, update.message.message_id, update.message.text))
    for key in keywords:
        logger.debug("Sending message {} to {}".format(update.message.message_id, key.user.chat_id))
        update.message.forward(key.user.chat_id)
        bot.sendMessage(key.user.chat_id, text=text.actions_text.chats.new_message.format(key=key.key, username=update.message.from_user.username, chat=chat.title), parse_mode=telegram.ParseMode.MARKDOWN)
        # keyword.user.chat_id







PROCESS_KEY = range(1)

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
            CommandHandler('addkey', add_key),
            CallbackQueryHandler(callback=add_key, pattern=text.buttons.menu.add_key)
        ],
        states={
            PROCESS_KEY: [MessageHandler(Filters.text, process_key)],
        },
        fallbacks=[
            MessageHandler(Filters.all, default_fallback)
        ]
    ))

    # Pin key to the chat through inline query
    dp.add_handler(InlineQueryHandler(callback=pin_key_to_chat,pattern=text.buttons.menu.pin_key_to_chat[:-2]))

    dp.add_handler(RegexHandler(callback=process_pinning_key, pattern=text.re.choose_pin_key))

    dp.add_handler(InlineQueryHandler(callback=process_pinning_chat, pattern=text.re.choose_chat_to_pin))

    dp.add_handler(RegexHandler(callback=process_pinning, pattern=text.re.pin_key_to_chat))

    # Unpin key from the chat
    dp.add_handler(InlineQueryHandler(callback=prepare_chat_selection, pattern=text.buttons.menu.unpin_key_from_chat[:-2]))

    dp.add_handler(RegexHandler(callback=prepare_key_selection, pattern=text.re.unpin_key_select_chat))

    dp.add_handler(InlineQueryHandler(callback=prepare_key_list, pattern=text.re.unpin_key_choose_key))

    dp.add_handler(RegexHandler(callback=unpin_key_from_chat, pattern=text.re.unpin_key_from_chat))

    # Delete key
    dp.add_handler(InlineQueryHandler(callback=deletion_choose_keyword, pattern=text.buttons.menu.delete_key[:-2]))

    dp.add_handler(RegexHandler(callback=delete_key, pattern=text.re.delete_key))

    # Chat monitoring
    dp.add_handler(CallbackQueryHandler(callback=show_all_chats ,pattern=text.buttons.menu.chat_monitor))

    dp.add_handler(CallbackQueryHandler(callback=switch_chat, pattern=text.re.switch))


