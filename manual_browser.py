import os
import sys
import asyncio

# Настраиваем пути к кэшу Camoufox
# На Windows подменяем platformdirs, на Linux стандартные пути работают нормально
script_dir = os.path.dirname(os.path.abspath(__file__))
local_cache_path = os.path.join(script_dir, "local_cache")

if sys.platform == 'win32':
    try:
        import platformdirs
        import platformdirs.windows
        platformdirs.windows.get_win_folder_via_ctypes = lambda x: local_cache_path
        platformdirs.windows.get_win_folder_from_registry = lambda x: local_cache_path
        platformdirs.windows.get_win_folder_from_env_vars = lambda x: local_cache_path
        platformdirs.windows.get_win_folder = lambda x: local_cache_path
        platformdirs.user_cache_dir = lambda *args, **kwargs: os.path.join(local_cache_path, "camoufox", "Cache")
        platformdirs.user_data_dir = lambda *args, **kwargs: os.path.join(local_cache_path, "camoufox")
    except ImportError:
        pass

# Отключаем песочницу Firefox на Linux во избежание крашей seccomp
os.environ['MOZ_DISABLE_CONTENT_SANDBOX'] = '1'
os.environ['MOZ_DISABLE_GPU_SANDBOX'] = '1'
os.environ['MOZ_DISABLE_RDD_SANDBOX'] = '1'
os.environ['MOZ_DISABLE_SOCKET_PROCESS_SANDBOX'] = '1'

from camoufox.async_api import AsyncCamoufox
from urllib.parse import urlparse
async def main():
    proxy = None
    try:
        with open('proxies.txt') as f:
            lines = [l.strip() for l in f if l.strip()]
            if lines:
                proxy = lines[0]
                print(f'Использую прокси: {proxy}')
    except Exception:
        print('Не удалось прочитать proxies.txt, запускаю без прокси.')
    camoufox_args = {'headless': False, 'humanize': 1.0, 'geoip': '208.67.222.222' if proxy else False, 'locale': 'en-US', 'os': 'windows', 'window': (1280, 800), 'firefox_user_prefs': {'intl.accept_languages': 'en-US,en', 'javascript.use_us_english_locale': True, 'general.useragent.locale': 'en-US'}}
    if proxy:
        proxy_str = proxy if proxy.startswith('http') else f'http://{proxy}'
        parsed = urlparse(proxy_str)
        camoufox_args['proxy'] = {'server': f'http://{parsed.hostname}:{parsed.port}', 'username': parsed.username or '', 'password': parsed.password or ''}
    print('Запускаем браузер...')
    async with AsyncCamoufox(**camoufox_args) as browser:
        page = await browser.new_page()
        await page.goto('https://dash.cloudflare.com/login')
        print('\n' + '=' * 50)
        print('Браузер открыт! Попробуйте залогиниться вручную.')
        print('Скрипт будет висеть, пока вы его не остановите (Ctrl+C).')
        print('=' * 50 + '\n')
        while True:
            await asyncio.sleep(1)
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nОстановлено пользователем.')