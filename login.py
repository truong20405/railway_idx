import nodriver as uc
import asyncio
import random
import os
import json
import logging
import signal
import subprocess
import gc
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler("keepalive.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
        logging.StreamHandler(),  # In ra terminal luôn
    ],
)
log = logging.getLogger(__name__)

# ==================== CẤU HÌNH 2 ACCOUNT ====================
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
ACCOUNTS = [
    {
        "name": "profile_1",
        "email": os.getenv("GOOGLE_EMAIL_1", "phu413271@gmail.com"),
        "password": os.getenv("GOOGLE_PASSWORD_1", "nvt2005S!"),
        "recovery": os.getenv("RECOVERY_EMAIL_1", "mail2@hunght1890.com"),
        "proxy": os.getenv("PROXY_1", "http://45.137.70.90:2433"),
        "use_proxy_after_login": True,   # Sau login vẫn dùng proxy
        "firebase_url": "https://studio.firebase.google.com/windows-idx-97840365",
    },
    {
        "name": "profile_2",
        "email": os.getenv("GOOGLE_EMAIL_2", "vanlong1999u@gmail.com"),
        "password": os.getenv("GOOGLE_PASSWORD_2", "truongnguyen"),
        "recovery": os.getenv("RECOVERY_EMAIL_2", "mail3@hunght1890.com"),
        "proxy": os.getenv("PROXY_2", "http://45.137.70.90:2433"),
        "use_proxy_after_login": False,  # Sau login không dùng proxy
        "firebase_url": "https://studio.firebase.google.com/idxvpsgit-74148240",
    },
]

RELOAD_INTERVAL          = 300    # 5 phút
SCREENSHOT_INTERVAL      = 5     # 5 giây
MAX_RELOAD_ERRORS        = 5
NETWORK_TIMEOUT          = 30
MAX_RETRIES              = 3
BROWSER_RESTART_INTERVAL = 3600   # 1 tiếng
FORCE_KILL_STALE_BROWSER = os.getenv("FORCE_KILL_STALE_BROWSER", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Tạo thư mục profile riêng cho mỗi account
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for acc in ACCOUNTS:
    profile_dir = os.path.join(BASE_DIR, f"chrome_{acc['name']}")
    os.makedirs(profile_dir, exist_ok=True)

# ==================== SHARED STATE PER PROFILE ====================
class ProfileState:
    """Trạng thái riêng cho mỗi profile"""
    def __init__(self, name: str):
        self.name = name
        self.current_tab = None
        self.screenshot_task = None
        self.running = True
        self.reload_error_count = 0
        self.session_start = time.time()
        self.profile_dir = os.path.join(BASE_DIR, f"chrome_{name}")
        self.login_flag = os.path.join(self.profile_dir, "login_done.flag")
        self.firebase_url = ""  # Sẽ được gán từ account config

# Flag toàn cục để dừng tất cả
global_running = True

# ==================== SIGNAL HANDLER ====================
def handle_shutdown(sig, frame):
    del sig, frame
    global global_running
    log.info("Nhận tín hiệu dừng, đang tắt...")
    global_running = False

signal.signal(signal.SIGINT,  handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# ==================== HELPERS ====================
def is_logged_in(pstate: ProfileState) -> bool:
    return os.path.exists(pstate.login_flag)

def mark_logged_in(pstate: ProfileState):
    with open(pstate.login_flag, "w") as f:
        f.write(datetime.now().isoformat())
    log.info(f"[{pstate.name}] [✓] Profile đã lưu: {pstate.profile_dir}")

def clear_stale_profile_locks(profile_dir: str, profile_name: str):
    removed = []
    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
        lock_path = os.path.join(profile_dir, lock_name)
        if not os.path.exists(lock_path):
            continue
        try:
            os.remove(lock_path)
            removed.append(lock_name)
        except Exception as e:
            log.info(f"[{profile_name}] [-] Khong xoa duoc lock file {lock_name}: {e}")
    if removed:
        log.info(f"[{profile_name}] [~] Da don lock profile cu: {', '.join(removed)}")


def _kill_profile_browser_processes_posix(profile_dir: str) -> int:
    try:
        marker = os.path.abspath(profile_dir).lower()
        proc = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return 0
    except Exception:
        return 0

    pids = []
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        pid_text, cmdline = parts
        cmdline_lower = cmdline.lower()
        if "--user-data-dir" not in cmdline_lower:
            continue
        if marker not in cmdline_lower:
            continue
        if not any(name in cmdline_lower for name in ("chrome", "chromium", "msedge")):
            continue
        if pid_text.isdigit():
            pids.append(int(pid_text))

    killed = 0
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
            killed += 1
        except Exception:
            continue
    return killed


def _kill_profile_browser_processes_windows(profile_dir: str) -> int:
    script = r"""
$profile = $env:IDX_PROFILE_DIR
if (-not $profile) { Write-Output 0; exit 0 }
$profile = $profile.ToLowerInvariant()
$killed = 0
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.Name -match '^(chrome|chromium|msedge)(\.exe)?$'
} | ForEach-Object {
    $cmd = $_.CommandLine.ToLowerInvariant()
    if ($cmd.Contains('--user-data-dir') -and $cmd.Contains($profile)) {
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
            $killed += 1
        } catch {}
    }
}
Write-Output $killed
"""
    env = os.environ.copy()
    env["IDX_PROFILE_DIR"] = os.path.abspath(profile_dir).lower()
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        for line in reversed(proc.stdout.splitlines()):
            value = line.strip()
            if value.isdigit():
                return int(value)
    except Exception:
        return 0
    return 0


def force_kill_profile_browser(profile_dir: str, profile_name: str, reason: str) -> int:
    if not FORCE_KILL_STALE_BROWSER:
        return 0
    if os.name == "nt":
        killed = _kill_profile_browser_processes_windows(profile_dir)
    else:
        killed = _kill_profile_browser_processes_posix(profile_dir)
    if killed > 0:
        log.info(f"[{profile_name}] [~] Force-kill {killed} process browser cu ({reason})")
    return killed


def stop_browser_safely(browser, pstate: ProfileState):
    try:
        if browser:
            browser.stop()
    except Exception as e:
        log.info(f"[{pstate.name}] [-] Loi khi stop browser: {e}")
    finally:
        force_kill_profile_browser(pstate.profile_dir, pstate.name, "sau browser.stop()")
        clear_stale_profile_locks(pstate.profile_dir, pstate.name)


async def wait_for_element(tab, selector: str, timeout: int = 15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            el = await tab.find(selector, timeout=0.5)
            if el:
                return el
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return None

async def human_type(element, text: str):
    for char in text:
        await element.send_keys(char)
        await asyncio.sleep(random.uniform(0.04, 0.12))

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

async def safe_navigate(browser, url: str, pstate: ProfileState, retries: int = 3):
    """Điều hướng với timeout và retry"""
    for attempt in range(1, retries + 1):
        try:
            tab = await asyncio.wait_for(browser.get(url), timeout=NETWORK_TIMEOUT)
            return tab
        except asyncio.TimeoutError:
            log.warning(f"[{pstate.name}] Timeout navigate lần {attempt}/{retries}: {url}")
        except Exception as e:
            log.warning(f"[{pstate.name}] Lỗi navigate lần {attempt}/{retries}: {e}")
        await asyncio.sleep(5 * attempt)
    return None

# ==================== SCREENSHOT (mỗi profile riêng) ====================
async def continuous_screenshot(pstate: ProfileState):
    """Chụp ảnh từ pstate.current_tab mỗi 5s, lưu tên riêng"""
    path = os.path.join(SCREENSHOT_DIR, f"{pstate.name}.png")
    while pstate.running and global_running:
        try:
            tab = pstate.current_tab
            if tab is not None:
                await tab.save_screenshot(path)
        except Exception:
            pass  # Tab có thể đang reload, bỏ qua
        await asyncio.sleep(SCREENSHOT_INTERVAL)

def restart_screenshot_task(pstate: ProfileState):
    """Hủy task cũ và tạo task mới"""
    if pstate.screenshot_task and not pstate.screenshot_task.done():
        pstate.screenshot_task.cancel()
    pstate.screenshot_task = asyncio.create_task(continuous_screenshot(pstate))

# ==================== RECOVERY EMAIL ====================
async def handle_recovery(tab, pstate: ProfileState, recovery_email: str) -> bool:
    log.info(f"[{pstate.name}] [*] Xử lý xác minh email khôi phục...")
    try:
        recovery_option = None

        for selector in ["div[jsname='fmcmS']", "div.l5PPKe", "li[data-challengetype]"]:
            try:
                elements = await tab.find_all(selector, timeout=2)
                for el in elements:
                    el_text = str(getattr(el, "text", "") or getattr(el, "text_all", "") or "")
                    if "recovery" in el_text.lower() or "khôi phục" in el_text.lower():
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
            log.info(f"[{pstate.name}] [-] Không tìm thấy recovery option")
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
            log.info(f"[{pstate.name}] [-] Không tìm thấy ô nhập recovery email")
            return False

        await recovery_input.click()
        await asyncio.sleep(0.3)
        await human_type(recovery_input, recovery_email)
        await asyncio.sleep(0.5)
        await click_next(tab)
        log.info(f"[{pstate.name}] [✓] Đã điền recovery: {recovery_email}")
        return True

    except Exception as e:
        log.info(f"[{pstate.name}] [-] Lỗi recovery: {e}")
        return False

# ==================== KEEP-ALIVE PER PROFILE ====================
async def keep_alive(browser, pstate: ProfileState):
    """
    Reload định kỳ mỗi 5 phút, tự recover khi lỗi.
    Sau BROWSER_RESTART_INTERVAL (1 tiếng) trả về 'restart'
    """
    reload_count       = 0
    consecutive_errors = 0
    browser_start_time = time.time()

    while pstate.running and global_running:
        if time.time() - browser_start_time >= BROWSER_RESTART_INTERVAL:
            elapsed_min = int((time.time() - browser_start_time) / 60)
            log.info(
                f"[{pstate.name}] ⏰ Đã chạy {elapsed_min} phút — Tắt Chrome, dọn RAM, khởi động lại..."
            )
            return "restart"

        sleep_remaining = RELOAD_INTERVAL
        while sleep_remaining > 0 and pstate.running and global_running:
            chunk = min(sleep_remaining, 10)
            await asyncio.sleep(chunk)
            sleep_remaining -= chunk
            if time.time() - browser_start_time >= BROWSER_RESTART_INTERVAL:
                break

        if not pstate.running or not global_running:
            break

        reload_count += 1
        uptime_min = int((time.time() - pstate.session_start) / 60)

        try:
            tab = pstate.current_tab
            if tab is None:
                raise RuntimeError("Tab is None")

            await asyncio.wait_for(tab.reload(), timeout=20)
            consecutive_errors = 0
            pstate.reload_error_count = 0

            time_to_restart = int((BROWSER_RESTART_INTERVAL - (time.time() - browser_start_time)) / 60)
            log.info(
                f"[{pstate.name}] [✓] Reload #{reload_count} OK | Uptime: {uptime_min} phút "
                f"| Restart browser sau: ~{time_to_restart} phút"
            )

            if reload_count % 10 == 0:
                gc.collect()
                log.info(f"[{pstate.name}] [~] GC chạy xong | Reload tổng: {reload_count}")

        except Exception as e:
            consecutive_errors += 1
            pstate.reload_error_count += 1
            log.info(
                f"[{pstate.name}] [-] Reload lỗi lần {consecutive_errors}/{MAX_RELOAD_ERRORS}: {e}"
            )

            if consecutive_errors >= MAX_RELOAD_ERRORS:
                log.info(
                    f"[{pstate.name}] ⚠️ Quá nhiều lỗi reload! Đang mở lại tab Firebase..."
                )
                new_tab = await safe_navigate(browser, pstate.firebase_url, pstate)
                if new_tab:
                    pstate.current_tab = new_tab
                    consecutive_errors = 0
                    log.info(f"[{pstate.name}] [✓] Tab mới OK, tiếp tục keep-alive")
                else:
                    log.info(f"[{pstate.name}] ❌ Không thể mở tab mới! Dừng profile.")
                    pstate.running = False
                    break

# ==================== ĐĂNG NHẬP PER PROFILE ====================
async def do_login(browser, pstate: ProfileState, account: dict) -> bool:
    """Thực hiện đăng nhập Gmail cho 1 profile"""
    GMAIL_LOGIN_URL = (
        "https://accounts.google.com/v3/signin/identifier"
        "?continue=https%3A%2F%2Fmail.google.com%2Fmail%2F"
        "&service=mail&flowName=GlifWebSignIn&flowEntry=ServiceLogin"
    )

    tab = await safe_navigate(browser, GMAIL_LOGIN_URL, pstate)
    if not tab:
        log.info(f"[{pstate.name}] ❌ Không thể mở trang đăng nhập")
        return False

    pstate.current_tab = tab
    restart_screenshot_task(pstate)

    # Bước 1: Email
    log.info(f"[{pstate.name}] [1] Nhập Email: {account['email']}...")
    email_inp = await wait_for_element(tab, "input[type='email']")
    if not email_inp:
        log.info(f"[{pstate.name}] [-] Không tìm thấy ô email")
        return False
    await email_inp.click()
    await human_type(email_inp, account["email"])
    await click_next(tab)
    await asyncio.sleep(4)

    # Bước 2: Password
    log.info(f"[{pstate.name}] [2] Nhập Mật khẩu...")
    pw_inp = await wait_for_element(tab, "input[type='password']", timeout=10)
    if not pw_inp:
        log.info(f"[{pstate.name}] [!] Không thấy ô mật khẩu")
    else:
        await pw_inp.click()
        await human_type(pw_inp, account["password"])
        await click_next(tab)
        await asyncio.sleep(5)

    # Bước 3: Kiểm tra kết quả
    for i in range(20):
        url = tab.target.url

        if "mail.google.com" in url or "myaccount.google.com" in url:
            log.info(f"[{pstate.name}] ✅ ĐĂNG NHẬP THÀNH CÔNG!")
            mark_logged_in(pstate)
            return True

        try:
            content_lower = (await tab.get_content()).lower()
        except Exception:
            content_lower = ""

        if "recovery" in content_lower or "khôi phục" in content_lower:
            await handle_recovery(tab, pstate, account["recovery"])
            await asyncio.sleep(5)
            continue

        if "denied" in content_lower or "blocked" in content_lower:
            log.info(f"[{pstate.name}] ❌ Tài khoản bị chặn!")
            return False

        log.info(f"[{pstate.name}] [#] Chờ... lần {i+1}/20 | {url[:50]}")
        await asyncio.sleep(3)

    log.info(f"[{pstate.name}] [-] Hết thời gian chờ đăng nhập")
    return False

# ==================== MAIN LOOP PER PROFILE ====================
async def run_profile(account: dict):
    """Vòng lặp chính cho 1 profile, chạy độc lập"""
    pstate = ProfileState(account["name"])
    pstate.firebase_url = account["firebase_url"]
    attempt = 0

    while pstate.running and global_running:
        attempt += 1
        log.info(
            f"[{pstate.name}] {'='*40}\n"
            f"  Lần khởi động #{attempt}\n"
            f"  Email: {account['email']}\n"
            f"  Proxy: {account['proxy'] or 'Không dùng'}\n"
            f"  Logged in: {is_logged_in(pstate)}\n"
            f"{'='*40}"
        )

        browser = None
        try:
            force_kill_profile_browser(pstate.profile_dir, pstate.name, "truoc khi start browser")
            clear_stale_profile_locks(pstate.profile_dir, pstate.name)

            # Cấu hình Chrome
            browser_args = [
                f"--user-agent={USER_AGENT}",
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--window-size=1280,720",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--memory-pressure-off",
                "--js-flags=--max-old-space-size=256",
            ]

            # Quyết định dùng proxy hay không
            if not is_logged_in(pstate):
                # Chưa login → dùng proxy nếu có
                if account["proxy"]:
                    browser_args.insert(0, f"--proxy-server={account['proxy']}")
            else:
                # Đã login → chỉ dùng proxy nếu use_proxy_after_login=True
                if account["use_proxy_after_login"] and account["proxy"]:
                    browser_args.insert(0, f"--proxy-server={account['proxy']}")

            config = uc.Config(
                user_data_dir=pstate.profile_dir,
                browser_args=browser_args,
                lang="en-US",
            )

            browser = await uc.start(config=config)

            # Đăng nhập nếu chưa có profile
            if not is_logged_in(pstate):
                success = await do_login(browser, pstate, account)
                if not success:
                    log.info(f"[{pstate.name}] [-] Đăng nhập thất bại, thử lại sau 60s...")
                    await asyncio.sleep(60)
                    continue

            # Vào Firebase
            log.info(f"[{pstate.name}] [*] Mở Firebase: {pstate.firebase_url}")
            tab = await safe_navigate(browser, pstate.firebase_url, pstate, retries=MAX_RETRIES)
            if not tab:
                log.info(f"[{pstate.name}] ❌ Không mở được Firebase, restart...")
                await asyncio.sleep(30)
                continue

            pstate.current_tab = tab
            pstate.session_start = time.time()
            restart_screenshot_task(pstate)

            log.info(f"[{pstate.name}] [✓] Firebase Studio sẵn sàng! Bắt đầu keep-alive...")

            result = await keep_alive(browser, pstate)
            if result == "restart":
                attempt = 0
                continue

        except Exception as e:
            log.info(f"[{pstate.name}] ❌ Crash ngoài dự kiến: {e}")
            log.exception(f"[{pstate.name}] Crash chi tiết:")

        finally:
            if pstate.screenshot_task and not pstate.screenshot_task.done():
                pstate.screenshot_task.cancel()
                try:
                    await pstate.screenshot_task
                except asyncio.CancelledError:
                    pass

            stop_browser_safely(browser, pstate)

            pstate.current_tab = None
            gc.collect()

            if pstate.running and global_running:
                wait = min(30 * attempt, 300)
                log.info(f"[{pstate.name}] [~] Restart sau {wait}s...")
                await asyncio.sleep(wait)

# ==================== ENTRY POINT ====================
async def run():
    """Chạy tất cả profile song song"""
    log.info(f"Bot Firebase Keep-Alive 24/7 khởi động — {len(ACCOUNTS)} profile")
    tasks = [run_profile(account) for account in ACCOUNTS]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(run())
