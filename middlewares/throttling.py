# epicservice/middlewares/throttling.py

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from cachetools import TTLCache

logger = logging.getLogger(__name__)

class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware для захисту від флуду (частих натискань).
    Якщо користувач надсилає запити частіше, ніж дозволено (rate_limit),
    бот їх ігнорує або відповідає попередженням.
    """

    def __init__(self, rate_limit: float = 0.7):
        # Кеш з часом життя (TTL) дорівнює rate_limit.
        # Якщо запис є в кеші — значить, ліміт перевищено.
        # maxsize=10000 — зберігаємо дані про 10k активних юзерів одночасно.
        self.cache = TTLCache(maxsize=10000, ttl=rate_limit)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        
        # Працюємо тільки з повідомленнями та колбеками
        user = data.get("event_from_user")
        
        if user:
            # Якщо користувач є в кеші — блокуємо дію
            if user.id in self.cache:
                # Для CallbackQuery можна відповісти спливаючим вікном, щоб не було відчуття, що бот завис
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("⏳ Не так швидко! Зачекайте трішки.", show_alert=False)
                    except Exception:
                        pass
                # Перериваємо обробку (handler не викликається)
                return

            # Якщо користувача немає в кеші — додаємо його (позначаємо, що він щойно зробив дію)
            self.cache[user.id] = True

        # Пропускаємо далі
        return await handler(event, data)