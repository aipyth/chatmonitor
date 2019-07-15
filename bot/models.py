from django.db import models
from django.core.exceptions import ObjectDoesNotExist

from contextlib import suppress

# Create your models here.

class LocalManager(models.Manager):
    def get_or_none(self, **kwargs):
        with suppress(ObjectDoesNotExist):
            return self.get(**kwargs)


class User(models.Model):
    chat_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=1024)
    username = models.CharField(max_length=256, blank=True)

    objects = LocalManager()


    def __str__(self):
        return "{} {}".format(self.name, self.username)


    def get_keywords_info(self):
        for keyword in self.keywords.all():
            yield {
                'title': keyword.key,
                'description': keyword.prepare_description_with_emoji(),
            }


    def get_chats_info(self, kw=None):
        if kw:
            # TODO: return only chats without current key binded to them
            for chat in self.chats.filter(bot_in_chat=True):
                yield {
                    'id': chat.id,
                    'title': chat.title,
                    'keys': chat.get_keys(),
                }
        else:
            for chat in self.chats.filter(bot_in_chat=True):
                yield {
                    'id': chat.id,
                    'title': chat.title,
                    'keys': chat.get_keys(),
                }


class Chat(models.Model):
    PRIVATE_CHAT = 'P'
    GROUP_CHAT = 'G'
    SUPERGROUP_CHAT = 'S'
    CHANNEL_CHAT = 'C'
    CHATS = (
        (PRIVATE_CHAT, 'private'),
        (GROUP_CHAT, 'group'),
        (SUPERGROUP_CHAT, 'supergroup'),
        (CHANNEL_CHAT, 'channel'),
    )

    active = models.BooleanField(default=True)
    bot_in_chat = models.BooleanField(default=True)
    chat_id = models.BigIntegerField(unique=True)
    chat_type = models.CharField(
        choices=CHATS,
        max_length=1,
    )
    title = models.TextField(blank=True)
    username = models.CharField(max_length=512, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats')

    objects = LocalManager()


    def __str__(self):
        state = 'active' if self.active and self.bot_in_chat else 'unactive'
        return "\'{chat_title}\' ({user}) Status: {status}".format(chat_title=self.title, user=self.user, status=state)


    def represent(self):
        return "{} {}".format(self.title, '☑️' if self.active else '❎')

    
    def get_keys(self):
        return ' | '.join([kw.key for kw in self.keywords.all()])



class Keyword(models.Model):
    chats = models.ManyToManyField(Chat, related_name='keywords')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='keywords')
    key = models.TextField()

    objects = LocalManager()


    def __str__(self):
        return "'{}' by {}".format(self.key, self.user)

    
    def prepare_description_with_emoji(self):
        chats = self.chats.all()
        return ', '.join(['{} {}'.format(chat.title, '🔵' if  chat.active else '🔴') for chat in chats])