from django.db import models
from django.core.exceptions import ObjectDoesNotExist

from contextlib import suppress


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

    bot_in_chat = models.BooleanField(default=True)
    chat_id = models.BigIntegerField(unique=True)
    chat_type = models.CharField(
        choices=CHATS,
        max_length=1,
    )
    title = models.TextField(blank=True)
    username = models.CharField(max_length=512, blank=True)
    user = models.ManyToManyField(User, through='Relation', related_name='chats')

    objects = LocalManager()


    def __str__(self):
        return "{chat_title}".format(chat_title=self.title)


    def represent(self, user):
        active = self.relation_set.filter(user=user)[0].active
        return "{} {}".format(self.title, '☑️' if active else '❎')


    def get_keys(self, user):
        return ' | '.join([kw.key for kw in self.keywords.filter(user=user)])



class Relation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)



class Keyword(models.Model):
    chats = models.ManyToManyField(Chat, related_name='keywords')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='keywords')
    key = models.TextField()
    state = models.BooleanField(default=True)

    objects = LocalManager()


    def __str__(self):
        return "'{}' by {}".format(self.key, self.user)


    def prepare_description(self):
        chats = self.chats.all()[:10]
        return ', '.join(['{}'.format(chat.title) for chat in chats])


    def nkeys_description(self):
        return ', '.join([nkey.key for nkey in self.negativekeyword.all()[:10]])



class NegativeKeyword(models.Model):
    keywords = models.ManyToManyField(Keyword, related_name='negativekeyword')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='negativekeyword')
    key = models.TextField()

    objects = LocalManager()


    def __str__(self):
        return "'{}' by {}".format(self.key, self.user)


    def prepare_description(self):
        return ', '.join(['{}'.format(kw.key) for kw in self.keywords.all()[:10]])



class KeywordsGroup(models.Model):
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='groups')
    keys = models.ManyToManyField(Keyword, related_name='groups')
    state = models.BooleanField(default=True)

    objects = LocalManager()

    def __str__(self):
        return "<KGroup {} by {}>".format(self.name, self.user)


    def prepare_state(self):
        return '✔️' if self.state else '❌'

    
    def prepare_description(self):
        if self.keys.count() > 7:
            return ', '.join(map(lambda x: x.key, self.keys.all()[:3])) + ', ... , ' + ', '.join(map(lambda x: x.key, self.keys.order_by('-id')[:2]))
        else:
            return ', '.join(map(lambda x: x.key, self.keys.all()))

