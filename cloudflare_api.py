import asyncio
import logging
import random
from curl_cffi.requests import AsyncSession
logger = logging.getLogger(__name__)
CF_API = 'https://dash.cloudflare.com/api/v4'
FIREFOX_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0'
CHROME_UA = FIREFOX_UA
BASE_HEADERS = {
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://dash.cloudflare.com',
    'Referer': 'https://dash.cloudflare.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'X-Cross-Site-Security': 'dash',
    'User-Agent': FIREFOX_UA
}

def _make_session(proxy: str | None = None, cookies: dict | None = None) -> AsyncSession:
    kwargs = {'impersonate': 'firefox133'}
    if proxy:
        proxy_url = proxy if '://' in proxy else f'http://{proxy}'
        kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
    session = AsyncSession(**kwargs)
    if cookies:
        for k, v in cookies.items():
            session.cookies.set(k, v, domain='dash.cloudflare.com')
    return session
async def get_security_token(session: AsyncSession) -> str:

    r = await session.get(f'{CF_API}/system/bootstrap', headers=BASE_HEADERS, timeout=30)
    data = r.json()
    logger.debug(f'get_security_token status={r.status_code}')
    if r.status_code != 200:
        raise RuntimeError(f'get_security_token failed {r.status_code}: {r.text[:300]}')
    token = data.get('result', {}).get('data', {}).get('data', {}).get('security_token')
    if not token:
        token = data.get('result', {}).get('security_token')
    if not token:
        raise RuntimeError(f'security_token not found in bootstrap response: {r.text[:300]}')
    return token
async def create_user(session: AsyncSession, email: str, password: str, security_token: str, cf_challenge_response: str, max_retries: int=3) -> dict:

    payload = {'email': email, 'password': password, 'mrk_optin': True, 'security_token': security_token, 'method': 'Onboarding: New_v2', 'locale': 'en-US', 'mrktCheckboxDisplayed': True, 'hCaptchaDisplayed': False, 'cf_challenge_response': cf_challenge_response}
    for attempt in range(1, max_retries + 1):
        r = await session.post(f'{CF_API}/user/create', json=payload, headers=BASE_HEADERS, timeout=30)
        data = r.json()
        logger.debug(f'create_user [{email}] attempt={attempt} status={r.status_code} body={r.text[:200]}')
        if r.status_code in (200, 201):
            return data
        
        errors = data.get('errors', [])
        if errors and any(err.get('code') == 1111 for err in errors):
            raise RuntimeError(f'create_user blocked (1111): {errors[0].get("message")}')

        if r.status_code == 429:
            if attempt < max_retries:
                base_wait = 8 * attempt
                jitter = random.uniform(0, 5 * attempt)
                wait = base_wait + jitter
                logger.warning(f'[{email}] 429 rate limit, wait {wait:.0f}s ({attempt}/{max_retries})')
                await asyncio.sleep(wait)
                continue
            else:
                raise RuntimeError(f'create_user failed {r.status_code} after {max_retries} retries: {r.text[:300]}')
        raise RuntimeError(f'create_user failed {r.status_code}: {r.text[:300]}')
    raise RuntimeError(f'create_user: max retries exhausted for {email}')

async def verify_email(session: AsyncSession, token: str) -> dict:
    try:
        await session.get(f'https://dash.cloudflare.com/email-verification?token={token}', headers=BASE_HEADERS, timeout=20)
    except Exception:
        pass
    headers = {**BASE_HEADERS, 'Referer': f'https://dash.cloudflare.com/email-verification?token={token}'}
    r = await session.put(f'{CF_API}/user/email-verification', json={'token': token}, headers=headers, timeout=30)
    data = r.json()
    if r.status_code != 200 or not data.get('success'):
        raise RuntimeError(f'verify_email failed {r.status_code}: {r.text[:300]}')
    return data


async def check_email_verified(session: AsyncSession) -> bool:
    headers = {**BASE_HEADERS, 'Referer': 'https://dash.cloudflare.com/profile', 'cache-control': 'no-cache', 'pragma': 'no-cache'}
    r = await session.get(f'{CF_API}/user', headers=headers, timeout=20)
    if r.status_code != 200:
        logger.debug(f'check_email_verified: status={r.status_code} body={r.text[:200]}')
        return False
    data = r.json()
    res = data.get('result', {})
    verified = res.get('email_verified', False) or res.get('has_verified_email', False)
    if not verified:
        logger.debug(f'check_email_verified: API responded 200 but email_verified={verified}')
    return bool(verified)


async def login_user(session: AsyncSession, email: str, password: str, cf_challenge_response: str) -> dict:
    payload = {'email': email, 'password': password, 'cf_challenge_response': cf_challenge_response}
    r = await session.post(f'{CF_API}/login', json=payload, headers=BASE_HEADERS, timeout=30)
    data = r.json()
    logger.debug(f'login_user [{email}] status={r.status_code} body={r.text[:200]}')
    if r.status_code != 200:
        raise RuntimeError(f'login_user failed {r.status_code}: {r.text[:300]}')
    return data


async def reauthenticate(session: AsyncSession) -> dict:
    headers = {**BASE_HEADERS, 'Referer': 'https://dash.cloudflare.com/profile/api-tokens', 'Content-Type': 'application/json'}
    r = await session.post(f'{CF_API}/user/reauthenticate', data='', headers=headers, timeout=30)
    data = r.json()
    logger.debug(f'reauthenticate status={r.status_code} body={r.text[:200]}')
    if r.status_code not in (200, 202):
        raise RuntimeError(f'reauthenticate failed {r.status_code}: {r.text[:300]}')
    return data


async def get_global_api_key(session: AsyncSession, otp_code: str, cf_challenge_response: str) -> str:
    payload = {'password': otp_code, 'cf_challenge_response': cf_challenge_response}
    headers = {
        **BASE_HEADERS,
        'Referer': 'https://dash.cloudflare.com/profile/api-tokens',
        'cache-control': 'no-cache',
        'pragma': 'no-cache'
    }

    r = await session.post(f'{CF_API}/user/api_key', json=payload, headers=headers, timeout=30)
    logger.debug(f'get_global_api_key status={r.status_code} body={r.text[:300]}')
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f'get_global_api_key non-JSON response {r.status_code}: {r.text[:300]}')

    if r.status_code == 200 and data.get('success'):
        api_key = (data.get('result') or {}).get('api_key')
        if not api_key:
            raise RuntimeError(f'api_key not found in response: {r.text[:300]}')
        return api_key

    raise RuntimeError(f'get_global_api_key failed {r.status_code}: {r.text[:300]}')