import os

from peewee import Model, CharField, BooleanField, ForeignKeyField, DatabaseProxy, PostgresqlDatabase, BigIntegerField

from app.logger import logger
from exceptions import AppException

db = DatabaseProxy()


class BaseModel(Model):
    class Meta:
        database = db


class UserContext(BaseModel):
    chat_id = CharField()
    is_authorized = BooleanField(default=False)
    username = CharField(null=True, default=None)
    password = CharField(null=True, default=None)


class SavedNodeContext(BaseModel):
    user_ctx = ForeignKeyField(UserContext, on_delete='CASCADE')

    # user message id
    message_id = BigIntegerField()

    # bot reply id
    reply_id = BigIntegerField()

    # created node id
    node_id = CharField(null=True, default=None)

    # todo add parent_id?


def init_db():
    db.initialize(PostgresqlDatabase(
        os.getenv('PGDATABASE'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        host=os.getenv('PGHOST'),
        port=5432
    ))

    db.create_tables([UserContext, SavedNodeContext], safe=True)

    logger.info('Database initialized')


def get_or_create_context(message):
    chat_id = message.chat.id
    ctx, created = UserContext.get_or_create(chat_id=chat_id, defaults={'is_authorized': False})

    if created:
        logger.info(f'New context is created for chat {chat_id}')

    return chat_id, ctx


def del_context(message):
    chat_id = message.chat.id
    count = UserContext.delete().where(UserContext.chat_id == chat_id).execute()

    if count:
        logger.info(f'Context is deleted for chat {chat_id}')


class NodeContextNotFoundException(AppException):
    pass


def get_node_context(user_ctx, message):
    try:
        return SavedNodeContext.get(user_ctx=user_ctx, message_id=message.message_id)
    except SavedNodeContext.DoesNotExist:
        raise NodeContextNotFoundException


def get_last_node_context(user_ctx):
    try:
        return SavedNodeContext\
            .select()\
            .where(SavedNodeContext.user_ctx == user_ctx)\
            .where(SavedNodeContext.node_id.is_null(False))\
            .order_by(SavedNodeContext.id.desc())\
            .get()
    except SavedNodeContext.DoesNotExist:
        return None


def create_node_context(user_ctx, message, reply):
    return SavedNodeContext.create(user_ctx=user_ctx, message_id=message.message_id, reply_id=reply.message_id)


def update_node_context(user_ctx, message, node_id: str):
    ctx = get_node_context(user_ctx, message)
    ctx.node_id = node_id
    ctx.save()
