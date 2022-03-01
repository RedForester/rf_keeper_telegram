# RedForester Keeper bot for Telegram

[Link to the bot](https://t.me/redforester_keeper_bot) | [Support email](mailto:support@redforester.com)

## Self-hosting

This app should be compatible with Heroku deployment.

In general, to run this app you have to execute the following steps:
- [Create the bot](https://core.telegram.org/bots#6-botfather)
- Prepare Python 3.7+ environment
- Run the PostgreSQL database (Tested with Postgres 11)
- Fill environment variables:
  - `RF_KEEPER_TOKEN` - token from BotFather
  - `PGHOST`
  - `PGDATABASE`
  - `PGUSER`
  - `PGPASSWORD`
- Run the `main.py` script
