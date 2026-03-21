# Railway Setup (Ban gon)

## 1) Files can deploy
- `railway_task.py`
- `requirements.txt`
- `Dockerfile`

## 2) Deploy
1. Push code len GitHub.
2. Railway -> New Project -> Deploy from GitHub.
3. Chon repository va branch.

## 3) Variables can set (optional)
Neu khong set, script van chay theo default trong code.

```
GOOGLE_EMAIL_1=
GOOGLE_PASSWORD_1=
RECOVERY_EMAIL_1=
PROXY_1=

GOOGLE_EMAIL_2=
GOOGLE_PASSWORD_2=
RECOVERY_EMAIL_2=
PROXY_2=

RUN_DURATION=900
RELOAD_INTERVAL=300
SCREENSHOT_INTERVAL=10
NAVIGATION_TIMEOUT=30
MAX_NAV_RETRIES=3
MAX_CONCURRENT_ACCOUNTS=2
ENABLE_SCREENSHOT=0
MEMORY_SAVER=1
AUTO_LIMIT_BY_RAM=0
ESTIMATED_RAM_PER_ACCOUNT_MB=650
RAM_RESERVE_MB=256

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_THREAD_ID=
TELEGRAM_SEND_EVENTS=1
TELEGRAM_SEND_SCREENSHOT=1
TELEGRAM_PHOTO_INTERVAL=300
TELEGRAM_TIMEOUT=20
```

## 4) Runtime behavior
- Co 2 mode:
  - `MAX_CONCURRENT_ACCOUNTS=1`: chay tuan tu account_1 roi account_2.
  - `MAX_CONCURRENT_ACCOUNTS=2`: chay dong thoi 2 account (log xen ke).
- Mac dinh dang ep chay 2 acc cung luc (`MAX_CONCURRENT_ACCOUNTS=2`, `AUTO_LIMIT_BY_RAM=0`).
- Neu doi sang `AUTO_LIMIT_BY_RAM=1`, script tu dong ha muc song song neu RAM khong du.
- Moi account chay `RUN_DURATION` giay.
- Reload tab moi `RELOAD_INTERVAL` giay.
- Screenshot cap nhat trong `screenshots/<account>.png` (tat bang `ENABLE_SCREENSHOT=0`).
- Co the gui thong bao + anh ve Telegram neu set `TELEGRAM_BOT_TOKEN` va `TELEGRAM_CHAT_ID`.
- `TELEGRAM_SEND_SCREENSHOT=1` de gui anh dinh ky, chu ky theo `TELEGRAM_PHOTO_INTERVAL` (giay).
- Profile trinh duyet luu tai `profiles/<account>/`.

## 5) Logs
- Xem tren Railway Deployment Logs.
- Trong container co file `railway.log`.
