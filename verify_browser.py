import asyncio
import logging
import random
import time
logger = logging.getLogger(__name__)


def _build_camoufox_args(proxy: str | None = None) -> dict:
    """Собирает аргументы Camoufox (общие для signup и verify)."""
    from camoufox import DefaultAddons
    firefox_user_agent = random.choice([
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
    ])
    args = {
        'headless': False,
        'humanize': True,
        'geoip': True if proxy else False,
        'enable_cache': False,
        'exclude_addons': [DefaultAddons.UBO],
        'os': 'windows',
        'block_images': False,
        'block_webrtc': False,
        'block_webgl': False,
        'window': (1280, 1024),
        'firefox_user_prefs': {
            'security.csp.enable': False,
            'browser.sessionhistory.max_entries': 5,
            'browser.cache.memory.enable': False,
            'dom.max_script_run_time': 20,
            'dom.max_chrome_script_run_time': 20,
            'network.http.keep-alive.timeout': 300,
            'network.http.max-persistent-connections-per-server': 4,
            'privacy.trackingprotection.enabled': False,
            'media.autoplay.default': 5,
            'intl.accept_languages': 'en-US,en',
            'general.useragent.override': firefox_user_agent,
            'browser.startup.firstrunSkipsHomepage': True,
            'browser.startup.homepage_override.mstone': 'ignore',
            'browser.shell.checkDefaultBrowser': False,
            'browser.startup.page': 0,
            'browser.sessionstore.enabled': False,
            'browser.sessionstore.resume_from_crash': False,
            'browser.sessionstore.max_tabs_undo': 0,
            'browser.translation.detectLanguage': False,
            'browser.translation.ui.show': False,
            'media.peerconnection.enabled': True,
            'media.peerconnection.ice.default_address_only': False,
            'media.peerconnection.ice.no_host': False,
        }
    }
    if proxy:
        proxy_str = proxy if proxy.startswith('http://') or proxy.startswith('https://') else f'http://{proxy}'
        from urllib.parse import urlparse
        parsed = urlparse(proxy_str)
        args['proxy'] = {
            'server': f'http://{parsed.hostname}:{parsed.port}',
            'username': parsed.username or '',
            'password': parsed.password or '',
        }
    return args


async def dismiss_cookie_banner(page) -> bool:
    """Закрывает и удаляет cookie-баннеры (Cloudflare / OneTrust) со страницы."""
    # 1. Попытка клика через Playwright по известным селекторам кнопок
    try:
        cookie_btn = page.locator(
            'button:has-text("Accept All Cookies"), '
            'button:has-text("Accept all cookies"), '
            'button:has-text("Accept All"), '
            'button:has-text("Accept all"), '
            'button:has-text("Reject All"), '
            'button#onetrust-accept-btn-handler, '
            'button.onetrust-close-btn-handler'
        ).first
        if await cookie_btn.count() > 0 and await cookie_btn.is_visible():
            await cookie_btn.click(timeout=1500)
            logger.info('Browser: 🍪 Cookie banner нажат (Playwright)')
            await asyncio.sleep(0.3)
            return True
    except Exception:
        pass

    # 2. Попытка клика и принудительного удаления оверлеев через DOM
    try:
        removed = await page.evaluate('''() => {
            let clicked = false;
            // Клик по тексту кнопки
            const allBtns = Array.from(document.querySelectorAll('button, a'));
            for (const b of allBtns) {
                const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                if (txt === 'accept all cookies' || txt === 'accept all' || txt === 'accept cookies' || txt === 'reject all') {
                    b.click();
                    clicked = true;
                    break;
                }
            }
            // Клик по крестику
            const closeBtn = document.querySelector('button[aria-label*="close" i], button[aria-label*="dismiss" i], .onetrust-close-btn-handler');
            if (closeBtn) {
                closeBtn.click();
                clicked = true;
            }
            // Принудительно скрываем/удаляем плавающие плашки куки
            const candidates = document.querySelectorAll(
                '#onetrust-consent-sdk, #onetrust-banner-sdk, .onetrust-pc-dark-filter, ' +
                '[class*="cookie" i], [id*="cookie" i], [class*="consent" i], [id*="consent" i]'
            );
            for (const el of candidates) {
                const s = window.getComputedStyle(el);
                if (s.position === 'fixed' || s.position === 'sticky') {
                    el.style.display = 'none';
                    el.remove();
                    clicked = true;
                }
            }
            return clicked;
        }''')
        if removed:
            logger.info('Browser: 🍪 Cookie banner обработан/удалён (JS)')
            return True
    except Exception:
        pass
    return False


async def signup_via_browser(email: str, password: str, proxy: str | None = None, after_signup_callback=None) -> tuple[bool, any]:
    """
    Регистрация аккаунта Cloudflare через браузер Camoufox.
    Turnstile решается кликом в браузере → IP совпадает → 1201 не будет.
    """
    from camoufox.async_api import AsyncCamoufox
    camoufox_args = _build_camoufox_args(proxy)
    logger.info('SignupBrowser: запускаем Camoufox...')

    async with AsyncCamoufox(**camoufox_args) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_navigation_timeout(60000)
        page.set_default_timeout(60000)

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
                    logger.info('SignupBrowser: ✅ create_user success!')
                else:
                    errors = body.get('errors', [])
                    signup_error = str(errors)
                    logger.warning(f'SignupBrowser: create_user errors: {errors}')
            except Exception:
                pass

        page.on('response', on_response)

        logger.info('SignupBrowser: открываем dash.cloudflare.com/sign-up...')
        try:
            await page.goto('https://dash.cloudflare.com/sign-up', wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            logger.warning(f'SignupBrowser: goto error: {e}')

        await asyncio.sleep(1)
        await dismiss_cookie_banner(page)

        # WAF Challenge
        for waf_round in range(5):
            if await page.locator('input[type="email"], input[type="password"]').count() > 0:
                break
            cf_frames = [f for f in page.frames if 'challenges.cloudflare.com' in f.url or 'challenge-platform' in f.url]
            try:
                page_text = await page.evaluate('document.body?.innerText || ""')
            except Exception:
                page_text = ''
            if cf_frames or any(kw in page_text for kw in ['Performing security verification', 'Just a moment']):
                logger.info(f'SignupBrowser: WAF Challenge (раунд {waf_round+1})')
                await bypass_turnstile_safely(page, timeout=8000)
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(1)

        # Ждём форму
        form_found = False
        for i in range(60):
            await asyncio.sleep(0.5)
            if i % 4 == 0:
                await dismiss_cookie_banner(page)
            if await page.locator('input[type="email"], input[name="email"]').count() > 0:
                form_found = True
                break
        if not form_found:
            logger.error('SignupBrowser: ❌ форма регистрации не появилась')
            return False

        await asyncio.sleep(0.5)
        await dismiss_cookie_banner(page)

        # Заполняем email
        email_filled = False
        email_input = page.locator('input[type="email"], input[name="email"], [data-testid="signup-input-email"]').first
        try:
            await email_input.fill(email, timeout=5000)
            email_filled = True
            logger.info('SignupBrowser: email заполнен')
        except Exception:
            pass

        if not email_filled:
            try:
                await page.evaluate('''(val) => {
                    const el = document.querySelector('input[type="email"], input[name="email"], [data-testid="signup-input-email"]');
                    if (el) {
                        const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        s.call(el, val);
                        el.dispatchEvent(new Event("input", {bubbles: true}));
                        el.dispatchEvent(new Event("change", {bubbles: true}));
                    }
                }''', email)
                logger.info('SignupBrowser: email заполнен (JS)')
            except Exception as e:
                logger.error(f'SignupBrowser: ❌ ошибка email: {e}')
                return False

        await asyncio.sleep(0.3)

        # Заполняем пароль
        pwd_filled = False
        pwd_input = page.locator('input[type="password"], input[name="password"], [data-testid="signup-input-password"]').first
        try:
            if await pwd_input.count() > 0:
                await pwd_input.click()
                await asyncio.sleep(0.1)
                await pwd_input.fill(password)
                await asyncio.sleep(0.1)
                # Триггерим blur и нажатие клавиши для React валидатора
                await page.keyboard.press('Tab')
                pwd_filled = True
                logger.info('SignupBrowser: пароль заполнен (fill)')
        except Exception as e:
            logger.debug(f'SignupBrowser: ошибка fill пароля: {e}')

        if not pwd_filled:
            try:
                await page.evaluate('''(val) => {
                    const el = document.querySelector('input[type="password"], input[name="password"], [data-testid="signup-input-password"]');
                    if (el) {
                        el.focus();
                        const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        s.call(el, val);
                        el.dispatchEvent(new Event("input", {bubbles: true}));
                        el.dispatchEvent(new Event("change", {bubbles: true}));
                        el.dispatchEvent(new Event("blur", {bubbles: true}));
                    }
                }''', password)
                logger.info('SignupBrowser: пароль заполнен (JS)')
            except Exception as e:
                logger.error(f'SignupBrowser: ❌ ошибка пароль: {e}')
                return (False, None)

        # Reset per-call captcha retry counter
        setattr(signup_via_browser, '_captcha_retry', 0)

        # Нажимаем Sign Up
        logger.info('SignupBrowser: нажимаем Sign Up...')
        await dismiss_cookie_banner(page)
        btn_clicked = False

        for wait_btn in range(20):
            # 1. Пробуем клик через JS (мгновенно)
            try:
                clicked_js = await page.evaluate('''() => {
                    const btn = document.querySelector('button[data-testid="signup-submit-button"], button[type="submit"]');
                    if (btn && !btn.disabled) {
                        btn.click();
                        return true;
                    }
                    return false;
                }''')
                if clicked_js:
                    btn_clicked = True
                    logger.info('SignupBrowser: ✅ Sign Up нажат (JS)!')
                    break
            except Exception:
                pass

            # 2. Пробуем Playwright клик
            btn = page.locator('button[data-testid="signup-submit-button"], button[type="submit"]').first
            if await btn.count() > 0:
                try:
                    if not await btn.is_disabled():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(timeout=2000)
                        btn_clicked = True
                        logger.info('SignupBrowser: ✅ Sign Up нажат (Playwright)!')
                        break
                except Exception:
                    pass
            await asyncio.sleep(0.5)

        if not btn_clicked:
            try:
                await page.evaluate('''() => {
                    const btn = document.querySelector('button[data-testid="signup-submit-button"], button[type="submit"]');
                    if (btn) btn.click();
                }''')
                logger.info('SignupBrowser: ✅ Sign Up нажат принудительно (force JS)')
            except Exception as e:
                logger.error(f'SignupBrowser: ❌ не удалось нажать Sign Up: {e}')

        # Хелпер — вызвать callback в текущей сессии и вернуть результат
        async def _finish(ok: bool) -> tuple[bool, any]:
            if ok and after_signup_callback:
                try:
                    cb_result = await after_signup_callback(page)
                    return (True, cb_result)
                except Exception as cb_err:
                    logger.error(f'SignupBrowser: ошибка в after_signup_callback: {cb_err}')
            return (ok, None)

        # Ждём результат
        logger.info('SignupBrowser: ожидаем результат регистрации...')
        for i in range(60):
            await asyncio.sleep(1)

            if signup_success:
                logger.info('SignupBrowser: ✅ регистрация успешна!')
                return await _finish(True)

            # Проверяем URL
            try:
                cur_url = page.url
                if any(p in cur_url for p in ['/verify-email', '/email-verification', '/onboarding', '/welcome', '/home']):
                    logger.info(f'SignupBrowser: ✅ redirect → {cur_url}')
                    return await _finish(True)
            except Exception:
                pass

            # Проверяем текст страницы
            try:
                text = await page.evaluate('document.body?.innerText || ""')
                text_lower = text.lower()
                if 'verify your email' in text_lower or 'verification email' in text_lower or 'check your inbox' in text_lower:
                    logger.info('SignupBrowser: ✅ обнаружен запрос верификации email')
                    return await _finish(True)
                if 'already registered' in text_lower or 'already exists' in text_lower:
                    logger.error('SignupBrowser: ❌ email уже зарегистрирован')
                    return (False, None)
            except Exception:
                pass

            # Обрабатываем WAF после submit
            cf_frames = [f for f in page.frames if 'challenges.cloudflare.com' in f.url]
            if cf_frames:
                await bypass_turnstile_safely(page, timeout=10000)

            if signup_error:
                logger.warning(f'SignupBrowser: ошибка: {signup_error}')
                if '1200' in signup_error or '1201' in signup_error:
                    signup_error = None
                    captcha_retry = getattr(signup_via_browser, '_captcha_retry', 0)
                    setattr(signup_via_browser, '_captcha_retry', captcha_retry + 1)

                    if captcha_retry >= 5:
                        logger.error('SignupBrowser: ❌ CAPTCHA не решается после 5 попыток')
                        return (False, None)

                    logger.info(f'SignupBrowser: 1200 (попытка {captcha_retry}/5) — решаем Turnstile...')

                    # Запускаем клик и AnySolver параллельно — кто быстрее
                    solved = False
                    api_token = None

                    async def _try_click():
                        return await bypass_turnstile_safely(page, timeout=8000, max_attempts=1)

                    async def _try_anysolver():
                        try:
                            import turnstile as turnstile_mod
                            tok = await turnstile_mod.solve_turnstile(action='signup')
                            logger.info('SignupBrowser: ✅ AnySolver токен получен')
                            return tok
                        except Exception as e:
                            logger.warning(f'SignupBrowser: ⚠️ AnySolver: {e}')
                            return None

                    click_result, any_token = await asyncio.gather(
                        _try_click(), _try_anysolver(), return_exceptions=True
                    )

                    if click_result is True:
                        solved = True
                        logger.info('SignupBrowser: ✅ Turnstile решён кликом!')
                    elif isinstance(any_token, str) and any_token:
                        api_token = any_token
                        solved = True
                        logger.info('SignupBrowser: ✅ Инжектим AnySolver токен...')
                        try:
                            await page.evaluate('''(token) => {
                                const fields = document.querySelectorAll(
                                    'input[name="cf-turnstile-response"], input[name*="turnstile"], textarea[name="cf-turnstile-response"]'
                                );
                                for (const f of fields) { f.value = token; }
                                window._cf_turnstile_token = token;
                            }''', api_token)
                        except Exception:
                            pass

                    # Повторно нажимаем Sign Up
                    await asyncio.sleep(0.3)
                    await dismiss_cookie_banner(page)
                    try:
                        await page.evaluate('''() => {
                            const btn = document.querySelector('button[data-testid="signup-submit-button"], button[type="submit"]');
                            if (btn && !btn.disabled) btn.click();
                        }''')
                        logger.info('SignupBrowser: Sign Up нажат повторно после Turnstile')
                    except Exception:
                        pass
                elif '1111' in signup_error:
                    logger.error('SignupBrowser: ❌ регистрация заблокирована (1111)')
                    return (False, None)

        logger.warning('SignupBrowser: ⏱ таймаут')
        return await _finish(signup_success)


async def _is_turnstile_solved(page, frame=None) -> bool:
    """Проверяет решён ли Turnstile: токен получен."""
    try:
        has_token = await asyncio.wait_for(page.evaluate('''
            (() => {
                const inputs = document.querySelectorAll('input[name*="turnstile"], input[name*="cf-"], [data-turnstile-response], input[name="cf_challenge_response"]');
                for (const inp of inputs) {
                    if (inp.value && inp.value.length > 20) return true;
                }
                const idInputs = document.querySelectorAll('input[id*="cf-chl-widget"]');
                for (const inp of idInputs) {
                    if (inp.value && inp.value.length > 20) return true;
                }
                const widgets = document.querySelectorAll('.cf-turnstile, [data-sitekey]');
                for (const w of widgets) {
                    const resp = w.querySelector('input[type="hidden"]');
                    if (resp && resp.value && resp.value.length > 20) return true;
                }
                return false;
            })()
        '''), timeout=2.0)
        if has_token:
            return True
    except Exception:
        pass
    return False


async def move_mouse_smoothly_to(page, target_x: float, target_y: float):
    """
    Плавно перемещает курсор мыши к целевым координатам, имитируя человеческую наводку.
    """
    try:
        await page.mouse.move(target_x, target_y)
        await asyncio.sleep(0.01)
    except Exception as e:
        logger.warning(f'⚠️ Ошибка при плавном движении мыши: {e}')


async def bypass_turnstile_safely(page, timeout=12000, max_attempts=4) -> bool:
    """
    Находит интерактивный фрейм Cloudflare Turnstile и кликает по чекбоксу 'Verify you are human'.
    Поддерживает:
    1. Поиск по iframe[src*="challenges.cloudflare.com"]
    2. Поиск по родительскому контейнеру cf-chl-widget input
    """
    logger.info('⏳ Ожидание появления фрейма Cloudflare Turnstile...')
    try:
        init_pt = await page.evaluate('document.body?.innerText || ""')
    except Exception:
        init_pt = ''
    was_waf = any(kw in init_pt.lower() for kw in ['security verification', 'just a moment', 'verify you are human'])

    for attempt in range(1, max_attempts + 1):
        target_box = None
        deadline = asyncio.get_event_loop().time() + timeout / 1000.0

        while asyncio.get_event_loop().time() < deadline:
            # 1. Ищем Turnstile iframe напрямую через Playwright (без page.evaluate)
            try:
                iframe_loc = page.locator(
                    'iframe[src*="challenges.cloudflare.com"], '
                    'iframe[src*="challenge-platform"], '
                    'iframe[title*="Cloudflare"], '
                    'iframe[title*="Turnstile"]'
                ).first
                cnt = await asyncio.wait_for(iframe_loc.count(), timeout=1.5)
                if cnt > 0:
                    try:
                        await asyncio.wait_for(iframe_loc.scroll_into_view_if_needed(), timeout=1.5)
                    except Exception:
                        pass
                    await asyncio.sleep(0.1)
                    box = await asyncio.wait_for(iframe_loc.bounding_box(), timeout=1.5)
                    if box and box['width'] > 50 and box['height'] > 20:
                        target_box = box
                        break
            except Exception:
                pass

            # 2. Fallback: ищем через input[id*="cf-chl-widget"] с таймаутом
            try:
                scrolled_box = await asyncio.wait_for(page.evaluate('''() => {
                    const inp = document.querySelector('input[id*="cf-chl-widget"], input[name="cf_challenge_response"]');
                    if (inp && inp.parentElement) {
                        let curr = inp.parentElement;
                        while (curr && curr !== document.body) {
                            const r = curr.getBoundingClientRect();
                            if (r.width > 50 && r.width < 900 && r.height >= 30 && r.height <= 200) {
                                return { x: r.x, y: r.y, width: r.width, height: r.height };
                            }
                            curr = curr.parentElement;
                        }
                    }
                    return null;
                }'''), timeout=2.0)
                if scrolled_box:
                    target_box = scrolled_box
                    break
            except Exception:
                pass

            await asyncio.sleep(0.5)

        if not target_box:
            logger.info('ℹ️ Интерактивный фрейм Cloudflare не найден.')
            return False

        logger.info(f'✅ Виджет Turnstile найден (box={target_box}) (попытка {attempt}/{max_attempts})')

        # 2. Клик по точным координатам чекбокса Turnstile
        try:
            click_x = target_box['x'] + 28 + random.uniform(-1, 1)
            click_y = target_box['y'] + (target_box['height'] / 2) + random.uniform(-1, 1)
            await asyncio.wait_for(page.mouse.move(click_x, click_y), timeout=3.0)
            await asyncio.sleep(0.05)
            await page.mouse.down()
            await asyncio.sleep(random.uniform(0.04, 0.08))
            await page.mouse.up()
            logger.info(f'👆 Клик по координатам чекбокса (x={click_x:.1f}, y={click_y:.1f})')
        except Exception as ce:
            logger.warning(f'⚠️ Ошибка клика по координатам: {ce}')

        # Ждем решение (4 секунды)
        await asyncio.sleep(4)

        # Проверка решения
        if await _is_turnstile_solved(page):
            logger.info('✅ Cloudflare Turnstile успешно пройден!')
            return True

        # Для WAF Challenge страниц: если изначально это была WAF страница и после клика текст исчез
        if was_waf:
            try:
                pt = await page.evaluate('document.body?.innerText || ""')
                is_waf_text = any(kw in pt.lower() for kw in ['security verification', 'just a moment', 'verify you are human'])
                if not is_waf_text:
                    logger.info('✅ Cloudflare WAF успешно пройден (страница перенаправилась)!')
                    return True
            except Exception:
                pass

        if attempt < max_attempts:
            logger.warning(f'⚠️ Turnstile не подтвердился после клика, повторяю (попытка {attempt + 1})...')
            await asyncio.sleep(0.5)

    logger.warning('⚠️ Turnstile фрейм не решён после всех попыток.')
    return False


async def extract_global_api_key_via_browser(page, email: str, password: str, otp_provider_func=None) -> str | None:
    """
    Извлекает Global API Key напрямую через UI профиля Cloudflare.
    Реактивный конечный автомат:
    1. Перехватывает сетевые ответы /api/v4/user/api_key
    2. Сканирует DOM на наличие ключа
    3. Обрабатывает состояния модалки (Send Verification Code, OTP, пароль, Turnstile).
    """
    import time as _time
    logger.info(f'Browser: [{email}] Начинаем процесс извлечения Global API Key...')
    captured_key = None
    cached_otp = None
    extract_global_api_key_via_browser._1211_count = 0

    async def on_response_key(response):
        nonlocal captured_key, cached_otp
        url = response.url
        if '/api/v4/' in url:
            try:
                body = await response.json()
                logger.info(f'Browser: 📡 API Response [{response.request.method} {url}] status={response.status} body={body}')
                if ('/api/v4/user/api_key' in url or '/api/v4/user/keys' in url):
                    if body.get('success'):
                        res = body.get('result')
                        if isinstance(res, str) and len(res) >= 32:
                            captured_key = res
                        elif isinstance(res, dict):
                            k = res.get('api_key') or res.get('key') or res.get('secret') or res.get('value')
                            if k and isinstance(k, str) and len(k) >= 32:
                                captured_key = k
                        if captured_key:
                            logger.info(f'Browser: 🎉 Перехвачен API-ключ из сетевого ответа: {captured_key}')
                    else:
                        errors = body.get('errors') or []
                        err_codes = [e.get('code') for e in errors if isinstance(e, dict)]
                        if 1214 in err_codes or 1211 in err_codes:
                            logger.warning(f'Browser: сбрасываем cached_otp из-за ошибки в API: {errors}')
                            cached_otp = None
            except Exception:
                pass

    page.on('response', on_response_key)

    try:
        # 1. Переход на страницу API токенов
        current_url = page.url or ''
        if 'dash.cloudflare.com/profile/api-tokens' not in current_url:
            logger.info(f'Browser: [{email}] Переход на https://dash.cloudflare.com/profile/api-tokens...')
            try:
                await page.goto('https://dash.cloudflare.com/profile/api-tokens', wait_until='domcontentloaded', timeout=45000)
            except Exception as ge:
                logger.warning(f'Browser goto api-tokens: {ge}')
            await asyncio.sleep(2)

        await dismiss_cookie_banner(page)

        # 2а. Ждём пока email_verified станет True (до 60 секунд)
        logger.info(f'Browser: [{email}] Проверяем email_verified через API...')
        for ev_chk in range(30):
            try:
                ev_resp = await page.evaluate('''() =>
                    fetch('/api/v4/user', {
                        headers: {'Accept': 'application/json', 'X-Cross-Site-Security': 'dash'}
                    }).then(r => r.json())
                ''')
                ev = (ev_resp.get('result') or {}).get('email_verified', False)
                if ev:
                    logger.info(f'Browser: [{email}] ✅ email_verified=True!')
                    break
                logger.info(f'Browser: [{email}] email_verified=False, жду 2s... ({ev_chk+1}/30)')
            except Exception:
                pass
            await asyncio.sleep(2)

        # 2б. Ожидание загрузки страницы
        for _ in range(30):
            await asyncio.sleep(0.5)
            if await page.locator('input[id*="cf-chl-widget"]').count() > 0:
                await bypass_turnstile_safely(page, timeout=5000)
            text = await page.evaluate('document.body?.innerText || ""')
            if 'Global API Key' in text or 'API Keys' in text:
                logger.info(f'Browser: [{email}] Секция API Keys загружена')
                break

        async def _find_key_in_dom():
            return await page.evaluate('''() => {
                const candidates = document.querySelectorAll('input[readonly], textarea[readonly], code, pre, span, div, p');
                for (const el of candidates) {
                    const v = (el.value || el.innerText || el.textContent || '').trim();
                    const match = v.match(/\b([a-f0-9]{37})\b/i) || v.match(/\b([a-f0-9]{32,45})\b/i);
                    if (match && !match[1].startsWith('0x') && !match[1].includes('token') && !match[1].includes('widget')) {
                        return match[1];
                    }
                }
                return null;
            }''')

        async def _get_modal_state():
            return await page.evaluate('''() => {
                const d = document.querySelector('div[role="dialog"], [data-modal], [aria-modal="true"], div.modal');
                if (!d) return {found: false};
                const inps = Array.from(d.querySelectorAll('input')).map(i => ({
                    type: i.type, name: i.name, id: i.id, placeholder: i.placeholder, val: i.value, disabled: i.disabled
                }));
                const btns = Array.from(d.querySelectorAll('button')).map(b => ({
                    text: (b.innerText || b.textContent || '').trim(), disabled: b.disabled, type: b.type
                }));
                return {found: true, text: d.innerText, inputs: inps, buttons: btns};
            }''')

        async def _click_view_button():
            row_btn = page.locator('tr:has-text("Global API Key") button, div[role="row"]:has-text("Global API Key") button, li:has-text("Global API Key") button')
            if await row_btn.count() > 0:
                try:
                    await row_btn.first.scroll_into_view_if_needed()
                    await row_btn.first.click(timeout=5000)
                    logger.info(f'Browser: [{email}] Кликнули по кнопке View (Playwright)')
                    return True
                except Exception as be:
                    logger.debug(f'Playwright click view failed: {be}')
            return await page.evaluate('''() => {
                const allEls = document.querySelectorAll('tr, div[role="row"], li, div');
                for (const el of allEls) {
                    if (el.innerText && el.innerText.includes('Global API Key') && el.innerText.includes('View')) {
                        const btns = el.querySelectorAll('button');
                        for (const b of btns) {
                            if (b.innerText.includes('View') || b.textContent.includes('View')) {
                                b.click();
                                return true;
                            }
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

        # 3. Реактивный цикл (до 90 секунд)
        deadline = _time.time() + 90
        last_action_time = 0

        while _time.time() < deadline:
            if captured_key:
                return captured_key
            dom_key = await _find_key_in_dom()
            if dom_key:
                logger.info(f'Browser: 🎉 API-ключ найден в DOM: {dom_key}')
                return dom_key

            st = await _get_modal_state()
            logger.info(f'Browser: [{email}] Modal state: found={st.get("found")}, text={repr(st.get("text", "")[:60])}')

            # Модалка не открыта — кликаем View
            if not st.get('found'):
                logger.info(f'Browser: [{email}] Модалка не открыта, кликаем View...')
                await _click_view_button()
                await asyncio.sleep(1.5)
                continue

            modal_text = st.get('text', '').lower()
            inputs = st.get('inputs', [])

            # Ошибка 1211 — email не подтверждён в JWT
            if 'please verify your email' in modal_text:
                if not hasattr(extract_global_api_key_via_browser, '_1211_count'):
                    extract_global_api_key_via_browser._1211_count = 0
                extract_global_api_key_via_browser._1211_count += 1
                _1211_cnt = extract_global_api_key_via_browser._1211_count
                logger.warning(f'Browser: [{email}] 1211: email не подтвержден в JWT (попытка {_1211_cnt}/3)')
                cached_otp = None
                await page.evaluate('''() => {
                    const btns = document.querySelectorAll('div[role="dialog"] button, [data-modal] button');
                    for (const b of btns) {
                        if (b.innerText.toLowerCase().includes('cancel')) { b.click(); return; }
                    }
                    const d = document.querySelector('div[role="dialog"], [data-modal]');
                    if (d) d.remove();
                }''')
                await asyncio.sleep(1)
                if _1211_cnt >= 3:
                    logger.error(f'Browser: [{email}] 1211 после 3 попыток, сдаёмся')
                    return None
                # RE-LOGIN
                logger.info(f'Browser: [{email}] RE-LOGIN из-за 1211...')
                try:
                    await page.evaluate('''async () => {
                        try { await fetch('/api/v4/user/logout', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Cross-Site-Security': 'dash'}}); } catch(e) {}
                    }''')
                except Exception:
                    pass
                await asyncio.sleep(1)
                try:
                    await page.goto('https://dash.cloudflare.com/login', wait_until='domcontentloaded', timeout=45000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                await dismiss_cookie_banner(page)
                for _wf in range(30):
                    if await page.locator('input[type="email"], input[type="password"]').count() > 0:
                        break
                    await asyncio.sleep(0.5)
                if '/login' in (page.url or ''):
                    try:
                        await page.evaluate('''(emailVal) => {
                            const el = document.querySelector('input[data-testid="login-input-email"], input[type="email"]');
                            if (el) { const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set; s.call(el, emailVal); el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); }
                        }''', email)
                        await page.evaluate('''(pwdVal) => {
                            const el = document.querySelector('input[type="password"]');
                            if (el) { const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set; s.call(el, pwdVal); el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); }
                        }''', password)
                    except Exception:
                        pass
                    await asyncio.sleep(0.3)
                    await bypass_turnstile_safely(page, timeout=10000)
                    try:
                        await page.evaluate('''() => { const b = document.querySelector('button[data-testid="login-submit-button"], button[type="submit"]'); if (b && !b.disabled) b.click(); }''')
                    except Exception:
                        pass
                    for _rl in range(30):
                        await asyncio.sleep(1)
                        cur = page.url or ''
                        if 'dash.cloudflare.com' in cur and any(p in cur for p in ['/home', '/overview', '/profile', '/account']):
                            break
                        cf_fr = [f for f in page.frames if 'challenges.cloudflare.com' in f.url]
                        if cf_fr:
                            await bypass_turnstile_safely(page, timeout=8000)
                try:
                    await page.goto('https://dash.cloudflare.com/profile/api-tokens', wait_until='domcontentloaded', timeout=45000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                await dismiss_cookie_banner(page)
                continue

            # Кнопка "Send Verification Code"
            send_btn = page.locator('div[role="dialog"] button:has-text("Send Verification Code"), div[role="dialog"] button:has-text("Send code"), [data-modal] button:has-text("Send")')
            if (await send_btn.count() > 0 or 'send verification code' in modal_text or 'send a verification code' in modal_text) and not any(i.get('name') == 'code' for i in inputs):
                if _time.time() - last_action_time > 3:
                    logger.info(f'Browser: [{email}] Нажимаем "Send Verification Code"...')
                    cached_otp = None
                    clicked_send = False
                    try:
                        if await send_btn.count() > 0:
                            await send_btn.first.click(timeout=3000)
                            clicked_send = True
                    except Exception:
                        pass
                    if not clicked_send:
                        try:
                            await page.evaluate('''() => {
                                const btns = document.querySelectorAll('div[role="dialog"] button, [data-modal] button, [aria-modal="true"] button');
                                for (const b of btns) {
                                    const txt = (b.innerText || b.textContent || '').toLowerCase();
                                    if (txt.includes('send') && !b.disabled) { b.click(); return true; }
                                }
                                for (const b of btns) {
                                    const txt = (b.innerText || b.textContent || '').toLowerCase();
                                    if (!txt.includes('cancel') && !b.disabled && txt.length > 0) { b.click(); return true; }
                                }
                                return false;
                            }''')
                            clicked_send = True
                        except Exception:
                            pass
                    last_action_time = _time.time()
                    await asyncio.sleep(2)
                    continue

            # Ввод OTP кода
            code_inputs = [i for i in inputs if i.get('name') == 'code' or (i.get('type') == 'text' and not i.get('id', '').startswith('cf-chl'))]
            if code_inputs or '7 digit code' in modal_text or 'verify code' in modal_text:
                code_val = code_inputs[0].get('val', '') if code_inputs else ''
                if not code_val:
                    if not cached_otp and otp_provider_func:
                        logger.info(f'Browser: [{email}] Запрашиваем OTP-код...')
                        try:
                            cached_otp = await otp_provider_func()
                            logger.info(f'Browser: [{email}] Получен OTP-код: {cached_otp}')
                        except Exception as oe:
                            logger.warning(f'Browser: ошибка получения OTP: {oe}')
                    if cached_otp:
                        logger.info(f'Browser: [{email}] Вводим OTP {cached_otp}...')
                        inp_loc = page.locator('div[role="dialog"] input[name="code"], div[role="dialog"] input[type="text"], input[name="code"]')
                        if await inp_loc.count() > 0:
                            try:
                                await inp_loc.first.click()
                                await inp_loc.first.fill(cached_otp)
                            except Exception:
                                pass
                        await page.evaluate('''(val) => {
                            const inps = document.querySelectorAll('div[role="dialog"] input, [data-modal] input, input[name="code"], input[type="text"]');
                            for (const inp of inps) {
                                if (inp.type !== 'hidden') {
                                    inp.focus();
                                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                    setter.call(inp, val);
                                    inp.dispatchEvent(new Event("input", {bubbles: true}));
                                    inp.dispatchEvent(new Event("change", {bubbles: true}));
                                    inp.dispatchEvent(new Event("blur", {bubbles: true}));
                                }
                            }
                        }''', cached_otp)
                        await asyncio.sleep(0.5)
                logger.info(f'Browser: [{email}] Решаем Turnstile в OTP модалке...')
                await bypass_turnstile_safely(page, timeout=8000)
                logger.info(f'Browser: [{email}] Кликаем Submit (OTP)...')
                btn_candidates = page.locator('div[role="dialog"] button:not([aria-label*="close" i]), [data-modal] button:not([aria-label*="close" i])')
                count = await btn_candidates.count()
                clicked_submit = False
                for i in range(count):
                    b = btn_candidates.nth(i)
                    btxt = (await b.inner_text() or '').strip()
                    if btxt.lower() not in ('cancel', '', '✕', '×') and not await b.is_disabled():
                        await b.click(timeout=3000)
                        logger.info(f'Browser: [{email}] Нажали кнопку: "{btxt}"')
                        clicked_submit = True
                        break
                if not clicked_submit:
                    await page.evaluate('''() => {
                        const btns = document.querySelectorAll('div[role="dialog"] button, [data-modal] button');
                        for (const b of btns) {
                            const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                            if (t && !t.includes('cancel') && !b.disabled) { b.click(); return true; }
                        }
                    }''')
                last_action_time = _time.time()
                await asyncio.sleep(2)
                continue

            # Ввод пароля
            pwd_inputs = [i for i in inputs if i.get('type') == 'password']
            if pwd_inputs or 'password' in modal_text:
                pwd_val = pwd_inputs[0].get('val', '') if pwd_inputs else ''
                if not pwd_val:
                    logger.info(f'Browser: [{email}] Вводим пароль в модалку...')
                    pwd_loc = page.locator('div[role="dialog"] input[type="password"], [data-modal] input[type="password"], input[name="password"]')
                    if await pwd_loc.count() > 0:
                        try:
                            await pwd_loc.first.click()
                            await pwd_loc.first.fill(password)
                        except Exception:
                            pass
                    await page.evaluate('''(val) => {
                        const inps = document.querySelectorAll('div[role="dialog"] input[type="password"], [data-modal] input[type="password"], input[name="password"]');
                        for (const inp of inps) {
                            inp.focus();
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                            setter.call(inp, val);
                            inp.dispatchEvent(new Event("input", {bubbles: true}));
                            inp.dispatchEvent(new Event("change", {bubbles: true}));
                            inp.dispatchEvent(new Event("blur", {bubbles: true}));
                        }
                    }''', password)
                    await asyncio.sleep(0.5)
                logger.info(f'Browser: [{email}] Решаем Turnstile в Password модалке...')
                await bypass_turnstile_safely(page, timeout=8000)
                logger.info(f'Browser: [{email}] Кликаем Submit (пароль)...')
                btn_candidates = page.locator('div[role="dialog"] button:not([aria-label*="close" i]), [data-modal] button:not([aria-label*="close" i])')
                count = await btn_candidates.count()
                clicked_submit = False
                for i in range(count):
                    b = btn_candidates.nth(i)
                    btxt = (await b.inner_text() or '').strip()
                    if btxt.lower() not in ('cancel', '', '✕', '×') and not await b.is_disabled():
                        await b.click(timeout=3000)
                        logger.info(f'Browser: [{email}] Нажали кнопку: "{btxt}"')
                        clicked_submit = True
                        break
                if not clicked_submit:
                    await page.evaluate('''() => {
                        const btns = document.querySelectorAll('div[role="dialog"] button, [data-modal] button');
                        for (const b of btns) {
                            const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                            if (t && !t.includes('cancel') && !b.disabled) { b.click(); return true; }
                        }
                    }''')
                last_action_time = _time.time()
                await asyncio.sleep(2)
                continue

            await asyncio.sleep(1)

        return captured_key
    except Exception as e:
        logger.error(f'Browser: [{email}] Ошибка при извлечении API-ключа: {e}')
        return captured_key


async def get_api_key_via_native_modal(page, otp_code: str, timeout=60) -> str | None:
    """
    Получает Global API Key через нативный UI Cloudflare:
    1. Переходит на /profile/api-tokens
    2. Нажимает "View" на Global API Key
    3. В модалке заполняет OTP пароль
    4. Решает нативный Turnstile кликом
    5. Нажимает submit
    6. Перехватывает API ключ из ответа
    
    Возвращает сам API ключ (строку) или None.
    """
    logger.info('NativeModal: получаем Global API Key через нативный UI...')
    
    # Перехватчик ответов — ловим результат api_key
    api_key_result = {'key': None}
    
    async def intercept_api_key_response(response):
        url = response.url
        if '/api/v4/user/api_key' in url:
            try:
                body = await response.json()
                logger.info(f'NativeModal: перехватили ответ api_key: {body}')
                if body.get('success'):
                    api_key_result['key'] = (body.get('result') or {}).get('api_key')
                else:
                    errors = body.get('errors', [])
                    logger.warning(f'NativeModal: ошибка api_key: {errors}')
            except Exception as e:
                logger.debug(f'NativeModal: ошибка парсинга ответа: {e}')
    
    page.on('response', intercept_api_key_response)
    
    try:
        # 1. Переходим на страницу API токенов
        cur_url = page.url or ''
        if '/profile/api-tokens' not in cur_url:
            logger.info('NativeModal: переходим на /profile/api-tokens...')
            try:
                await page.goto('https://dash.cloudflare.com/profile/api-tokens', wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
            except Exception as ge:
                logger.warning(f'NativeModal: переход: {ge}')
        
        await dismiss_cookie_banner(page)
        
        # Решаем WAF если есть
        for waf_round in range(3):
            cf_frames = [f for f in page.frames if 'challenges.cloudflare.com' in f.url or 'challenge-platform' in f.url]
            try:
                page_text = await page.evaluate('document.body?.innerText || ""')
            except Exception:
                page_text = ''
            is_waf = any(kw in page_text for kw in ['Performing security verification', 'Just a moment', 'security service'])
            if is_waf or (cf_frames and 'Global API Key' not in page_text):
                logger.info(f'NativeModal: WAF обнаружен (раунд {waf_round + 1}). Решаем...')
                await bypass_turnstile_safely(page, timeout=8000)
                await asyncio.sleep(1)
            else:
                break
        
        await dismiss_cookie_banner(page)
        
        # 2. Ждём появления строки "Global API Key" на странице
        global_key_found = False
        for wait_i in range(30):
            try:
                found = await page.evaluate('''() => {
                    return document.body?.innerText?.includes('Global API Key') || false;
                }''')
                if found:
                    global_key_found = True
                    break
            except Exception:
                pass
            await asyncio.sleep(1)
        
        if not global_key_found:
            logger.warning('NativeModal: текст "Global API Key" не найден на странице')
            # Пробуем fallback через fetch
            return await _fallback_fetch_api_key(page, otp_code)
        
        # 3. Нажимаем кнопку "View" у Global API Key
        logger.info('NativeModal: ищем кнопку View у Global API Key...')
        view_clicked = False
        for click_attempt in range(3):
            try:
                clicked = await page.evaluate('''() => {
                    // Ищем по тексту элементов
                    const allText = document.querySelectorAll('*');
                    let globalKeySection = null;
                    for (const el of allText) {
                        if (el.childNodes.length <= 3 && el.textContent.trim() === 'Global API Key') {
                            globalKeySection = el;
                            break;
                        }
                    }
                    if (!globalKeySection) {
                        // Альтернативный поиск по строкам таблицы
                        const rows = document.querySelectorAll('tr, div[class*="row"], li, section, article, div[class*="item"]');
                        for (const r of rows) {
                            if (r.textContent.includes('Global API Key')) {
                                globalKeySection = r;
                                break;
                            }
                        }
                    }
                    if (!globalKeySection) return 'not_found';
                    
                    // Ищем кнопку View рядом или в родительском элементе
                    let container = globalKeySection;
                    for (let i = 0; i < 5; i++) {
                        const buttons = container.querySelectorAll('button, a[role="button"]');
                        for (const btn of buttons) {
                            const txt = btn.textContent.trim().toLowerCase();
                            if (txt === 'view' || txt.includes('view')) {
                                btn.scrollIntoView({behavior: 'smooth', block: 'center'});
                                btn.click();
                                return 'clicked';
                            }
                        }
                        container = container.parentElement;
                        if (!container) break;
                    }
                    
                    // Фоллбэк: ищем любую кнопку View на странице
                    const allButtons = document.querySelectorAll('button, a[role="button"]');
                    for (const btn of allButtons) {
                        const txt = btn.textContent.trim().toLowerCase();
                        if (txt === 'view' && btn.closest('[class*="api"], [class*="key"], tr, li, section')) {
                            btn.click();
                            return 'clicked_fallback';
                        }
                    }
                    return 'no_button';
                }''')
                logger.info(f'NativeModal: результат клика View: {clicked}')
                if clicked in ('clicked', 'clicked_fallback'):
                    view_clicked = True
                    break
            except Exception as e:
                logger.debug(f'NativeModal: ошибка клика: {e}')
            await asyncio.sleep(2)
        
        if not view_clicked:
            logger.warning('NativeModal: кнопка View не найдена')
            return await _fallback_fetch_api_key(page, otp_code)
        
        await asyncio.sleep(2)
        await dismiss_cookie_banner(page)
        
        # 4. Ждём модальное окно с полем ввода пароля/OTP
        logger.info('NativeModal: ждём модальное окно...')
        modal_found = False
        for modal_wait in range(20):
            try:
                # Проверяем наличие модального окна с полем пароля
                has_modal = await page.evaluate('''() => {
                    const modals = document.querySelectorAll('[role="dialog"], [class*="modal"], [class*="Modal"], [class*="overlay"], [data-testid*="modal"]');
                    for (const m of modals) {
                        const pwdField = m.querySelector('input[type="password"], input[type="text"][name*="password"], input[autocomplete="current-password"]');
                        if (pwdField) return true;
                    }
                    // Проверяем любой input password который появился
                    const allPwd = document.querySelectorAll('input[type="password"]');
                    return allPwd.length > 0;
                }''')
                if has_modal:
                    modal_found = True
                    break
            except Exception:
                pass
            await asyncio.sleep(1)
        
        if not modal_found:
            logger.warning('NativeModal: модальное окно с полем пароля не появилось')
            return await _fallback_fetch_api_key(page, otp_code)
        
        logger.info('NativeModal: ✅ модальное окно найдено! Заполняем OTP...')
        await asyncio.sleep(0.5)
        
        # 5. Заполняем OTP/пароль в модалке
        try:
            pwd_input = page.locator('input[type="password"]').last
            if await pwd_input.count() > 0:
                await pwd_input.fill(otp_code, timeout=5000)
                logger.info('NativeModal: OTP заполнен')
            else:
                # Fallback: JS fill
                await page.evaluate('''(code) => {
                    const inputs = document.querySelectorAll('input[type="password"]');
                    const inp = inputs[inputs.length - 1];
                    if (inp) {
                        const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        s.call(inp, code);
                        inp.dispatchEvent(new Event("input", {bubbles: true}));
                        inp.dispatchEvent(new Event("change", {bubbles: true}));
                    }
                }''', otp_code)
                logger.info('NativeModal: OTP заполнен (JS fallback)')
        except Exception as e:
            logger.warning(f'NativeModal: ошибка заполнения OTP: {e}')
            return await _fallback_fetch_api_key(page, otp_code)
        
        await asyncio.sleep(1)
        
        # 6. Решаем Turnstile в модалке (если есть)
        logger.info('NativeModal: проверяем Turnstile в модалке...')
        for turnstile_attempt in range(3):
            turnstile_solved = await bypass_turnstile_safely(page, timeout=5000, max_attempts=2)
            if turnstile_solved:
                logger.info('NativeModal: ✅ Turnstile в модалке решён')
                break
            await asyncio.sleep(1)
        
        await asyncio.sleep(0.5)
        
        # 7. Нажимаем кнопку Submit/View в модалке
        logger.info('NativeModal: нажимаем Submit в модалке...')
        for submit_attempt in range(3):
            try:
                submit_result = await page.evaluate('''() => {
                    // Ищем кнопку в модальном окне
                    const modals = document.querySelectorAll('[role="dialog"], [class*="modal"], [class*="Modal"], [class*="overlay"]');
                    for (const m of modals) {
                        const buttons = m.querySelectorAll('button[type="submit"], button');
                        for (const btn of buttons) {
                            const txt = btn.textContent.trim().toLowerCase();
                            if (txt === 'view' || txt === 'submit' || txt === 'confirm' || txt === 'view api key' || txt === 'show') {
                                if (!btn.disabled) {
                                    btn.click();
                                    return 'clicked:' + txt;
                                }
                                return 'disabled:' + txt;
                            }
                        }
                    }
                    // Фоллбэк: submit кнопка рядом с password полем
                    const pwd = document.querySelector('input[type="password"]');
                    if (pwd) {
                        const form = pwd.closest('form');
                        if (form) {
                            const btn = form.querySelector('button[type="submit"], button:not([type="button"])');
                            if (btn && !btn.disabled) {
                                btn.click();
                                return 'form_submit:' + btn.textContent.trim();
                            }
                        }
                    }
                    return 'not_found';
                }''')
                logger.info(f'NativeModal: submit результат: {submit_result}')
                
                if submit_result.startswith('disabled'):
                    # Кнопка disabled — ждём Turnstile
                    logger.info('NativeModal: кнопка disabled, ждём Turnstile...')
                    await bypass_turnstile_safely(page, timeout=5000, max_attempts=2)
                    await asyncio.sleep(1)
                    continue
                elif submit_result.startswith('clicked') or submit_result.startswith('form_submit'):
                    break
                else:
                    # Пробуем Playwright клик
                    submit_btn = page.locator('[role="dialog"] button[type="submit"], [class*="modal"] button[type="submit"], [class*="Modal"] button:has-text("View")').first
                    if await submit_btn.count() > 0:
                        await submit_btn.click(timeout=3000)
                        logger.info('NativeModal: submit через Playwright')
                        break
            except Exception as e:
                logger.debug(f'NativeModal: ошибка submit: {e}')
            await asyncio.sleep(2)
        
        # 8. Ждём ответ API с ключом
        logger.info('NativeModal: ждём ответ API с ключом...')
        for wait_key in range(30):
            await asyncio.sleep(1)
            if api_key_result['key']:
                logger.info(f'NativeModal: ✅ API ключ получен!')
                return api_key_result['key']
            
            # Пробуем прочитать ключ прямо из модалки (если отобразился в UI)
            try:
                key_from_ui = await page.evaluate('''() => {
                    const modals = document.querySelectorAll('[role="dialog"], [class*="modal"], [class*="Modal"]');
                    for (const m of modals) {
                        // Ищем элемент с текстом, похожим на API key
                        const codeEls = m.querySelectorAll('code, pre, [class*="key"], [class*="token"], input[readonly], input[type="text"][readonly], span[class*="mono"]');
                        for (const el of codeEls) {
                            const val = (el.value || el.textContent || '').trim();
                            if (val && val.length >= 32 && /^[a-f0-9]+$/.test(val)) {
                                return val;
                            }
                        }
                        // Ищем по всем текстовым элементам
                        const allEls = m.querySelectorAll('p, span, div, td');
                        for (const el of allEls) {
                            if (el.children.length > 2) continue;
                            const val = el.textContent.trim();
                            if (val && val.length >= 32 && val.length <= 48 && /^[a-f0-9]+$/.test(val)) {
                                return val;
                            }
                        }
                    }
                    return null;
                }''')
                if key_from_ui:
                    logger.info(f'NativeModal: ✅ API ключ считан из UI! (len={len(key_from_ui)})')
                    return key_from_ui
            except Exception:
                pass
        
        logger.warning('NativeModal: ⏱ таймаут — ключ не получен через модалку')
        return await _fallback_fetch_api_key(page, otp_code)
    
    finally:
        # Снимаем обработчик
        try:
            page.remove_listener('response', intercept_api_key_response)
        except Exception:
            pass


async def _fallback_fetch_api_key(page, otp_code: str) -> str | None:
    """
    Фоллбэк: пытаемся получить API ключ через fetch() из контекста авторизованного браузера
    БЕЗ cf_challenge_response (сессионные куки могут быть достаточны).
    """
    logger.info('FallbackFetch: пробуем получить API ключ через fetch...')
    
    # Попытка 1: без cf_challenge_response
    try:
        res = await page.evaluate('''async (otp) => {
            try {
                const r = await fetch('/api/v4/user/api_key', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Cross-Site-Security': 'dash'
                    },
                    body: JSON.stringify({password: otp})
                });
                return await r.json();
            } catch(e) {
                return {success: false, error: e.toString()};
            }
        }''', otp_code)
        logger.info(f'FallbackFetch: ответ (без cf_challenge): {res}')
        if res.get('success'):
            key = (res.get('result') or {}).get('api_key')
            if key:
                logger.info(f'FallbackFetch: ✅ API ключ получен без Turnstile!')
                return key
    except Exception as e:
        logger.debug(f'FallbackFetch: ошибка: {e}')
    
    # Попытка 2: с пустым cf_challenge_response
    try:
        res = await page.evaluate('''async (otp) => {
            try {
                const r = await fetch('/api/v4/user/api_key', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Cross-Site-Security': 'dash'
                    },
                    body: JSON.stringify({password: otp, cf_challenge_response: ''})
                });
                return await r.json();
            } catch(e) {
                return {success: false, error: e.toString()};
            }
        }''', otp_code)
        logger.info(f'FallbackFetch: ответ (пустой cf_challenge): {res}')
        if res.get('success'):
            key = (res.get('result') or {}).get('api_key')
            if key:
                logger.info(f'FallbackFetch: ✅ API ключ получен с пустым Turnstile!')
                return key
    except Exception as e:
        logger.debug(f'FallbackFetch: ошибка: {e}')
    
    logger.warning('FallbackFetch: ❌ не удалось получить API ключ через fetch')
    return None


async def verify_email_via_browser(verify_url: str, email: str, password: str, proxy: str | None = None, timeout: int = 90, otp_callback=None, initial_cookies: list | None = None) -> tuple[bool, any]:
    """
    Открыть verify_url через Camoufox → логин → Turnstile → Sign in.
    Returns (success, cookies).
    """
    from camoufox.async_api import AsyncCamoufox
    verified = False
    browser_cookies = None
    firefox_user_agent = random.choice([
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0',
    ])
    from camoufox import DefaultAddons
    camoufox_args = {
        'headless': False,
        'humanize': True,
        'geoip': True if proxy else False,
        'enable_cache': False,
        'exclude_addons': [DefaultAddons.UBO],
        'os': 'windows',
        'block_images': False,
        'block_webrtc': False,
        'block_webgl': False,
        'window': (1280, 1024),
        'firefox_user_prefs': {
            'security.csp.enable': False,
            'browser.sessionhistory.max_entries': 5,
            'browser.cache.memory.enable': False,
            'dom.max_script_run_time': 20,
            'dom.max_chrome_script_run_time': 20,
            'network.http.keep-alive.timeout': 300,
            'network.http.max-persistent-connections-per-server': 4,
            'privacy.trackingprotection.enabled': False,
            'media.autoplay.default': 5,
            'intl.accept_languages': 'en-US,en',
            'general.useragent.override': firefox_user_agent,
            'browser.startup.firstrunSkipsHomepage': True,
            'browser.startup.homepage_override.mstone': 'ignore',
            'browser.shell.checkDefaultBrowser': False,
            'browser.startup.page': 0,
            'browser.sessionstore.enabled': False,
            'browser.sessionstore.resume_from_crash': False,
            'browser.sessionstore.max_tabs_undo': 0,
            'browser.translation.detectLanguage': False,
            'browser.translation.ui.show': False,
            'media.peerconnection.enabled': True,
            'media.peerconnection.ice.default_address_only': False,
            'media.peerconnection.ice.no_host': False,
        }
    }
    if proxy:
        proxy_str = proxy if proxy.startswith('http://') or proxy.startswith('https://') else f'http://{proxy}'
        from urllib.parse import urlparse
        parsed = urlparse(proxy_str)
        camoufox_args['proxy'] = {
            'server': f'http://{parsed.hostname}:{parsed.port}',
            'username': parsed.username or '',
            'password': parsed.password or '',
        }
    logger.info('Browser: запускаем Camoufox (headless=False)...')
    async with AsyncCamoufox(**camoufox_args) as browser:
        try:
            page = await browser.new_page()
            page.set_default_navigation_timeout(120000)
            page.set_default_timeout(60000)
            await page.route('**/*.{woff,woff2,ttf,otf,mp4,webm,ogg}', lambda route: route.abort())

            verified = False
            login_success = False

            # ── Шаг 1: Идём на страницу логина ──────────────────────────────
            logger.info('Browser: открываем dash.cloudflare.com/login...')
            try:
                await page.goto('https://dash.cloudflare.com/login', wait_until='domcontentloaded', timeout=120000)
            except Exception as e:
                logger.warning(f'Browser goto login: {e}')
            await asyncio.sleep(2)
            await dismiss_cookie_banner(page)

            # ── Шаг 2: Ждём форму логина ─────────────────────────────────────
            form_found = False
            for i in range(200):
                await asyncio.sleep(0.3)
                try:
                    if await page.locator('input[type="password"]').count() > 0:
                        form_found = True
                        logger.info(f'Browser: форма логина найдена за {(i+1)*0.3:.1f}s')
                        break
                    if await page.locator('input[type="email"], input[data-testid="login-input-email"]').count() > 0:
                        form_found = True
                        logger.info(f'Browser: форма логина найдена за {(i+1)*0.3:.1f}s')
                        break
                except Exception:
                    pass
                # WAF
                try:
                    cf_frames = [f for f in page.frames if 'challenges.cloudflare.com' in f.url]
                    if cf_frames:
                        await bypass_turnstile_safely(page, timeout=10000)
                except Exception:
                    pass
                if i % 10 == 0 and i > 0:
                    await dismiss_cookie_banner(page)

            if not form_found:
                logger.error('Browser: форма логина не появилась')
                return (False, None)

            # ── Шаг 3: Заполняем email и пароль ──────────────────────────────
            await dismiss_cookie_banner(page)
            try:
                email_loc = page.locator('input[type="email"], input[data-testid="login-input-email"]').first
                if await email_loc.count() > 0:
                    await email_loc.fill(email, timeout=5000)
                else:
                    raise Exception('no email input')
            except Exception:
                await page.evaluate('''(v) => {
                    const el = document.querySelector('input[type="email"], input[data-testid="login-input-email"]');
                    if (el) { const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set; s.call(el,v); el.dispatchEvent(new Event("input",{bubbles:true})); }
                }''', email)
            logger.info('Browser: email заполнен')

            try:
                pwd_loc = page.locator('input[type="password"]').first
                await pwd_loc.fill(password, timeout=5000)
            except Exception:
                await page.evaluate('''(v) => {
                    const el = document.querySelector('input[type="password"]');
                    if (el) { const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set; s.call(el,v); el.dispatchEvent(new Event("input",{bubbles:true})); }
                }''', password)
            logger.info('Browser: пароль заполнен')

            # ── Шаг 4: Turnstile + Sign In ────────────────────────────────────
            for sign_attempt in range(1, 5):
                logger.info(f'Browser: обработка Turnstile (попытка {sign_attempt}/4)...')
                await dismiss_cookie_banner(page)
                turnstile_ok = await bypass_turnstile_safely(page, timeout=10000)
                if not turnstile_ok:
                    logger.warning(f'Browser: Turnstile не пройден (попытка {sign_attempt})')
                    if sign_attempt < 4:
                        await asyncio.sleep(1)
                        continue

                # Нажимаем Sign In
                await dismiss_cookie_banner(page)
                btn = page.locator('button[data-testid="login-submit-button"], button[type="submit"]').first
                for _ in range(10):
                    await asyncio.sleep(0.3)
                    try:
                        if await btn.count() > 0 and not await btn.is_disabled():
                            try:
                                box = await btn.bounding_box()
                                if box:
                                    tx = box['x'] + box['width']/2 + random.uniform(-3, 3)
                                    ty = box['y'] + box['height']/2 + random.uniform(-3, 3)
                                    await page.mouse.move(tx, ty)
                                    await page.mouse.click(tx, ty, delay=15)
                                else:
                                    await btn.click(timeout=3000)
                            except Exception:
                                await btn.click(timeout=3000)
                            logger.info('Browser: ✅ Sign In нажат')
                            break
                    except Exception:
                        pass

                # Ждём редирект на дашборд
                logger.info('Browser: ждём редирект после логина...')
                logged_in = False
                for w in range(100):
                    await asyncio.sleep(0.5)
                    try:
                        cur = page.url or ''
                        if any(p in cur for p in ['/home', '/overview', '/websites', '/welcome', '/onboarding']):
                            logger.info(f'Browser: ✅ Залогинились! URL={cur}')
                            logged_in = True
                            login_success = True
                            break
                        # Проверяем нет ли капчи снова
                        cf_frames = [f for f in page.frames if 'challenges.cloudflare.com' in f.url]
                        if cf_frames and w % 10 == 0:
                            await bypass_turnstile_safely(page, timeout=8000)
                    except Exception:
                        pass

                if logged_in:
                    break
                elif sign_attempt < 4:
                    logger.warning(f'Browser: логин не удался (попытка {sign_attempt}), повторяем...')

            if not login_success:
                logger.error('Browser: ❌ не удалось залогиниться')
                return (False, None)

            # ── Шаг 5: Ждём 2 секунды на дашборде, потом verify URL ──────────
            logger.info('Browser: ✅ Залогинились. Ждём 2с и переходим по verify URL...')
            await asyncio.sleep(2)

            try:
                await page.goto(verify_url, wait_until='domcontentloaded', timeout=60000)
            except Exception as e:
                logger.warning(f'Browser: goto verify_url: {e}')
            await asyncio.sleep(3)

            # Проверяем верификацию — смотрим URL / ответ
            cur = page.url or ''
            logger.info(f'Browser: URL после verify_url: {cur}')
            if any(p in cur for p in ['/home', '/overview', '/websites', '/welcome', '/onboarding', '/email-verification']):
                verified = True
                logger.info('Browser: ✅ email верифицирован (URL дашборда/верификации)')

            # Ждём ещё немного — может быть редирект
            for chk in range(20):
                await asyncio.sleep(1)
                try:
                    cur = page.url or ''
                    if any(p in cur for p in ['/home', '/overview', '/websites', '/welcome', '/onboarding']):
                        verified = True
                        logger.info(f'Browser: ✅ email верифицирован, дашборд: {cur}')
                        break
                    # Нажимаем Continue если есть
                    continue_btn = page.locator('button:has-text("Continue"), a:has-text("Continue to Cloudflare"), a:has-text("Continue")')
                    if await continue_btn.count() > 0:
                        logger.info('Browser: нажимаем Continue...')
                        await continue_btn.first.click()
                        await asyncio.sleep(1)
                        continue
                    # Проверяем текст дашборда
                    try:
                        text = await page.evaluate('document.body?.innerText || ""')
                        if any(kw in text.lower() for kw in ['add a website', 'get started', 'account home', 'welcome to cloudflare']):
                            verified = True
                            logger.info('Browser: ✅ email верифицирован (текст дашборда)')
                            break
                    except Exception:
                        pass
                except Exception:
                    pass

            if not verified:
                # Считаем верифицированным раз залогинились — Cloudflare может отложить верификацию
                verified = login_success
                logger.info(f'Browser: считаем verified={verified} т.к. login_success={login_success}')

            # Ждём пока email_verified=True в API (до 30 сек)
            if verified:
                logger.info('Browser: ждём email_verified=True в API...')
                for ev_wait in range(30):
                    try:
                        ev_r = await page.evaluate('''() =>
                            fetch('/api/v4/user', {
                                headers: {'Accept': 'application/json', 'X-Cross-Site-Security': 'dash'}
                            }).then(r => r.json())
                        ''')
                        if (ev_r.get('result') or {}).get('email_verified', False):
                            logger.info(f'Browser: ✅ email_verified=True в API ({ev_wait+1}s)')
                            break
                        logger.info(f'Browser: email_verified=False, жду 1s... ({ev_wait+1}/30)')
                    except Exception:
                        pass
                    await asyncio.sleep(1)

            # ── Шаг 6: Извлекаем API ключ через otp_callback ─────────────────
            result = None
            if verified and otp_callback:
                try:
                    result = await otp_callback(page)
                except Exception as cb_err:
                    logger.error(f'Browser: ошибка в otp_callback: {cb_err}')

            browser_cookies = None
            if verified:
                try:
                    browser_cookies = await page.context.cookies()
                except Exception:
                    pass

            return (verified, result or browser_cookies)

        except Exception as e:
            logger.error(f'Browser: критическая ошибка: {e}')
            return (False, None)
        finally:
            pass
