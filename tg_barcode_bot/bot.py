"""Telegram-бот, отслеживающий новые штрихкоды (ШК) в публичной Google Таблице.

Уведомления приходят ТОЛЬКО по подпискам (кнопки/команды), причём:
  * колонка «Статус» в строке таблицы пуста;
  * ID сотрудника из колонки «ID» входит в список отслеживаемых (настраивается).

Интерфейс — кнопки reply-клавиатуры + inline-кнопки. Текст без HTML-разметки.
"""
import asyncio
import logging
import os
import re
import subprocess

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import config
from sheet import fetch_barcodes, fetch_barcodes_by_employee
from state import State

# Версия бота. Увеличивайте при каждом изменении кода!
# Отображается в /help, /status, /version и в логе запуска.
BOT_VERSION = "2.1.3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("barcode-bot")

state = State(config.STATE_FILE, initial_employee_ids=config.TARGET_EMPLOYEE_IDS)
dp = Dispatcher()


def git_commit() -> str:
    """Короткий хеш последнего коммита (если рядом есть git-репозиторий).

    Позволяет по /help и /status понять, какой именно код сейчас запущен,
    и обновился ли бот после git pull. Кэш — чтобы не дёргать git на каждое
    сообщение.
    """
    if not hasattr(git_commit, "_cache"):
        try:
            out = subprocess.run(
                ["git", "-C", os.path.dirname(os.path.abspath(__file__)),
                 "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=3,
            )
            git_commit._cache = out.stdout.strip() or "?"
        except Exception:  # noqa: BLE001
            git_commit._cache = "?"
    return git_commit._cache


def version_line() -> str:
    return f"Версия: {config.BOT_VERSION} (код: {git_commit()})"


# --------------------------- Ограничение доступа ------------------------------
# Белый список Telegram ID (ALLOWED_USER_IDS в .env и/или команда /access add).
# Пока список пуст — доступ разрешён всем. /start запрещённым показывает их ID,
# чтобы владелец мог добавить человека в белый список.

def request_kb(uid: int) -> InlineKeyboardMarkup:
    """Inline-кнопки «Разрешить / Запретить» для неавторизованного пользователя."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Разрешить доступ", callback_data=f"acc:add:{uid}"),
                InlineKeyboardButton(text="🚫 Отклонить", callback_data=f"acc:deny:{uid}"),
            ]
        ]
    )


@dp.message(lambda m: not state.is_allowed(m.from_user.id if m.from_user else None))
async def access_denied(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    username = getattr(message.from_user, "username", "") or ""
    who = f"@{username}" if username else (getattr(message.from_user, "full_name", "") or "неизвестный")
    log.info("Отказано в доступе пользователю %s (%s)", uid, who)

    # Если доступ открыт (.env пуст) — просто отвечаем; сюда заходим только
    # когда список задан и пользователя в нём нет.
    admins = sorted(config.ALLOWED_USER_IDS | state.allowed_users)
    if admins and uid:
        # уведомляем админов о запросе доступа
        text = (
            f"🔐 Запрос доступа к боту\n"
            f"Кто: {who}\n"
            f"Telegram ID: {uid}\n"
            f"Добавить: /access add {uid}"
        )
        for admin_id in admins:
            try:
                await bot.send_message(admin_id, text, reply_markup=request_kb(uid))
            except Exception as e:  # noqa: BLE001
                log.warning("Не удалось уведомить админа %s: %s", admin_id, e)

    await message.answer(
        "⛔ Доступ к боту закрыт.\n\n"
        f"Ваш Telegram ID: {uid}\n"
        "Попросите владельца добавить вас командой:\n"
        f"/access add {uid}"
    )

bot: Bot = None  # инициализируется в main()

LOOKUP_COUNT = 20  # сколько последних ШК показывать по ID


# ----------------------------- Клавиатуры -----------------------------------

def main_kb(subscribed: bool) -> ReplyKeyboardMarkup:
    """Главное меню (постоянные кнопки под полем ввода)."""
    sub_btn = "🔕 Выключить" if subscribed else "🔔 Включить"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 Мои новые ШК"), KeyboardButton(text=sub_btn)],
            [KeyboardButton(text="🔎 Поиск по ID"), KeyboardButton(text="👥 Отслеживание")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def lookup_kb(ids: list[str]) -> InlineKeyboardMarkup:
    """Inline-кнопки «🔎 {ID}» для быстрого просмотра последних ШК по ID."""
    rows = [[InlineKeyboardButton(text=f"🔎 {x}", callback_data=f"look:{x}")] for x in ids[:10]]
    for x in ids[:10]:
        rows.append([InlineKeyboardButton(text=f"➕ Отслеживать {x}", callback_data=f"track:{x}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _validate_token() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен от @BotFather."
        )


# --------------------------- Общие тексты ------------------------------------

def filter_line() -> str:
    if state.employee_ids:
        return "ID сотрудников: " + ", ".join(sorted(state.employee_ids))
    return "ID сотрудников: все (добавьте конкретные в разделе 👥 Отслеживание)"


def access_line() -> str:
    lst = sorted(state.allowed_ids())
    if not lst:
        return "Доступ: открыт для всех (ограничьте через /access add <ID>)"
    return f"Доступ: закрытый режим, разрешён {len(lst)} пользовател(ям): " + \
        ", ".join(str(x) for x in lst[:20])


def help_text() -> str:
    return (
        "🔎 Бот отслеживания новых ШК\n"
        f"{version_line()}\n"
        f"Слежу за таблицей каждые {config.POLL_INTERVAL} сек.\n\n"
        "⚙️ Фильтр уведомлений:\n"
        f"• Колонка «{config.STATUS_COLUMN}» пустая\n"
        f"• {filter_line()}\n\n"
        f"{access_line()}\n\n"
        "Кнопки меню:\n"
        "🆕 Мои новые ШК — последние уведомления\n"
        "🔎 Поиск по ID — последние 20 ШК любого сотрудника\n"
        "👥 Отслеживание — настройка ID для уведомлений\n"
        "🔔/🔕 — включить/выключить уведомления\n\n"
        "Команды доступа:\n"
        "/access — список разрешённых\n"
        "/access add <Telegram ID> — разрешить\n"
        "/access remove <Telegram ID> — запретить\n"
        "/access clear — открыть бота для всех"
    )


# ------------------------------ Команды --------------------------------------

@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "🔎 Привет! Я слежу за новыми ШК в Google Таблице.\n\n"
        "Уведомления настроены так:\n"
        "• приходит только новый ШК с ПУСТЫМ статусом;\n"
        "• и только если ID сотрудника из таблицы входит в ваш список отслеживания.\n\n"
        f"{filter_line()}\n\n"
        "Включить/выключить рассылку можно кнопкой ниже или командой /subscribe.",
        reply_markup=main_kb(message.chat.id in state.subscribers),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(help_text(), reply_markup=main_kb(message.chat.id in state.subscribers))


@dp.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")


@dp.message(Command("version"))
async def cmd_version(message: Message) -> None:
    import datetime
    import os as _os
    code_dir = os.path.dirname(os.path.abspath(__file__))
    mtime = _os.path.getmtime(_os.path.join(code_dir, "bot.py"))
    updated = datetime.datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
    await message.answer(
        f"{version_line()}\n"
        f"Файл bot.py обновлён: {updated}"
    )


@dp.message(Command("status"))
async def cmd_status(message: Message) -> None:
    subscribed = message.chat.id in state.subscribers
    last = state.last_lookup_id or "—"
    await message.answer(
        "📊 Статус\n"
        f"{version_line()}\n"
        f"Подписка этого чата: {'✅ включена' if subscribed else '❌ выключена'}\n"
        f"Известных ШК: {len(state.seen_barcodes)}\n"
        f"Последний просмотренный ID: {last}\n"
        f"{filter_line()}\n"
        f"{access_line()}\n"
        f"Интервал проверки: {config.POLL_INTERVAL} сек.",
        reply_markup=main_kb(subscribed),
    )


@dp.message(Command("subscribe"))
async def cmd_subscribe(message: Message) -> None:
    added = state.subscribe(message.chat.id)
    state.save()
    text = (
        "✅ Уведомления включены!\n"
        f"В таблице уже известно {len(state.seen_barcodes)} ШК — приходить будут только новые."
        if added
        else "👍 Вы уже подписаны на уведомления."
    )
    await message.answer(text, reply_markup=main_kb(True))


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message) -> None:
    removed = state.unsubscribe(message.chat.id)
    state.save()
    text = (
        "🔕 Уведомления отключены."
        if removed
        else "Вы и так не подписаны."
    )
    await message.answer(text, reply_markup=main_kb(False))


# ------------------------- Кнопки основного меню ------------------------------

@dp.message(F.text == "ℹ️ Помощь")
async def kb_help(message: Message) -> None:
    await cmd_help(message)


@dp.message(F.text.in_({"🔔 Включить", "🔕 Выключить"}))
async def kb_toggle_sub(message: Message) -> None:
    if message.text.startswith("🔔"):
        await cmd_subscribe(message)
    else:
        await cmd_unsubscribe(message)


@dp.message(F.text == "🆕 Мои новые ШК")
async def kb_my_new(message: Message) -> None:
    items = list(state.newest_notifications.items())
    items.reverse()  # сначала самые свежие
    if not items:
        await message.answer(
            "Пока новых ШК не приходило.\n"
            "Как только в таблице появится ШК с пустым статусом и вашим ID — сообщу.",
            reply_markup=main_kb(message.chat.id in state.subscribers),
        )
        return
    lines = ["🆕 Последние новые ШК (сначала свежие):"]
    for code, row in items[:10]:
        parts = [f"• {code}"]
        if row.get("Дата создания"):
            parts.append(f"от {row['Дата создания']}")
        if row.get("ФИО"):
            parts.append(row["ФИО"])
        if row.get("ID"):
            parts.append(f"ID {row['ID']}")
        lines.append(" | ".join(parts))
    await message.answer("\n".join(lines))


@dp.message(F.text == "👥 Отслеживание")
async def kb_tracking(message: Message) -> None:
    ids = ", ".join(sorted(state.employee_ids)) if state.employee_ids else "— пусто —"
    await message.answer(
        "👥 Отслеживание сотрудников\n\n"
        f"Сейчас уведомления настроены на ID: {ids}\n\n"
        "Чтобы изменить список, отправьте мне числовые ID сотрудников из таблицы:\n"
        "• через запятую или пробел — заменит весь список,\n"
        "• со знаком «+» перед каждым (например: +112946 +5994498) — добавит к текущему,\n"
        "• команда /ids clear — очистит список (будут приходить ШК всех сотрудников\n"
        "  с пустым статусом).\n\n"
        "Пример: 112946, 5994498",
        reply_markup=main_kb(message.chat.id in state.subscribers),
    )


@dp.message(Command("ids"))
async def cmd_ids(message: Message) -> None:
    arg = (message.text or "").split(maxsplit=1)
    action = arg[1].strip().lower() if len(arg) > 1 else ""
    if action in ("clear", "очистить"):
        state.employee_ids = set()
        state.save()
        await message.answer("🗑 Список ID очищен — слежу за всеми сотрудниками (с пустым статусом).")
        await kb_tracking(message)
        return
    await kb_tracking(message)


# --------------------------- Управление доступом ------------------------------

def _access_status_text() -> str:
    lst = sorted(state.allowed_ids())
    env_ids = ", ".join(str(x) for x in sorted(config.ALLOWED_USER_IDS)) or "—"
    state_ids = ", ".join(str(x) for x in sorted(state.allowed_users)) or "—"
    return (
        "🔐 Управление доступом\n\n"
        f"{access_line()}\n\n"
        f"Из .env (ALLOWED_USER_IDS): {env_ids}\n"
        f"Добавлены через /access: {state_ids}\n\n"
        "Команды:\n"
        "/access add <Telegram ID> — разрешить пользователя\n"
        "/access remove <Telegram ID> — запретить\n"
        "/access clear — очистить список из /access\n"
        "(чтобы полностью открыть бота, уберите и ALLOWED_USER_IDS из .env)\n\n"
        "Узнать чей-то Telegram ID: пусть человек напишет боту /id."
    )


@dp.message(Command("access"))
async def cmd_access(message: Message) -> None:
    parts = (message.text or "").split()
    action = parts[1].lower() if len(parts) > 1 else ""
    ids = [int(x) for x in parts[2:] if x.isdigit()]

    if action == "add":
        if not ids:
            await message.answer("Укажите Telegram ID. Пример: /access add 810321569")
            return
        added = state.add_allowed(ids)
        state.save()
        await message.answer(
            f"✅ Разрешён доступ: {', '.join(map(str, added)) if added else 'уже были в списке'}\n"
            + _access_status_text()
        )
    elif action in ("remove", "del", "удалить"):
        if not ids:
            await message.answer("Укажите Telegram ID. Пример: /access remove 123456789")
            return
        removed = state.remove_allowed(ids)
        state.save()
        await message.answer(
            f"🚫 Запрещён доступ: {', '.join(map(str, removed)) if removed else 'их не было в списке'}\n"
            + _access_status_text()
        )
    elif action in ("clear", "очистить"):
        state.clear_allowed()
        state.save()
        await message.answer("🗑 Список /access очищен.\n" + _access_status_text())
    else:
        await message.answer(_access_status_text())


@dp.message(F.text == "🔎 Поиск по ID")
async def kb_search_ask(message: Message) -> None:
    remembered = f" Последний запрошенный ID: {state.last_lookup_id}" if state.last_lookup_id else ""
    await message.answer(
        "🔎 Введите ID сотрудника из таблицы — покажу последние "
        f"{LOOKUP_COUNT} его ШК (с датами и статусами)."
        f"{remembered}",
    )


@dp.message(~F.text.startswith("/"))
async def handle_text(message: Message) -> None:
    text = (message.text or "").strip()
    nums = [x for x in re.split(r"[,\s;]+", text.replace("+", " ")) if x.isdigit()]

    # 1) Если ждём ввод ID для поиска — ищем сразу
    waiting = message.chat.id in waiting_for_lookup
    if waiting:
        waiting_for_lookup.discard(message.chat.id)
        if not nums:
            await message.answer(
                "Не похоже на ID. Пример: 112946",
                reply_markup=main_kb(message.chat.id in state.subscribers),
            )
            return
        await do_lookup(message, nums[0])
        return

    # 2) Ввод состоит только из чисел — предлагаем кнопки «посмотреть» и «+добавить»
    tokens = _tokens(text)
    if nums and all(t.startswith("+") or t.isdigit() for t in tokens):
        if any(t.startswith("+") for t in tokens):
            added = state.add_employee_ids(nums)
            state.save()
            await message.answer(
                f"✅ Добавлено в отслеживание: {', '.join(added) if added else 'уже были в списке'}\n"
                f"Текущий список: {', '.join(sorted(state.employee_ids))}"
            )
            await kb_tracking(message)
        else:
            ids_list = ", ".join(sorted(state.employee_ids)) if state.employee_ids else "—"
            lines = [f"🔎 Что сделать с ID {', '.join(nums)}?"]
            lines += [
                "",
                "• Нажмите кнопку 🔎 — покажу последние " + str(LOOKUP_COUNT) + " ШК этого сотрудника;",
                f"• отправьте «+{nums[0]}» — добавлю этот ID в отслеживание (уведомления",
                "  о новых ШК с пустым статусом);",
                f"• /ids clear — очистить текущий список.",
                "",
                f"Сейчас в отслеживании: {ids_list}",
            ]
            await message.answer("\n".join(lines), reply_markup=lookup_kb(nums))
        return

    # 3) Просто число — тоже считаем запросом поиска
    if text.isdigit():
        await do_lookup(message, text)
        return

    await message.answer(
        "Не понимаю 🤔 Отправьте ID сотрудника (например, 112946) или выберите действие кнопкой.",
        reply_markup=main_kb(message.chat.id in state.subscribers),
    )


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[,\s;]+", text) if t]


waiting_for_lookup: set[int] = set()


# ------------------------------ Поиск по ID ----------------------------------

async def do_lookup(message: Message, emp_id: str) -> None:
    state.last_lookup_id = emp_id  # запоминаем навсегда
    state.save()

    msg = await message.answer(f"⏳ Ищу ШК для ID {emp_id}…")
    text = await build_lookup_text(emp_id)
    await msg.edit_text(
        text,
        reply_markup=main_kb(message.chat.id in state.subscribers),
    )


async def do_lookup_message(src: Message, emp_id: str) -> None:
    """Поиск по ID из inline-кнопки (отвечаем в тот же чат)."""
    state.last_lookup_id = emp_id  # запоминаем навсегда
    state.save()
    text = await build_lookup_text(emp_id)
    await src.reply(
        text,
        reply_markup=main_kb(src.chat.id in state.subscribers),
    )


async def build_lookup_text(emp_id: str) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            rows = await fetch_barcodes_by_employee(
                session,
                config.GOOGLE_SHEET_URL,
                config.BARCODE_COLUMN,
                config.EMPLOYEE_ID_COLUMN,
                emp_id,
            )
        except Exception as e:  # noqa: BLE001
            return f"❌ Ошибка чтения таблицы: {e}"

    name = next((r["name"] for r in rows if r["name"]), "")
    who = f" ({name})" if name else ""
    if not rows:
        return f"🔎 По ID {emp_id}{who} в таблице нет ни одного ШК."

    shown = rows[:LOOKUP_COUNT]
    lines = [
        f"🔎 ID {emp_id}{who}: всего ШК — {len(rows)}.",
        f"Последние {len(shown)} (сначала свежие):",
        "",
    ]
    for i, r in enumerate(shown, 1):
        status = r["status"] if r["status"] else "без статуса"
        line = f"{i}. {r['barcode']}"
        if r["date"]:
            line += f" · {r['date']}"
        line += f" · 📌 {status}"
        lines.append(line)
        if r["decision"]:
            lines.append(f"     ⚖️ {r['decision']}")
    if len(rows) > LOOKUP_COUNT:
        lines.append(f"\n…и ещё {len(rows) - LOOKUP_COUNT} более ранних.")

    # Telegram ограничивает сообщение 4096 символами
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n…"
    return text


# --------------------------- Мониторинг таблицы -----------------------------

def format_barcode_message(barcode: str, row: dict) -> str:
    """Форматирует сообщение об одном новом ШК (plain text, без HTML)."""
    fields = [
        ("Дата создания", "📅"),
        ("ID", "🆔"),
        ("ФИО", "👤"),
        ("Решение по заявке", "⚖️"),
    ]
    lines = [f"🆕 Новый ШК: {barcode}"]
    for name, icon in fields:
        value = row.get(name, "")
        if value:
            lines.append(f"{icon} {name}: {value}")
    return "\n".join(lines)


async def send_to_subscribers(text: str, reply_markup=None) -> None:
    allowed = state.allowed_ids()
    for chat_id in list(state.subscribers):
        if allowed and chat_id not in allowed:
            continue  # доступ запрещён — не рассылаем
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception as e:  # noqa: BLE001
            log.warning("Не удалось отправить %s: %s", chat_id, e)


async def poll_sheet(session: aiohttp.ClientSession) -> None:
    """Один цикл проверки таблицы: находит новые подходящие ШК и рассылает их."""
    try:
        known = await fetch_barcodes(
            session,
            config.GOOGLE_SHEET_URL,
            config.BARCODE_COLUMN,
            status_column=config.STATUS_COLUMN,
            employee_id_column=config.EMPLOYEE_ID_COLUMN,
            target_employee_ids=state.employee_ids,
        )
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
        log.info("Первый запуск: запомнено %d подходящих ШК", len(known))
        return

    if new_codes:
        log.info("Найдено новых подходящих ШК: %d", len(new_codes))
        for code in new_codes:
            state.push_notification(code, known[code])
            await send_to_subscribers(format_barcode_message(code, known[code]))
            await asyncio.sleep(0.1)  # бережём лимиты Telegram API
        state.save()


async def monitor_loop() -> None:
    async with aiohttp.ClientSession() as session:
        while True:
            await poll_sheet(session)
            await asyncio.sleep(config.POLL_INTERVAL)


# ------------------------------ Inline-кнопки --------------------------------

@dp.callback_query(F.data.startswith("look:"))
async def cb_lookup(call: CallbackQuery) -> None:
    emp_id = call.data.split(":", 1)[1]
    await call.answer(f"Ищу ШК для ID {emp_id}…")
    await do_lookup_message(call.message, emp_id)


@dp.callback_query(F.data.startswith("track:"))
async def cb_track(call: CallbackQuery) -> None:
    emp_id = call.data.split(":", 1)[1]
    added = state.add_employee_ids([emp_id])
    state.save()
    await call.answer(
        "Добавлено в отслеживание" if added else "Уже отслеживается"
    )
    await call.message.reply(
        f"✅ Теперь слежу за ID {emp_id}: буду присылать его новые ШК с пустым статусом.\n"
        f"Список отслеживания: {', '.join(sorted(state.employee_ids))}"
    )


# --------------------------- Inline-кнопки доступа ----------------------------

@dp.callback_query(F.data.startswith("acc:"))
async def cb_access(call: CallbackQuery) -> None:
    action, _, uid_str = call.data.partition(":")
    action = action.split(":", 1)[1]  # add / deny
    uid = int(uid_str)
    if action == "add":
        added = state.add_allowed([uid])
        state.save()
        await call.message.edit_text(
            f"✅ Пользователю {uid} разрешён доступ."
            + ("" if added else " (он уже был в списке)")
            + f"\n{access_line()}"
        )
        await call.answer("Разрешено")
    else:
        await call.message.edit_text(
            f"🚫 Никому ничего не разрешил — кнопка «Запретить» просто закрыла это сообщение."
        )
        await call.answer("Отклонено")


# --------------------------------- Запуск -----------------------------------

async def main() -> None:
    _validate_token()

    global bot
    bot = Bot(token=config.BOT_TOKEN)

    from aiogram.types import BotCommand

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="subscribe", description="Включить уведомления"),
            BotCommand(command="unsubscribe", description="Выключить уведомления"),
            BotCommand(command="status", description="Статус и фильтры"),
            BotCommand(command="ids", description="Настройка ID сотрудников"),
            BotCommand(command="access", description="Управление доступом пользователей"),
            BotCommand(command="help", description="Справка"),
            BotCommand(command="version", description="Версия бота"),
        ]
    )

    # Сбрасываем webhook (если он был задан), иначе getUpdates/polling не получит апдейты.
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:  # noqa: BLE001
        log.warning("delete_webhook не выполнен: %s", e)

    log.info("Бот запущен. Версия: %s (код: %s). Интервал опроса: %d сек.",
             config.BOT_VERSION, git_commit(), config.POLL_INTERVAL)

    monitor_task = asyncio.create_task(monitor_loop())
    try:
        await dp.start_polling(bot)
    finally:
        monitor_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
