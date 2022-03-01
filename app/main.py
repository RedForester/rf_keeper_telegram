import os
from enum import Enum
import asyncio
from typing import List

from rf_api_client.models.tags_api_models import TaggedNodeDto
from telebot import asyncio_filters, types
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_handler_backends import StatesGroup, State

from app.logger import logger
from app.api import create_node, login_to_rf, get_favorite_nodes, move_node, get_node
from app.db import init_db, get_or_create_context, del_context, \
    create_node_context, get_node_context, update_node_context, get_last_node_context
from content_handler import ContentHandler
from messages import Messages
from utils.bot import CallbackResponse, LoggerMiddleware
from utils.html import html_to_text
from utils.rf_links import link_to_node


logger.info('RedForester Keeper bot started')


bot = AsyncTeleBot(
    token=os.getenv('RF_KEEPER_TOKEN'),
    parse_mode='HTML',
)
bot.add_custom_filter(asyncio_filters.StateFilter(bot))
bot.setup_middleware(LoggerMiddleware(logger))


HELP_MESSAGE = (
    'Hi! I am RedForester Keeper bot.\n'
    'I will save your messages to one of your favorite nodes.\n'
)


GH_LINK = 'https://github.com/RedForester/rf_keeper_telegram'


COMMANDS = [
    types.BotCommand('/start', 'Login to RedForester'),
    types.BotCommand('/stop', 'Logout from RedForester'),
    types.BotCommand('/cancel', 'Cancel the current action'),
    types.BotCommand('/help', 'Show the help message'),
]


async def init_bot():
    logger.info('Update bot info')
    await bot.set_my_commands(COMMANDS)


class BotState(StatesGroup):
    get_username = State()
    get_password = State()


@bot.message_handler(commands=['help'])
async def help_(message):
    await bot.reply_to(
        message,
        f'{HELP_MESSAGE}\n'
        f'<a href="{GH_LINK}">Link to bot source code</a>'
    )


@bot.message_handler(commands=['start'])
async def start(message):
    chat_id, ctx = get_or_create_context(message)

    if ctx.is_authorized:
        return await bot.reply_to(message, 'We\'ve already started. To logout from your account type /stop')

    await bot.reply_to(
        message,
        f'{HELP_MESSAGE}\n'
        'Let\'s start, type your username (email) for your RedForester account or /cancel:'
    )

    await bot.set_state(message.from_user.id, BotState.get_username, message.chat.id)


@bot.message_handler(commands=['stop'])
async def stop(message):
    del_context(message)
    await bot.delete_state(message.from_user.id, message.chat.id)
    await bot.reply_to(message, 'Session has been terminated\n\nType /start to login again')


@bot.message_handler(state='*', commands=['cancel'])
async def cancel(message):
    state = await bot.get_state(message.from_user.id, message.chat.id)

    if not state:
        await bot.reply_to(message, 'Nothing to cancel')
    else:
        await bot.reply_to(message, 'Action was canceled. Type /start to repeat')
        await bot.delete_state(message.from_user.id, message.chat.id)


@bot.message_handler(state=BotState.get_username)
async def start_get_username(message):
    chat_id, ctx = get_or_create_context(message)
    ctx.username = message.text.strip()
    ctx.save()

    await bot.send_message(
        chat_id,
        'And then type your password or /cancel:'
    )

    await bot.set_state(message.from_user.id, BotState.get_password, message.chat.id)


@bot.message_handler(state=BotState.get_password)
async def start_get_password(message):
    chat_id, ctx = get_or_create_context(message)

    password = message.text.strip()

    try:
        rf_user = await login_to_rf(ctx.username, password)

        # fixme
        #  Yes, this is extremely bad to store unhashed password, but I have no choice for now.
        #  If you really concern - self host this bot.
        #  Meanwhile I am trying to create better solution.
        ctx.password = password
        ctx.is_authorized = True
        ctx.save()

        await bot.send_message(
            chat_id,
            f'Hi, {rf_user.name} {rf_user.surname}, we are ready to go!\n\n'
            f'Send me messages and I will save them to RedForester'
        )

        await bot.delete_state(message.from_user.id, message.chat.id)

    except Exception as e:
        logger.exception(e)

        await bot.send_message(
            chat_id,
            'Something went wrong.\nPlease try again or type /cancel\n\nType your username (email):'
        )

        await bot.set_state(message.from_user.id, BotState.get_username, message.chat.id)

    finally:
        await bot.delete_message(chat_id, message.message_id)


class SaveMessageCallbacks(Enum):
    save_request = 'save-node-request'
    save_to_last = 'save-node-to-last'
    save_to = 'save-node-to-'
    save_go_back = 'save-node-go-back'

    move_request = 'move-node-request'
    move_to = 'move-node-to-'
    move_go_back = 'move-node-go-back'


class Keyboards:
    @staticmethod
    def empty():
        return types.InlineKeyboardMarkup()

    @staticmethod
    def save_to():
        kbd = types.InlineKeyboardMarkup()
        kbd.add(
            types.InlineKeyboardButton(text='Save to last', callback_data=SaveMessageCallbacks.save_to_last.value),
            types.InlineKeyboardButton(text='Save to ...', callback_data=SaveMessageCallbacks.save_request.value),
        )

        return kbd

    @staticmethod
    def move_to(url: str):
        kbd = types.InlineKeyboardMarkup()
        kbd.add(
            types.InlineKeyboardButton(text='Open in the browser', url=url),
            types.InlineKeyboardButton(text='Move to ...', callback_data=SaveMessageCallbacks.move_request.value),
        )

        return kbd

    @staticmethod
    def favorites_list(favorites: List[TaggedNodeDto], node_callback: str, go_back_callback: str):
        kbd = types.InlineKeyboardMarkup(row_width=1)

        favorite_buttons = [types.InlineKeyboardButton(
            text=f'{fav.map.name} / {html_to_text(fav.title)}',
            callback_data=f'{node_callback}{fav.id}'
        ) for fav in favorites if fav.title]

        back_button = types.InlineKeyboardButton(
            text='🔙 Go Back',
            callback_data=go_back_callback
        )

        kbd.add(*favorite_buttons, back_button)

        return kbd


# Edge cases:
#  [x] The user might send messages and press buttons after /stop
#  [x] The user might delete bot messages (no code required)
#  [x] node_ctx might be None for existing messages after user logout
#  [-] 'Move to ...' states that the node is not found or the user does not have access to it, even if the node exists
#  [x] The user has no previously saved nodes
#  [x] Last saved node has been moved or deleted and the user press 'Save to last' button
#  [x] Last saved node has been deleted
#  [x] 'Save to...' list contains nodes that have been deleted and the user has selected one of them
#  [x] The incoming message has been deleted before the user saved it (no code required)
#  [x] 'Move to...' list contains nodes that have been deleted and the user has selected one of them
#  [x] If created node has been deleted while the user selects destination node
#       both actions ('Move to...' and 'Go back') should handle this state normally
#  [-] If Created node has been deleted immediately after creation. 'Move to ...' should throw an error
#       on the first interaction


@bot.message_handler(func=lambda m: True, content_types=ContentHandler.ALL_TYPES)
async def main_handler(message):
    chat_id, ctx = get_or_create_context(message)

    if not ctx.is_authorized:
        return await bot.reply_to(message, Messages.no_start_error)

    if not ContentHandler.is_supported(message):
        return await bot.reply_to(message, Messages.unsupported_type_error)

    reply = await bot.reply_to(
        message,
        Messages.select_action,
        reply_markup=Keyboards.save_to()
    )

    create_node_context(ctx, message, reply)


async def request_favorites_callback(query, node_callback: str, go_back_callback: str):
    response = CallbackResponse(bot, query)

    bot_message = query.message

    chat_id, ctx = get_or_create_context(query.message.reply_to_message)

    if not ctx.is_authorized:
        return await response.error(Messages.auth_error)

    # todo check if node has been deleted

    try:
        # todo filter out node links or use their sources as destination nodes
        favorites = await get_favorite_nodes(ctx)

    except Exception as e:
        logger.exception(e)

        return await response.error(Messages.get_favorites_error)

    kbd = Keyboards.favorites_list(
        favorites,
        node_callback,
        go_back_callback
    )

    await bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=bot_message.message_id,
        reply_markup=kbd
    )


async def create_node_callback(query, map_id: str, parent_id: str):
    bot_message = query.message
    user_message = bot_message.reply_to_message

    chat_id, ctx = get_or_create_context(user_message)

    content, files = await ContentHandler(bot).handle(ctx, user_message)

    node = await create_node(ctx, map_id, parent_id, content, files)

    update_node_context(ctx, user_message, node.id)

    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=bot_message.message_id,
        text=Messages.node_created,
        reply_markup=Keyboards.move_to(link_to_node(node.map_id, node.id))
    )


@bot.callback_query_handler(lambda query: query.data == SaveMessageCallbacks.save_request.value)
async def save_node_request(query):
    await request_favorites_callback(
        query,
        SaveMessageCallbacks.save_to.value,
        SaveMessageCallbacks.save_go_back.value
    )

    await CallbackResponse(bot, query).ok()


@bot.callback_query_handler(lambda query: query.data == SaveMessageCallbacks.save_to_last.value)
async def save_node_to_last(query):
    response = CallbackResponse(bot, query)

    bot_message = query.message
    user_message = bot_message.reply_to_message

    chat_id, ctx = get_or_create_context(user_message)

    if not ctx.is_authorized:
        return await response.error(Messages.auth_error)

    last_node_ctx = get_last_node_context(ctx)

    if not last_node_ctx:
        return await response.notification(Messages.no_last_saved_node)

    try:
        last_node = await get_node(ctx, last_node_ctx.node_id)
    except Exception as e:
        logger.exception(e)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=last_node_ctx.reply_id,
            text=Messages.node_not_found,
            reply_markup=Keyboards.empty()
        )

        last_node_ctx.delete_instance()

        return await response.notification(Messages.last_saved_node_not_found)

    try:
        await create_node_callback(query, last_node.map_id, last_node.parent)
    except Exception as e:
        logger.exception(e)

        destination_url = link_to_node(last_node.map_id, last_node.parent)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_message.message_id,
            text=Messages.node_create_error.format(destination_url=destination_url),
        )

    await response.ok()


@bot.callback_query_handler(lambda query: query.data.startswith(SaveMessageCallbacks.save_to.value))
async def save_node_to(query):
    response = CallbackResponse(bot, query)

    bot_message = query.message
    user_message = bot_message.reply_to_message

    chat_id, ctx = get_or_create_context(user_message)

    if not ctx.is_authorized:
        return await response.error(Messages.auth_error)

    selected_node_id = query.data.split(SaveMessageCallbacks.save_to.value)[1]

    try:
        destination_node = await get_node(ctx, selected_node_id)
    except Exception as e:
        logger.exception(e)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_message.message_id,
            text=Messages.destination_node_not_found,
            reply_markup=Keyboards.save_to()
        )

        return await response.ok()

    try:
        await create_node_callback(query, destination_node.map_id, destination_node.id)
    except Exception as e:
        logger.exception(e)

        destination_url = link_to_node(destination_node.map_id, destination_node.id)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_message.message_id,
            text=Messages.node_create_error.format(destination_url=destination_url),
            reply_markup=Keyboards.save_to()
        )

    await response.ok()


@bot.callback_query_handler(lambda query: query.data == SaveMessageCallbacks.save_go_back.value)
async def save_node_go_back(query):
    response = CallbackResponse(bot, query)

    chat_id, ctx = get_or_create_context(query.message.reply_to_message)

    if not ctx.is_authorized:
        return await response.error(Messages.auth_error)

    await bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=query.message.message_id,
        reply_markup=Keyboards.save_to()
    )

    await response.ok()


@bot.callback_query_handler(lambda query: query.data == SaveMessageCallbacks.move_request.value)
async def move_node_request(query):
    await request_favorites_callback(
        query,
        SaveMessageCallbacks.move_to.value,
        SaveMessageCallbacks.move_go_back.value
    )

    await CallbackResponse(bot, query).ok()


@bot.callback_query_handler(lambda query: query.data.startswith(SaveMessageCallbacks.move_to.value))
async def move_node_to(query):
    response = CallbackResponse(bot, query)

    bot_message = query.message
    user_message = bot_message.reply_to_message

    chat_id, ctx = get_or_create_context(user_message)

    if not ctx.is_authorized:
        return await response.error(Messages.auth_error)

    try:
        node_ctx = get_node_context(ctx, user_message)

        node = await get_node(ctx, node_ctx.node_id)
    except Exception as e:
        logger.exception(e)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_message.message_id,
            text=Messages.node_not_found,
            reply_markup=Keyboards.empty()
        )

        return await response.ok()

    node_url = link_to_node(node.map_id, node.id)

    selected_node_id = query.data.split(SaveMessageCallbacks.move_to.value)[1]

    try:
        destination_node = await get_node(ctx, selected_node_id)
    except Exception as e:
        logger.exception(e)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_message.message_id,
            text=Messages.destination_node_not_found,
            reply_markup=Keyboards.move_to(node_url)
        )

        return await response.ok()

    try:
        moved_node = await move_node(ctx, node.id, destination_node.id)
    except Exception as e:
        logger.exception(e)

        destination_url = link_to_node(destination_node.map_id, destination_node.id)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_message.message_id,
            text=Messages.node_move_error.format(destination_url=destination_url),
            reply_markup=Keyboards.move_to(node_url)
        )

        return await response.ok()

    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=bot_message.message_id,
        text=Messages.node_moved,
        reply_markup=Keyboards.move_to(link_to_node(moved_node.map_id, moved_node.id))
    )

    await response.ok()


@bot.callback_query_handler(lambda query: query.data == SaveMessageCallbacks.move_go_back.value)
async def move_node_go_back(query):
    response = CallbackResponse(bot, query)

    bot_message = query.message
    user_message = bot_message.reply_to_message

    chat_id, ctx = get_or_create_context(user_message)

    if not ctx.is_authorized:
        return await response.error(Messages.auth_error)

    try:
        node_ctx = get_node_context(ctx, user_message)

        node = await get_node(ctx, node_ctx.node_id)
    except Exception as e:
        logger.exception(e)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_message.message_id,
            text=Messages.node_not_found,
            reply_markup=Keyboards.empty()
        )

        return await response.ok()

    await bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=bot_message.message_id,
        reply_markup=Keyboards.move_to(link_to_node(node.map_id, node.id))
    )

    await response.ok()


if __name__ == '__main__':
    init_db()

    asyncio.run(init_bot())

    logger.info('Starting the polling')
    asyncio.run(bot.infinity_polling())
