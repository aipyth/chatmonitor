from telegram.ext.filters import BaseFilter

from .models import Chat


class GroupFilters(object):

    class _AllowedGroups(BaseFilter):
        name = 'GroupFilters.allowed_groups'
        # update_filter = True

        def filter(self, message):
            # if update.message:
            chat_id = message.chat.id
            
            return True if Chat.objects.get_or_none(chat_id=chat_id) else False

    allowed_groups = _AllowedGroups()