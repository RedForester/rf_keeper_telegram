from app.db import UserContext


class Guards:
    @staticmethod
    def is_command(message):
        return message.text and message.text.startswith('/')

    @staticmethod
    def is_cancel(message):
        return message.text and message.text == '/cancel'

    @staticmethod
    def is_setup_completed(ctx: UserContext):
        return ctx.target

    @staticmethod
    def is_authorized(ctx: UserContext):
        return ctx.is_authorized
