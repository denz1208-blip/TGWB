"""Telegram-бот отслеживания новых ШК в Google Таблице (многопользовательский).

У каждого пользователя Telegram — свой аккаунт отслеживания:
  • свой список ID сотрудников;
  • свой список уже известных ШК и своя лента уведомлений;
  • свои чаты подписки;
  • своя ссылка на Google-таблицу (по желанию).

Белый список /access остаётся общим (администраторы бота).
Интерфейс — reply-клавиатура + inline-кнопки, текст без HTML-разметки.
"""
import asyncio
import datetime
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
from sheet import fetch_rows, normalize_sheet_url
from state import Account, State

# Версия бота. Увеличивайте при каждом изменении кода!
BOT_VERSION = "3.1.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("barcode-bot")

state = State(config.STATE_FILE, initial_employee_ids=config.TARGET_EMPLOYEE_IDS)
dp = Dispatcher()
bot: Bot = None  # инициализируется в main()

LOOKUP_COUNT = 20  # сколько последних ШК показывать по ID
waiting_for_lookup: set[int] = set()  # Telegram ID пользователей, ждущих ввод ID


def git_commit() -> str:
    """Короткий хеш последнего коммита (если рядом есть git-репозиторий)."""
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


# --------------------------- Аккаунты пользователей ---------------------------

def account_from_message(message: Message) -> Account:
    user = message.from_user
    return state.get_account(
        user.id if user else 0,
        ((getattr(user, "username", "") or "") if user else ""),
    )


def account_from_call(call: CallbackQuery) -> Account:
    user = call.from_user
    return state.get_account(
        user.id if user else 0,
        ((getattr(user, "username", "") or "") if user else ""),
    )


def sheet_of(acc: Account) -> str:
    return acc.sheet_url or config.GOOGLE_SHEET_URL


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and int(user_id) in state.admin_ids()


# --------------------------- Ограничение доступа ------------------------------

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

    admins = sorted(state.admin_ids())
    if admins and uid:
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


# ----------------------------- Клавиатуры -----------------------------------

def main_kb(acc: Account) -> ReplyKeyboardMarkup:
    """Главное меню (постоянные кнопки под полем ввода)."""
    sub_btn = "🔕 Выключить" if acc.is_subscribed() else "🔔 Включить"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 Мои новые ШК"), KeyboardButton(text=sub_btn)],
            [KeyboardButton(text="🔎 Поиск по ID"), KeyboardButton(text="👥 Отслеживание")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def lookup_kb(ids: list[str]) -> InlineKeyboardMarkup:
    """Inline-кнопки «🔎 {ID}» для быстрого просмотра последних ШК по ID."""
    rows = [[InlineKeyboardButton(text=f"🔎 {x}", callback_data=f"look:{x}")] for x in ids[:10]]
    for x in ids[:10]:
        rows.append([InlineKeyboardButton(text=f"➕ Отслеживать {x}", callback_data=f"track:{x}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --------------------------- Общие тексты ------------------------------------

def filter_line(acc: Account) -> str:
    if acc.employee_ids:
        return "Ваши ID сотрудников: " + ", ".join(sorted(acc.employee_ids))
    return "Ваши ID сотрудников: все (добавьте конкретные в разделе 👥 Отслеживание)"


def sheet_line(acc: Account) -> str:
    return "Ваша таблица: своя (/sheet)" if acc.sheet_url else "Ваша таблица: общая (/sheet)"


def today_key() -> str:
    return datetime.date.today().isoformat()


def stats_text(acc: Account) -> str:
    """Текст дневной статистики пользователя (последние 7 дней)."""
    days = sorted(acc.daily_stats, reverse=True)[:7]
    lines = ["📊 Ваша статистика по ШК", ""]
    if not days:
        lines.append("Данных пока нет — как только появятся новые ШК, статистика начнёт вестись.")
        return "\n".join(lines)
    for day in days:
        rec = acc.daily_stats[day]
        try:
            label = "Сегодня" if day == today_key() else \
                datetime.date.fromisoformat(day).strftime("%d.%m.%Y")
        except ValueError:
            label = day
        lines.append(
            f"• {label}: всего ШК за день — {rec.get('total', 0)}, "
            f"осталось «в работе» — {rec.get('in_work', 0)}"
        )
    if len(acc.daily_stats) > 7:
        lines.append(f"\n…ещё {len(acc.daily_stats) - 7} дней в истории (храню {acc.MAX_STAT_DAYS}).")
    lines.append("\n«В работе» — признак колонки «Статус» в вашей таблице на момент последней проверки.")
    return "\n".join(lines)


def access_line() -> str:
    lst = sorted(state.allowed_ids())
    if not lst:
        return "Доступ: открыт для всех (ограничьте через /access add <ID>)"
    return f"Доступ: закрытый режим, разрешён {len(lst)} пользовател(ям): " + \
        ", ".join(str(x) for x in lst[:20])


def help_text(acc: Account) -> str:
    return (
        "🔎 Бот отслеживания новых ШК\n"
        f"{version_line()}\n"
        f"Слежу за таблицей каждые {config.POLL_INTERVAL} сек.\n\n"
        "👤 У вас свой личный аккаунт отслеживания:\n"
        f"• {filter_line(acc)}\n"
        f"• {sheet_line(acc)}\n"
        f"• Подписка: {'включена' if acc.is_subscribed() else 'выключена'}\n\n"
        "⚙️ Фильтр уведомлений:\n"
        f"• колонка «{config.STATUS_COLUMN}» пустая;\n"
        "• ID сотрудника из вашего списка (пустой список = все).\n\n"
        f"{access_line()}\n\n"
        "Кнопки меню:\n"
        "🆕 Мои новые ШК — ваши последние уведомления\n"
        "🔎 Поиск по ID — последние 20 ШК любого сотрудника\n"
        "👥 Отслеживание — ваш список ID для уведомлений\n"
        "🔔/🔕 — включить/выключить ваши уведомления\n"
        "📊 Статистика — сколько ШК было за день и сколько «в работе»\n\n"
        "Команды:\n"
        "/stats — дневная статистика (последние 7 дней)\n"
        "/sheet [ссылка|reset] — своя Google-таблица\n"
        "/id — ваш Telegram ID\n"
        "/status — ваш аккаунт\n"
        "/access — управление доступом (админы)\n"
        "/users — список аккаунтов (админы)"
    )


def _validate_token() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен от @BotFather."
        )


# ------------------------------ Команды --------------------------------------

@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    acc = account_from_message(message)
    await message.answer(
        "🔎 Привет! Я слежу за новыми ШК в Google Таблице.\n\n"
        "У каждого пользователя свой аккаунт отслеживания: свои ID сотрудников,\n"
        "свои уведомления и (если нужно) своя таблица.\n\n"
        f"{filter_line(acc)}\n"
        f"{sheet_line(acc)}\n\n"
        "Уведомления приходят только по вашей подписке, только для новых ШК\n"
        "с пустым статусом и только от ваших ID сотрудников.\n\n"
        "Включить/выключить рассылку можно кнопкой ниже или командой /subscribe.",
        reply_markup=main_kb(acc),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    acc = account_from_message(message)
    await message.answer(help_text(acc), reply_markup=main_kb(acc))


@dp.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")


@dp.message(Command("version"))
async def cmd_version(message: Message) -> None:
    import datetime
    code_dir = os.path.dirname(os.path.abspath(__file__))
    mtime = os.path.getmtime(os.path.join(code_dir, "bot.py"))
    updated = datetime.datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
    await message.answer(f"{version_line()}\nФайл bot.py обновлён: {updated}")


@dp.message(Command("status"))
async def cmd_status(message: Message) -> None:
    acc = account_from_message(message)
    today = acc.day_stats(today_key())
    await message.answer(
        "📊 Статус вашего аккаунта\n"
        f"{version_line()}\n"
        f"Telegram ID: {acc.user_id}\n"
        f"Подписка: {'✅ включена' if acc.is_subscribed() else '❌ выключена'}\n"
        f"Известных вам ШК: {len(acc.seen_barcodes)}\n"
        f"В ленте уведомлений: {len(acc.newest_notifications)}\n"
        f"Последний просмотренный ID: {acc.last_lookup_id or '—'}\n"
        f"За сегодня: всего ШК — {today['total']}, «в работе» — {today['in_work']}\n"
        f"{filter_line(acc)}\n"
        f"{sheet_line(acc)}\n"
        f"{access_line()}\n"
        f"Интервал проверки: {config.POLL_INTERVAL} сек.",
        reply_markup=main_kb(acc),
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    acc = account_from_message(message)
    await message.answer(stats_text(acc), reply_markup=main_kb(acc))


@dp.message(F.text == "📊 Статистика")
async def kb_stats(message: Message) -> None:
    await cmd_stats(message)


@dp.message(Command("subscribe"))
async def cmd_subscribe(message: Message) -> None:
    acc = account_from_message(message)
    added = acc.subscribe(message.chat.id)
    state.save()
    text = (
        "✅ Уведомления включены!\n"
        f"В таблице уже известно {len(acc.seen_barcodes)} ваших ШК — приходить будут только новые."
        if added
        else "👍 Вы уже подписаны на уведомления."
    )
    await message.answer(text, reply_markup=main_kb(acc))


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message) -> None:
    acc = account_from_message(message)
    removed = acc.unsubscribe_all()
    state.save()
    text = "🔕 Уведомления отключены." if removed else "Вы и так не подписаны."
    await message.answer(text, reply_markup=main_kb(acc))


# ------------------------ Своя таблица пользователя --------------------------

@dp.message(Command("sheet"))
async def cmd_sheet(message: Message) -> None:
    acc = account_from_message(message)
    args = (message.text or "").split(maxsplit=1)
    arg = args[1].strip() if len(args) > 1 else ""

    if not arg:
        await message.answer(
            "📄 Ваша Google-таблица\n\n"
            f"Сейчас: {sheet_of(acc)}\n"
            f"Источник: {'своя' if acc.sheet_url else 'общая (из .env)'}\n\n"
            "/sheet <ссылка> — использовать свою таблицу\n"
            "/sheet reset — вернуться к общей таблице"
        )
        return

    if arg.lower() in ("reset", "сброс", "общая", "default"):
        acc.sheet_url = ""
        acc.reset_tracking()
        state.save()
        await message.answer(
            "✅ Вернул вас к общей таблице. Известные ШК сброшены — "
            "старые строки не будут присланы заново."
        )
        return

    try:
        url = normalize_sheet_url(arg)
    except ValueError as e:
        await message.answer(f"❌ {e}\n\nПример: /sheet https://docs.google.com/spreadsheets/d/.../edit")
        return

    acc.sheet_url = url
    acc.reset_tracking()
    state.save()
    await message.answer(
        "✅ Установлена ваша таблица:\n" + url + "\n\n"
        "Известные ШК сброшены, при первом опросе текущие строки запомнятся "
        "и не будут отправлены как новые."
    )


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
    acc = account_from_message(message)
    items = list(acc.newest_notifications.items())
    items.reverse()  # сначала самые свежие
    if not items:
        await message.answer(
            "Пока новых ШК не приходило.\n"
            "Как только в таблице появится ШК с пустым статусом и вашим ID — сообщу.",
            reply_markup=main_kb(acc),
        )
        return
    lines = ["🆕 Ваши последние новые ШК (сначала свежие):"]
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
    acc = account_from_message(message)
    ids = ", ".join(sorted(acc.employee_ids)) if acc.employee_ids else "— пусто —"
    await message.answer(
        "👥 Ваше отслеживание сотрудников\n\n"
        f"Сейчас уведомления настроены на ID: {ids}\n\n"
        "Чтобы изменить список, отправьте мне числовые ID сотрудников из таблицы:\n"
        "• через запятую или пробел — заменит весь список,\n"
        "• со знаком «+» перед каждым (например: +112946 +5994498) — добавит,\n"
        "• команда /ids clear — очистит список (будут приходить ШК всех сотрудников\n"
        "  с пустым статусом).\n\n"
        "Пример: 112946, 5994498",
        reply_markup=main_kb(acc),
    )


@dp.message(Command("ids"))
async def cmd_ids(message: Message) -> None:
    acc = account_from_message(message)
    arg = (message.text or "").split(maxsplit=1)
    action = arg[1].strip().lower() if len(arg) > 1 else ""
    if action in ("clear", "очистить"):
        acc.employee_ids = set()
        state.save()
        await message.answer("🗑 Ваш список ID очищен — слежу за всеми сотрудниками (с пустым статусом).")
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
    if not is_admin(message.from_user.id if message.from_user else None):
        await message.answer("⛔ Только администратор может управлять доступом.")
        return
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


@dp.message(Command("users"))
async def cmd_users(message: Message) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        await message.answer("⛔ Только администратор может смотреть список аккаунтов.")
        return
    accounts = sorted(state.all_accounts(), key=lambda a: a.user_id)
    if not accounts:
        await message.answer("Аккаунтов пока нет — пользователи создаются при первом сообщении боту.")
        return
    lines = [f"👥 Аккаунтов: {len(accounts)}", ""]
    for acc in accounts[:40]:
        who = f"@{acc.username}" if acc.username else "—"
        ids = ", ".join(sorted(acc.employee_ids)) or "все"
        if len(ids) > 60:
            ids = ids[:57] + "..."
        lines.append(
            f"• {acc.user_id} ({who}) | ID: {ids} | ШК: {len(acc.seen_barcodes)} | "
            f"подписка: {'вкл' if acc.is_subscribed() else 'выкл'} | "
            f"таблица: {'своя' if acc.sheet_url else 'общая'}"
        )
    if len(accounts) > 40:
        lines.append(f"…и ещё {len(accounts) - 40}")
    text = "\n".join(lines)
    await message.answer(text[:4000])


# ------------------------------ Поиск по ID ----------------------------------

@dp.message(F.text == "🔎 Поиск по ID")
async def kb_search_ask(message: Message) -> None:
    acc = account_from_message(message)
    default_id = config.DEFAULT_LOOKUP_EMPLOYEE_ID
    if default_id:
        waiting_for_lookup.add(acc.user_id)
        await message.answer(
            f"🔎 Ищу по умолчанию ШК для ID {default_id}…\n"
            "Чтобы искать по другому ID — просто отправьте его числом.",
        )
        await do_lookup(message, default_id)
        return
    remembered = f" Последний запрошенный ID: {acc.last_lookup_id}" if acc.last_lookup_id else ""
    await message.answer(
        "🔎 Введите ID сотрудника из таблицы — покажу последние "
        f"{LOOKUP_COUNT} его ШК (с датами и статусами).{remembered}",
    )


@dp.message(~F.text.startswith("/"))
async def handle_text(message: Message) -> None:
    acc = account_from_message(message)
    text = (message.text or "").strip()
    nums = [x for x in re.split(r"[,\s;]+", text.replace("+", " ")) if x.isdigit()]

    # 1) Если ждём ввод ID для поиска — ищем сразу
    waiting = acc.user_id in waiting_for_lookup
    if waiting:
        waiting_for_lookup.discard(acc.user_id)
        if not nums:
            await message.answer(
                "Не похоже на ID. Пример: 112946",
                reply_markup=main_kb(acc),
            )
            return
        await do_lookup(message, nums[0])
        return

    # 2) Ввод состоит только из чисел — предлагаем кнопки «посмотреть» и «+добавить»
    tokens = _tokens(text)
    if nums and all(t.startswith("+") or t.isdigit() for t in tokens):
        if any(t.startswith("+") for t in tokens):
            added = acc.add_employee_ids(nums)
            state.save()
            await message.answer(
                f"✅ Добавлено в ваш список: {', '.join(added) if added else 'уже были в списке'}\n"
                f"Текущий список: {', '.join(sorted(acc.employee_ids))}"
            )
            await kb_tracking(message)
        else:
            ids_list = ", ".join(sorted(acc.employee_ids)) if acc.employee_ids else "—"
            lines = [f"🔎 Что сделать с ID {', '.join(nums)}?"]
            lines += [
                "",
                "• Нажмите кнопку 🔎 — покажу последние " + str(LOOKUP_COUNT) + " ШК этого сотрудника;",
                f"• отправьте «+{nums[0]}» — добавлю этот ID в ваш список;",
                "• /ids clear — очистить ваш список.",
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
        reply_markup=main_kb(acc),
    )


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[,\s;]+", text) if t]


async def do_lookup(message: Message, emp_id: str) -> None:
    acc = account_from_message(message)
    acc.last_lookup_id = emp_id
    state.save()

    msg = await message.answer(f"⏳ Ищу ШК для ID {emp_id}…")
    text = await build_lookup_text(emp_id, acc)
    try:
        await msg.edit_text(text)
    except Exception:  # noqa: BLE001
        pass
    await message.answer("Меню:", reply_markup=main_kb(acc))


async def do_lookup_message(src: Message, emp_id: str, acc: Account) -> None:
    """Поиск по ID из inline-кнопки (отвечаем в тот же чат)."""
    acc.last_lookup_id = emp_id
    state.save()
    text = await build_lookup_text(emp_id, acc)
    await src.reply(text, reply_markup=main_kb(acc))


async def build_lookup_text(emp_id: str, acc: Account) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            rows = await fetch_rows(session, sheet_of(acc))
        except Exception as e:  # noqa: BLE001
            return f"❌ Ошибка чтения таблицы: {e}"

        found = [
            r for r in rows
            if (r.get(config.EMPLOYEE_ID_COLUMN, "") or "").strip() == emp_id
            and (r.get(config.BARCODE_COLUMN, "") or "").strip()
        ]

    import datetime as _dt

    def _parse_date(s: str):
        s = (s or "").strip()
        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
            try:
                return _dt.datetime.strptime(s, fmt)
            except ValueError:
                pass
        return None

    parsed = [(_parse_date(r.get("Дата создания", "")), r) for r in found]
    with_dates = sorted(
        (p for p in parsed if p[0] is not None), key=lambda p: p[0], reverse=True
    )
    without = [r for d, r in parsed if d is None]
    ordered = [r for _, r in with_dates] + without

    name = next((r.get("ФИО", "") for r in ordered if r.get("ФИО", "")), "")
    who = f" ({name})" if name else ""
    if not ordered:
        return f"🔎 По ID {emp_id}{who} в вашей таблице нет ни одного ШК."

    shown = ordered[:LOOKUP_COUNT]
    lines = [
        f"🔎 ID {emp_id}{who}: всего ШК — {len(ordered)}.",
        f"Последние {len(shown)} (сначала свежие):",
        "",
    ]
    for i, r in enumerate(shown, 1):
        status = r.get("Статус", "") or "без статуса"
        line = f"{i}. {r.get(config.BARCODE_COLUMN, '')}"
        if r.get("Дата создания", ""):
            line += f" · {r['Дата создания']}"
        line += f" · 📌 {status}"
        lines.append(line)
        if r.get("Решение по заявке", ""):
            lines.append(f"     ⚖️ {r['Решение по заявке']}")
    if len(ordered) > LOOKUP_COUNT:
        lines.append(f"\n…и ещё {len(ordered) - LOOKUP_COUNT} более ранних.")

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


def rows_for_account(rows: list[dict], acc: Account) -> dict[str, dict]:
    """Применить личные фильтры пользователя к строкам его таблицы."""
    result: dict[str, dict] = {}
    for row in rows:
        code = (row.get(config.BARCODE_COLUMN, "") or "").strip()
        if not code:
            continue
        if config.STATUS_COLUMN and (row.get(config.STATUS_COLUMN, "") or "").strip():
            continue
        if acc.employee_ids:
            emp_id = (row.get(config.EMPLOYEE_ID_COLUMN, "") or "").strip()
            if emp_id not in acc.employee_ids:
                continue
        result[code] = row
    return result


def count_in_work(rows: list[dict], acc: Account) -> int:
    """Сколько ШК из строк пользователя сейчас со статусом «в работе»."""
    count = 0
    for row in rows:
        code = (row.get(config.BARCODE_COLUMN, "") or "").strip()
        if not code:
            continue
        if acc.employee_ids:
            emp_id = (row.get(config.EMPLOYEE_ID_COLUMN, "") or "").strip()
            if emp_id not in acc.employee_ids:
                continue
        status = (row.get(config.STATUS_COLUMN, "") or "").strip().lower()
        if "в работе" in status:
            count += 1
    return count


async def send_to_user_chats(acc: Account, text: str) -> None:
    """Отправить уведомление только в чаты этого пользователя."""
    allowed = state.allowed_ids()
    if allowed and acc.user_id not in allowed:
        return
    for chat_id in list(acc.subscribed_chats):
        try:
            await bot.send_message(chat_id, text)
        except Exception as e:  # noqa: BLE001
            log.warning("Не удалось отправить %s (пользователь %s): %s",
                        chat_id, acc.user_id, e)


async def poll_sheet(session: aiohttp.ClientSession) -> None:
    """Один цикл: для каждого аккаунта найти его новые ШК и разослать."""
    accounts = state.all_accounts()
    if not accounts:
        return

    # Таблиц может быть несколько — скачиваем каждую один раз за цикл.
    rows_by_url: dict[str, list[dict]] = {}
    for url in {sheet_of(a) for a in accounts}:
        try:
            rows_by_url[url] = await fetch_rows(session, url)
        except Exception as e:  # noqa: BLE001
            log.error("Ошибка чтения таблицы %s: %s", url, e)

    changed = False
    for acc in accounts:
        rows = rows_by_url.get(sheet_of(acc))
        if rows is None:
            continue  # таблица недоступна — не трогаем состояние аккаунта

        known = rows_for_account(rows, acc)
        day = today_key()

        # Сколько ШК осталось «в работе» — обновляем даже если новых ШК нет.
        in_work = count_in_work(rows, acc)
        if acc.day_stats(day).get("in_work", 0) != in_work:
            acc.set_daily_in_work(day, in_work)
            changed = True

        if not acc.initialized:
            # Первый опрос аккаунта: запоминаем все текущие ШК, ничего не шлём.
            acc.seen_barcodes = set(known)
            acc.initialized = True
            changed = True
            log.info("Аккаунт %s: первый опрос, запомнено ШК — %d",
                     acc.user_id, len(known))
            continue

        new_codes = [c for c in known if not acc.is_seen(c)]
        if not new_codes:
            continue

        for code in new_codes:
            acc.add_seen(code)
        acc.add_daily_total(day, len(new_codes))
        for code in new_codes:
            acc.push_notification(code, known[code])
            await send_to_user_chats(acc, format_barcode_message(code, known[code]))
            await asyncio.sleep(0.1)  # бережём лимиты Telegram API
        changed = True
        log.info("Аккаунт %s: новых ШК — %d", acc.user_id, len(new_codes))

    if changed:
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
    acc = account_from_call(call)
    if call.message:
        await do_lookup_message(call.message, emp_id, acc)


@dp.callback_query(F.data.startswith("track:"))
async def cb_track(call: CallbackQuery) -> None:
    emp_id = call.data.split(":", 1)[1]
    acc = account_from_call(call)
    acc.employee_ids = {emp_id}
    state.save()
    await call.answer("Добавлено в отслеживание")
    if call.message:
        await call.message.reply(
            f"✅ Теперь в вашем списке ID {emp_id}: буду присылать его новые ШК с пустым статусом.\n"
            f"Ваш список: {', '.join(sorted(acc.employee_ids))}"
        )


@dp.callback_query(F.data.startswith("acc:"))
async def cb_access(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id if call.from_user else None):
        await call.answer("Только администратор", show_alert=True)
        return
    action, _, uid_str = call.data.partition(":")
    action = action.split(":", 1)[1]  # add / deny
    uid = int(uid_str)
    if action == "add":
        added = state.add_allowed([uid])
        state.save()
        if call.message:
            await call.message.edit_text(
                f"✅ Пользователю {uid} разрешён доступ."
                + ("" if added else " (он уже был в списке)")
                + f"\n{access_line()}"
            )
        await call.answer("Разрешено")
    else:
        if call.message:
            await call.message.edit_text(
                "🚫 Никому ничего не разрешил — кнопка «Запретить» просто закрыла это сообщение."
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
            BotCommand(command="subscribe", description="Включить мои уведомления"),
            BotCommand(command="unsubscribe", description="Выключить мои уведомления"),
            BotCommand(command="status", description="Мой аккаунт"),
            BotCommand(command="stats", description="Статистика за день"),
            BotCommand(command="ids", description="Мои ID сотрудников"),
            BotCommand(command="sheet", description="Моя Google-таблица"),
            BotCommand(command="access", description="Доступ (админы)"),
            BotCommand(command="users", description="Аккаунты (админы)"),
            BotCommand(command="help", description="Справка"),
            BotCommand(command="version", description="Версия бота"),
        ]
    )

    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:  # noqa: BLE001
        log.warning("delete_webhook не выполнен: %s", e)

    log.info("Бот запущен. Версия: %s (код: %s). Аккаунтов: %d. Интервал: %d сек.",
             config.BOT_VERSION, git_commit(), len(state.accounts), config.POLL_INTERVAL)

    monitor_task = asyncio.create_task(monitor_loop())
    try:
        await dp.start_polling(bot)
    finally:
        monitor_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
