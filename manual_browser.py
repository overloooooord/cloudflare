import asyncio
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
    camoufox_args = {'headless': False, 'humanize': True, 'geoip': True if proxy else False, 'os': 'windows', 'window': (1280, 800), 'firefox_user_prefs': {'intl.accept_languages': 'en-US,en'}}
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