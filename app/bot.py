from maxapi import Bot

_bot: Bot | None = None


def init_bot(bot: Bot):
    global _bot
    _bot = bot


def get_bot() -> Bot:
    if _bot is None:
        raise RuntimeError("Bot is not inited")
    return _bot
