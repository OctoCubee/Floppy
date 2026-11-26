import asyncio
import logging

# Configure logging before importing the bot so import-time messages show up.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from hypercorn.config import Config
from hypercorn.asyncio import serve
from main import get_bot
from dash import app
from messenger import messenger_app

log = logging.getLogger("floppy.entrypoint")

# Mount messenger routes onto the main dash app under /messenger
app.register_blueprint(messenger_app, url_prefix="/messenger")


async def run_bot(bot, token):
    while True:
        try:
            await bot.start(token)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Bot crashed — restarting in 5s")
            try:
                await bot.close()
            except Exception:
                pass
            await asyncio.sleep(5)
        else:
            log.warning("Bot.start() returned cleanly — restarting in 5s")
            await asyncio.sleep(5)


async def run_web(hypercorn_config):
    """Keep the web server alive independently of the bot."""
    while True:
        try:
            await serve(app, hypercorn_config)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Web server crashed — restarting in 5s")
            await asyncio.sleep(5)


async def main():
    bot, token = get_bot()

    hypercorn_config = Config()
    hypercorn_config.bind = ["0.0.0.0:8080"]

    bot_task = asyncio.create_task(run_bot(bot, token))
    web_task = asyncio.create_task(run_web(hypercorn_config))

    # return_exceptions=True so one task's failure never cancels the other.
    await asyncio.gather(bot_task, web_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
