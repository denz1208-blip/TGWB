#!/usr/bin/env bash
# Простая настройка токена Telegram-бота без ручного редактирования .env.
#
#   sudo ./setup.sh                       — спросит токен интерактивно
#   sudo ./setup.sh "123456:AA..."       — можно сразу аргументом
#   sudo ./setup.sh "токен" "https://docs.google.com/..."  — плюс ссылка на таблицу
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="/opt/tg_barcode_bot"

# Если бот уже установлен на сервере — пишем .env именно туда,
# откуда его читает systemd-сервис.
if [ -d "$TARGET_DIR" ]; then
    ENV_DIR="$TARGET_DIR"
else
    ENV_DIR="$SCRIPT_DIR"
fi
ENV_FILE="$ENV_DIR/.env"

if [ -d "$TARGET_DIR" ] && [ "$(id -u)" -ne 0 ]; then
    echo "Нужны права root: sudo ./setup.sh"
    exit 1
fi

TOKEN="${1:-}"
if [ -z "$TOKEN" ]; then
    echo "=== Настройка токена Telegram-бота ==="
    echo "Токен можно получить у @BotFather командой /newbot"
    read -rp "Вставьте токен: " TOKEN
fi
TOKEN="$(printf '%s' "$TOKEN" | tr -d '\r\n' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"

if ! [[ "$TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
    echo "❌ Это не похоже на токен бота. Ожидается вид: 123456789:AA... "
    exit 1
fi

SHEET="${2:-}"
if [ -z "$SHEET" ] && [ -t 0 ]; then
    read -rp "Ссылка на таблицу (Enter — оставить как есть): " SHEET || true
fi
SHEET="$(printf '%s' "${SHEET:-}" | tr -d '\r\n' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"

touch "$ENV_FILE"

set_env_value() {
    local key="$1" value="$2" file="$3"
    awk -v key="$key" -v val="$value" '
        BEGIN { done = 0 }
        index($0, key "=") == 1 {
            if (!done) { print key "=" val; done = 1 }
            next
        }
        { print }
        END { if (!done) print key "=" val }
    ' "$file" > "$file.tmp"
    mv "$file.tmp" "$file"
}

set_env_value "BOT_TOKEN" "$TOKEN" "$ENV_FILE"

if [ -n "$SHEET" ]; then
    if [[ "$SHEET" =~ ^https?:// && "$SHEET" == *"/spreadsheets/d/"* ]]; then
        set_env_value "GOOGLE_SHEET_URL" "$SHEET" "$ENV_FILE"
        echo "✅ Ссылка на таблицу сохранена"
    else
        echo "⚠️ Ссылка не распознана — оставил таблицу по умолчанию"
    fi
fi

chmod 600 "$ENV_FILE"

if [ -f /etc/systemd/system/barcode-bot.service ]; then
    systemctl restart barcode-bot
    echo "✅ Сервис barcode-bot перезапущен"
fi

echo "✅ Токен сохранён в $ENV_FILE"
echo "   ${TOKEN:0:7}...${TOKEN: -4}"
echo "Проверьте в Telegram: /start и /version"
