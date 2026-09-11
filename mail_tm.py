import asyncio
import logging
import re
import socket
import string
import random
import aiohttp
logger = logging.getLogger(__name__)
BASE_URL = 'https://api.mail.tm'
def _random_str(length: int, chars: str=string.ascii_lowercase) -> str:
    return ''.join(random.choices(chars, k=length))
async def get_domain(session: aiohttp.ClientSession) -> str:
    """Получить первый доступный домен mail.tm."""
    for attempt in range(8):
        try:
            async with session.get(f'{BASE_URL}/domains?page=1', headers={'Accept': '*/*'}, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 429:
                    wait = 5 * (attempt + 1)
                    logger.warning(f'mail.tm /domains 429 — rate limit, жду {wait}s...')
                    await asyncio.sleep(wait)
                    continue
                if r.status != 200:
                    text = await r.text()
                    logger.warning(f'mail.tm /domains статус {r.status}: {text[:200]}')
                    await asyncio.sleep(3)
                    continue
                data = await r.json()
                members = data.get('hydra:member', [])
                if members:
                    return members[0]['domain']
                logger.warning(f'mail.tm /domains: пустой список доменов (попытка {attempt + 1}/8)')
        except aiohttp.ClientError as e:
            logger.warning(f'mail.tm /domains сетевая ошибка (попытка {attempt + 1}/8): {type(e).__name__}: {e}')
            logger.debug(f'mail.tm /domains traceback:', exc_info=True)
        except Exception as e:
            logger.warning(f'mail.tm /domains неожиданная ошибка (попытка {attempt + 1}/8): {type(e).__name__}: {e}')
            logger.debug(f'mail.tm /domains traceback:', exc_info=True)
        await asyncio.sleep(3 + attempt * 2)
    raise RuntimeError('mail.tm: не удалось получить домен')

async def create_mailbox(session: aiohttp.ClientSession) -> dict:

    domain = await get_domain(session)
    login = 'fast_' + _random_str(10)
    password = _random_str(10, string.ascii_lowercase + string.digits)
    email = f'{login}@{domain}'
    payload = {'address': email, 'password': password}
    headers = {'Accept': '*/*', 'Content-Type': 'application/json'}
    for attempt in range(6):
        try:
            async with session.post(f'{BASE_URL}/accounts', json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status in (200, 201):
                    break
                if r.status == 429:
                    wait = 3 * 2 ** attempt
                    logger.debug(f'mail.tm 429, ждём {wait}s...')
                    await asyncio.sleep(wait)
                    continue
                text = await r.text()
                raise RuntimeError(f'mail.tm create account {r.status}: {text}')
        except aiohttp.ClientError as e:
            if attempt == 5:
                raise
            await asyncio.sleep(2)
    for attempt in range(6):
        try:
            async with session.post(f'{BASE_URL}/token', json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    token = data.get('token')
                    if token:
                        return {'email': email, 'password': password, 'token': token}
                if r.status == 429:
                    wait = 3 * 2 ** attempt
                    await asyncio.sleep(wait)
                    continue
                text = await r.text()
                raise RuntimeError(f'mail.tm get token {r.status}: {text}')
        except aiohttp.ClientError:
            if attempt == 5:
                raise
            await asyncio.sleep(2)
    raise RuntimeError('mail.tm: не удалось получить токен')
async def wait_for_message(session: aiohttp.ClientSession, token: str, timeout: int=120, poll_interval: int=5) -> str:

    auth_headers = {'Authorization': f'Bearer {token}', 'Accept': '*/*'}
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with session.get(f'{BASE_URL}/messages?page=1', headers=auth_headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    members = data.get('hydra:member', [])
                    if members:
                        msg_id = members[0]['id']
                        async with session.get(f'{BASE_URL}/messages/{msg_id}', headers=auth_headers, timeout=aiohttp.ClientTimeout(total=15)) as r2:
                            if r2.status == 200:
                                msg = await r2.json()
                                html_parts = msg.get('html', [])
                                text_parts = msg.get('text', [])
                                if html_parts:
                                    return html_parts[0]
                                if text_parts:
                                    return text_parts[0]
        except Exception:
            pass
        await asyncio.sleep(poll_interval)
    raise TimeoutError('mail.tm: письмо не пришло за отведённое время')
async def wait_for_new_message(session: aiohttp.ClientSession, token: str, known_ids: set, timeout: int=120, poll_interval: int=5) -> str:
    
    auth_headers = {'Authorization': f'Bearer {token}', 'Accept': '*/*'}
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with session.get(f'{BASE_URL}/messages?page=1', headers=auth_headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    members = data.get('hydra:member', [])
                    for m in members:
                        msg_id = m['id']
                        if msg_id not in known_ids:
                            async with session.get(f'{BASE_URL}/messages/{msg_id}', headers=auth_headers, timeout=aiohttp.ClientTimeout(total=15)) as r2:
                                if r2.status == 200:
                                    msg = await r2.json()
                                    html_parts = msg.get('html', [])
                                    text_parts = msg.get('text', [])
                                    if html_parts:
                                        return html_parts[0]
                                    if text_parts:
                                        return text_parts[0]
        except Exception:
            pass
        await asyncio.sleep(poll_interval)
    raise TimeoutError('mail.tm: новое письмо не пришло за отведённое время')
def extract_verification_token(html: str) -> str:
    patterns = ['token=([^"&\\s\\\']+)']
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    raise ValueError('Не найден token в письме верификации')
def extract_verification_url(html: str) -> str:
    # 1. Ссылка кнопки 'Verify your email' со ссылкой на dash.cloudflare.com/email-verification?token=
    patterns = [
        r'<a\s+[^>]*?href=["\'](https?://dash\.cloudflare\.com/email-verification\?token=[^"\']+)["\'][^>]*>[\s\S]*?Verify\s+your\s+email',
        r'href=["\'](https?://dash\.cloudflare\.com/email-verification\?token=[^"\']+)["\']',
        r'href=["\'](https?://[^"\']*(?:email-verification|verify-email)[^"\']*token=[^"\']+)["\']',
        r'(https?://dash\.cloudflare\.com/email-verification\?token=[^\s"\'<>]*)'
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            url = m.group(1).replace('&amp;', '&')
            if 'unintended' not in url and 'delete' not in url:
                return url

    raise ValueError('Не найден URL верификации в письме')
def extract_otp_code(html: str) -> str:
    m = re.search('\\b(\\d{7})\\b', html)
    if m:
        return m.group(1)
    raise ValueError('Не найден 7-значный OTP-код в письме')
async def get_existing_message_ids(session: aiohttp.ClientSession, token: str) -> set:
    auth_headers = {'Authorization': f'Bearer {token}', 'Accept': '*/*'}
    try:
        async with session.get(f'{BASE_URL}/messages?page=1', headers=auth_headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                data = await r.json()
                return {m['id'] for m in data.get('hydra:member', [])}
    except Exception:
        pass
    return set()