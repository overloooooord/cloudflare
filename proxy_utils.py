import itertools
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class ProxyPool:
    def __init__(self, proxies: list[str], max_errors: int = 4):
        import random
        self._initial = list(proxies)
        self._pool = list(proxies)
        random.shuffle(self._pool)
        self._cycle = itertools.cycle(self._pool) if self._pool else None
        self._lock = threading.Lock()
        self._errors = {p: 0 for p in self._pool}
        self._dead = set()
        self.max_errors = max_errors

    @classmethod
    def from_file(cls, filepath: str) -> 'ProxyPool':
        proxies = []
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and (not line.startswith('#')):
                        proxies.append(line)
        return cls(proxies)

    def get(self) -> Optional[str]:
        with self._lock:
            if not self._pool:
                return None
            return next(self._cycle)

    def report_success(self, proxy: str | None):
        if not proxy:
            return
        with self._lock:
            if proxy in self._errors:
                self._errors[proxy] = 0

    def report_failure(self, proxy: str | None, reason: str = ""):
        if not proxy:
            return
        with self._lock:
            if proxy in self._dead or proxy not in self._errors:
                return
            self._errors[proxy] += 1
            if self._errors[proxy] >= self.max_errors:
                self._dead.add(proxy)
                if proxy in self._pool:
                    self._pool.remove(proxy)
                    self._cycle = itertools.cycle(self._pool) if self._pool else None
                short_p = proxy.split('@')[-1] if '@' in proxy else proxy
                logger.warning(f"[Proxy] Отключен нерабочий прокси ({reason}): {short_p} (живых: {len(self._pool)}/{len(self._initial)})")

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._pool) == 0

    @property
    def alive_count(self) -> int:
        with self._lock:
            return len(self._pool)

    @property
    def total_count(self) -> int:
        return len(self._initial)

    def __len__(self) -> int:
        with self._lock:
            return len(self._pool)
def normalize_proxy(proxy: str) -> str:
    if not proxy:
        return proxy
    if '://' not in proxy:
        proxy = 'http://' + proxy
    return proxy
def proxy_for_curl_cffi(proxy: str) -> str:
    return normalize_proxy(proxy)