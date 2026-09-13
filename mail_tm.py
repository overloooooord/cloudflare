import asyncio
import logging
import os
import re
import random
import json
import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.notletters.com'

_email_pool: list[dict] = []
_email_lock = None
_pool_loaded = False


def _load_pool(filepath: str = None):
    global _email_pool, _pool_loaded
    if _pool_loaded:
        return
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), 'emails.txt')

    registered_emails = set()
    try:
        import config
        out_file = getattr(config, 'OUTPUT_FILE', 'results.json')
        if not os.path.isabs(out_file):
            out_file = os.path.join(os.path.dirname(__file__), out_file)
        if os.path.exists(out_file):
            with open(out_file, 'r', encoding='utf-8') as f:
                res_data = json.load(f)
                for entry in res_data.get('clouds', []):
                    reg_email = entry.split(':')[0].strip().lower()
                    if reg_email:
                        registered_emails.add(reg_email)
    except Exception:
        pass

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(':', 1)
            if len(parts) == 2:
                em = parts[0].strip()
                if em.lower() not in registered_emails:
                    _email_pool.append({'email': em, 'password': parts[1].strip()})
    random.shuffle(_email_pool)
    _pool_loaded = True


class OutOfEmailsError(Exception):
    pass


def get_remaining_emails() -> int:
    global _email_pool
    _load_pool()
    return len(_email_pool)


async def create_mailbox(session: aiohttp.ClientSession = None) -> dict:
    global _email_pool, _email_lock
    _load_pool()
    if _email_lock is None:
        _email_lock = asyncio.Lock()

    async with _email_lock:
        if not _email_pool:
            raise OutOfEmailsError('Все почты из emails.txt обработаны!')
        mailbox = _email_pool.pop(0)

    return {
        'email': mailbox['email'],
        'password': mailbox['password'],
        'token': None,
    }


async def _fetch_letters(
    session: aiohttp.ClientSession,
    email: str,
    mail_password: str,
    search: str = None,
) -> list[dict]:
    import config
    api_key = getattr(config, 'NOTLETTERS_API_KEY', '')
    if not api_key:
        raise RuntimeError('NOTLETTERS_API_KEY не задан в config.py!')

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'email': email,
        'password': mail_password,
    }
    if search:
        payload['filters'] = {'search': search}

    async with session.post(
        f'{BASE_URL}/v1/letters',
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=20),
    ) as r:
        if r.status != 200:
            return []
        data = await r.json()
        return data.get('data', {}).get('letters', [])


async def get_existing_message_ids(
    session: aiohttp.ClientSession,
    token: str = None,
    *,
    email: str = None,
    mail_password: str = None,
) -> set:
    if not email or not mail_password:
        return set()
    try:
        letters = await _fetch_letters(session, email, mail_password)
        return {letter['id'] for letter in letters}
    except Exception:
        return set()


async def wait_for_new_message(
    session: aiohttp.ClientSession,
    token: str = None,
    known_ids: set = None,
    timeout: int = 120,
    poll_interval: int = 2,
    *,
    email: str = None,
    mail_password: str = None,
) -> str:
    if known_ids is None:
        known_ids = set()
    if not email or not mail_password:
        raise RuntimeError('email и mail_password обязательны для wait_for_new_message')

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            letters = await _fetch_letters(session, email, mail_password)
            for letter in letters:
                if letter['id'] not in known_ids:
                    html = letter.get('letter', {}).get('html', '')
                    text = letter.get('letter', {}).get('text', '')
                    content = html or text
                    if content:
                        return content
        except Exception:
            pass
        await asyncio.sleep(poll_interval)

    raise TimeoutError(f'Новое письмо не получено за {timeout}s')


def extract_verification_url(html: str) -> str:
    patterns = [
        r'<a\s+[^>]*?href=["\']'
        r'(https?://dash\.cloudflare\.com/email-verification\?token=[^"\']+)'
        r'["\'][^>]*>[\s\S]*?Verify\s+your\s+email',
        r'href=["\'](https?://dash\.cloudflare\.com/email-verification\?token=[^"\']+)["\']',
        r'href=["\'](https?://[^"\']*(?:email-verification|verify-email)[^"\']*token=[^"\']+)["\']',
        r'(https?://dash\.cloudflare\.com/email-verification\?token=[^\s"\'<>]*)',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            url = m.group(1).replace('&amp;', '&')
            if 'unintended' not in url and 'delete' not in url:
                return url
    raise ValueError('Не найден URL верификации в письме')


def extract_verification_token(html: str) -> str:
    patterns = [r'token=([^"&\s\']+)']
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    raise ValueError('Не найден token в письме верификации')


def extract_otp_code(html: str) -> str:
    m = re.search(r'\b(\d{7})\b', html)
    if m:
        return m.group(1)
    raise ValueError('Не найден 7-значный OTP-код в письме')