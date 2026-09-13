import os
import sys
import json
import time
import zipfile
import shutil
import ssl
import urllib.request
import subprocess

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

script_dir = os.path.dirname(os.path.abspath(__file__))
local_cache = os.path.join(script_dir, "local_cache")

if sys.platform == 'win32':
    try:
        import platformdirs
        import platformdirs.windows
        platformdirs.windows.get_win_folder_via_ctypes = lambda x: local_cache
        platformdirs.windows.get_win_folder_from_registry = lambda x: local_cache
        platformdirs.windows.get_win_folder_from_env_vars = lambda x: local_cache
        platformdirs.windows.get_win_folder = lambda x: local_cache
        platformdirs.user_cache_dir = lambda *args, **kwargs: os.path.join(local_cache, "camoufox", "Cache")
        platformdirs.user_data_dir = lambda *args, **kwargs: os.path.join(local_cache, "camoufox")
    except ImportError:
        pass

camoufox_dir = os.path.join(local_cache, "camoufox")
target_dir = os.path.join(camoufox_dir, "browsers", "official", "135.0.1-beta.24")
exe_name = "camoufox.exe" if sys.platform == 'win32' else "camoufox-bin"
exe_path = os.path.join(target_dir, exe_name)

if os.path.exists(exe_path):
    print(f"[OK] Camoufox browser already installed at: {target_dir}")
    sys.exit(0)

os.makedirs(target_dir, exist_ok=True)
os.makedirs(camoufox_dir, exist_ok=True)

if sys.platform == 'win32':
    filename = "camoufox-135.0.1-beta.24-win.x86_64.zip"
else:
    filename = "camoufox-135.0.1-beta.24-lin.x86_64.zip"

raw_url = f"https://github.com/daijro/camoufox/releases/download/v135.0.1-beta.24/{filename}"

# Быстрые зеркала в обход блокировок GitHub CDN (Fastly)
download_urls = [
    f"https://gh-proxy.com/{raw_url}",
    f"https://mirror.ghproxy.com/{raw_url}",
    f"https://ghproxy.net/{raw_url}",
    raw_url
]

zip_path = os.path.join(camoufox_dir, "camoufox_download.zip")

print("=" * 60)
print("   DOWNLOADING CAMOUFOX BROWSER (~500 MB)")
print("============================================================")

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

download_ok = False

# Попытка 1: через встроенный Windows curl.exe (он быстрее всего и не виснет)
curl_exe = shutil.which("curl") or (r"C:\Windows\System32\curl.exe" if os.path.exists(r"C:\Windows\System32\curl.exe") else None)
if curl_exe:
    for url in download_urls:
        print(f"[*] Trying download via curl: {url[:55]}...")
        cmd = [curl_exe, "-L", "-k", "--connect-timeout", "15", "-#", "-o", zip_path, url]
        try:
            res = subprocess.run(cmd)
            if res.returncode == 0 and os.path.exists(zip_path) and os.path.getsize(zip_path) > 100 * 1024 * 1024:
                download_ok = True
                print("\n[OK] Download completed successfully via curl!")
                break
            else:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
        except Exception:
            pass

# Попытка 2: через Python (с коротким таймаутом на коннект)
if not download_ok:
    for url in download_urls:
        print(f"[*] Trying download via Python: {url[:55]}...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp, open(zip_path, 'wb') as out_f:
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0
                block_size = 1024 * 512
                last_time = time.time()
                while True:
                    chunk = resp.read(block_size)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_time >= 0.5 or (total_size and downloaded >= total_size):
                        last_time = now
                        mb = downloaded / (1024 * 1024)
                        if total_size > 0:
                            pct = min(100, int(downloaded * 100 / total_size))
                            tot_mb = total_size / (1024 * 1024)
                            sys.stdout.write(f"\r[+] Progress: {pct}% ({mb:.1f} MB / {tot_mb:.1f} MB)   ")
                        else:
                            sys.stdout.write(f"\r[+] Downloaded: {mb:.1f} MB   ")
                        sys.stdout.flush()
            if os.path.exists(zip_path) and os.path.getsize(zip_path) > 100 * 1024 * 1024:
                download_ok = True
                print("\n[OK] Download completed!")
                break
        except Exception as e:
            print(f"\n[-] Mirror failed: {e}")
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except Exception:
                    pass

if not download_ok:
    print("\n[X] Automatic download failed due to network restriction.")
    print("    Manual 1-click download link:")
    print(f"    https://gh-proxy.com/{raw_url}")
    print(f"    Extract its contents into:\n    {target_dir}\n")
    sys.exit(1)

print("\n[*] Extracting Camoufox browser...")
try:
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(target_dir)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    print("[OK] Extraction complete!")
except Exception as e:
    print(f"[X] Extraction error: {e}")
    sys.exit(1)

try:
    with open(os.path.join(target_dir, 'version.json'), 'w', encoding='utf-8') as f:
        json.dump({"version": "135.0.1", "build": "beta.24"}, f)
    with open(os.path.join(camoufox_dir, 'config.json'), 'w', encoding='utf-8') as f:
        json.dump({"active_version": "browsers/official/135.0.1-beta.24"}, f)
    with open(os.path.join(camoufox_dir, '.0.5_FLAG'), 'w', encoding='utf-8') as f:
        f.write("")
except Exception as e:
    pass

print("\n============================================================")
print("   [OK] CAMOUFOX BROWSER READY!")
print("============================================================\n")
sys.exit(0)
