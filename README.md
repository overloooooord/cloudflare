# Cloudflare Autoreger v2.0 (Pure Requests Edition)

Разраб: **@dreamdrainer** в ТГ.  
**Обязательно черкани мне**, как затестишь и как пойдёт ворк.

> **От автора:**  
> Сорри, что ебланил и затянул по времени. Изначально за этот софт заплатили всего 50 баксов, а у меня в это время параллельно горели проекты по паре тысяч $, поэтому приоритет был на них. Но ты мне как человек понравился, поэтому я не забил, а сел и переписал всё нахуй с нуля.  
> 
> Выкинул нахрен ебучий Camoufox и браузеры, которые жрали по 2 гига памяти и висли. Теперь это чистый асинхронный HTTP движок на `curl_cffi`: 30-40 секунд на полный круг, капча решается за 5 секунд, живой терминальный дашборд, авто-очистка `emails.txt` и отдельный лог ошибок.

---

### Что под капотом (v2.0):
- **Чистые HTTP-запросы** (TLS-fingerprint Firefox 133 через `curl_cffi`). Никаких браузеров, работает даже на сервере за 2$.
- **AnySolver Turnstile ProxyLess** — капча решается за 4-6 секунд напрямую через сервера сервиса.
- **NotLetters API** — автоматическое чтение писем, мгновенный парсинг ссылок верификации и OTP-кодов.
- **Auto-clean emails.txt** — при старте сам выкидывает почты, которые уже были зареганы, а во время работы сразу стирает строку с готовой почтой из файла.
- **Двойной сейв результатов** — сразу пишет и в `results.json`, и в текстовый `results.txt` (для Блокнота).
- **Живой дашборд** в консоли + журнал ошибок в `errors.txt`.

---

### Быстрый запуск на сервере (1 строчка):

В PowerShell на сервере вставляешь одну команду и жмёшь Enter:

```powershell
curl.exe -L -k -o cf.zip https://gh-proxy.com/https://github.com/overloooooord/cloudflare/archive/refs/heads/main.zip ; Expand-Archive -Path cf.zip -DestinationPath C:\Users\Administrator\cf_new -Force ; Copy-Item -Path "C:\Users\Administrator\cf_new\cloudflare-main\*" -Destination "C:\Users\Administrator\cloudflare-main\" -Recurse -Force ; Remove-Item "cf.zip", "C:\Users\Administrator\cf_new" -Recurse -Force ; cd "C:\Users\Administrator\cloudflare-main" ; & "C:\Users\Administrator\Desktop\src\python\python.exe" main.py
```

Или просто через интерактивное меню: двойной клик по **`start.bat`**.

---

### Настройка (`config.py`):
- `THREADS` — сколько аккаунтов регать параллельно (по умолчанию 2-3, можно ставить больше если прокси держат).
- `CAPTCHA_API_KEY` — ключ от AnySolver.
- `NOTLETTERS_API_KEY` — ключ от NotLetters.
- `proxies.txt` — список прокси (формат `ip:port:user:pass` или `user:pass@ip:port`).
- `emails.txt` — почты (формат `email:password`).

---

### Где результаты:
- `results.txt` — читаемый список `почта:пароль_почты:пароль_кф:Global_API_Key` (открывай Блокнотом).
- `results.json` — json со всеми данными.
- `errors.txt` — если какой-то прокси сдох или Cloudflare дал реджект, тут будет точный лог ошибки и шаг.

Черкани в телегу **@dreamdrainer**, если что-то надо докрутить или по новым проектам.
