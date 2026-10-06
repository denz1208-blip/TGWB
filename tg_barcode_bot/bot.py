"""Telegram-бот, отслеживающий новые штрихкоды (ШК) в публичной Google Таблице.

Команды:
  /start   — подключить уведомления для этого чата
  /stop    — отключить уведомления
  /status  — показать статус подписки и число известных ШК
  /help    — справка

При первом запуске бот запоминает все текущие ШК как «известные» и не рассылает их.
Далее каждые POLL_INTERVAL секунд проверяет таблицу и присылает всем подписчикам
сообщения о новых ШК.
"""
import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import config
from sheet import fetch_new_barcodes
from state import State

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("barcode-bot")

state = State(config.STATE_FILE)
dp = Dispatcher()


def _validate_token() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен от @BotFather."
        )


bot: Bot = None  # инициализируется в main()


# ----------------------------- Команды -------------------------------------

HELP_TEXT = (
    "🔎 <b>Бот отслеживания новых ШК</b>\n\n"
    f"Слежу за таблицей: {config.GOOGLE_SHEET_URL}\n\n"
    "<b>Команды:</b>\n"
    "/start — включить уведомления\n"
    "/stop — выключить уведомления\n"
    "/status — текущий статус\n"
    "/help — эта справка\n\n"
    f"Проверка таблицы выполняется каждые {config.POLL_INTERVAL} сек."
)


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    added = state.subscribe(message.chat.id)
    state.save()
    if added:
        await message.answer(
            "✅ Уведомления о новых ШК включены!\n"
            f"В таблице уже известно {len(state.seen_barcodes)} ШК — "
            "будут приходить только те, что появятся позже.\n\n"
            f"Подписка действует для чата <code>{message.chat.id}</code>."
        )
    else:
        await message.answer("👍 Вы уже подписаны на уведомления.")


@dp.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    removed = state.unsubscribe(message.chat.id)
    state.save()
    if removed:
        await message.answer("🔕 Уведомления отключены. Вернуть — /start")
    else:
        await message.answer("Вы и так не подписаны. Включить — /start")


@dp.message(Command("status"))
async def cmd_status(message: Message) -> None:
    subscribed = message.chat.id in state.subscribers
    await message.answer(
        "📊 <b>Статус</b>\n"
        f"Подписка этого чата: {'✅ включена' if subscribed else '❌ выключена'}\n"
        f"Известных ШК: <code>{len(state.seen_barcodes)}</code>\n"
        f"Всего подписчиков: <code>{len(state.subscribers)}</code>\n"
        f"Интервал проверки: <code>{config.POLL_INTERVAL}</code> сек."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@dp.message(~F.text.startswith("/"))
async def cmd_unknown(message: Message) -> None:
    await message.answer("Не понимаю 🤔 Список команд: /help")


# --------------------------- Мониторинг таблицы -----------------------------

def format_barcode_message(barcode: str, row: dict) -> str:
    """Форматирует сообщение об одном новом ШК по данным строки таблицы."""
    fields = [
        ("Дата создания", "📅"),
        ("ID", "🆔"),
        ("ФИО", "👤"),
        ("Статус", "📌"),
        ("Решение по заявке", "⚖️"),
    ]
    lines = [f"🆕 <b>Новый ШК:</b> <code>{barcode}</code>"]
    for name, icon in fields:
        value = row.get(name, "")
        if value:
            lines.append(f"{icon} {name}: <b>{value}</b>")
    return "\n".join(lines)


async def send_to_subscribers(text: str) -> None:
    for chat_id in list(state.subscribers):
        try:
            await bot.send_message(chat_id, text)
        except Exception as e:  # noqa: BLE001 - логируем и продолжаем
            log.warning("Не удалось отправить %s: %s", chat_id, e)


async def poll_sheet(session: aiohttp.ClientSession) -> None:
    """Один цикл проверки таблицы: находит новые ШК и рассылает их."""
    try:
        known = await fetch_new_barcodes(session, config.GOOGLE_SHEET_URL, config.BARCODE_COLUMN)
    except Exception as e:  # noqa: BLE001
        log.error("Ошибка чтения таблицы: %s", e)
        return

    first_run = not state.seen_barcodes and len(known) > 0

    new_codes = [c for c in known if not state.is_seen(c)]
    for code in new_codes:
        state.add_seen(code)

    if first_run:
        # Первый запуск: запоминаем всё существующее, ничего не рассылаем
        state.save()
        log.info("Первый запуск: запомнено %d существующих ШК", len(known))
        return

    if new_codes:
        log.info("Найдено новых ШК: %d", len(new_codes))
        for code in new_codes:
            await send_to_subscribers(format_barcode_message(code, known[code]))
            await asyncio.sleep(0.1)  # бережём лимиты Telegram API
        state.save()


async def monitor_loop() -> None:
    async with aiohttp.ClientSession() as session:
        while True:
            await poll_sheet(session)
            await asyncio.sleep(config.POLL_INTERVAL)


# --------------------------------- Запуск -----------------------------------

async def main() -> None:
    _validate_token()

    global bot
    bot = Bot(token=config.BOT_TOKEN)

    # Инициализация команд в меню Telegram
    from aiogram.types import BotCommand

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Включить уведомления"),
            BotCommand(command="stop", description="Выключить уведомления"),
            BotCommand(command="status", description="Статус подписки"),
            BotCommand(command="help", description="Справка"),
        ]
    )

    log.info("Бот запущен. Интервал опроса: %d сек.", config.POLL_INTERVAL)

    monitor_task = asyncio.create_task(monitor_loop())
    try:
        await dp.start_polling(bot)
    finally:
        monitor_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
