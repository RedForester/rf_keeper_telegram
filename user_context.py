import logging
import os

from peewee import Model, CharField, BooleanField, ForeignKeyField, DatabaseProxy, PostgresqlDatabase

logger = logging.getLogger('bot')


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


def init_db():
    db.initialize(PostgresqlDatabase(
        os.getenv('PGDATABASE'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        host=os.getenv('PGHOST'),
        port=5432
    ))

    db.create_tables([TargetNode, UserContext], safe=True)


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
