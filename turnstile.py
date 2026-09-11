import asyncio
import logging
import socket
import ssl
import aiohttp
import config
logger = logging.getLogger(__name__)
CF_SITEKEY = '0x4AAAAAAAJel0iaAR3mgkjp'
ACTION_URLS = {'signup': 'https://dash.cloudflare.com/sign-up', 'login': 'https://dash.cloudflare.com/login', 'onboarding': 'https://dash.cloudflare.com/profile/api-tokens'}

async def _solve_anysolver(website_url: str, website_key: str, action: str, session: aiohttp.ClientSession, proxy: str | None = None) -> str:
    """Решить Turnstile через anysolver.com API."""
    api_key = config.CAPTCHA_API_KEY
    base = 'https://api.anysolver.com'
    
    task = {
        'type': 'TurnstileTokenProxyLess',
        'websiteURL': website_url,
        'websiteKey': website_key,
        'action': action,
        'data': action,
        'metadata': {'action': action},
    }
    
    create_payload = {'clientKey': api_key, 'task': task}
    
    if proxy:
        # Передаём прокси — AnySolver решит капчу через тот же IP
        proxy_str = proxy if proxy.startswith('http://') or proxy.startswith('https://') else f'http://{proxy}'
        task['proxy'] = proxy_str
        create_payload['settings'] = {'allowProxyReuse': True}
        logger.info(f'AnySolver: TurnstileTokenProxyLess (с прокси + allowProxyReuse)')
    else:
        logger.info(f'AnySolver: TurnstileTokenProxyLess (без прокси)')
    
    async with session.post(f'{base}/createTask', json=create_payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
        data = await r.json()
    if data.get('errorId', 0) != 0:
        raise RuntimeError(f"AnySolver createTask error: {data.get('errorDescription')}")
    task_id = data['taskId']
    logger.debug(f'AnySolver taskId={task_id}')
    get_payload = {'clientKey': api_key, 'taskId': task_id}
    for attempt in range(35):
        await asyncio.sleep(2)
        async with session.post(f'{base}/getTaskResult', json=get_payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
            result = await r.json()
        status = result.get('status')
        if status == 'ready':
            token = result.get('solution', {}).get('token') or result.get('token')
            if not token:
                raise RuntimeError(f'AnySolver ready but token missing: {result}')
            logger.debug(f'AnySolver token: {token[:30]}...')
            return token
        elif status in ('processing', 'idle'):
            continue
        else:
            raise RuntimeError(f'AnySolver ошибка: {result}')
    raise TimeoutError('AnySolver: не решил за 70 сек')

async def _solve_2captcha(website_url: str, website_key: str, action: str, session: aiohttp.ClientSession) -> str:
    """Решить Turnstile через 2captcha.com API."""
    api_key = config.CAPTCHA_API_KEY
    base = 'https://api.2captcha.com'
    from cloudflare_api import CHROME_UA
    create_payload = {'clientKey': api_key, 'task': {'type': 'TurnstileTaskProxyless', 'websiteURL': website_url, 'websiteKey': website_key, 'action': action, 'userAgent': CHROME_UA}}
    async with session.post(f'{base}/createTask', json=create_payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
        data = await r.json()
    if data.get('errorId', 0) != 0:
        raise RuntimeError(f"2captcha createTask error: {data.get('errorDescription')}")
    task_id = data['taskId']
    logger.debug(f'2captcha taskId={task_id}')
    get_payload = {'clientKey': api_key, 'taskId': task_id}
    for _ in range(30):
        await asyncio.sleep(4)
        async with session.post(f'{base}/getTaskResult', json=get_payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
            result = await r.json()
        status = result.get('status')
        if status == 'ready':
            token = result['solution']['token']
            logger.debug(f'2captcha token: {token[:30]}...')
            return token
        elif status in ('processing', 'idle'):
            continue
        else:
            raise RuntimeError(f'2captcha ошибка: {result}')
    raise TimeoutError('2captcha: не решил за 120 сек')

async def solve_turnstile(action: str, proxy: str | None=None) -> str:
    if not config.CAPTCHA_API_KEY:
        raise RuntimeError('CAPTCHA_API_KEY не задан в config.py!')
    website_url = ACTION_URLS.get(action, ACTION_URLS['onboarding'])
    service = config.CAPTCHA_SERVICE.lower()
    for attempt in range(1, 4):
        try:
            _ssl_ctx = ssl.create_default_context()
            _ssl_ctx.check_hostname = False
            _ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=_ssl_ctx)
            async with aiohttp.ClientSession(connector=connector) as session:
                if service == 'anysolver':
                    return await _solve_anysolver(website_url, CF_SITEKEY, action, session, proxy=proxy)
                elif service == '2captcha':
                    return await _solve_2captcha(website_url, CF_SITEKEY, action, session)
                elif service == 'capsolver':
                    # Capsolver оставлен как fallback
                    from cloudflare_api import CHROME_UA
                    base = 'https://api.capsolver.com'
                    api_key = config.CAPTCHA_API_KEY
                    create_payload = {'clientKey': api_key, 'task': {'type': 'AntiTurnstileTaskProxyLess', 'websiteURL': website_url, 'websiteKey': CF_SITEKEY, 'metadata': {'action': action}, 'userAgent': CHROME_UA}}
                    async with session.post(f'{base}/createTask', json=create_payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
                        data = await r.json()
                    if data.get('errorId', 0) != 0:
                        raise RuntimeError(f"Capsolver error: {data.get('errorDescription')}")
                    task_id = data['taskId']
                    get_payload = {'clientKey': api_key, 'taskId': task_id}
                    for _ in range(30):
                        await asyncio.sleep(3 if _ == 0 else 2)
                        async with session.post(f'{base}/getTaskResult', json=get_payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
                            result = await r.json()
                        if result.get('status') == 'ready':
                            return result['solution']['token']
                        elif result.get('status') in ('processing', 'idle'):
                            continue
                        else:
                            raise RuntimeError(f'Capsolver: {result}')
                    raise TimeoutError('Capsolver: timeout')
                else:
                    raise ValueError(f'Неизвестный сервис капчи: {service}')
        except Exception as e:
            logger.warning(f'⚠️ Попытка {attempt}/3 решения Turnstile ({action}) завершилась ошибкой: {e}')
            if attempt == 3:
                raise e
            await asyncio.sleep(2)



async def solve_cf_challenge(url: str, proxy: str) -> dict:

    if not config.CAPTCHA_API_KEY:
        raise RuntimeError('CAPTCHA_API_KEY не задан!')
    base = 'https://api.capsolver.com'
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=_ssl_ctx)
    async with aiohttp.ClientSession(connector=connector) as session:
        from urllib.parse import urlparse
        import urllib.request
        proxy_ip = proxy
        proxy_to_parse = proxy if '://' in proxy else f'http://{proxy}'
        parsed = urlparse(proxy_to_parse)
        try:
            ip = socket.gethostbyname(parsed.hostname)
            auth = ''
            if parsed.username:
                auth = f'{parsed.username}:{parsed.password}@' if parsed.password else f'{parsed.username}@'
            scheme = parsed.scheme or 'http'
            proxy_ip = f'{scheme}://{auth}{ip}:{parsed.port or 80}'
        except Exception as e:
            logger.warning(f'Failed to resolve proxy hostname: {e}')
        payload = {'clientKey': config.CAPTCHA_API_KEY, 'task': {'type': 'AntiCloudflareTask', 'websiteURL': url, 'proxy': proxy_ip}}
        async with session.post(f'{base}/createTask', json=payload, timeout=30) as r:
            data = await r.json()
        if data.get('errorId', 0) != 0:
            raise RuntimeError(f"Capsolver AntiCF error: {data.get('errorDescription')}")
        task_id = data['taskId']
        logger.debug(f'Capsolver AntiCF taskId={task_id}')
        for attempt in range(40):
            await asyncio.sleep(4)
            async with session.post(f'{base}/getTaskResult', json={'clientKey': config.CAPTCHA_API_KEY, 'taskId': task_id}, timeout=30) as r:
                result = await r.json()
            status = result.get('status')
            if status == 'ready':
                token = result['solution']['token']
                ua = result['solution']['userAgent']
                logger.debug(f'Capsolver AntiCF ready!')
                return {'cf_clearance': token, 'user_agent': ua}
            elif status in ('processing', 'idle'):
                continue
            else:
                raise RuntimeError(f'Capsolver AntiCF error: {result}')
        raise TimeoutError('Capsolver AntiCF: timeout')