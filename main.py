import os
import sys
import subprocess

if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
        hStdin = ctypes.windll.kernel32.GetStdHandle(-10)
        mode = ctypes.c_ulong()
        ctypes.windll.kernel32.GetConsoleMode(hStdin, ctypes.byref(mode))
        mode.value &= ~0x0040
        mode.value |= 0x0080
        ctypes.windll.kernel32.SetConsoleMode(hStdin, mode.value)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
try:
    os.chdir(_SRC_DIR)
except Exception:
    pass

_CONFIG_PATH = os.path.join(_SRC_DIR, 'config.py')
if not os.path.exists(_CONFIG_PATH):
    _DEFAULT_CONFIG = '''THREADS = 2
COUNT = 0
CAPTCHA_SERVICE = 'anysolver'
CAPTCHA_API_KEY = 'anysolver_01M1ZBD1RYM894FD4H1EAV2CK9'
PROXIES_FILE = 'proxies.txt'
EMAILS_FILE = 'emails.txt'
NOTLETTERS_API_KEY = 'tSgRsPcuEZIMY5zxVYCpha88buBoSaYS'
CLOUDFLARE_PASSWORD = 'random'
OUTPUT_FILE = 'results.json'
OUTPUT_FORMAT = 'json'
MAX_RETRIES = 3
DEBUG = False
'''
    try:
        with open(_CONFIG_PATH, 'w', encoding='utf-8') as _f:
            _f.write(_DEFAULT_CONFIG)
    except Exception:
        pass

for _fn in ['emails.txt', 'proxies.txt']:
    _fp = os.path.join(_SRC_DIR, _fn)
    if not os.path.exists(_fp):
        try:
            with open(_fp, 'w', encoding='utf-8') as _f:
                pass
        except Exception:
            pass

_UI_PATH = os.path.join(_SRC_DIR, 'ui.py')
if not os.path.exists(_UI_PATH):
    _DEFAULT_UI = '''import time
import asyncio
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.live import Live

console = Console()

class TerminalUI:
    def __init__(self, threads: int, total_proxies: int):
        self.threads = threads
        self.total_proxies = total_proxies
        self.start_time = time.time()
        self.success = 0
        self.failed = 0
        self.emails_left = 0
        self.alive_proxies = total_proxies
        self.workers = {}
        self.recent_keys = []
        self.alerts = []

    def set_stats(self, success: int, failed: int, emails_left: int, alive_proxies: int):
        self.success = success
        self.failed = failed
        self.emails_left = emails_left
        self.alive_proxies = alive_proxies

    def update_worker(self, worker_id: int, email: str = "", status: str = "", proxy: str = ""):
        now = time.time()
        if worker_id not in self.workers:
            self.workers[worker_id] = {'email': email, 'status': status, 'proxy': proxy, 'start': now}
        else:
            if email:
                self.workers[worker_id]['email'] = email
            if status:
                self.workers[worker_id]['status'] = status
            if proxy:
                self.workers[worker_id]['proxy'] = proxy
            if not email and not status:
                self.workers[worker_id] = {'email': '-', 'status': '[dim]Свободен[/dim]', 'proxy': '-', 'start': now}

    def add_success(self, email: str, key: str, elapsed: float):
        self.recent_keys.insert(0, (email, key, elapsed))
        if len(self.recent_keys) > 4:
            self.recent_keys.pop()

    def add_alert(self, alert_msg: str):
        if alert_msg not in self.alerts:
            self.alerts.append(alert_msg)

    def render(self) -> Group:
        elapsed = time.time() - self.start_time
        rpm = (self.success / elapsed * 60) if elapsed >= 5 else 0.0

        stats_tbl = Table.grid(expand=True, padding=(0, 2))
        stats_tbl.add_column(ratio=1, justify="center")
        stats_tbl.add_column(ratio=1, justify="center")
        stats_tbl.add_column(ratio=1, justify="center")
        stats_tbl.add_column(ratio=1, justify="center")
        stats_tbl.add_column(ratio=1, justify="center")

        emails_str = f"[bold green]{self.emails_left}[/bold green]" if self.emails_left > 10 else f"[bold yellow]{self.emails_left}[/bold yellow]" if self.emails_left > 0 else "[bold red blink]0 (НЕТ ПОЧТ)[/bold red blink]"
        proxies_str = f"[bold green]{self.alive_proxies}/{self.total_proxies}[/bold green]" if self.alive_proxies > 0 else "[bold red blink]0 (ВСЕ ОТВАЛИЛИСЬ)[/bold red blink]"

        stats_tbl.add_row(
            f"✅ Успешно: [bold green]{self.success}[/bold green]",
            f"❌ Ошибок: [bold red]{self.failed}[/bold red]",
            f"🚀 Скорость: [bold cyan]{rpm:.1f}/мин[/bold cyan]",
            f"📬 Почт в пуле: {emails_str}",
            f"🌐 Прокси: {proxies_str}"
        )

        header_panel = Panel(
            stats_tbl,
            title="[bold white on dark_blue] CLOUDFLARE AUTOREGER - LIVE DASHBOARD [/bold white on dark_blue]",
            subtitle=f"[dim]Потоков: {self.threads} | Время работы: {int(elapsed//60):02d}:{int(elapsed%60):02d}[/dim]",
            border_style="blue"
        )

        worker_tbl = Table(expand=True, show_edge=False, box=None, header_style="bold magenta")
        worker_tbl.add_column("#", width=4, justify="center")
        worker_tbl.add_column("Почта", ratio=3)
        worker_tbl.add_column("Текущий статус", ratio=3)
        worker_tbl.add_column("Прокси", ratio=2)
        worker_tbl.add_column("Время", width=8, justify="right")

        now = time.time()
        for wid in range(1, self.threads + 1):
            w = self.workers.get(wid, {'email': '-', 'status': '[dim]Ожидание задачи[/dim]', 'proxy': '-', 'start': now})
            dur = int(now - w['start'])
            dur_str = f"{dur}s" if w['email'] != '-' else "-"
            short_p = w['proxy'].split('@')[-1] if '@' in w['proxy'] else w['proxy']
            worker_tbl.add_row(
                f"[bold cyan]{wid}[/bold cyan]",
                w['email'],
                w['status'],
                short_p or "-",
                dur_str
            )

        workers_panel = Panel(worker_tbl, title="[bold]Активные потоки[/bold]", border_style="cyan")
        components = [header_panel, workers_panel]

        if self.alerts:
            alert_text = "\\n".join([f"[bold red]⚠️ {a}[/bold red]" for a in self.alerts])
            components.append(Panel(alert_text, title="[bold red]ВНИМАНИЕ[/bold red]", border_style="red"))

        if self.recent_keys:
            recent_tbl = Table(expand=True, show_edge=False, box=None)
            recent_tbl.add_column("Email", ratio=3, style="dim")
            recent_tbl.add_column("Global API Key", ratio=4, style="bold green")
            recent_tbl.add_column("Время", width=8, justify="right", style="cyan")

            for em, k, t in self.recent_keys:
                recent_tbl.add_row(em, k, f"{t:.1f}s")

            components.append(Panel(recent_tbl, title="[bold green]Последние зарегистрированные аккаунты[/bold green]", border_style="green"))

        return Group(*components)
'''
    try:
        with open(_UI_PATH, 'w', encoding='utf-8') as _f:
            _f.write(_DEFAULT_UI)
    except Exception:
        pass

def _ensure_deps():
    reqs = ['curl_cffi', 'aiohttp', 'aiofiles', 'certifi', 'rich']
    missing = []
    for mod in reqs:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        req_file = os.path.join(_SRC_DIR, 'requirements.txt')
        cmd = [sys.executable, '-m', 'pip', 'install', '-r', req_file] if os.path.exists(req_file) else [sys.executable, '-m', 'pip', 'install'] + missing
        try:
            subprocess.check_call(cmd, cwd=_SRC_DIR)
        except Exception:
            pass

_ensure_deps()

from datetime import datetime
import asyncio
import argparse
import logging
import random
import socket
import ssl
import time
import urllib.parse
import aiohttp
import config
import mail_tm
import proxy_utils
import results as res_module
import cloudflare_api as cf_api
import turnstile

try:
    from ui import TerminalUI, console
    from rich.live import Live
    HAS_UI = True
except Exception:
    HAS_UI = False
    TerminalUI = None
    console = None
    Live = None

logger = logging.getLogger(__name__)


def generate_random_password(length: int = 16) -> str:
    import string
    chars = string.ascii_letters + string.digits + '!@#$%^&*'
    pwd = [
        random.choice(string.ascii_lowercase),
        random.choice(string.ascii_uppercase),
        random.choice(string.digits),
        random.choice('!@#$%^&*')
    ]
    pwd += [random.choice(chars) for _ in range(max(0, length - 4))]
    random.shuffle(pwd)
    return ''.join(pwd)


_err_lock = asyncio.Lock()


async def log_error_to_file(email: str, step: str, err_msg: str, proxy: str = ""):
    async with _err_lock:
        err_file = os.path.join(_SRC_DIR, 'errors.txt')
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        clean_err = str(err_msg).replace('\n', ' ').strip()
        short_p = proxy.split('@')[-1] if '@' in proxy else proxy
        line = f"[{now_str}] [{email or 'N/A'}] [Шаг: {step}] [Прокси: {short_p or '-'}] {clean_err}\n"
        try:
            with open(err_file, 'a', encoding='utf-8') as f:
                f.write(line)
                f.flush()
        except Exception:
            pass


def setup_logging(debug: bool = False, use_ui: bool = True):
    level = logging.DEBUG if debug else logging.INFO
    fmt = '%(asctime)s [%(levelname)s] %(message)s'
    if use_ui and HAS_UI:
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'autoreger.log')
        logging.basicConfig(level=level, format=fmt, filename=log_file, filemode='a', force=True)
    else:
        logging.basicConfig(level=level, format=fmt, stream=sys.stdout, force=True)
    logging.getLogger('pycares').setLevel(logging.ERROR)
    logging.getLogger('aiodns').setLevel(logging.ERROR)


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
        rpm = self.success / elapsed * 60 if elapsed >= 5 else 0
        return f'✅ {self.success} | ❌ {self.failed} | ⏱ {elapsed:.1f}s | 🚀 {rpm:.1f}/min'


async def register_one(worker_id: int, proxy_pool: proxy_utils.ProxyPool, stats: Stats, ui: TerminalUI | None, shutdown: asyncio.Event, debug: bool = False) -> bool:
    proxy = proxy_pool.get()
    if proxy_pool.is_empty and proxy_pool.total_count > 0:
        if ui:
            ui.add_alert("Все прокси в пуле перестали отвечать!")
        logger.error("Все прокси в пуле недоступны!")
        shutdown.set()
        return False

    step = 'init'
    email = mail_email = mail_pass = cloud_pass = api_key = ''
    start_t = time.time()
    try:
        step = 'createMail'
        if ui:
            ui.update_worker(worker_id, "-", "[dim]Получение почты...[/dim]", proxy or "-")
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=ssl_ctx)

        async with aiohttp.ClientSession(connector=connector) as mail_session:
            mailbox = await mail_tm.create_mailbox(mail_session)
            mail_email = mailbox['email']
            mail_pass = mailbox['password']
            mail_token = mailbox['token']
            email = mail_email

            if config.CLOUDFLARE_PASSWORD == 'random':
                cloud_pass = generate_random_password()
            else:
                cloud_pass = config.CLOUDFLARE_PASSWORD

            known_ids = await mail_tm.get_existing_message_ids(
                mail_session, mail_token, email=mail_email, mail_password=mail_pass
            )

            step = 'turnstile_signup'
            if ui:
                ui.update_worker(worker_id, email, "[cyan]Решение Turnstile (signup)...[/cyan]", proxy or "-")
            else:
                logger.info(f'[{email}] Решение капчи signup...')

            cf_challenge_signup = await turnstile.solve_turnstile(action='signup', proxy=proxy)

            step = 'create_user'
            if ui:
                ui.update_worker(worker_id, email, "[blue]Создание пользователя...[/blue]", proxy or "-")

            cf_session = cf_api._make_session(proxy)
            async with cf_session:
                sec_token = await cf_api.get_security_token(cf_session)
                await cf_api.create_user(cf_session, email, cloud_pass, sec_token, cf_challenge_signup)

                step = 'wait_verify_email'
                if ui:
                    ui.update_worker(worker_id, email, "[yellow]Ожидание ссылки...[/yellow]", proxy or "-")

                html = await mail_tm.wait_for_new_message(
                    mail_session, mail_token, known_ids, timeout=50, poll_interval=0.5,
                    email=mail_email, mail_password=mail_pass
                )
                verify_token = mail_tm.extract_verification_token(html)

                step = 'verify_email'
                if ui:
                    ui.update_worker(worker_id, email, "[blue]Верификация email...[/blue]", proxy or "-")
                await cf_api.verify_email(cf_session, verify_token)
                await asyncio.sleep(1.0)

                step = 'reauthenticate'
                known_ids_otp = await mail_tm.get_existing_message_ids(
                    mail_session, mail_token, email=mail_email, mail_password=mail_pass
                )
                await cf_api.reauthenticate(cf_session)

                step = 'wait_otp_and_turnstile'
                if ui:
                    ui.update_worker(worker_id, email, "[yellow]Ожидание OTP + Капча...[/yellow]", proxy or "-")

                async def _get_otp():
                    h_otp = await mail_tm.wait_for_new_message(
                        mail_session, mail_token, known_ids_otp, timeout=50, poll_interval=0.5,
                        email=mail_email, mail_password=mail_pass
                    )
                    return mail_tm.extract_otp_code(h_otp)

                async def _get_turnstile():
                    return await turnstile.solve_turnstile(action='onboarding', proxy=proxy)

                otp_code, cf_challenge_key = await asyncio.gather(_get_otp(), _get_turnstile())

                step = 'get_api_key'
                if ui:
                    ui.update_worker(worker_id, email, "[green]Запрос Global API Key...[/green]", proxy or "-")

                api_key = None
                for key_attempt in range(1, 3):
                    try:
                        api_key = await cf_api.get_global_api_key(cf_session, otp_code, cf_challenge_key)
                        break
                    except Exception as e:
                        if '1211' in str(e) and key_attempt < 2:
                            logger.warning(f'[{email}] Cloudflare 1211 (синхронизация email), решаем свежую капчу и повторяем...')
                            if ui:
                                ui.update_worker(worker_id, email, "[yellow]Синхронизация CF (1211)...[/yellow]", proxy or "-")
                            await asyncio.sleep(3.0)
                            cf_challenge_key = await turnstile.solve_turnstile(action='onboarding', proxy=proxy)
                            continue
                        raise
                if not api_key:
                    raise RuntimeError('Global API Key не получен')

        step = 'save'
        await res_module.save_result(config.OUTPUT_FILE, email=mail_email, mail_password=mail_pass, cloud_password=cloud_pass, api_key=api_key, fmt=config.OUTPUT_FORMAT)
        await mail_tm.remove_email_from_file(mail_email)
        elapsed_one = time.time() - start_t
        await stats.inc_success()
        proxy_pool.report_success(proxy)
        logger.info(f'[{email}] Успешно: {api_key} ({elapsed_one:.1f}s)')
        if ui:
            ui.add_success(email, api_key, elapsed_one)
            ui.update_worker(worker_id, "-", "[dim]Свободен[/dim]", "-")
        return True
    except mail_tm.OutOfEmailsError:
        logger.warning("Все почты в emails.txt обработаны!")
        if ui:
            ui.add_alert("Все почты в emails.txt закончились! Регистрация остановлена.")
            ui.update_worker(worker_id, "-", "[red]Почты закончились[/red]", "-")
        shutdown.set()
        return False
    except Exception as e:
        err_msg = str(e)
        if proxy and any(err_kw in err_msg for err_kw in ("Proxy", "Connection", "Timeout", "429", "Connect", "502", "504", "CurlError")):
            proxy_pool.report_failure(proxy, reason=err_msg[:30])
        await stats.inc_failed()
        logger.error(f"❌ [{email or 'N/A'}] ({step}) {err_msg}")
        await log_error_to_file(email, step, err_msg, proxy or "")
        if ui:
            ui.add_error(email, f"[{step}] {err_msg}", proxy or "-")
            ui.update_worker(worker_id, email or "-", f"[red]Ошибка ({step})[/red]", proxy or "-")
        if debug:
            logger.exception('Traceback:')
        return False


async def run_forever(count: int | None, proxy_pool: proxy_utils.ProxyPool, debug: bool, use_ui: bool = True):
    semaphore = asyncio.Semaphore(config.THREADS)
    stats = Stats()
    tasks = []
    shutdown = asyncio.Event()

    ui = TerminalUI(threads=config.THREADS, total_proxies=proxy_pool.total_count) if (use_ui and HAS_UI and TerminalUI) else None

    worker_slots = asyncio.Queue()
    for i in range(1, config.THREADS + 1):
        worker_slots.put_nowait(i)

    async def worker():
        if shutdown.is_set():
            return False
        wid = await worker_slots.get()
        try:
            async with semaphore:
                if shutdown.is_set():
                    return False
                return await register_one(wid, proxy_pool, stats, ui, shutdown, debug=debug)
        finally:
            worker_slots.put_nowait(wid)

    async def ui_loop(live):
        while not shutdown.is_set():
            try:
                emails_left = mail_tm.get_remaining_emails()
                alive_p = proxy_pool.alive_count
                ui.set_stats(stats.success, stats.failed, emails_left, alive_p)
                live.update(ui.render())
            except Exception:
                pass
            await asyncio.sleep(0.3)
        try:
            emails_left = mail_tm.get_remaining_emails()
            ui.set_stats(stats.success, stats.failed, emails_left, proxy_pool.alive_count)
            live.update(ui.render())
        except Exception:
            pass

    async def execute_batch():
        nonlocal tasks
        if count:
            tasks.extend(asyncio.create_task(worker()) for _ in range(count))
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            while not shutdown.is_set():
                active = sum(1 for t in tasks if not t.done())
                while active < config.THREADS and not shutdown.is_set():
                    tasks.append(asyncio.create_task(worker()))
                    active += 1
                await asyncio.sleep(0.2)
                tasks = [t for t in tasks if not t.done()]

    try:
        if use_ui and ui:
            with Live(ui.render(), console=console, refresh_per_second=4) as live:
                ui_task = asyncio.create_task(ui_loop(live))
                await execute_batch()
                shutdown.set()
                await ui_task
        else:
            await execute_batch()
    except asyncio.CancelledError:
        pass
    finally:
        shutdown.set()
        pending = [t for t in tasks if not t.done()]
        if pending:
            done, still_pending = await asyncio.wait(pending, timeout=5)
            for t in still_pending:
                t.cancel()
        if not use_ui:
            logger.info(f'\n🏁 Итого: {stats.summary()}')


def parse_args():
    p = argparse.ArgumentParser(description='Cloudflare Autoreger + Global API Key')
    p.add_argument('--count', type=int, default=None)
    p.add_argument('--threads', type=int, default=None)
    p.add_argument('--proxy-file', type=str, default=None)
    p.add_argument('--output', type=str, default=None)
    p.add_argument('--no-ui', action='store_true', help='Disable live UI dashboard')
    p.add_argument('--debug', action='store_true')
    return p.parse_args()


async def run_diagnostics(proxy: str | None):
    logger.info('=' * 60)
    logger.info('🔍 Проверка окружения')
    try:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        conn = aiohttp.TCPConnector(family=socket.AF_INET, ssl=ssl_ctx)
        api_key = getattr(config, 'NOTLETTERS_API_KEY', '')
        if not api_key:
            logger.error('❌ NOTLETTERS_API_KEY не указан в config.py')
        else:
            async with aiohttp.ClientSession(connector=conn) as s:
                async with s.get(
                    'https://api.notletters.com/v1/me',
                    headers={'Authorization': f'Bearer {api_key}'},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        bal = data.get('data', {}).get('balance', '?')
                        logger.info(f'✅ NotLetters API: OK (баланс: {bal})')
                    else:
                        logger.warning(f'⚠️ NotLetters API: HTTP {r.status}')
    except Exception as e:
        logger.warning(f'⚠️ NotLetters API error: {e}')

    try:
        mail_tm._load_pool()
        logger.info(f'✅ emails.txt: {len(mail_tm._email_pool)} почт готово к регистрации')
    except Exception as e:
        logger.error(f'❌ Ошибка загрузки emails.txt: {e}')

    try:
        if config.CAPTCHA_API_KEY:
            ssl_ctx2 = ssl.create_default_context()
            ssl_ctx2.check_hostname = False
            ssl_ctx2.verify_mode = ssl.CERT_NONE
            conn2 = aiohttp.TCPConnector(family=socket.AF_INET, ssl=ssl_ctx2)
            async with aiohttp.ClientSession(connector=conn2) as s:
                async with s.post(
                    'https://api.anysolver.com/getBalance',
                    json={'clientKey': config.CAPTCHA_API_KEY},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        logger.info(f'✅ AnySolver API: OK (баланс: ${data.get("balance", "?")})')
                    else:
                        logger.warning(f'⚠️ AnySolver API: HTTP {r.status}')
    except Exception as e:
        logger.warning(f'⚠️ AnySolver API error: {e}')

    try:
        from curl_cffi.requests import AsyncSession
        logger.info('✅ curl_cffi (pure requests engine): OK')
    except ImportError as e:
        logger.error(f'❌ curl_cffi не установлен: {e}')
    logger.info('=' * 60)


def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    args = parse_args()
    debug = args.debug or config.DEBUG
    use_ui = not args.no_ui and not debug and HAS_UI

    setup_logging(debug, use_ui=False)

    if args.threads:
        config.THREADS = args.threads
    if args.output:
        config.OUTPUT_FILE = args.output
    count = args.count if args.count else config.COUNT if config.COUNT else None
    proxy_file = args.proxy_file or config.PROXIES_FILE
    proxy_pool = proxy_utils.ProxyPool.from_file(proxy_file)

    if proxy_pool.is_empty:
        logger.warning('Прокси не найдены — работа без прокси')
    else:
        logger.info(f'Загружено {len(proxy_pool)} прокси')

    logger.info(f"Потоки: {config.THREADS} | Вывод: {config.OUTPUT_FILE} | Лимит: {('без лимита' if not count else count)}")

    loop = asyncio.new_event_loop()
    test_proxy = proxy_pool.get() if not proxy_pool.is_empty else None
    loop.run_until_complete(run_diagnostics(test_proxy))

    if use_ui and HAS_UI:
        setup_logging(debug, use_ui=True)

    main_task = loop.create_task(run_forever(count=count, proxy_pool=proxy_pool, debug=debug, use_ui=use_ui))
    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        if not use_ui:
            logger.info('\nОстановка процесса...')
        main_task.cancel()
        try:
            loop.run_until_complete(main_task)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
    finally:
        loop.close()


if __name__ == '__main__':
    main()