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
# Сохраняем локальные файлы сервера, чтобы cp их не перезаписал
if [ -f /opt/tg_barcode_bot/.env ]; then
    cp /opt/tg_barcode_bot/.env /tmp/barcode-bot.env.backup
fi
if [ -f /opt/tg_barcode_bot/state.json ]; then
    cp /opt/tg_barcode_bot/state.json /tmp/barcode-bot-state.backup.json
fi
mkdir -p /opt/tg_barcode_bot
# Копируем только файлы проекта; служебные каталоги (.git, venv, __pycache__) не трогаем
if [ "$PROJECT_DIR" != "/opt/tg_barcode_bot" ]; then
    find "$PROJECT_DIR" -maxdepth 1 -type f -exec cp {} /opt/tg_barcode_bot/ \;
fi
cd /opt/tg_barcode_bot
# Возвращаем .env сервера (в репозитории его может не быть или он может отличаться)
if [ -f /tmp/barcode-bot.env.backup ]; then
    cp /tmp/barcode-bot.env.backup /opt/tg_barcode_bot/.env
fi

echo "==> Создание виртуального окружения и установка библиотек..."
# Если venv битый (например, был закоммичен в git или скопирован с другой машины),
# пересоздаём его. Проверяем и python3, и python (в venv они разные симлинки).
venv_broken=0
if [ -d venv ]; then
    for p in venv/bin/python3 venv/bin/python; do
        if [ -e "$p" ] && ! "$p" --version >/dev/null 2>&1; then venv_broken=1; fi
    done
fi
if [ "$venv_broken" = "1" ]; then
    echo "!! Существующее venv нерабочее — пересоздаю..."
    rm -rf venv
fi
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
