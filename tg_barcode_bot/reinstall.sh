#!/usr/bin/env bash
# Переустановка бота: подтягивает свежий код с GitHub и переустанавливает сервис
set -euo pipefail

REPO_URL="https://github.com/denz1208-blip/TGWB.git"
SRC_DIR="/opt/tg_barcode_bot_src"   # клон репозитория на сервере
PROJ="$SRC_DIR/tg_barcode_bot"

# Для приватного репозитория GitHub нужен токен с доступом к коду.
# Положите его в /etc/barcode-bot-token (или экспортируйте GITHUB_TOKEN).
TOKEN_FILE="/etc/barcode-bot-token"
if [ -z "${GITHUB_TOKEN:-}" ] && [ -f "$TOKEN_FILE" ]; then
    GITHUB_TOKEN="$(cat "$TOKEN_FILE")"
fi
if [ -n "${GITHUB_TOKEN:-}" ]; then
    REPO_URL_AUTH="https://${GITHUB_TOKEN}@github.com/denz1208-blip/TGWB.git"
else
    REPO_URL_AUTH="$REPO_URL"
    echo "!! GITHUB_TOKEN не задан — публичный репозиторий. Если репозиторий приватный, клон не удастся."
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Запустите с правами root: sudo ./reinstall.sh"
    exit 1
fi

# git может отсутствовать на сервере (например, минимальный образ) — ставим при необходимости
if ! command -v git >/dev/null 2>&1; then
    echo "==> Установка git..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -yq git ca-certificates
fi

echo "==> Обновление кода с GitHub..."
if [ -d "$SRC_DIR/.git" ]; then
    git -C "$SRC_DIR" remote set-url origin "$REPO_URL_AUTH"
    git -C "$SRC_DIR" fetch origin main
    git -C "$SRC_DIR" reset --hard origin/main
    # не оставляем токен в конфиге клона
    git -C "$SRC_DIR" remote set-url origin "$REPO_URL"
elif [ -f /opt/tg_barcode_bot/bot.py ] && grep -q 'BOT_VERSION = "3.0.0"' /opt/tg_barcode_bot/bot.py 2>/dev/null; then
    # Клон отсутствует, но код в /opt/tg_barcode_bot уже свежей версии —
    # GitHub недоступен (приватный репо/нет токена). Обновляем сервис на месте.
    echo "!! Клон $SRC_DIR не найден, но текущий код уже актуален — обновление с GitHub пропускаю."
    SRC_DIR="/opt/tg_barcode_bot"
    PROJ="/opt/tg_barcode_bot"
else
    rm -rf "$SRC_DIR"
    if ! git clone --branch main "$REPO_URL_AUTH" "$SRC_DIR"; then
        echo ""
        echo "!! Клонирование с GitHub не удалось (приватный репозиторий или нет доступа)."
        echo "   Вариант 1: сделать репозиторий публичным (Settings -> Danger Zone -> Change visibility)"
        echo "              и повторить: sudo ./reinstall.sh"
        echo "   Вариант 2: загрузить файлы со своего компьютера (см. README: раздел 'Обновление файлов')"
        exit 1
    fi
    # не оставляем токен в конфиге клона
    git -C "$SRC_DIR" remote set-url origin "$REPO_URL" 2>/dev/null || true
fi

echo "==> Перезапуск сервиса (или первая установка)..."
cd "$PROJ"

# сохраняем текущий state.json (известные ШК и подписчики), чтобы не слать старое заново
if [ -f /opt/tg_barcode_bot/state.json ]; then
    cp /opt/tg_barcode_bot/state.json /tmp/state.backup.json
fi

# подтягиваем актуальный install.sh из свежего кода (в /opt может лежать старая версия)
cp -f "$SRC_DIR/tg_barcode_bot/install.sh" /opt/tg_barcode_bot/install.sh 2>/dev/null || true
chmod +x install.sh

# если в /opt попал битый venv (симлинки на чужую машину) — удаляем, install.sh создаст новый
if [ -d /opt/tg_barcode_bot/venv ]; then
    if ! /opt/tg_barcode_bot/venv/bin/python3 --version >/dev/null 2>&1 || \
       ! /opt/tg_barcode_bot/venv/bin/python --version >/dev/null 2>&1; then
        echo "!! Найден нерабочий venv в /opt/tg_barcode_bot — удаляю, будет создан заново."
        rm -rf /opt/tg_barcode_bot/venv
    fi
fi

./install.sh

if [ -f /tmp/state.backup.json ]; then
    cp /tmp/state.backup.json /opt/tg_barcode_bot/state.json
    systemctl restart barcode-bot
    echo "(восстановлен state.json из резервной копии)"
fi

echo ""
echo "Проверка: systemctl status barcode-bot ; логи: journalctl -u barcode-bot -f"
