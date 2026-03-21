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
```

## 4) Runtime behavior
- Chay tuan tu account_1 roi account_2.
- Moi account chay `RUN_DURATION` giay.
- Reload tab moi `RELOAD_INTERVAL` giay.
- Screenshot cap nhat trong `screenshots/<account>.png`.
- Profile trinh duyet luu tai `profiles/<account>/`.

## 5) Logs
- Xem tren Railway Deployment Logs.
- Trong container co file `railway.log`.
