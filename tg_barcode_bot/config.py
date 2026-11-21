"""Конфигурация бота. Значения берутся из переменных окружения / файла .env."""
import os

from dotenv import load_dotenv

load_dotenv()

# Токен Telegram-бота, полученный у @BotFather.
# Секрет НЕ хранится в коде: обязательно задайте BOT_TOKEN в .env или окружении.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Глобальная таблица по умолчанию. Каждый пользователь может задать свою
# командой /sheet — она сохраняется в его личном аккаунте в state.json.
GOOGLE_SHEET_URL = os.getenv(
    "GOOGLE_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1eVAliG0JG98RCFXPeAhbSsDNn_CWL7LQKIDr0ZLBdZo/edit?gid=0#gid=0",
).strip()

# Интервал опроса таблицы, в секундах
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

# Путь к файлу состояния (аккаунты пользователей, белый список, known ШК)
STATE_FILE = os.getenv("STATE_FILE", os.path.join(os.path.dirname(__file__), "state.json"))

# Колонка со штрихкодами в таблице
BARCODE_COLUMN = os.getenv("BARCODE_COLUMN", "ШК")

# Колонка со статусом (уведомления только если она пустая)
STATUS_COLUMN = os.getenv("STATUS_COLUMN", "Статус")

# Колонка с ID сотрудника (ФИО/данные подтягиваются из строки таблицы)
EMPLOYEE_ID_COLUMN = os.getenv("EMPLOYEE_ID_COLUMN", "ID")

# Стартовый список ID сотрудников для НОВОГО аккаунта.
# Каждый пользователь потом меняет свой список через 👥 Отслеживание.
DEFAULT_TARGET_EMPLOYEE_IDS = "5978877"

TARGET_EMPLOYEE_IDS: set[str] = {
    x.strip()
    for x in os.getenv("TARGET_EMPLOYEE_IDS", DEFAULT_TARGET_EMPLOYEE_IDS).split(",")
    if x.strip()
}

# ID по умолчанию для кнопки «🔎 Поиск по ID».
DEFAULT_LOOKUP_EMPLOYEE_ID = os.getenv("DEFAULT_LOOKUP_EMPLOYEE_ID", "5978877").strip()

# ------------------------- Ограничение доступа -------------------------------
# Telegram ID администраторов (им разрешено /access и /users).
# Пусто = доступ к боту разрешён всем; тогда админом считается каждый,
# кто добавил себя через /access (первый пользователь может это сделать).
ALLOWED_USER_IDS: set[int] = {
    int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip().isdigit()
}

# Версия бота. Увеличивайте при каждом изменении кода (и в bot.py).
BOT_VERSION = "3.1.0"
