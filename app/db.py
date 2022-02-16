import os

from peewee import Model, CharField, BooleanField, ForeignKeyField, DatabaseProxy, PostgresqlDatabase, BigIntegerField

from app.logger import logger

db = DatabaseProxy()


class BaseModel(Model):
    class Meta:
        database = db


class TargetNode(BaseModel):
    node_id = CharField()
    map_id = CharField()


class UserContext(BaseModel):
    chat_id = CharField()
    is_authorized = BooleanField(default=False)
    username = CharField(null=True, default=None)
    password = CharField(null=True, default=None)
    target = ForeignKeyField(TargetNode, null=True, default=None)


class SavedNodeContext(BaseModel):
    user_ctx = ForeignKeyField(UserContext, on_delete='CASCADE')

    # user message id
    message_id = BigIntegerField()

    # created node id
    node_id = CharField()

    # bot reply id
    reply_id = BigIntegerField()


def init_db():
    db.initialize(PostgresqlDatabase(
        os.getenv('PGDATABASE'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        host=os.getenv('PGHOST'),
        port=5432
    ))

    db.create_tables([TargetNode, UserContext, SavedNodeContext], safe=True)

    logger.info("Database initialized")


def get_or_create_context(message):
    chat_id = message.chat.id
    ctx, created = UserContext.get_or_create(chat_id=chat_id, defaults={'is_authorized': False})

    if created:
        logger.info(f"New context is created for chat {chat_id}")

    return chat_id, ctx


def del_context(message):
    chat_id = message.chat.id
    count = UserContext.delete().where(UserContext.chat_id == chat_id).execute()

    if count:
        logger.info(f"Context is deleted for chat {chat_id}")


def create_node_context(user_ctx, message, node_id, reply):
    return SavedNodeContext.create(user_ctx=user_ctx, message_id=message.message_id, node_id=node_id, reply_id=reply.message_id)


def get_node_context(user_ctx, message):
    return SavedNodeContext.get_or_none(user_ctx=user_ctx, message_id=message.message_id)
