#!/usr/bin/env bash
# Установка бота как systemd-сервиса (автозапуск при загрузке Linux)
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="barcode-bot"
RUN_USER="${SUDO_USER:-$(whoami)}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Запустите с правами root: sudo ./install.sh"
    exit 1
fi

echo "==> Установка зависимостей..."
if command -v apt-get >/dev/null 2>&1; then
    apt-get update -q
    apt-get install -yq python3-venv python3-pip git
fi

echo "==> Копирование проекта в /opt/tg_barcode_bot..."
mkdir -p /opt/tg_barcode_bot
cp -r "$PROJECT_DIR"/. /opt/tg_barcode_bot/
cd /opt/tg_barcode_bot

echo "==> Создание виртуального окружения и установка библиотек..."
python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

chown -R "$RUN_USER":"$RUN_USER" /opt/tg_barcode_bot || true

echo "==> Регистрация systemd-сервиса '$SERVICE_NAME'..."
sed "s|^User=.*|User=$RUN_USER|" barcode-bot.service > "/etc/systemd/system/$SERVICE_NAME.service"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

sleep 2
systemctl --no-pager status "$SERVICE_NAME" | head -n 8
echo ""
echo "Готово! Бот запущен и будет стартовать автоматически при загрузке."
echo "Логи: journalctl -u $SERVICE_NAME -f"
