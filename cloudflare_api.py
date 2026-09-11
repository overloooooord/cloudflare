import asyncio
import logging
import random
from curl_cffi.requests import AsyncSession
logger = logging.getLogger(__name__)
CF_API = 'https://dash.cloudflare.com/api/v4'
CHROME_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
BASE_HEADERS = {'Accept': '*/*', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Accept-Language': 'en-US,en;q=0.9', 'Origin': 'https://dash.cloudflare.com', 'Referer': 'https://dash.cloudflare.com/', 'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not_A Brand";v="99"', 'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"', 'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'same-origin', 'X-Cross-Site-Security': 'dash', 'User-Agent': CHROME_UA}
def _make_session(proxy: str | None=None, cookies: dict | None=None) -> AsyncSession:
    kwargs = {'impersonate': 'chrome124'}
    if proxy:
        kwargs['proxies'] = {'http': proxy, 'https': proxy}
    session = AsyncSession(**kwargs)
    if cookies:
        for k, v in cookies.items():
            session.cookies.set(k, v, domain='dash.cloudflare.com')
    return session
async def get_security_token(session: AsyncSession) -> str:

    r = await session.get(f'{CF_API}/system/bootstrap', headers=BASE_HEADERS)
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
        r = await session.post(f'{CF_API}/user/create', json=payload, headers=BASE_HEADERS)
        data = r.json()
        logger.debug(f'create_user [{email}] attempt={attempt} status={r.status_code} body={r.text[:200]}')
        if r.status_code in (200, 201):
            return data
        if r.status_code == 429:
            if attempt < max_retries:
                base_wait = 8 * attempt
                jitter = random.uniform(0, 5 * attempt)
                wait = base_wait + jitter
                logger.warning(f'⏳ [{email}] 429 rate limit на create_user, жду {wait:.0f}s (попытка {attempt}/{max_retries})...')
                await asyncio.sleep(wait)
                continue
            else:
                raise RuntimeError(f'create_user failed {r.status_code} after {max_retries} retries: {r.text[:300]}')
        raise RuntimeError(f'create_user failed {r.status_code}: {r.text[:300]}')
    raise RuntimeError(f'create_user: max retries exhausted for {email}')
async def check_email_verified(session: AsyncSession) -> bool:

    r = await session.get(f'{CF_API}/user', headers={**BASE_HEADERS, 'cache-control': 'no-cache', 'pragma': 'no-cache'})
    if r.status_code != 200:
        return False
    return r.json().get('result', {}).get('email_verified', False)
async def login_user(session: AsyncSession, email: str, password: str, cf_challenge_response: str) -> dict:

    payload = {'email': email, 'password': password, 'cf_challenge_response': cf_challenge_response}
    r = await session.post(f'{CF_API}/login', json=payload, headers=BASE_HEADERS)
    data = r.json()
    logger.debug(f'login_user [{email}] status={r.status_code} body={r.text[:200]}')
    if r.status_code != 200:
        raise RuntimeError(f'login_user failed {r.status_code}: {r.text[:300]}')
    return data
async def reauthenticate(session: AsyncSession) -> dict:

    r = await session.post(f'{CF_API}/user/reauthenticate', data='', headers={**BASE_HEADERS, 'Content-Type': 'application/json'})
    data = r.json()
    logger.debug(f'reauthenticate status={r.status_code} body={r.text[:200]}')
    if r.status_code not in (200, 202):
        raise RuntimeError(f'reauthenticate failed {r.status_code}: {r.text[:300]}')
    return data
async def get_global_api_key(session: AsyncSession, otp_code: str, cf_challenge_response: str) -> str:

    payload = {'password': otp_code, 'cf_challenge_response': cf_challenge_response}
    headers = {**BASE_HEADERS, 'cache-control': 'no-cache', 'pragma': 'no-cache'}
    r = await session.post(f'{CF_API}/user/api_key', json=payload, headers=headers)
    data = r.json()
    logger.debug(f'get_global_api_key status={r.status_code} body={r.text[:200]}')
    if r.status_code != 200:
        raise RuntimeError(f'get_global_api_key failed {r.status_code}: {r.text[:300]}')
    api_key = (data.get('result') or {}).get('api_key')
    if not api_key:
        raise RuntimeError(f'api_key not found in response: {r.text[:300]}')
    return api_key