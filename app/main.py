import os

import telebot
from telebot import apihelper

from app.logger import logger
from app.guards import Guards
from app.rf_tasks import create_new_node, login_to_rf, execute
from app.user_context import init_db, get_or_create_context, del_context, TargetNode
from app.utils import link_to_node, parse_node_link


logger.info('RedForester Keeper bot is started!')

bot = telebot.TeleBot(os.getenv('RF_KEEPER_TOKEN'))

apihelper.ENABLE_MIDDLEWARE = True


@bot.middleware_handler(update_types=['message'])
def log_message(bot_instance, message):
    logger.info(f"Incoming message from chat: {message.chat.id}")


GREET = 'Hi! I am RedForester Keeper bot'
ABOUT = 'I will save your messages as nodes to a specific branch on your map'
COMMANDS = (
    'Available commands are:\n'
    '/start\n'
    '/setup\n'
    '/stop\n'
)


@bot.message_handler(commands=['help'])
def help(message):
    bot.reply_to(
        message,
        f'{GREET}.\n'
        f'{ABOUT}.\n'
        '\n'
        f'{COMMANDS}\n'
        f'<a href="https://github.com/RedForester/rf_keeper_telegram">Bot source code</a>',
        parse_mode='HTML'
    )


@bot.message_handler(commands=['start'])
def start(message):
    chat_id, ctx = get_or_create_context(message)

    if Guards.is_authorized(ctx):
        return bot.reply_to(message, 'We\'ve already started. To logout from your account type /stop')

    msg = bot.reply_to(
        message,
        f'{GREET}.\n'
        f'{ABOUT}.\n'
        '\n'
        'Let\'s start, type your username (email) from your RedForester account or /cancel:'
    )
    bot.register_next_step_handler(msg, start_get_username)


def start_get_username(message):
    if Guards.is_cancel(message) or Guards.is_command(message):
        return bot.reply_to(message, 'Action was canceled. Type /start to repeat')

    chat_id, ctx = get_or_create_context(message)
    ctx.username = message.text
    ctx.save()

    msg = bot.send_message(
        chat_id,
        'And then type your password or /cancel:'
    )
    bot.register_next_step_handler(msg, start_get_password)


def start_get_password(message):
    if Guards.is_cancel(message) or Guards.is_command(message):
        return bot.reply_to(message, 'Action was canceled. Type /start to repeat')

    chat_id, ctx = get_or_create_context(message)

    password = message.text

    try:
        rf_user = execute(login_to_rf(ctx.username, password))

        # fixme
        #  Yes, this is extremely bad to store unhashed password, but I have no choice for now.
        #  If you really concern - self host this bot.
        #  Meanwhile I am trying to create better solution.
        ctx.password = password
        ctx.is_authorized = True
        ctx.save()

        msg = bot.send_message(
            chat_id,
            f'Hi, {rf_user.surname} {rf_user.name}!\n'
            f'Your login and password is correct!\n'
            f'\n'
            f'Now, paste URL to the destination node:\n'
        )
        bot.register_next_step_handler(msg, setup_complete)

    except Exception as e:
        logger.exception(e)

        msg = bot.send_message(
            chat_id,
            'Something went wrong. Please try again or type /cancel\n'
            'Type your username (email):'
        )
        bot.register_next_step_handler(msg, start_get_username)

    finally:
        bot.delete_message(chat_id, message.message_id)


@bot.message_handler(commands=['setup'])
def setup_init(message):
    chat_id, ctx = get_or_create_context(message)

    if not Guards.is_authorized(ctx):
        return bot.reply_to(message, 'You have to /start first')

    target = link_to_node(ctx.target.map_id, ctx.target.node_id) if ctx.target else None
    status_text = f'Current destination node is {target}' if target else 'Destination node is not specified'

    msg = bot.reply_to(
        message,
        f'{status_text}\n'
        '\n'
        'Please paste link to the new destination node or type /cancel:'
    )
    bot.register_next_step_handler(msg, setup_complete)


def setup_complete(message):
    if Guards.is_cancel(message) or Guards.is_command(message):
        return bot.reply_to(message, 'Action was canceled. Type /setup to repeat')

    chat_id, ctx = get_or_create_context(message)

    map_id, node_id = parse_node_link(message.text)

    if not map_id or not node_id:
        return bot.send_message(chat_id, 'Node link is incorrect, please try again with /setup command')

    ctx.target = TargetNode.create(node_id=node_id, map_id=map_id)
    ctx.save()

    bot.send_message(chat_id, 'Setup is complete, send me messages and I will save them to RedForester')


@bot.message_handler(commands=['stop'])
def stop(message):
    del_context(message)
    bot.reply_to(message, 'Done')


@bot.message_handler(func=lambda m: True)
def catch_all(message):
    chat_id, ctx = get_or_create_context(message)

    if Guards.is_cancel(message):
        return bot.reply_to(message, 'Nothing to cancel')

    if Guards.is_command(message):
        return bot.reply_to(
            message,
            'Unsupported command\n'
            f'{COMMANDS}'
        )

    if not Guards.is_authorized(ctx):
        return bot.reply_to(message, 'You have to /start first')

    if not Guards.is_setup_completed(ctx):
        return bot.reply_to(message, 'You have to /setup first')

    try:
        rf_node = execute(create_new_node(ctx, message.text))
        url = link_to_node(rf_node.map_id, rf_node.id)

        bot.reply_to(message, f'<a href="{url}">Saved to RedForester</a>', parse_mode='HTML')

    except Exception as e:
        logger.exception(e)

        target_url = link_to_node(ctx.target.map_id, ctx.target.node_id)

        bot.reply_to(
            message,
            'Something went wrong. Please check if you have access to the destination node and try again\n'
            f'<a href="{target_url}">Destination node</a>',
            parse_mode='HTML'
        )


if __name__ == '__main__':
    init_db()
    logger.info("Database initialized")

    logger.info('Polling is started')
    bot.infinity_polling()
