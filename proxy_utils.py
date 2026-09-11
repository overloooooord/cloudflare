import itertools
import os
import threading
from typing import Optional
class ProxyPool:
    def __init__(self, proxies: list[str]):
        self._pool = list(proxies)
        self._cycle = itertools.cycle(self._pool) if self._pool else None
        self._lock = threading.Lock()
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
        if not self._cycle:
            return None
        with self._lock:
            return next(self._cycle)
    @property
    def is_empty(self) -> bool:
        return not self._pool
    def __len__(self) -> int:
        return len(self._pool)
def normalize_proxy(proxy: str) -> str:
    if not proxy:
        return proxy
    if '://' not in proxy:
        proxy = 'http://' + proxy
    return proxy
def proxy_for_curl_cffi(proxy: str) -> str:
    return normalize_proxy(proxy)