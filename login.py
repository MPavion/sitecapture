"""
Detects the login form on a site, submits credentials, and returns
the resulting session with its cookies set.
"""

import requests
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False


_COMMON_LOGIN_PATHS = [
    "/login", "/signin", "/sign-in", "/log-in",
    "/account/login", "/user/login", "/users/sign_in",
    "/auth/login", "/members/login", "/portal/login",
    "/student/login", "/wp-login.php", "/login.php",
]

_USER_FIELD_HINTS  = ["email", "username", "user", "login",
                      "user_email", "user_login", "identifier", "name"]
_ERROR_PHRASES     = [
    "invalid password", "incorrect password", "wrong password",
    "login failed", "sign in failed", "authentication failed",
    "invalid credentials", "invalid email", "user not found",
    "account not found", "invalid username", "email or password",
]


# ── public API ────────────────────────────────────────────────────────────────

def find_login_url(base_url: str, session: requests.Session) -> str | None:
    """
    Try to locate the login page.
    First scans links on the page, then probes common paths.
    Returns None if nothing is found.
    """
    if not BS4_OK:
        return None

    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    try:
        resp = session.get(base_url, timeout=12)
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup.find_all("a", href=True):
            href = tag["href"].lower()
            if any(kw in href for kw in ("login", "signin", "sign-in", "log-in")):
                return urljoin(base_url, tag["href"])
    except Exception:
        pass

    for path in _COMMON_LOGIN_PATHS:
        url = origin + path
        try:
            r = session.head(url, timeout=5, allow_redirects=True)
            if r.status_code == 200:
                return url
        except Exception:
            pass

    return None


def attempt_login(
    login_url: str,
    username: str,
    password: str,
    session: requests.Session,
) -> tuple[bool, str]:
    """
    Fetch the login page, identify the form, inject credentials,
    and submit. Returns (success, human-readable message).
    """
    if not BS4_OK:
        return False, "BeautifulSoup not installed — run setup.bat."

    # ── fetch login page ──────────────────────────────────────────────────────
    try:
        resp = session.get(login_url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return False, f"Could not load the login page: {e}"

    soup = BeautifulSoup(resp.text, "lxml")
    form = _find_password_form(soup)
    if form is None:
        return False, (
            "No login form with a password field was found on this page. "
            "The site may use JavaScript-only login — try supplying a cookies file instead."
        )

    action = urljoin(login_url, form.get("action") or login_url)
    method = form.get("method", "post").lower()

    # ── build form payload ────────────────────────────────────────────────────
    data: dict[str, str] = {}
    for inp in form.find_all("input"):
        itype = (inp.get("type") or "text").lower()
        name  = inp.get("name", "")
        if name and itype not in ("submit", "button", "image", "reset"):
            data[name] = inp.get("value") or ""

    # Locate username and password fields
    user_field = _field_by_hints(form, _USER_FIELD_HINTS, skip_type="password")
    pass_field = _field_by_type(form, "password")

    if not user_field:
        return False, (
            "Could not identify the username/email field. "
            "Try entering the login URL manually, or use a cookies file instead."
        )
    if not pass_field:
        return False, "Could not identify the password field in the login form."

    data[user_field] = username
    data[pass_field] = password

    # ── submit ────────────────────────────────────────────────────────────────
    try:
        if method == "post":
            resp2 = session.post(action, data=data, timeout=20, allow_redirects=True)
        else:
            resp2 = session.get(action, params=data, timeout=20, allow_redirects=True)
    except Exception as e:
        return False, f"Form submission failed: {e}"

    return _check_success(resp2, login_url)


# ── helpers ───────────────────────────────────────────────────────────────────

def _find_password_form(soup):
    for form in soup.find_all("form"):
        if form.find("input", {"type": "password"}):
            return form
    return None


def _field_by_hints(form, hints: list[str], skip_type: str = "") -> str | None:
    for inp in form.find_all("input"):
        if (inp.get("type") or "").lower() == skip_type:
            continue
        name = (inp.get("name") or "").lower()
        id_  = (inp.get("id")   or "").lower()
        if any(h in name or h in id_ for h in hints):
            return inp.get("name")
    return None


def _field_by_type(form, itype: str) -> str | None:
    inp = form.find("input", {"type": itype})
    return inp.get("name") if inp else None


def _check_success(resp, login_url: str) -> tuple[bool, str]:
    text_lower = resp.text.lower()

    for phrase in _ERROR_PHRASES:
        if phrase in text_lower:
            return False, f"Login rejected — site reported: \"{phrase}\"."

    if resp.url and urlparse(resp.url).path != urlparse(login_url).path:
        return True, f"Logged in successfully (redirected to {resp.url})."

    if resp.cookies:
        return True, "Login appears successful (session cookies received)."

    return False, (
        "Login status unclear — page did not redirect and no session cookies were set. "
        "The site may require JavaScript-based login. Use a cookies file as a fallback."
    )
