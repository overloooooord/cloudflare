import asyncio
import json
import os
from datetime import datetime

_lock = asyncio.Lock()

async def save_result(output_file: str, email: str, mail_password: str, cloud_password: str, api_key: str, fmt: str='txt') -> None:
    async with _lock:
        cloud_str = f'{email}:{mail_password}:{cloud_password}:{api_key}'
        
        out_dir = os.path.dirname(os.path.abspath(output_file)) if os.path.dirname(output_file) else os.getcwd()
        os.makedirs(out_dir, exist_ok=True)
        
        json_file = os.path.join(out_dir, 'results.json')
        txt_file = os.path.join(out_dir, 'results.txt')

        # 1. Save to JSON
        try:
            data = {'clouds': []}
            if os.path.exists(json_file):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if 'clouds' not in data or not isinstance(data['clouds'], list):
                        data = {'clouds': []}
                except Exception:
                    data = {'clouds': []}
            if cloud_str not in data['clouds']:
                data['clouds'].append(cloud_str)
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 2. Also append to TXT
        try:
            with open(txt_file, 'a', encoding='utf-8') as f:
                f.write(cloud_str + '\n')
        except Exception:
            pass