import os
from enum import Enum
from typing import Optional
import asyncio

from telebot import types, asyncio_filters
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_handler_backends import StatesGroup, State, BaseMiddleware
from pathvalidate import sanitize_filename

from app.logger import logger
from app.rf_tasks import create_new_node, login_to_rf, get_favorite_nodes, move_node, get_node, FileInfoDto, \
    upload_file_to_rf, UploadFileData
from app.db import init_db, get_or_create_context, del_context, TargetNode, \
    create_node_context, get_node_context, UserContext
from app.utils import link_to_node, parse_node_link, tg_html_to_rf_html, html_to_text, guess_file_extension, \
    link_to_file, CUSTOM_SUBS


logger.info('RedForester Keeper bot started')


class LoggerMiddleware(BaseMiddleware):
    update_types = ['message']

    async def pre_process(self, message, data):
        logger.info(f"Incoming message from chat: {message.chat.id}")

    async def post_process(self, message, data, exception):
        pass


bot = AsyncTeleBot(
    token=os.getenv('RF_KEEPER_TOKEN'),
    parse_mode='HTML',
)
bot.add_custom_filter(asyncio_filters.StateFilter(bot))
bot.setup_middleware(LoggerMiddleware())


GREET = 'Hi! I am RedForester Keeper bot'
ABOUT = 'I will save your messages as nodes to a specific branch on your map'
COMMANDS = (
    'Available commands are:\n'
    '/start\n'
    '/setup\n'
    '/stop\n'
)


class BotState(StatesGroup):
    get_username = State()
    get_password = State()
    get_destination_node = State()


@bot.message_handler(commands=['help'])
async def help(message):
    await bot.reply_to(
        message,
        f'{GREET}.\n'
        f'{ABOUT}.\n'
        '\n'
        f'{COMMANDS}\n'
        f'<a href="https://github.com/RedForester/rf_keeper_telegram">Bot source code</a>',
    )


@bot.message_handler(commands=['start'])
async def start(message):
    chat_id, ctx = get_or_create_context(message)

    if ctx.is_authorized:
        return await bot.reply_to(message, 'We\'ve already started. To logout from your account type /stop')

    await bot.reply_to(
        message,
        f'{GREET}.\n'
        f'{ABOUT}.\n'
        '\n'
        'Let\'s start, type your username (email) from your RedForester account or /cancel:'
    )

    await bot.set_state(message.from_user.id, BotState.get_username, message.chat.id)


@bot.message_handler(commands=['stop'])
async def stop(message):
    del_context(message)
    await bot.delete_state(message.from_user.id, message.chat.id)
    await bot.reply_to(message, 'Done')


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
    ctx.username = message.text
    ctx.save()

    await bot.send_message(
        chat_id,
        'And then type your password or /cancel:'
    )

    await bot.set_state(message.from_user.id, BotState.get_password, message.chat.id)


@bot.message_handler(state=BotState.get_password)
async def start_get_password(message):
    chat_id, ctx = get_or_create_context(message)

    password = message.text

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
            f'Hi, {rf_user.surname} {rf_user.name}!\n'
            f'Your login and password is correct!\n'
            f'\n'
            f'Now, paste URL to the destination node:\n'
        )

        await bot.set_state(message.from_user.id, BotState.get_destination_node, message.chat.id)

    except Exception as e:
        logger.exception(e)

        await bot.send_message(
            chat_id,
            'Something went wrong. Please try again or type /cancel\n'
            'Type your username (email):'
        )

        await bot.set_state(message.from_user.id, BotState.get_username, message.chat.id)

    finally:
        await bot.delete_message(chat_id, message.message_id)


@bot.message_handler(commands=['setup'])
async def setup(message):
    chat_id, ctx = get_or_create_context(message)

    if not ctx.is_authorized:
        return await bot.reply_to(message, 'You have to /start first')

    target = link_to_node(ctx.target.map_id, ctx.target.node_id) if ctx.target else None
    status_text = f'Current destination node is {target}' if target else 'Destination node is not specified'

    await bot.reply_to(
        message,
        f'{status_text}\n'
        '\n'
        'Please paste link to the new destination node or type /cancel:'
    )

    await bot.set_state(message.from_user.id, BotState.get_destination_node, message.chat.id)


@bot.message_handler(state=BotState.get_destination_node)
async def setup_get_destination_node(message):
    chat_id, ctx = get_or_create_context(message)

    map_id, node_id = parse_node_link(message.text)

    if not map_id or not node_id:
        return await bot.send_message(chat_id, 'Node link is incorrect, please try again with /setup command')

    ctx.target = TargetNode.create(node_id=node_id, map_id=map_id)
    ctx.save()

    await bot.send_message(chat_id, 'Setup is complete, send me messages and I will save them to RedForester')
    await bot.delete_state(message.from_user.id, message.chat.id)


class MoveNodeCallbacks(Enum):
    request = "move-node-request"
    go_back = "move-node-go-back"
    to = "move-node-to-"


def create_move_to_keyboard(url):
    kbd = types.InlineKeyboardMarkup()
    kbd.add(
        types.InlineKeyboardButton(text="Open in the browser", url=url),
        types.InlineKeyboardButton(text="Move to ...", callback_data=MoveNodeCallbacks.request.value)
    )

    return kbd


async def _upload_file(ctx: UserContext, file_id: str, file_name: str) -> UploadFileData:
    file_info = await bot.get_file(file_id)
    file_content = await bot.download_file(file_info.file_path)

    return await upload_file_to_rf(ctx, file_content, file_name)


def _process_media(upload_info: UploadFileData, caption: Optional[str]):
    return (
        tg_html_to_rf_html(caption) if caption else '',
        [FileInfoDto(
            name=upload_info.file_name,
            filepath=upload_info.file_id,
            last_modified_timestamp=upload_info.timestamp,
            last_modified_user=upload_info.user_id
        )]
    )


async def process_message(ctx: UserContext, message):
    # html formatting customization
    message.custom_subs = CUSTOM_SUBS

    if message.text:
        content = tg_html_to_rf_html(message.html_text)
        files = None

    elif message.photo:
        photo = message.photo[-1]  # best quality photo

        file_name = f'image.jpg'  # always jpeg
        upload_info = await _upload_file(ctx, photo.file_id, file_name)
        content, files = _process_media(upload_info, message.html_caption)

        url = link_to_file(upload_info.file_id, file_name)
        content = f'<p><img src="{url}" height="{photo.height}" width="{photo.width}"></p>' + content

    elif message.audio:
        file_extension = guess_file_extension(message.audio.mime_type)
        file_name = sanitize_filename(
            f'{message.audio.title or "Unknown"} - {message.audio.performer or "Unknown"}{file_extension}')
        content, files = _process_media(await _upload_file(ctx, message.audio.file_id, file_name), message.html_caption)

    elif message.voice:
        # always .oga?
        file_extension = guess_file_extension(message.voice.mime_type)
        file_name = sanitize_filename(
            f'{message.voice.title or "Unknown"} - {message.voice.performer or "Unknown"}{file_extension}')
        content, files = _process_media(await _upload_file(ctx, message.voice.file_id, file_name), message.html_caption)

    elif message.video:
        file_extension = guess_file_extension(message.video.mime_type)
        file_name = f'video{file_extension}'
        content, files = _process_media(await _upload_file(ctx, message.video.file_id, file_name), message.html_caption)

    elif message.video_note:
        file_name = 'video_note.mp4'  # video_note has no mime type
        content, files = _process_media(await _upload_file(ctx, message.video_note.file_id, file_name), message.html_caption)

    elif message.document:
        file_name = sanitize_filename(message.document.file_name or 'unknown')
        content, files = _process_media(await _upload_file(ctx, message.document.file_id, file_name), message.html_caption)

    else:
        raise UnsupportedContentException()

    return content, files


def process_forwarded_message(message, content: str) -> str:
    source_url = None

    if message.forward_from:
        user = message.forward_from
        source_title = f'{user.last_name} {user.first_name}' if user.last_name else user.first_name
        if user.username:
            source_url = f'https://t.me/{user.username}'

    elif message.forward_from_chat:
        channel = message.forward_from_chat
        source_title = channel.title
        if channel.username:
            source_url = f'https://t.me/{channel.username}'
            if message.forward_from_message_id:
                source_url += f'/{message.forward_from_message_id}'

    else:
        return content

    source = f'<a href="{source_url}" target="_blank">{source_title}</a>' if source_url else source_title
    return f'<p>Forwarded from {source}:</p>' + content


class UnsupportedContentException(Exception):
    pass


@bot.message_handler(
    func=lambda m: True,
    content_types=['text', 'photo', 'audio', 'voice', 'video', 'video_note', 'document',
                   'location', 'venue', 'contact', 'sticker', 'animation']
)
async def main_handler(message):
    chat_id, ctx = get_or_create_context(message)

    if not ctx.is_authorized:
        return await bot.reply_to(message, 'You have to /start first')

    if not ctx.target:
        return await bot.reply_to(message, 'You have to /setup first')

    try:
        content, files = await process_message(ctx, message)

        content = process_forwarded_message(message, content)

        rf_node = await create_new_node(ctx, content, files)

        reply = await bot.reply_to(
            message,
            "Saved",  # todo add the path?
            reply_markup=create_move_to_keyboard(link_to_node(rf_node.map_id, rf_node.id))
        )

        create_node_context(ctx, message, rf_node.id, reply)

    except UnsupportedContentException:
        await bot.reply_to(message, 'Unsupported message type')

    except Exception as e:
        logger.exception(e)

        target_url = link_to_node(ctx.target.map_id, ctx.target.node_id)

        await bot.reply_to(
            message,
            f'Something went wrong. '
            f'Please check if you have access to the <a href="{target_url}">destination node</a> and try again',
        )


@bot.callback_query_handler(lambda query: query.data == MoveNodeCallbacks.go_back.value)
async def move_node_go_back(query):
    chat_id, ctx = get_or_create_context(query.message.reply_to_message)

    node_ctx = get_node_context(ctx, query.message.reply_to_message)

    try:
        node = await get_node(ctx, node_ctx.node_id)

        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=query.message.message_id,
            reply_markup=create_move_to_keyboard(link_to_node(node.map_id, node.id))
        )

        await bot.answer_callback_query(callback_query_id=query.id)
    except Exception as e:
        # todo better error handling
        logger.exception(e)
        await bot.answer_callback_query(
            callback_query_id=query.id,
            text="An error occurred. Check if the node still exist and can be accessed.",
            show_alert=True
        )


@bot.callback_query_handler(lambda query: query.data == MoveNodeCallbacks.request.value)
async def move_node_request(query):
    chat_id, ctx = get_or_create_context(query.message.reply_to_message)

    # todo handle errors?
    favorites = await get_favorite_nodes(ctx)

    back_button = types.InlineKeyboardButton(
        text="🔙 Go Back",
        callback_data=MoveNodeCallbacks.go_back.value
    )

    favorite_buttons = [types.InlineKeyboardButton(
        text=f"{fav.map.name} / {html_to_text(fav.title)}",
        callback_data=f"{MoveNodeCallbacks.to.value}{fav.id}"
    ) for fav in favorites if fav.title]

    kbd = types.InlineKeyboardMarkup(row_width=1)

    kbd.add(*favorite_buttons, back_button)

    await bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=query.message.message_id,
        reply_markup=kbd
    )

    await bot.answer_callback_query(callback_query_id=query.id)


@bot.callback_query_handler(lambda query: query.data.startswith(MoveNodeCallbacks.to.value))
async def move_node_to(query):
    chat_id, ctx = get_or_create_context(query.message.reply_to_message)

    node_ctx = get_node_context(ctx, query.message.reply_to_message)

    selected_node_id = query.data.split(MoveNodeCallbacks.to.value)[1]

    try:
        root = await move_node(ctx, node_ctx.node_id, selected_node_id)

        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=query.message.message_id,
            reply_markup=create_move_to_keyboard(link_to_node(root.map_id, root.id))
        )

        await bot.answer_callback_query(
            callback_query_id=query.id,
            text="The node has been moved"
        )
    except Exception as e:
        logger.exception(e)

        await bot.answer_callback_query(
            callback_query_id=query.id,
            text="An error occurred. Check if you have access to the node.",
            show_alert=True
        )


if __name__ == '__main__':
    init_db()

    logger.info('Polling is started')
    asyncio.run(bot.infinity_polling())
