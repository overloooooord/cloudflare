# 2>nul & @echo off
# 2>nul & chcp 65001 >nul
# 2>nul & cd /d "%~dp0"
# 2>nul & set "PYTHON_EXE=%~dp0python\python.exe"
# 2>nul & if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
# 2>nul & "%PYTHON_EXE%" "%~f0" %*
# 2>nul & exit /b

import os
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import subprocess
import json
import urllib.request
import urllib.error

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def open_file(path):
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            pass
    if os.name == 'nt':
        os.system(f'start notepad "{path}"')
    else:
        print(f"Файл: {path}")
        input("Нажмите Enter для возврата в меню...")

def check_balances(py_dir):
    clear()
    print("============================================================")
    print("   ПРОВЕРКА БАЛАНСОВ И СТАТУСА")
    print("============================================================\n")

    sys.path.insert(0, py_dir)
    try:
        import config
    except Exception as e:
        print(f"[-] Ошибка загрузки config.py: {e}")
        input("\nНажмите Enter...")
        return

    nl_key = getattr(config, 'NOTLETTERS_API_KEY', '')
    if nl_key:
        try:
            req = urllib.request.Request(
                'https://api.notletters.com/v1/me',
                headers={'Authorization': f'Bearer {nl_key}', 'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                balance = data.get('data', {}).get('balance', '?')
                print(f" [OK] NotLetters API: Баланс = {balance}")
        except Exception as e:
            print(f" [-] NotLetters API: Ошибка ({e})")
    else:
        print(" [-] NotLetters API: Ключ не указан в config.py")

    as_key = getattr(config, 'CAPTCHA_API_KEY', '')
    if as_key and 'anysolver' in getattr(config, 'CAPTCHA_SERVICE', ''):
        try:
            req = urllib.request.Request(
                'https://api.anysolver.com/getBalance',
                data=json.dumps({'clientKey': as_key}).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                balance = data.get('balance', '?')
                print(f" [OK] AnySolver: Баланс = {balance}")
        except Exception as e:
            print(f" [-] AnySolver: Ошибка ({e})")

    emails_file = os.path.join(py_dir, getattr(config, 'EMAILS_FILE', 'emails.txt'))
    if os.path.exists(emails_file):
        with open(emails_file, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        print(f" [OK] Почты (emails.txt): {len(lines)} шт.")
    else:
        print(" [-] emails.txt не найден")

    proxies_file = os.path.join(py_dir, getattr(config, 'PROXIES_FILE', 'proxies.txt'))
    if os.path.exists(proxies_file):
        with open(proxies_file, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        print(f" [OK] Прокси (proxies.txt): {len(lines)} шт.")
    else:
        print(" [-] proxies.txt не найден")

    results_file = os.path.join(py_dir, getattr(config, 'OUTPUT_FILE', 'results.json'))
    if os.path.exists(results_file):
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                res_data = json.load(f)
                registered = len(res_data.get('clouds', []))
            print(f" [OK] Успешно зарегистрировано: {registered} аккаунтов")
        except Exception:
            pass

    print("\n============================================================")
    input("Нажмите Enter для возврата в меню...")

def main():
    py_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        os.chdir(py_dir)
    except Exception:
        pass
    if py_dir not in sys.path:
        sys.path.insert(0, py_dir)
    local_cache = os.path.join(py_dir, "local_cache")

    if sys.platform == 'win32':
        try:
            import platformdirs
            import platformdirs.windows
            platformdirs.windows.get_win_folder_via_ctypes = lambda x: local_cache
            platformdirs.windows.get_win_folder_from_registry = lambda x: local_cache
            platformdirs.windows.get_win_folder_from_env_vars = lambda x: local_cache
            platformdirs.windows.get_win_folder = lambda x: local_cache
            platformdirs.user_cache_dir = lambda *args, **kwargs: os.path.join(local_cache, "camoufox", "Cache")
            platformdirs.user_data_dir = lambda *args, **kwargs: os.path.join(local_cache, "camoufox")
        except ImportError:
            pass

    python_exe = os.path.join(py_dir, "python", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable or "python"

    while True:
        clear()
        print("============================================================")
        print("   CLOUDFLARE AUTOREGER + GLOBAL API KEY")
        print("============================================================\n")
        print("    1. Запустить авторегер (Start)")
        print("    2. Настройки (config.py)")
        print("    3. Список почт (emails.txt)")
        print("    4. Список прокси (proxies.txt)")
        print("    5. Результаты (results.json)")
        print("    6. Проверка балансов и статуса")
        print("    7. Выход\n")

        try:
            choice = input("Выберите действие (1-7): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nВыход...")
            sys.exit(0)

        if choice == "1":
            clear()
            print("============================================================")
            print("   ЗАПУСК АВТОРЕГЕРА")
            print("============================================================\n")

            try:
                subprocess.run([python_exe, "-c", "import curl_cffi, aiohttp, rich"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=py_dir)
            except Exception:
                print("[*] Установка зависимостей...")
                req_file = os.path.join(py_dir, "requirements.txt")
                if os.path.exists(req_file):
                    subprocess.run([python_exe, "-m", "pip", "install", "-r", req_file], cwd=py_dir)
                else:
                    subprocess.run([python_exe, "-m", "pip", "install", "curl-cffi", "aiohttp", "aiofiles", "certifi", "rich"], cwd=py_dir)

            count_in = input("Сколько аккаунтов зарегистрировать (Enter = из config): ").strip()
            threads_in = input("Сколько потоков (Enter = из config): ").strip()

            main_py = os.path.join(py_dir, "main.py")
            cmd = [python_exe, main_py]
            if count_in.isdigit():
                cmd += ["--count", count_in]
            if threads_in.isdigit():
                cmd += ["--threads", threads_in]

            try:
                subprocess.run(cmd, cwd=py_dir)
            except KeyboardInterrupt:
                print("\nОстановлено пользователем.")
            input("\nГотово. Нажмите Enter для возврата в меню...")

        elif choice == "2":
            open_file(os.path.join(py_dir, "config.py"))
        elif choice == "3":
            open_file(os.path.join(py_dir, "emails.txt"))
        elif choice == "4":
            open_file(os.path.join(py_dir, "proxies.txt"))
        elif choice == "5":
            results_path = os.path.join(py_dir, "results.json")
            if not os.path.exists(results_path):
                results_path = os.path.join(py_dir, "results.txt")
            open_file(results_path)
        elif choice == "6":
            check_balances(py_dir)
        elif choice == "7":
            sys.exit(0)

if __name__ == "__main__":
    main()
