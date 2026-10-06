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
