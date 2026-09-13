#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if ! command -v python3 &>/dev/null; then
    echo "[!] Python 3 не найден. Попытка установки..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -y && sudo apt-get install -y python3 python3-pip
    elif command -v yum &>/dev/null; then
        sudo yum install -y python3 python3-pip
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3 python3-pip
    else
        echo "[X] Установите python3 вручную."
        exit 1
    fi
fi

if [ -f "requirements.txt" ]; then
    echo "[*] Проверка и установка зависимостей из requirements.txt..."
    python3 -m pip install -r requirements.txt --break-system-packages 2>/dev/null || python3 -m pip install -r requirements.txt
fi

echo "[+] Запуск..."
exec python3 -u main.py "$@"
