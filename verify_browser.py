import asyncio
import logging
import random
from camoufox import DefaultAddons

logger = logging.getLogger(__name__)


def _build_camoufox_args(proxy: str | None = None) -> dict:
    user_agent = random.choice([
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
    ])
    args = {
        'headless': False,
        'humanize': 1.5,
        'geoip': False,
        'enable_cache': False,
        'exclude_addons': [DefaultAddons.UBO],
        'os': 'windows',
        'block_images': False,
        'block_webrtc': False,
        'block_webgl': False,
        'window': (1280, 1024),
        'firefox_user_prefs': {
            'security.csp.enable': False,
            'browser.sessionhistory.max_entries': 3,
            'browser.cache.memory.enable': False,
            'dom.max_script_run_time': 20,
            'dom.max_chrome_script_run_time': 20,
            'network.http.keep-alive.timeout': 300,
            'network.http.max-persistent-connections-per-server': 6,
            'privacy.trackingprotection.enabled': False,
            'media.autoplay.default': 5,
            'intl.accept_languages': 'en-US,en',
            'general.useragent.override': user_agent,
            'browser.startup.firstrunSkipsHomepage': True,
            'browser.startup.homepage_override.mstone': 'ignore',
            'browser.shell.checkDefaultBrowser': False,
            'browser.startup.page': 0,
            'browser.sessionstore.enabled': False,
            'browser.sessionstore.resume_from_crash': False,
        }
    }
    if proxy:
        from urllib.parse import urlparse
        proxy_str = proxy if proxy.startswith('http://') or proxy.startswith('https://') else f'http://{proxy}'
        parsed = urlparse(proxy_str)
        args['proxy'] = {
            'server': f'http://{parsed.hostname}:{parsed.port}',
            'username': parsed.username or '',
            'password': parsed.password or '',
        }
    return args


async def dismiss_cookie_banner(page) -> bool:
    """Удаляет и закрывает оверлеи OneTrust и cookie-баннеры."""
    try:
        removed = await page.evaluate('''() => {
            let clicked = false;
            const otAccept = document.querySelector('#onetrust-accept-btn-handler, button#onetrust-accept-btn-handler');
            if (otAccept) {
                otAccept.click();
                clicked = true;
            }
            const otReject = document.querySelector('#onetrust-reject-all-handler, button#onetrust-reject-all-handler');
            if (otReject && !clicked) {
                otReject.click();
                clicked = true;
            }

            const COOKIE_ACCEPT = [
                'accept all cookies', 'accept all', 'accept cookies', 'reject all',
                'alle cookies akzeptieren', 'alle akzeptieren', 'alle ablehnen',
                'akzeptieren', 'ablehnen'
            ];
            for (const b of document.querySelectorAll('button, a')) {
                const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                if (COOKIE_ACCEPT.includes(txt)) {
                    b.click();
                    clicked = true;
                    break;
                }
            }

            const closeBtn = document.querySelector(
                'button[aria-label*="close" i], button[aria-label*="dismiss" i], .onetrust-close-btn-handler, #onetrust-close-btn-container button'
            );
            if (closeBtn) {
                closeBtn.click();
                clicked = true;
            }

            const otSdk = document.querySelector('#onetrust-consent-sdk, #onetrust-banner-sdk');
            if (otSdk) {
                otSdk.style.display = 'none';
                try { otSdk.remove(); } catch(e) {}
                clicked = true;
            }
            document.querySelectorAll('.onetrust-pc-dark-filter, [id*="onetrust"]').forEach(el => {
                el.style.display = 'none';
                try { el.remove(); } catch(e) {}
            });

            const COOKIE_DETECT = ['cookie', 'akzeptieren', 'ablehnen', 'einstellung', 'privacy', 'consent'];
            for (const d of document.querySelectorAll('[role="dialog"], [aria-modal="true"]')) {
                const txt = (d.innerText || '').toLowerCase();
                if (COOKIE_DETECT.some(kw => txt.includes(kw))) {
                    d.style.display = 'none';
                    try { d.remove(); } catch(e) {}
                    clicked = true;
                }
            }

            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';
            return clicked;
        }''')
        if removed:
            return True
    except Exception:
        pass

    try:
        cookie_btn = page.locator(
            '#onetrust-accept-btn-handler, '
            'button#onetrust-accept-btn-handler, '
            'button:has-text("Accept All Cookies"), '
            'button:has-text("Accept all cookies"), '
            'button:has-text("Reject All"), '
            'button.onetrust-close-btn-handler'
        ).first
        if await cookie_btn.count() > 0 and await cookie_btn.is_visible():
            await cookie_btn.click(timeout=800)
            return True
    except Exception:
        pass
    return False


async def _is_turnstile_solved(page) -> bool:
    try:
        return await page.evaluate('''() => {
            const inputs = document.querySelectorAll(
                'input[name*="turnstile"], input[name*="cf-"], [data-turnstile-response], input[name="cf_challenge_response"], input[id*="cf-chl-widget"]'
            );
            for (const inp of inputs) {
                if (inp.value && inp.value.length > 20) return true;
            }
            const widgets = document.querySelectorAll('.cf-turnstile, [data-sitekey]');
            for (const w of widgets) {
                const resp = w.querySelector('input[type="hidden"]');
                if (resp && resp.value && resp.value.length > 20) return true;
            }
            return false;
        }''')
    except Exception:
        return False


async def bypass_turnstile_safely(page, timeout=15000, max_attempts=6) -> bool:
    try:
        init_pt = (await page.evaluate('document.body?.innerText || ""')).lower()
    except Exception:
        init_pt = ''
    was_waf = any(kw in init_pt for kw in ['security verification', 'just a moment', 'verify you are human'])

    for attempt in range(1, max_attempts + 1):
        if await _is_turnstile_solved(page):
            logger.info('✅ Cloudflare Turnstile решён!')
            return True

        # Скроллим виджет в центр видимой области
        try:
            await page.evaluate('''() => {
                const el = document.querySelector('iframe[src*="challenges.cloudflare.com"], iframe[src*="challenge-platform"], div[class*="cf-turnstile"]');
                if (el) el.scrollIntoView({ block: "center", behavior: "instant" });
            }''')
            await asyncio.sleep(0.2)
        except Exception:
            pass

        target_box = None
        attempt_deadline = asyncio.get_event_loop().time() + 5.0
        while asyncio.get_event_loop().time() < attempt_deadline:
            # 1. Поиск через page.frames и frame_element (прямой доступ к реальному фрейму Turnstile)
            for f in page.frames:
                if 'challenges.cloudflare.com' in f.url or 'challenge-platform' in f.url:
                    try:
                        el = await f.frame_element()
                        b = await el.bounding_box()
                        if b and b['width'] > 40 and b['height'] > 20:
                            target_box = b
                            break
                    except Exception:
                        pass
            if target_box:
                break

            # 2. Поиск через селекторы iframe
            try:
                iframe_loc = page.locator(
                    'iframe[src*="challenges.cloudflare.com"], '
                    'iframe[src*="challenge-platform"], '
                    'iframe[name*="cf-chl-widget"], '
                    'iframe[title*="Cloudflare"], '
                    'iframe[title*="Turnstile"]'
                ).first
                if await iframe_loc.count() > 0:
                    box = await iframe_loc.bounding_box()
                    if box and box['width'] > 40 and box['height'] > 20:
                        target_box = box
                        break
            except Exception:
                pass
            await asyncio.sleep(0.25)

        if not target_box:
            await asyncio.sleep(0.5)
            continue

        logger.info(f'✅ Turnstile найден ({target_box}), кликаем (попытка {attempt}/{max_attempts})')
        try:
            # Чекбокс Turnstile расположен слева по центру фрейма (x + 28..30px, y + height / 2)
            click_x = target_box['x'] + 28 + random.uniform(-1.0, 1.0)
            click_y = target_box['y'] + (target_box['height'] / 2) + random.uniform(-1.0, 1.0)
            await page.mouse.move(click_x, click_y)
            await asyncio.sleep(0.08)
            await page.mouse.down()
            await asyncio.sleep(random.uniform(0.05, 0.09))
            await page.mouse.up()
        except Exception as ce:
            logger.warning(f'Ошибка клика Turnstile: {ce}')

        for _ in range(12):
            await asyncio.sleep(0.5)
            if await _is_turnstile_solved(page):
                logger.info('✅ Cloudflare Turnstile решён!')
                return True

            if was_waf:
                try:
                    pt = (await page.evaluate('document.body?.innerText || ""')).lower()
                    if not any(kw in pt for kw in ['security verification', 'just a moment', 'verify you are human']):
                        logger.info('✅ Cloudflare WAF пройден!')
                        return True
                except Exception:
                    pass

    return await _is_turnstile_solved(page)


async def _fill_input_reliably(page, selector: str, value: str) -> bool:
    loc = page.locator(selector).first
    for _ in range(4):
        try:
            if await loc.count() > 0:
                await loc.click(timeout=1500)
                await loc.fill(value, timeout=2000)
                if await loc.input_value() == value:
                    return True
        except Exception:
            pass

        try:
            if await loc.count() > 0:
                await loc.click(timeout=1000)
                await page.keyboard.press('Control+A')
                await page.keyboard.press('Backspace')
                await page.keyboard.type(value, delay=10)
                if await loc.input_value() == value:
                    return True
        except Exception:
            pass

        try:
            await page.evaluate('''({sel, val}) => {
                const el = document.querySelector(sel);
                if (el) {
                    el.focus();
                    if (el._valueTracker) el._valueTracker.setValue('');
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, val);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                }
            }''', {'sel': selector, 'val': value})
            if await loc.input_value() == value:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.2)
    return False


async def signup_via_browser(email: str, password: str, proxy: str | None = None, after_signup_callback=None) -> tuple[bool, any]:
    from camoufox.async_api import AsyncCamoufox
    camoufox_args = _build_camoufox_args(proxy)

    async with AsyncCamoufox(**camoufox_args) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_navigation_timeout(45000)
        page.set_default_timeout(45000)

        signup_success = False
        signup_error = None

        async def on_response(response):
            nonlocal signup_success, signup_error
            if '/user/create' not in response.url or response.request.method != 'POST':
                return
            try:
                body = await response.json()
                if body.get('success'):
                    signup_success = True
                    logger.info(f'[{email}] Signup: create_user success')
                else:
                    errors = body.get('errors', [])
                    signup_error = str(errors)
            except Exception:
                pass

        page.on('response', on_response)

        try:
            await page.goto('https://dash.cloudflare.com/sign-up', wait_until='domcontentloaded', timeout=45000)
        except Exception as e:
            logger.warning(f'[{email}] Signup goto error: {e}')

        await dismiss_cookie_banner(page)

        # WAF Challenge если возник
        for _ in range(3):
            if await page.locator('input[name="email"], input[type="password"], [data-testid="signup-input-email"]').count() > 0:
                break
            cf_frames = [f for f in page.frames if 'challenges.cloudflare.com' in f.url or 'challenge-platform' in f.url]
            if cf_frames:
                await bypass_turnstile_safely(page, timeout=8000)
            await asyncio.sleep(0.4)

        # Ожидание формы
        for _ in range(30):
            await dismiss_cookie_banner(page)
            if await page.locator('input[name="email"], [data-testid="signup-input-email"]').count() > 0:
                break
            await asyncio.sleep(0.3)

        email_sel = 'input[name="email"], [data-testid="signup-input-email"]'
        pwd_sel = 'input[name="password"], input[type="password"], [data-testid="signup-input-password"]'

        # Заполнение полей
        await _fill_input_reliably(page, email_sel, email)
        await dismiss_cookie_banner(page)
        await _fill_input_reliably(page, pwd_sel, password)
        await page.keyboard.press('Tab')

        email_loc = page.locator(email_sel).first
        pwd_loc = page.locator(pwd_sel).first

        # Контрольная проверка значений перед кликом
        try:
            if await email_loc.input_value() != email:
                logger.warning(f'[{email}] Повторный ввод email перед сабмитом')
                await _fill_input_reliably(page, email_sel, email)
            if await pwd_loc.input_value() != password:
                logger.warning(f'[{email}] Повторный ввод пароля перед сабмитом')
                await _fill_input_reliably(page, pwd_sel, password)
        except Exception:
            pass

        # Ждём появления виджета Turnstile
        for _ in range(12):
            if any('challenges.cloudflare.com' in f.url or 'challenge-platform' in f.url for f in page.frames):
                break
            await asyncio.sleep(0.25)

        # Проверка и решение Turnstile перед отправкой формы
        if not await _is_turnstile_solved(page):
            if any('challenges.cloudflare.com' in f.url or 'challenge-platform' in f.url for f in page.frames):
                logger.info(f'[{email}] Решаем Turnstile перед отправкой формы...')
                await bypass_turnstile_safely(page, timeout=15000, max_attempts=5)

        # Отправка формы
        await dismiss_cookie_banner(page)
        try:
            clicked = await page.evaluate('''() => {
                const btn = document.querySelector('button[data-testid="signup-submit-button"], button[type="submit"]');
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }''')
            if not clicked:
                btn = page.locator('button[data-testid="signup-submit-button"], button[type="submit"]').first
                if await btn.count() > 0:
                    await btn.click(timeout=2000)
        except Exception:
            pass

        async def _finish(ok: bool) -> tuple[bool, any]:
            if ok and after_signup_callback:
                try:
                    cb_result = await after_signup_callback(page)
                    return (True, cb_result)
                except Exception as cb_err:
                    logger.error(f'[{email}] Ошибка в after_signup_callback: {cb_err}')
            return (ok, None)

        for _ in range(80):
            await asyncio.sleep(0.8)

            if signup_success:
                return await _finish(True)

            try:
                cur_url = page.url or ''
                if any(p in cur_url for p in ['/verify-email', '/email-verification', '/onboarding', '/welcome', '/home']):
                    return await _finish(True)
            except Exception:
                pass

            try:
                text_lower = (await page.evaluate('document.body?.innerText || ""')).lower()
                if any(kw in text_lower for kw in ['verify your email', 'verification email', 'check your inbox']):
                    return await _finish(True)
                if 'already exists' in text_lower or 'already registered' in text_lower:
                    logger.error(f'[{email}] Email уже зарегистрирован в Cloudflare')
                    return (False, None)

                # Обработка сброса email / ошибки валидации
                if 'email address is required' in text_lower or 'enter an email' in text_lower:
                    logger.warning(f'[{email}] Обнаружена ошибка валидации формы — повторный ввод email...')
                    await _fill_input_reliably(page, email_sel, email)
                    try:
                        if await pwd_loc.input_value() != password:
                            await _fill_input_reliably(page, pwd_sel, password)
                    except Exception:
                        pass
                    await dismiss_cookie_banner(page)
                    await page.evaluate('''() => {
                        const btn = document.querySelector('button[data-testid="signup-submit-button"], button[type="submit"]');
                        if (btn && !btn.disabled) btn.click();
                    }''')
            except Exception:
                pass

            # Активное решение Turnstile если он появился или ещё не решён
            has_cf = any('challenges.cloudflare.com' in f.url or 'challenge-platform' in f.url for f in page.frames)
            if has_cf and not await _is_turnstile_solved(page):
                signup_error = None
                logger.info(f'[{email}] Кликаем Turnstile на форме...')
                if await bypass_turnstile_safely(page, timeout=15000, max_attempts=5):
                    await asyncio.sleep(0.3)
                    await dismiss_cookie_banner(page)
                    await page.evaluate('''() => {
                        const btn = document.querySelector('button[data-testid="signup-submit-button"], button[type="submit"]');
                        if (btn && !btn.disabled) btn.click();
                    }''')
            elif signup_error and ('1200' in signup_error or '1201' in signup_error):
                signup_error = None
                if await bypass_turnstile_safely(page, timeout=15000, max_attempts=5):
                    await asyncio.sleep(0.3)
                    await dismiss_cookie_banner(page)
                    await page.evaluate('''() => {
                        const btn = document.querySelector('button[data-testid="signup-submit-button"], button[type="submit"]');
                        if (btn && !btn.disabled) btn.click();
                    }''')

        return await _finish(signup_success)
