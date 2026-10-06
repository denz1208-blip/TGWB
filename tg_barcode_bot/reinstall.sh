#!/usr/bin/env bash
# Переустановка бота: подтягивает свежий код с GitHub и переустанавливает сервис
set -euo pipefail

REPO_URL="https://github.com/denz1208-blip/TGWB.git"
SRC_DIR="/opt/tg_barcode_bot_src"   # клон репозитория на сервере
PROJ="$SRC_DIR/tg_barcode_bot"

if [ "$(id -u)" -ne 0 ]; then
    echo "Запустите с правами root: sudo ./reinstall.sh"
    exit 1
fi

echo "==> Обновление кода с GitHub..."
if [ -d "$SRC_DIR/.git" ]; then
    git -C "$SRC_DIR" fetch origin main
    git -C "$SRC_DIR" reset --hard origin/main
else
    rm -rf "$SRC_DIR"
    git clone --branch main "$REPO_URL" "$SRC_DIR"
fi

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
