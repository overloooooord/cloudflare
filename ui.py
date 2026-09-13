import time
import asyncio
from datetime import datetime
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text

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
        self.workers = {}  # worker_id -> {'email': '', 'status': 'Ожидание...', 'proxy': '', 'start': time.time()}
        self.recent_keys = []  # list of (email, key, elapsed)
        self.alerts = []
        self._live = None
        self._lock = asyncio.Lock()

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
            alert_text = "\n".join([f"[bold red]⚠️ {a}[/bold red]" for a in self.alerts])
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
