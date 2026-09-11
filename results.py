import asyncio
import json
import os
from datetime import datetime

_lock = asyncio.Lock()

async def save_result(output_file: str, email: str, mail_password: str, cloud_password: str, api_key: str, fmt: str='txt') -> None:
    async with _lock:
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        if fmt == 'json':
            # Формат: {"clouds": ["email:mail_pass:cloud_pass:api_key", ...]}
            cloud_str = f'{email}:{mail_password}:{cloud_password}:{api_key}'
            data = {'clouds': []}
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if 'clouds' not in data or not isinstance(data['clouds'], list):
                        data = {'clouds': []}
                except (json.JSONDecodeError, IOError):
                    data = {'clouds': []}
            data['clouds'].append(cloud_str)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            line = f'{email}:{mail_password}:{cloud_password}:{api_key}\n'
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(line)