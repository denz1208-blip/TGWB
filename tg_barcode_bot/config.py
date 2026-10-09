"""Конфигурация бота. Значения берутся из переменных окружения / файла .env"""
import os

from dotenv import load_dotenv

load_dotenv()

# Токен Telegram-бота, полученный у @BotFather
# Значение по умолчанию вшито; при наличии BOT_TOKEN в .env или окружении — берётся оно
BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "8545402880:AAGg_mvy-rbQKj0H5eVAFiTbNS2-8U7pEA0",
)

# Публичная ссылка на Google Таблицу (должна быть открыта по ссылке "Все, у кого есть ссылка")
GOOGLE_SHEET_URL = os.getenv(
    "GOOGLE_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1eVAliG0JG98RCFXPeAhbSsDNn_CWL7LQKIDr0ZLBdZo/edit?gid=0#gid=0",
)

# Интервал опроса таблицы, в секундах
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

# Путь к файлу состояния (хранит уже отправленные ШК и список подписчиков)
STATE_FILE = os.getenv("STATE_FILE", os.path.join(os.path.dirname(__file__), "state.json"))

# Колонка со штрихкодами в таблице
BARCODE_COLUMN = os.getenv("BARCODE_COLUMN", "ШК")

# Колонка со статусом (уведомления только если она пустая)
STATUS_COLUMN = os.getenv("STATUS_COLUMN", "Статус")

# Колонка с ID сотрудника (ФИО/данные подтягиваются из строки таблицы)
EMPLOYEE_ID_COLUMN = os.getenv("EMPLOYEE_ID_COLUMN", "ID")

# Список ID сотрудников, за которыми следим (через запятую).
# Пусто = следить за всеми. Пример: "112946,5994498"
TARGET_EMPLOYEE_IDS: set[str] = {
    x.strip() for x in os.getenv("TARGET_EMPLOYEE_IDS", "").split(",") if x.strip()
}

# ------------------------- Ограничение доступа -------------------------------
# Белый список Telegram ID пользователей, которым разрешено пользоваться ботом.
# Через запятую. Пусто = доступ разрешён всем (текущее поведение).
# Свой Telegram ID можно узнать командой /id (работает и у запрещённых —
# чтобы вы могли добавить себя в ALLOWED_USER_IDS).
# Пример: ALLOWED_USER_IDS=810321569,123456789
ALLOWED_USER_IDS: set[int] = {
    int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip().isdigit()
}

# Версия бота. Показывается в /help, /status, /version и в логе запуска.
# Раньше читалась через os.getenv("BOT_VERSION", ...) — и пустая строка
# BOT_VERSION= в .env делала версию пустой («Версия:  (код: ?)»).
# Теперь env-файл её НЕ перекрывает: актуальная версия всегда в коде.
# При каждом изменении кода увеличивайте номер И в config.py, и в bot.py.
BOT_VERSION = "2.1.3"
