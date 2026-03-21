"""
Railway runner - sequential keep-alive for multiple Firebase accounts.
"""

import asyncio
import logging
import os
import random
import signal
import time
from datetime import datetime
from pathlib import Path

import nodriver as uc

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("railway.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ==================== CONFIG ====================
ACCOUNTS = [
    {
        "name": "account_1",
        "email": os.getenv("GOOGLE_EMAIL_1", "phu413271@gmail.com"),
        "password": os.getenv("GOOGLE_PASSWORD_1", "nvt2005S!"),
        "recovery": os.getenv("RECOVERY_EMAIL_1", "mail2@hunght1890.com"),
        "proxy": os.getenv("PROXY_1", "http://45.137.70.90:2433"),
        "firebase_url": "https://studio.firebase.google.com/windows-idx-97840365",
    },
    {
        "name": "account_2",
        "email": os.getenv("GOOGLE_EMAIL_2", "vanlong1999u@gmail.com"),
        "password": os.getenv("GOOGLE_PASSWORD_2", "truongnguyen"),
        "recovery": os.getenv("RECOVERY_EMAIL_2", "mail3@hunght1890.com"),
        "proxy": os.getenv("PROXY_2", "http://45.137.70.90:2433"),
        "firebase_url": "https://studio.firebase.google.com/idxvpsgit-74148240",
    },
]

RUN_DURATION = int(os.getenv("RUN_DURATION", "900"))  # seconds/account
RELOAD_INTERVAL = int(os.getenv("RELOAD_INTERVAL", "300"))  # seconds
SCREENSHOT_INTERVAL = int(os.getenv("SCREENSHOT_INTERVAL", "10"))  # seconds
NAVIGATION_TIMEOUT = int(os.getenv("NAVIGATION_TIMEOUT", "30"))  # seconds
MAX_NAV_RETRIES = int(os.getenv("MAX_NAV_RETRIES", "3"))

SCREENSHOT_DIR = Path("screenshots")
PROFILES_DIR = Path("profiles")
SCREENSHOT_DIR.mkdir(exist_ok=True)
PROFILES_DIR.mkdir(exist_ok=True)

GMAIL_LOGIN_URL = (
    "https://accounts.google.com/v3/signin/identifier"
    "?continue=https%3A%2F%2Fmail.google.com%2Fmail%2F"
    "&service=mail&flowName=GlifWebSignIn&flowEntry=ServiceLogin"
)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

global_running = True


def handle_shutdown(sig, frame):
    del sig, frame
    global global_running
    log.info("Nhan tin hieu dung, dang tat an toan...")
    global_running = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def is_google_login_url(url: str) -> bool:
    if not url:
        return False
    lower_url = url.lower()
    return "accounts.google.com" in lower_url or "signin" in lower_url


async def wait_for_element(tab, selector: str, timeout: int = 15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            el = await tab.find(selector, timeout=0.5)
            if el:
                return el
        except Exception:
            pass
        await asyncio.sleep(0.3)
    return None


async def human_type(element, text: str):
    for char in text:
        await element.send_keys(char)
        await asyncio.sleep(random.uniform(0.04, 0.1))


async def click_next(tab) -> bool:
    for selector in ["#identifierNext", "#passwordNext", "button[jsname='LgbsSe']"]:
        try:
            btn = await tab.find(selector, timeout=1)
            if btn:
                await btn.click()
                return True
        except Exception:
            continue
    return False


async def safe_navigate(browser, url: str, account_name: str, timeout: int = NAVIGATION_TIMEOUT):
    for attempt in range(1, MAX_NAV_RETRIES + 1):
        try:
            tab = await asyncio.wait_for(browser.get(url), timeout=timeout)
            return tab
        except asyncio.TimeoutError:
            log.warning("[%s] Timeout navigate %s/%s: %s", account_name, attempt, MAX_NAV_RETRIES, url)
        except Exception as e:
            log.warning("[%s] Navigate loi %s/%s: %s", account_name, attempt, MAX_NAV_RETRIES, e)
        await asyncio.sleep(2 * attempt)
    return None


async def handle_recovery(tab, account_name: str, recovery_email: str) -> bool:
    log.info("[%s] Dang xu ly recovery email...", account_name)
    try:
        recovery_option = None

        for selector in ["div[jsname='fmcmS']", "div.l5PPKe", "li[data-challengetype]"]:
            try:
                elements = await tab.find_all(selector, timeout=2)
                for el in elements:
                    el_text = str(getattr(el, "text", "") or getattr(el, "text_all", "") or "")
                    if "recovery" in el_text.lower():
                        recovery_option = el
                        break
                if recovery_option:
                    break
            except Exception:
                continue

        if not recovery_option:
            for text in ["Confirm your recovery email", "recovery email"]:
                try:
                    recovery_option = await tab.find(text, best_match=True, timeout=3)
                    if recovery_option:
                        break
                except Exception:
                    continue

        if not recovery_option:
            return False

        await recovery_option.click()
        await asyncio.sleep(3)

        recovery_input = None
        for sel in [
            "input[name='knowledgePreregisteredEmailResponse']",
            "input#knowledge-preregistered-email-response",
            "input[type='email']",
            "input[type='text']",
        ]:
            try:
                recovery_input = await tab.find(sel, timeout=3)
                if recovery_input:
                    break
            except Exception:
                continue

        if not recovery_input:
            return False

        await recovery_input.click()
        await asyncio.sleep(0.3)
        await human_type(recovery_input, recovery_email)
        await asyncio.sleep(0.5)
        await click_next(tab)
        return True
    except Exception:
        return False


async def login_gmail(browser, account: dict) -> bool:
    account_name = account["name"]

    tab = await safe_navigate(browser, GMAIL_LOGIN_URL, account_name)
    if not tab:
        log.error("[%s] Khong mo duoc trang dang nhap", account_name)
        return False

    log.info("[%s] Dang nhap email...", account_name)
    email_inp = await wait_for_element(tab, "input[type='email']")
    if not email_inp:
        log.error("[%s] Khong tim thay o email", account_name)
        return False

    await email_inp.click()
    await human_type(email_inp, account["email"])
    await click_next(tab)
    await asyncio.sleep(4)

    log.info("[%s] Dang nhap password...", account_name)
    pw_inp = await wait_for_element(tab, "input[type='password']", timeout=15)
    if not pw_inp:
        log.error("[%s] Khong tim thay o password", account_name)
        return False

    await pw_inp.click()
    await human_type(pw_inp, account["password"])
    await click_next(tab)
    await asyncio.sleep(5)

    for i in range(20):
        current_url = getattr(tab.target, "url", "")
        if "mail.google.com" in current_url or "myaccount.google.com" in current_url:
            log.info("[%s] Dang nhap thanh cong", account_name)
            return True

        page_lower = ""
        try:
            page_lower = (await tab.get_content()).lower()
        except Exception:
            pass

        if "recovery" in page_lower:
            ok = await handle_recovery(tab, account_name, account["recovery"])
            if ok:
                await asyncio.sleep(4)
                continue

        if "blocked" in page_lower or "denied" in page_lower:
            log.error("[%s] Tai khoan bi chan", account_name)
            return False

        await asyncio.sleep(2)
        log.info("[%s] Cho xac minh %s/20 ...", account_name, i + 1)

    log.error("[%s] Dang nhap timeout", account_name)
    return False


async def run_account(account: dict):
    account_name = account["name"]
    log.info("[%s] Bat dau session", account_name)

    browser = None
    try:
        profile_dir = PROFILES_DIR / account_name
        profile_dir.mkdir(parents=True, exist_ok=True)

        browser_args = [
            f"--user-agent={USER_AGENT}",
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--window-size=1280,720",
            "--disable-blink-features=AutomationControlled",
        ]
        if account.get("proxy"):
            browser_args.insert(0, f"--proxy-server={account['proxy']}")

        config = uc.Config(
            user_data_dir=str(profile_dir),
            browser_args=browser_args,
            lang="en-US",
        )
        browser = await uc.start(config=config)

        tab = await safe_navigate(browser, account["firebase_url"], account_name)
        if not tab:
            log.error("[%s] Khong mo duoc Firebase URL", account_name)
            return

        current_url = getattr(tab.target, "url", "")
        if is_google_login_url(current_url):
            log.info("[%s] Can dang nhap Gmail", account_name)
            ok = await login_gmail(browser, account)
            if not ok:
                return
            tab = await safe_navigate(browser, account["firebase_url"], account_name)
            if not tab:
                log.error("[%s] Dang nhap xong nhung khong vao lai duoc Firebase", account_name)
                return

        log.info("[%s] Da vao Firebase, chay %ss", account_name, RUN_DURATION)
        start_time = time.time()
        next_reload = start_time + RELOAD_INTERVAL
        next_shot = start_time
        reload_count = 0

        while global_running and (time.time() - start_time < RUN_DURATION):
            now = time.time()
            if now >= next_shot:
                shot_path = SCREENSHOT_DIR / f"{account_name}.png"
                try:
                    await tab.save_screenshot(str(shot_path))
                except Exception:
                    pass
                next_shot = now + SCREENSHOT_INTERVAL

            if now >= next_reload:
                try:
                    await asyncio.wait_for(tab.reload(), timeout=20)
                    reload_count += 1
                    log.info("[%s] Reload #%s OK", account_name, reload_count)
                except Exception as e:
                    log.warning("[%s] Reload loi: %s", account_name, e)
                    new_tab = await safe_navigate(browser, account["firebase_url"], account_name)
                    if new_tab:
                        tab = new_tab
                next_reload = now + RELOAD_INTERVAL

            await asyncio.sleep(1)

        elapsed = int(time.time() - start_time)
        log.info("[%s] Ket thuc session sau %ss", account_name, elapsed)

    except Exception as e:
        log.exception("[%s] Crash: %s", account_name, e)
    finally:
        if browser:
            try:
                browser.stop()
            except Exception:
                pass
        log.info("[%s] Browser da dong", account_name)


async def main():
    cycle = 0
    while global_running:
        cycle += 1
        log.info("===== Chu ky #%s | %s =====", cycle, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        for account in ACCOUNTS:
            if not global_running:
                break
            await run_account(account)
            if global_running:
                await asyncio.sleep(3)

    log.info("Da dung toan bo chuong trinh.")


if __name__ == "__main__":
    asyncio.run(main())
