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
RELOAD_INTERVAL=600
BROWSER_RESTART_INTERVAL=3600
LOGIN_STAGGER_SECONDS=60
SCREENSHOT_INTERVAL=10
NAVIGATION_TIMEOUT=30
MAX_NAV_RETRIES=3
MAX_CONCURRENT_ACCOUNTS=1
ENABLE_SCREENSHOT=0
MEMORY_SAVER=1
AUTO_LIMIT_BY_RAM=0
ESTIMATED_RAM_PER_ACCOUNT_MB=650
RAM_RESERVE_MB=256
MAX_KEEPALIVE_FAILURES=2
CRASH_RESTART_ATTEMPTS=3
CRASH_RESTART_BACKOFF_BASE=8
CRASH_RESTART_BACKOFF_MAX=60
BROWSER_HEALTHCHECK_INTERVAL=90
BROWSER_HEALTHCHECK_TIMEOUT=10

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_THREAD_ID=
TELEGRAM_SEND_EVENTS=1
TELEGRAM_SEND_LOGIN_SCREENSHOT=1
TELEGRAM_SEND_IDX_ENTRY_SCREENSHOT=1
TELEGRAM_SEND_SCREENSHOT=0
TELEGRAM_PHOTO_INTERVAL=300
TELEGRAM_TIMEOUT=20
MIN_SCREENSHOT_BYTES=12000
```

## 4) Runtime behavior
- Login tuan tu theo thu tu account:
  - Login `account_1`.
  - Cho `LOGIN_STAGGER_SECONDS` (mac dinh 60s).
  - Login `account_2`.
- Sau khi login, giu ca 2 browser mo dong thoi (khong dong browser giua chu ky).
- Reload moi tab moi `RELOAD_INTERVAL` giay (mac dinh 600s = 10 phut).
- Tu dong tat/mo lai browser moi `BROWSER_RESTART_INTERVAL` giay (mac dinh 3600s = 1 gio).
- `RUN_DURATION` hien khong dung trong mode keep-alive lien tuc.
- Screenshot cap nhat trong `screenshots/<account>.png` (tat bang `ENABLE_SCREENSHOT=0`).
- Moi lan vao lai trang IDX/Firebase thanh cong, script chup anh `screenshots/<account>_idx_entry_<timestamp>.png` (va cap nhat file latest).
- Co the gui thong bao + anh ve Telegram neu set `TELEGRAM_BOT_TOKEN` va `TELEGRAM_CHAT_ID`.
- `TELEGRAM_SEND_IDX_ENTRY_SCREENSHOT=1` de gui anh moi lan vao lai IDX/Firebase thanh cong.
- `TELEGRAM_SEND_SCREENSHOT=1` de gui anh dinh ky, chu ky theo `TELEGRAM_PHOTO_INTERVAL` (giay).
- `MIN_SCREENSHOT_BYTES` dung de loc anh qua nho (de bi trang); script se tu chup lai.
- Profile trinh duyet luu tai `profiles/<account>/`.
- Neu browser/profile bi sap trong luc keep-alive, script se tu mo lai profile (co backoff va retry theo cac bien `CRASH_*`).

## 5) Logs
- Xem tren Railway Deployment Logs.
- Trong container co file `railway.log`.
