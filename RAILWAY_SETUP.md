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
MAX_CONCURRENT_ACCOUNTS=1
ENABLE_SCREENSHOT=0
MEMORY_SAVER=1
AUTO_LIMIT_BY_RAM=0
ESTIMATED_RAM_PER_ACCOUNT_MB=650
RAM_RESERVE_MB=256

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_THREAD_ID=
TELEGRAM_SEND_EVENTS=1
TELEGRAM_SEND_LOGIN_SCREENSHOT=1
TELEGRAM_SEND_SCREENSHOT=0
TELEGRAM_PHOTO_INTERVAL=300
TELEGRAM_TIMEOUT=20
MIN_SCREENSHOT_BYTES=12000
```

## 4) Runtime behavior
- Chay tuan tu, 2 pha:
  - Pha login ban dau: login `account_1` xong moi login `account_2`.
  - Pha keep-alive: chay `account_1` theo `RUN_DURATION`, xong moi den `account_2`.
- Moi account chay `RUN_DURATION` giay.
- Reload tab moi `RELOAD_INTERVAL` giay.
- Screenshot cap nhat trong `screenshots/<account>.png` (tat bang `ENABLE_SCREENSHOT=0`).
- Co the gui thong bao + anh ve Telegram neu set `TELEGRAM_BOT_TOKEN` va `TELEGRAM_CHAT_ID`.
- `TELEGRAM_SEND_LOGIN_SCREENSHOT=1` de gui 1 anh duy nhat luc account vao Firebase thanh cong.
- `TELEGRAM_SEND_SCREENSHOT=1` de gui anh dinh ky, chu ky theo `TELEGRAM_PHOTO_INTERVAL` (giay).
- `MIN_SCREENSHOT_BYTES` dung de loc anh qua nho (de bi trang); script se tu chup lai.
- Profile trinh duyet luu tai `profiles/<account>/`.

## 5) Logs
- Xem tren Railway Deployment Logs.
- Trong container co file `railway.log`.
