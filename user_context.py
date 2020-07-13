from typing import Dict, Optional


class TargetNode:
    def __init__(self):
        self.node_id: Optional[str] = None
        self.map_id: Optional[str] = None


class UserContext:
    def __init__(self):
        self.is_authorized: Optional[bool] = False
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.target: Optional[TargetNode] = None


USERS_CONTEXT: Dict[str, UserContext] = {}


def get_or_create_context(message):
    chat_id = message.chat.id
    ctx = USERS_CONTEXT.get(chat_id)

    if ctx is None:
        ctx = UserContext()
        USERS_CONTEXT[chat_id] = ctx

    return chat_id, ctx


def del_context(message):
    chat_id = message.chat.id
    ctx = USERS_CONTEXT.get(chat_id)

    if ctx:
        del USERS_CONTEXT[chat_id]
