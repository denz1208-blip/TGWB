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

echo "==> Обновление кода с GitHub..."
if [ -d "$SRC_DIR/.git" ]; then
    git -C "$SRC_DIR" remote set-url origin "$REPO_URL_AUTH"
    git -C "$SRC_DIR" fetch origin main
    git -C "$SRC_DIR" reset --hard origin/main
else
    rm -rf "$SRC_DIR"
    git clone --branch main "$REPO_URL_AUTH" "$SRC_DIR"
fi
# не оставляем токен в конфиге клона
git -C "$SRC_DIR" remote set-url origin "$REPO_URL"

echo "==> Перезапуск сервиса (или первая установка)..."
cd "$PROJ"

# сохраняем текущий state.json (известные ШК и подписчики), чтобы не слать старое заново
if [ -f /opt/tg_barcode_bot/state.json ]; then
    cp /opt/tg_barcode_bot/state.json /tmp/state.backup.json
fi

sudo ./install.sh

if [ -f /tmp/state.backup.json ] && [ ! -f /opt/tg_barcode_bot/state.json ]; then
    cp /tmp/state.backup.json /opt/tg_barcode_bot/state.json
    systemctl restart barcode-bot
    echo "(восстановлен state.json из резервной копии)"
fi

echo ""
echo "Проверка: systemctl status barcode-bot ; логи: journalctl -u barcode-bot -f"
