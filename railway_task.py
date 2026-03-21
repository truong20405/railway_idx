"""
Railway runner - keep-alive for multiple Firebase accounts.
Supports sequential or concurrent account sessions with RAM safety limit.
"""

import asyncio
import logging
import os
import random
import re
import signal
import time
from datetime import datetime
from pathlib import Path

import nodriver as uc
import requests

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


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError:
        log.warning("ENV %s=%r khong hop le, dung mac dinh %s", name, raw, default)
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def detect_total_ram_mb():
    # Railway containers expose memory info via /proc/meminfo.
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) // 1024
    except Exception:
        return None
    return None


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

RUN_DURATION = env_int("RUN_DURATION", 900)  # kept for backward compatibility logs
RELOAD_INTERVAL = env_int("RELOAD_INTERVAL", 600)  # seconds (10 minutes)
LOGIN_STAGGER_SECONDS = max(0, env_int("LOGIN_STAGGER_SECONDS", 60))
SCREENSHOT_INTERVAL = env_int("SCREENSHOT_INTERVAL", 10)  # seconds
NAVIGATION_TIMEOUT = env_int("NAVIGATION_TIMEOUT", 30)  # seconds
MAX_NAV_RETRIES = env_int("MAX_NAV_RETRIES", 3)
# Force sequential flow: account_1 completes before account_2 starts.
MAX_CONCURRENT_ACCOUNTS = 1
ENABLE_SCREENSHOT = env_bool("ENABLE_SCREENSHOT", False)
MEMORY_SAVER = env_bool("MEMORY_SAVER", True)
AUTO_LIMIT_BY_RAM = env_bool("AUTO_LIMIT_BY_RAM", False)
ESTIMATED_RAM_PER_ACCOUNT_MB = max(128, env_int("ESTIMATED_RAM_PER_ACCOUNT_MB", 650))
RAM_RESERVE_MB = max(128, env_int("RAM_RESERVE_MB", 256))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8431444806:AAFuLZnElTNtLoVBTTiVtnzKonkM00wE2h4").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5788963050").strip()
TELEGRAM_THREAD_ID = os.getenv("TELEGRAM_THREAD_ID", "").strip()
TELEGRAM_SEND_EVENTS = env_bool("TELEGRAM_SEND_EVENTS", True)
TELEGRAM_SEND_LOGIN_SCREENSHOT = env_bool("TELEGRAM_SEND_LOGIN_SCREENSHOT", True)
TELEGRAM_SEND_SCREENSHOT = env_bool("TELEGRAM_SEND_SCREENSHOT", False)
TELEGRAM_PHOTO_INTERVAL = max(10, env_int("TELEGRAM_PHOTO_INTERVAL", 300))
TELEGRAM_TIMEOUT = max(5, env_int("TELEGRAM_TIMEOUT", 20))
MIN_SCREENSHOT_BYTES = max(1000, env_int("MIN_SCREENSHOT_BYTES", 12000))

SCREENSHOT_DIR = Path("screenshots")
PROFILES_DIR = Path("profiles")
SCREENSHOT_DIR.mkdir(exist_ok=True)
PROFILES_DIR.mkdir(exist_ok=True)

GMAIL_LOGIN_URL = (
    "https://accounts.google.com/v3/signin/identifier"
    "?continue=https%3A%2F%2Fmail.google.com%2Fmail%2F"
    "&service=mail&flowName=GlifWebSignIn&flowEntry=ServiceLogin"
)
GMAIL_ATOM_URL = "https://mail.google.com/mail/u/0/feed/atom"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

global_running = True


def is_telegram_enabled() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def _telegram_payload(text: str):
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    if TELEGRAM_THREAD_ID:
        payload["message_thread_id"] = TELEGRAM_THREAD_ID
    return payload


def send_telegram_message_sync(text: str):
    if not is_telegram_enabled():
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, data=_telegram_payload(text), timeout=TELEGRAM_TIMEOUT)
        if resp.ok:
            return True
        log.warning("Telegram sendMessage that bai: HTTP %s %s", resp.status_code, resp.text[:300])
        return False
    except Exception as e:
        log.warning("Telegram sendMessage loi: %s", e)
        return False


def send_telegram_photo_sync(photo_path: Path, caption: str = ""):
    if not is_telegram_enabled():
        return False
    if not photo_path.exists():
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
        if TELEGRAM_THREAD_ID:
            payload["message_thread_id"] = TELEGRAM_THREAD_ID
        with photo_path.open("rb") as f:
            files = {"photo": (photo_path.name, f, "image/png")}
            resp = requests.post(url, data=payload, files=files, timeout=TELEGRAM_TIMEOUT)
        if resp.ok:
            return True
        log.warning("Telegram sendPhoto that bai: HTTP %s %s", resp.status_code, resp.text[:300])
        return False
    except Exception as e:
        log.warning("Telegram sendPhoto loi: %s", e)
        return False


async def send_telegram_message(text: str):
    await asyncio.to_thread(send_telegram_message_sync, text)


async def send_telegram_photo(photo_path: Path, caption: str = ""):
    await asyncio.to_thread(send_telegram_photo_sync, photo_path, caption)


def handle_shutdown(sig, frame):
    del sig, frame
    global global_running
    log.info("Nhan tin hieu dung, dang tat an toan...")
    global_running = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def compute_effective_concurrency(requested: int) -> int:
    requested = max(1, requested)
    if not AUTO_LIMIT_BY_RAM:
        return requested

    total_ram_mb = detect_total_ram_mb()
    if not total_ram_mb:
        return requested

    browser_budget_mb = max(0, total_ram_mb - RAM_RESERVE_MB)
    ram_based_limit = max(1, browser_budget_mb // ESTIMATED_RAM_PER_ACCOUNT_MB)
    effective = max(1, min(requested, ram_based_limit))
    if effective < requested:
        log.warning(
            "RAM ~%sMB, giam song song tu %s -> %s (uoc tinh %sMB/account, reserve=%sMB)",
            total_ram_mb,
            requested,
            effective,
            ESTIMATED_RAM_PER_ACCOUNT_MB,
            RAM_RESERVE_MB,
        )
    return effective


def is_google_login_url(url: str) -> bool:
    if not url:
        return False
    lower_url = url.lower()
    return "accounts.google.com" in lower_url or "signin" in lower_url


def extract_first_email(text: str):
    if not text:
        return None
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else None


async def wait_for_firebase_ready(tab, account_name: str, timeout: int = 25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        current_url = getattr(tab.target, "url", "")
        if is_google_login_url(current_url):
            return False
        if "studio.firebase.google.com" in (current_url or "").lower():
            try:
                content = await tab.get_content()
                if content and len(content) > 1500:
                    return True
            except Exception:
                pass
        await asyncio.sleep(1)
    log.warning("[%s] Firebase load cham/khong on dinh truoc khi chup anh", account_name)
    return True


async def save_screenshot_with_retry(tab, shot_path: Path, account_name: str, retries: int = 5) -> bool:
    for attempt in range(1, retries + 1):
        try:
            await tab.save_screenshot(str(shot_path))
            size = shot_path.stat().st_size if shot_path.exists() else 0
            if size >= MIN_SCREENSHOT_BYTES:
                return True
            log.warning(
                "[%s] Anh nho bat thuong (%s bytes), thu lai %s/%s",
                account_name,
                size,
                attempt,
                retries,
            )
        except Exception as e:
            log.warning("[%s] Loi chup anh lan %s/%s: %s", account_name, attempt, retries, e)

        if attempt < retries:
            await asyncio.sleep(2)
            if attempt == 3:
                try:
                    await asyncio.wait_for(tab.reload(), timeout=20)
                except Exception:
                    pass
    return False


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
            if TELEGRAM_SEND_EVENTS and is_telegram_enabled():
                await send_telegram_message(f"[{account_name}] Dang nhap Gmail thanh cong")
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


async def verify_google_identity(browser, account: dict):
    account_name = account["name"]
    expected_email = (account.get("email") or "").strip().lower()

    tab = await safe_navigate(browser, GMAIL_ATOM_URL, account_name, timeout=20)
    if not tab:
        log.warning("[%s] Khong mo duoc trang xac minh Gmail", account_name)
        return False, None

    await asyncio.sleep(2)
    current_url = getattr(tab.target, "url", "")
    if is_google_login_url(current_url):
        log.info("[%s] Chua dang nhap Google (redirect login)", account_name)
        return False, None

    content = ""
    try:
        content = await tab.get_content()
    except Exception:
        pass

    detected_email = extract_first_email(content)
    if detected_email:
        detected_lower = detected_email.strip().lower()
        if expected_email and detected_lower != expected_email:
            log.warning(
                "[%s] Dang dang nhap bang email khac: %s (mong doi: %s)",
                account_name,
                detected_email,
                account.get("email"),
            )
            return False, detected_email
        log.info("[%s] Xac nhan da dang nhap dung account: %s", account_name, detected_email)
        return True, detected_email

    # Fallback: khong lay duoc email nhung khong bi redirect login.
    log.info("[%s] Co session Google, khong doc duoc email de doi chieu", account_name)
    return True, None


async def ensure_firebase_tab(browser, account: dict):
    account_name = account["name"]

    tab = await safe_navigate(browser, account["firebase_url"], account_name)
    if not tab:
        log.error("[%s] Khong mo duoc Firebase URL", account_name)
        return None

    current_url = getattr(tab.target, "url", "")
    need_login = is_google_login_url(current_url)
    if need_login:
        log.info("[%s] Can dang nhap Gmail", account_name)
    else:
        verified, _ = await verify_google_identity(browser, account)
        if verified:
            log.info("[%s] Da co session dang nhap hop le, bo qua buoc login", account_name)
        else:
            log.info("[%s] Chua dung account, se dang nhap lai", account_name)
            need_login = True

    if need_login:
        ok = await login_gmail(browser, account)
        if not ok:
            return None
        verified, detected_email = await verify_google_identity(browser, account)
        if not verified:
            log.error(
                "[%s] Dang nhap xong nhung chua xac nhan dung account (detected=%s)",
                account_name,
                detected_email,
            )
            return None

    tab = await safe_navigate(browser, account["firebase_url"], account_name)
    if not tab:
        log.error("[%s] Khong mo duoc Firebase URL sau buoc xac minh", account_name)
        return None
    current_url = getattr(tab.target, "url", "")
    if is_google_login_url(current_url):
        log.error("[%s] Bi day ve trang login khi vao Firebase", account_name)
        return None

    await wait_for_firebase_ready(tab, account_name)
    return tab


async def init_account_session(account: dict):
    account_name = account["name"]
    log.info("[%s] Bat dau phase: login-only", account_name)

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
            "--window-size=1024,640",
            "--disable-blink-features=AutomationControlled",
        ]
        if MEMORY_SAVER:
            browser_args.extend(
                [
                    "--disable-extensions",
                    "--disable-sync",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--mute-audio",
                    "--blink-settings=imagesEnabled=false",
                    "--renderer-process-limit=2",
                    "--disk-cache-size=1",
                    "--media-cache-size=1",
                ]
            )
        if account.get("proxy"):
            browser_args.insert(0, f"--proxy-server={account['proxy']}")

        config = uc.Config(
            user_data_dir=str(profile_dir),
            browser_args=browser_args,
            lang="en-US",
        )
        browser = await uc.start(config=config)

        tab = await ensure_firebase_tab(browser, account)
        if not tab:
            if browser:
                try:
                    browser.stop()
                except Exception:
                    pass
            return None

        log.info("[%s] Login OK, giu browser mo de keep-alive", account_name)
        if TELEGRAM_SEND_EVENTS and is_telegram_enabled():
            await send_telegram_message(f"[{account_name}] Da vao Firebase, bat dau keep-alive")

        if TELEGRAM_SEND_LOGIN_SCREENSHOT and is_telegram_enabled():
            login_shot_path = SCREENSHOT_DIR / f"{account_name}_login.png"
            try:
                ok = await save_screenshot_with_retry(tab, login_shot_path, account_name)
                if ok:
                    caption = f"{account_name} login OK | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    await send_telegram_photo(login_shot_path, caption=caption)
                    log.info("[%s] Da gui 1 anh login ve Telegram", account_name)
                else:
                    log.warning("[%s] Bo qua gui anh login vi chup anh khong dat chat luong", account_name)
            except Exception as e:
                log.warning("[%s] Loi gui anh login Telegram: %s", account_name, e)

        now = time.time()
        session = {
            "account": account,
            "account_name": account_name,
            "browser": browser,
            "tab": tab,
            "need_capture": ENABLE_SCREENSHOT or (is_telegram_enabled() and TELEGRAM_SEND_SCREENSHOT),
            "next_reload": now + RELOAD_INTERVAL,
            "next_shot": now + SCREENSHOT_INTERVAL,
            "next_telegram_photo": now + TELEGRAM_PHOTO_INTERVAL,
            "reload_count": 0,
        }
        return session
    except Exception as e:
        log.exception("[%s] Crash khoi tao session: %s", account_name, e)
        if browser:
            try:
                browser.stop()
            except Exception:
                pass
        return None


async def keepalive_tick(session: dict):
    account = session["account"]
    account_name = session["account_name"]
    browser = session["browser"]
    tab = session["tab"]
    now = time.time()

    if session["need_capture"] and now >= session["next_shot"]:
        shot_path = SCREENSHOT_DIR / f"{account_name}.png"
        try:
            await save_screenshot_with_retry(tab, shot_path, account_name, retries=3)
        except Exception:
            pass
        session["next_shot"] = now + SCREENSHOT_INTERVAL

        if is_telegram_enabled() and TELEGRAM_SEND_SCREENSHOT and now >= session["next_telegram_photo"]:
            caption = f"{account_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await send_telegram_photo(shot_path, caption=caption)
            session["next_telegram_photo"] = now + TELEGRAM_PHOTO_INTERVAL

    if now < session["next_reload"]:
        return

    try:
        await asyncio.wait_for(tab.reload(), timeout=25)
        session["reload_count"] += 1
        log.info("[%s] Reload #%s OK", account_name, session["reload_count"])
    except Exception as e:
        log.warning("[%s] Reload loi: %s", account_name, e)
        recovered_tab = await ensure_firebase_tab(browser, account)
        if recovered_tab:
            tab = recovered_tab
            session["tab"] = recovered_tab
            log.info("[%s] Khoi phuc tab Firebase thanh cong sau loi reload", account_name)
        else:
            log.error("[%s] Khong khoi phuc duoc tab sau loi reload", account_name)

    session["next_reload"] = now + RELOAD_INTERVAL


async def main():
    mode = "login-tuan-tu + keepalive-song-hanh"
    log.info(
        "Cau hinh: mode=%s, reload_interval=%ss, login_stagger=%ss, screenshot=%s, memory_saver=%s, telegram=%s",
        mode,
        RELOAD_INTERVAL,
        LOGIN_STAGGER_SECONDS,
        ENABLE_SCREENSHOT,
        MEMORY_SAVER,
        is_telegram_enabled(),
    )
    if (TELEGRAM_SEND_SCREENSHOT or TELEGRAM_SEND_LOGIN_SCREENSHOT) and not is_telegram_enabled():
        log.warning(
            "TELEGRAM_SEND_SCREENSHOT/TELEGRAM_SEND_LOGIN_SCREENSHOT bat nhung thieu TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID"
        )
    if TELEGRAM_SEND_EVENTS and is_telegram_enabled():
        await send_telegram_message(
            f"Runner bat dau | mode={mode} | reload={RELOAD_INTERVAL}s | stagger={LOGIN_STAGGER_SECONDS}s"
        )

    sessions = []
    try:
        for idx, account in enumerate(ACCOUNTS):
            if not global_running:
                break
            session = await init_account_session(account)
            if session:
                sessions.append(session)
            else:
                log.error("[%s] Khoi tao session that bai", account["name"])

            if idx < len(ACCOUNTS) - 1 and global_running:
                log.info("Cho %ss truoc khi mo %s", LOGIN_STAGGER_SECONDS, ACCOUNTS[idx + 1]["name"])
                await asyncio.sleep(LOGIN_STAGGER_SECONDS)

        if not sessions:
            log.error("Khong co session nao khoi tao thanh cong. Dung chuong trinh.")
            return

        log.info("Da khoi tao %s/%s session, bat dau vong keep-alive", len(sessions), len(ACCOUNTS))
        while global_running:
            for session in sessions:
                if not global_running:
                    break
                await keepalive_tick(session)
            await asyncio.sleep(1)
    finally:
        for session in sessions:
            browser = session.get("browser")
            account_name = session.get("account_name", "unknown")
            if not browser:
                continue
            try:
                browser.stop()
                log.info("[%s] Browser da dong", account_name)
            except Exception:
                pass

    log.info("Da dung toan bo chuong trinh.")


if __name__ == "__main__":
    asyncio.run(main())
