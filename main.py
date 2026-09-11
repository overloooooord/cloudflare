import asyncio
import argparse
import logging
import random
import socket
import ssl
import sys
import time
import aiohttp
import config
import mail_tm
import turnstile
import cloudflare_api as cf_api
import proxy_utils
import results as res_module
import verify_browser
from cloudflare_api import _make_session

def generate_random_password(length: int = 16) -> str:
    import string
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%^&*"
    # Гарантируем буквы в начале и в конце, чтобы Cloudflare не ругался на спецсимволы по краям
    password = [
        random.choice(lower),
        random.choice(upper),
        random.choice(digits),
        random.choice(special)
    ]
    all_chars = lower + upper + digits + special
    password += [random.choice(all_chars) for _ in range(max(0, length - 4))]
    random.shuffle(password)
    res = "".join(password).strip()
    return res

def setup_logging(debug: bool=False):
    level = logging.DEBUG if debug else logging.INFO
    fmt = '%(asctime)s [%(levelname)s] %(message)s'
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)
    logging.getLogger("pycares").setLevel(logging.ERROR)
    logging.getLogger("aiodns").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)
class ProxyClientSession(aiohttp.ClientSession):
    def __init__(self, *args, proxy_url: str | None=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.proxy_url = proxy_url
    async def _request(self, method, str_or_url, **kwargs):
        if self.proxy_url and 'proxy' not in kwargs:
            kwargs['proxy'] = self.proxy_url
        return await super()._request(method, str_or_url, **kwargs)
class Stats:
    def __init__(self):
        self.success = 0
        self.failed = 0
        self._lock = asyncio.Lock()
        self._start = time.time()
    async def inc_success(self):
        async with self._lock:
            self.success += 1
    async def inc_failed(self):
        async with self._lock:
            self.failed += 1
    def summary(self) -> str:
        elapsed = time.time() - self._start
        rpm = self.success / elapsed * 60 if elapsed > 0 else 0
        return f'✅ {self.success} | ❌ {self.failed} | ⏱ {elapsed:.0f}s | 🚀 {rpm:.1f}/min'
async def register_one(proxy: str | None, stats: Stats, debug: bool=False) -> bool:
    """Регистрация одного аккаунта."""
    step = 'init'
    email = mail_email = mail_pass = cloud_pass = api_key = ''
    reg_cookies = []
    startup_jitter = random.uniform(1, 5)
    logger.info(f'⏳ Задержка перед стартом: {startup_jitter:.0f}s (anti-rate-limit)')
    await asyncio.sleep(startup_jitter)
    try:
        step = 'createMail'
        proxy_url = proxy if proxy and (proxy.startswith('http://') or proxy.startswith('https://')) else f'http://{proxy}' if proxy else None
        _mail_ssl = ssl.create_default_context()
        _mail_ssl.check_hostname = False
        _mail_ssl.verify_mode = ssl.CERT_NONE
        _mail_connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=_mail_ssl)
        async with ProxyClientSession(connector=_mail_connector, proxy_url=proxy_url) as mail_session:
            mailbox = await mail_tm.create_mailbox(mail_session)
            mail_email = mailbox['email']
            mail_pass = mailbox['password']
            mail_token = mailbox['token']
            if config.CLOUDFLARE_PASSWORD == 'random':
                cloud_pass = generate_random_password()
            else:
                cloud_pass = config.CLOUDFLARE_PASSWORD
            email = mail_email
            logger.info(f'📧 [{email}] Почта создана')
            # Запоминаем known_ids ДО регистрации — письмо может прийти во время signup
            known_ids = await mail_tm.get_existing_message_ids(mail_session, mail_token)
            step = 'signup'
            signup_ok = False
            reg_cookies = []
            
            # Регистрация через браузер — Turnstile решается автоматически
            logger.info(f'🌐 [{email}] Регистрация через браузер...')

            # after_signup_callback: вызывается в ТОМ ЖЕ браузере сразу после регистрации
            async def after_signup_callback(page):
                logger.info(f'📨 [{email}] Аккаунт создан. Ждём письмо верификации...')
                html = await mail_tm.wait_for_new_message(mail_session, mail_token, known_ids, timeout=180, poll_interval=2)
                verify_url = mail_tm.extract_verification_url(html)
                logger.info(f'🔗 [{email}] Ссылка верификации получена: {verify_url}')

                # Открываем ссылку верификации В НОВОЙ ВКЛАДКЕ
                logger.info(f'🌐 [{email}] Открываем новую вкладку для перехода по ссылке верификации...')
                verify_tab = await page.context.new_page()
                try:
                    logger.info(f'🔗 [{email}] Переходим по ссылке: {verify_url}')
                    await verify_tab.goto(verify_url, wait_until='domcontentloaded', timeout=60000)
                    await asyncio.sleep(2)

                    # Проверяем и решаем WAF Challenge на странице верификации
                    logger.info(f'🔐 [{email}] Проверяем WAF Turnstile на странице верификации...')
                    for _waf in range(8):
                        await asyncio.sleep(1.2)
                        cf_frames = [f for f in verify_tab.frames if 'challenges.cloudflare.com' in f.url or 'challenge-platform' in f.url]
                        try:
                            pt = await verify_tab.evaluate('document.body?.innerText || ""')
                        except Exception:
                            pt = ''
                        is_waf = any(kw in pt.lower() for kw in ['security verification', 'verify you are human', 'just a moment'])

                        if cf_frames or is_waf:
                            logger.info(f'🔐 [{email}] Решаем WAF Challenge на странице верификации (раунд {_waf+1})...')
                            await verify_browser.bypass_turnstile_safely(verify_tab, timeout=12000, max_attempts=3)
                            await asyncio.sleep(2)
                        else:
                            if _waf >= 2:
                                break

                    # Ожидаем подтверждения и редиректа в новой вкладке
                    logger.info(f'⏳ [{email}] Ожидаем подтверждения в новой вкладке...')
                    for _wv in range(15):
                        await asyncio.sleep(1)
                        cur_url = verify_tab.url or ''
                        try:
                            p_txt = await verify_tab.evaluate('document.body?.innerText?.toLowerCase() || ""')
                        except Exception:
                            p_txt = ''
                        
                        # Если страница ушла со страницы верификации на дашборд — почта подтверждена!
                        if 'email-verification' not in cur_url and 'token=' not in cur_url and len(cur_url) > 20:
                            logger.info(f'✅ [{email}] Редирект с email-verification на дашборд ({cur_url}) — подтверждено!')
                            break
                        if 'verified' in p_txt or 'confirmed' in p_txt or any(p in cur_url for p in ['/home', '/overview', '/websites']):
                            logger.info(f'✅ [{email}] Новая вкладка подтвердила верификацию email (url={cur_url})!')
                            break
                except Exception as ve:
                    logger.warning(f'verify_tab error: {ve}')
                finally:
                    try:
                        await verify_tab.close()
                        logger.info(f'🌐 [{email}] Вкладка верификации закрыта')
                    except Exception:
                        pass

                await asyncio.sleep(1)

                # ── Теперь переходим на /profile/api-tokens в основной сессии ──
                logger.info(f'🔑 [{email}] Переходим на /profile/api-tokens...')
                try:
                    await page.goto('https://dash.cloudflare.com/profile/api-tokens', wait_until='domcontentloaded', timeout=60000)
                except Exception as te:
                    logger.warning(f'goto /profile/api-tokens: {te}')
                await asyncio.sleep(3)
                await verify_browser.dismiss_cookie_banner(page)

                # Запоминаем текущие msg ids ДО нажатия Send Code
                known_ids_otp = await mail_tm.get_existing_message_ids(mail_session, mail_token)

                # Кликаем View на Global API Key
                logger.info(f'👆 [{email}] Кликаем View...')
                for _v in range(10):
                    try:
                        clicked = await page.evaluate('''() => {
                            const rows = document.querySelectorAll('tr, div[class*="row"], div[class*="item"]');
                            for (const row of rows) {
                                if (row.innerText && row.innerText.includes('Global API Key')) {
                                    const btn = row.querySelector('button, a');
                                    if (btn && (btn.innerText.includes('View') || btn.textContent.includes('View'))) {
                                        btn.click();
                                        return true;
                                    }
                                }
                            }
                            const allBtns = document.querySelectorAll('button');
                            for (const b of allBtns) {
                                if (b.innerText.trim() === 'View' || b.textContent.trim() === 'View') {
                                    b.click();
                                    return true;
                                }
                            }
                            return false;
                        }''')
                        if clicked:
                            logger.info(f'✅ [{email}] View нажат')
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(1)

                await asyncio.sleep(1.5)

                # Кликаем Send Verification Code
                logger.info(f'📨 [{email}] Ищем кнопку Send Verification Code...')
                for _s in range(10):
                    try:
                        sent = await page.evaluate('''() => {
                            const dlg = document.querySelector('div[role="dialog"], [data-modal], [aria-modal="true"]');
                            if (!dlg) return false;
                            const btns = dlg.querySelectorAll('button');
                            for (const b of btns) {
                                const txt = (b.innerText || b.textContent || '').toLowerCase();
                                if (txt.includes('send') && !txt.includes('cancel') && !b.disabled) {
                                    b.click();
                                    return true;
                                }
                            }
                            return false;
                        }''')
                        if sent:
                            logger.info(f'✅ [{email}] Send Verification Code нажат')
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(1)

                # Ждём OTP из почты
                logger.info(f'📨 [{email}] Ждём OTP-код...')
                html2 = await mail_tm.wait_for_new_message(mail_session, mail_token, known_ids_otp, timeout=120, poll_interval=2)
                otp_code = mail_tm.extract_otp_code(html2)
                logger.info(f'🔢 [{email}] OTP получен: {otp_code}')

                # Вводим OTP в поле модалки
                logger.info(f'✏️ [{email}] Вводим OTP...')
                await asyncio.sleep(1)
                try:
                    await page.evaluate('''(code) => {
                        const dlg = document.querySelector('div[role="dialog"], [data-modal], [aria-modal="true"]');
                        if (!dlg) return;
                        const inputs = dlg.querySelectorAll('input[type="text"], input[type="number"], input:not([type="hidden"])');
                        for (const inp of inputs) {
                            if (inp.type !== 'hidden') {
                                const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                s.call(inp, code);
                                inp.dispatchEvent(new Event("input", {bubbles: true}));
                                inp.dispatchEvent(new Event("change", {bubbles: true}));
                                break;
                            }
                        }
                    }''', otp_code)
                    logger.info(f'✅ [{email}] OTP введён')
                except Exception as e:
                    logger.warning(f'OTP fill error: {e}')

                # Решаем Turnstile в модалке КЛИКОМ (тот же IP = нет 1201)
                logger.info(f'🔐 [{email}] Решаем Turnstile кликом...')
                await asyncio.sleep(1)
                await verify_browser.bypass_turnstile_safely(page, timeout=15000, max_attempts=3)

                # Перехватчик ответа api_key
                captured_api_key = None
                async def _on_api_key_response(response):
                    nonlocal captured_api_key
                    if '/user/api_key' not in response.url:
                        return
                    try:
                        body = await response.json()
                        logger.info(f'🔑 [{email}] api_key response: {body}')
                        if body.get('success'):
                            ak = (body.get('result') or {}).get('api_key')
                            if ak:
                                captured_api_key = ak
                    except Exception:
                        pass
                page.on('response', _on_api_key_response)

                # Нажимаем кнопку Submit в модалке (именно внутри dialog, исключая Cancel и Send)
                logger.info(f'📤 [{email}] Нажимаем Submit в модалке...')
                await asyncio.sleep(0.5)
                try:
                    btn_text = await page.evaluate('''() => {
                        const dlg = document.querySelector('div[role="dialog"], [data-modal], [aria-modal="true"]');
                        if (!dlg) return 'no_dialog';
                        const btns = Array.from(dlg.querySelectorAll('button'));
                        const names = btns.map(b => (b.innerText || b.textContent || '').trim());
                        
                        // 1. Ищем явные целевые кнопки: View, Submit, Confirm, Verify
                        for (const b of btns) {
                            const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                            if ((txt === 'view' || txt === 'submit' || txt === 'confirm' || txt === 'verify') && !b.disabled) {
                                b.click();
                                return 'clicked_primary: ' + txt;
                            }
                        }
                        
                        // 2. Fallback: любая активная кнопка внутри диалога кроме Cancel и Send
                        for (const b of btns) {
                            const txt = (b.innerText || b.textContent || '').trim();
                            const low = txt.toLowerCase();
                            if (low.includes('cancel') || low.includes('send') || low.includes('close')) continue;
                            if (!b.disabled && txt.length > 0) {
                                b.click();
                                return 'clicked_fallback: ' + txt;
                            }
                        }
                        return 'not_found: ' + names.join(', ');
                    }''')
                    logger.info(f'📤 [{email}] Submit result: {btn_text}')
                except Exception as e:
                    logger.warning(f'Submit error: {e}')

                # Ждём ответ с ключом
                logger.info(f'⏳ [{email}] Ждём ответ с API ключом...')
                for _w in range(30):
                    await asyncio.sleep(1)
                    if captured_api_key:
                        logger.info(f'🗝️ [{email}] ✅ API Key перехвачен: {captured_api_key}')
                        return captured_api_key

                    # Fallback 1: читаем из DOM диалога (если ключ отобразился в инпуте после подтверждения)
                    try:
                        modal_val = await page.evaluate('''() => {
                            const dlg = document.querySelector('div[role="dialog"], [data-modal], [aria-modal="true"]');
                            if (!dlg) return null;
                            const els = dlg.querySelectorAll('input, code, pre, span, p');
                            for (const el of els) {
                                const v = (el.value || el.innerText || el.textContent || '').trim();
                                if ((v.startsWith('cfk_') || /^[a-f0-9]{37,}$/i.test(v)) && !v.includes(' ')) {
                                    return v;
                                }
                            }
                            return null;
                        }''')
                        if modal_val:
                            logger.info(f'🗝️ [{email}] ✅ API Key из DOM модалки: {modal_val}')
                            return modal_val
                    except Exception:
                        pass

                    # Fallback 2: ищем через fetch bootstrap
                    try:
                        check = await page.evaluate('''() =>
                            fetch('/api/v4/system/bootstrap', {
                                headers: {'Accept': 'application/json', 'X-Cross-Site-Security': 'dash'}
                            }).then(r => r.json())
                        ''')
                        ak = (check.get('result') or {}).get('api_key')
                        if ak and len(ak) >= 32:
                            logger.info(f'🗝️ [{email}] ✅ API Key из bootstrap: {ak}')
                            return ak
                    except Exception:
                        pass

                logger.warning(f'⚠️ [{email}] API Key не получен')
                return None

            signup_ok, api_key = await verify_browser.signup_via_browser(
                email, cloud_pass, proxy, after_signup_callback=after_signup_callback
            )
            if not signup_ok:
                raise RuntimeError('signup_via_browser failed')
            logger.info(f'🆔 [{email}] Аккаунт создан через браузер')
            if not api_key:
                raise RuntimeError('Не удалось получить Global API Key через браузер')

        step = 'save'
        await res_module.save_result(config.OUTPUT_FILE, email=mail_email, mail_password=mail_pass, cloud_password=cloud_pass, api_key=api_key, fmt=config.OUTPUT_FORMAT)
        logger.info(f'💾 [{email}] → {config.OUTPUT_FILE}')
        await stats.inc_success()
        return True
    except Exception as e:
        logger.error(f"❌ [{email or 'N/A'}] Шаг [{step}]: {e}")
        if debug:
            logger.exception('Traceback:')
        await stats.inc_failed()
        return False
async def run_forever(count: int | None, proxy_pool: proxy_utils.ProxyPool, debug: bool):
    semaphore = asyncio.Semaphore(config.THREADS)
    stats = Stats()
    tasks = []
    shutdown = asyncio.Event()
    async def worker():
        if shutdown.is_set():
            return False
        async with semaphore:
            if shutdown.is_set():
                return False
            proxy = proxy_pool.get()
            ok = await register_one(proxy, stats, debug=debug)
            logger.info(f'📊 {stats.summary()}')
            return ok
    try:
        if count:
            tasks = [asyncio.create_task(worker()) for _ in range(count)]
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            while not shutdown.is_set():
                active = sum((1 for t in tasks if not t.done()))
                while active < config.THREADS:
                    tasks.append(asyncio.create_task(worker()))
                    active += 1
                await asyncio.sleep(0.2)
                tasks = [t for t in tasks if not t.done()]
    except asyncio.CancelledError:
        pass
    finally:
        shutdown.set()
        pending = [t for t in tasks if not t.done()]
        if pending:
            logger.info(f'⏳ Ожидаем завершения {len(pending)} задач...')
            done, still_pending = await asyncio.wait(pending, timeout=5)
            for t in still_pending:
                t.cancel()
        logger.info(f'\n🏁 Итого: {stats.summary()}')
def parse_args():
    p = argparse.ArgumentParser(description='Cloudflare Autoreger + Global API Key')
    p.add_argument('--count', type=int, default=None, help='Кол-во аккаунтов (по умолчанию из config.COUNT)')
    p.add_argument('--threads', type=int, default=None, help=f'Потоков (default: {config.THREADS})')
    p.add_argument('--proxy-file', type=str, default=None)
    p.add_argument('--output', type=str, default=None)
    p.add_argument('--debug', action='store_true')
    return p.parse_args()
async def run_diagnostics(proxy: str | None):
    """Диагностика окружения при старте — проверяет все критические зависимости."""
    import platform
    logger.info('=' * 60)
    logger.info('🔍 ДИАГНОСТИКА ОКРУЖЕНИЯ')
    logger.info(f'   OS: {platform.system()} {platform.release()} ({platform.machine()})')
    logger.info(f'   Python: {sys.version}')
    logger.info(f'   Event Loop: {type(asyncio.get_event_loop()).__name__}')

    # 1. Проверка curl_cffi
    try:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate='chrome124') as s:
            r = await s.get('https://dash.cloudflare.com/api/v4/system/bootstrap', timeout=15)
            logger.info(f'   ✅ curl_cffi → Cloudflare API: OK (status={r.status_code})')
    except Exception as e:
        logger.error(f'   ❌ curl_cffi → Cloudflare API: {type(e).__name__}: {e}')

    # 2. Проверка aiohttp БЕЗ прокси → mail.tm
    try:
        _ssl = ssl.create_default_context()
        _ssl.check_hostname = False
        _ssl.verify_mode = ssl.CERT_NONE
        conn = aiohttp.TCPConnector(family=socket.AF_INET, ssl=_ssl)
        async with aiohttp.ClientSession(connector=conn) as s:
            async with s.get('https://api.mail.tm/domains?page=1', timeout=aiohttp.ClientTimeout(total=15)) as r:
                logger.info(f'   ✅ aiohttp (без прокси) → mail.tm: OK (status={r.status})')
    except Exception as e:
        logger.error(f'   ❌ aiohttp (без прокси) → mail.tm: {type(e).__name__}: {e}')

    # 3. Проверка aiohttp ЧЕРЕЗ прокси → mail.tm
    if proxy:
        proxy_url = proxy if proxy.startswith('http://') or proxy.startswith('https://') else f'http://{proxy}'
        try:
            _ssl2 = ssl.create_default_context()
            _ssl2.check_hostname = False
            _ssl2.verify_mode = ssl.CERT_NONE
            conn2 = aiohttp.TCPConnector(family=socket.AF_INET, ssl=_ssl2)
            async with aiohttp.ClientSession(connector=conn2) as s:
                async with s.get('https://api.mail.tm/domains?page=1', proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    logger.info(f'   ✅ aiohttp (через прокси) → mail.tm: OK (status={r.status})')
        except Exception as e:
            logger.error(f'   ❌ aiohttp (через прокси) → mail.tm: {type(e).__name__}: {e}')
            logger.error(f'      Прокси: {proxy_url}')
            logger.info(f'   💡 Совет: если aiohttp без прокси работает, а через прокси нет —')
            logger.info(f'      попробуйте формат прокси: http://user:pass@host:port')
            logger.info(f'      или проверьте, что прокси поддерживает HTTPS CONNECT')

        # 4. Проверка curl_cffi ЧЕРЕЗ прокси → mail.tm
        try:
            from curl_cffi.requests import AsyncSession
            async with AsyncSession(impersonate='chrome124', proxies={'http': proxy_url, 'https': proxy_url}) as s:
                r = await s.get('https://api.mail.tm/domains?page=1', timeout=15)
                logger.info(f'   ✅ curl_cffi (через прокси) → mail.tm: OK (status={r.status_code})')
        except Exception as e:
            logger.error(f'   ❌ curl_cffi (через прокси) → mail.tm: {type(e).__name__}: {e}')
    else:
        logger.info('   ⏭️  Прокси не указан, пропускаем проверку через прокси')

    # 5. Проверка Camoufox
    try:
        from camoufox.async_api import AsyncCamoufox
        logger.info(f'   ✅ Camoufox: импорт OK')
    except ImportError as e:
        logger.error(f'   ❌ Camoufox: {e}')
        logger.info(f'      Установите: pip install camoufox && python -m camoufox fetch')

    logger.info('=' * 60)

def main():
    # Windows: принудительно используем SelectorEventLoop,
    # тк. ProactorEventLoop ломает aiohttp HTTPS-прокси на Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    args = parse_args()
    debug = args.debug or config.DEBUG
    setup_logging(debug)
    if args.threads:
        config.THREADS = args.threads
    if args.output:
        config.OUTPUT_FILE = args.output
    count = args.count if args.count else config.COUNT if config.COUNT else None
    proxy_file = args.proxy_file or config.PROXIES_FILE
    proxy_pool = proxy_utils.ProxyPool.from_file(proxy_file)
    if proxy_pool.is_empty:
        logger.warning('⚠️ Прокси не загружены — работаем без прокси')
    else:
        logger.info(f'🌐 Загружено {len(proxy_pool)} прокси')
    logger.info(f"🚀 threads={config.THREADS} | output={config.OUTPUT_FILE} | count={('∞' if not count else count)}")
    loop = asyncio.new_event_loop()
    # Запускаем диагностику перед основным циклом
    test_proxy = proxy_pool.get() if not proxy_pool.is_empty else None
    loop.run_until_complete(run_diagnostics(test_proxy))
    main_task = loop.create_task(run_forever(count=count, proxy_pool=proxy_pool, debug=debug))
    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        logger.info('\n⛔ Остановка... ожидаем завершения текущих задач...')
        main_task.cancel()
        try:
            loop.run_until_complete(main_task)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
    finally:
        loop.close()
if __name__ == '__main__':
    main()