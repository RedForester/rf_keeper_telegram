from telebot.asyncio_handler_backends import BaseMiddleware


class LoggerMiddleware(BaseMiddleware):
    update_types = ['message']

    def __init__(self, logger):
        super().__init__()
        self._logger = logger

    async def pre_process(self, message, data):
        self._logger.info(f'Incoming message from chat: {message.chat.id}')

    async def post_process(self, message, data, exception):
        pass


class CallbackResponse:
    def __init__(self, bot, query):
        self._bot = bot
        self._query = query

    async def ok(self):
        await self._bot.answer_callback_query(callback_query_id=self._query.id)

    async def notification(self, message: str):
        await self._bot.answer_callback_query(
            callback_query_id=self._query.id,
            text=message
        )

    async def error(self, message: str):
        await self._bot.answer_callback_query(
            callback_query_id=self._query.id,
            text=message,
            show_alert=True
        )
