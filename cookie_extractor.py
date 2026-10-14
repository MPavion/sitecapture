import json
import os
import time


def extract_from_browser(browser_name: str, domain: str | None = None):
    """Return (cookie_list, message). cookie_list is None on failure."""
    try:
        import browser_cookie3 as bc
    except ImportError:
        return None, "browser-cookie3 not installed — run setup.bat first."

    fn_map = {
        "chrome":   getattr(bc, "chrome",   None),
        "firefox":  getattr(bc, "firefox",  None),
        "edge":     getattr(bc, "edge",     None),
        "brave":    getattr(bc, "brave",    None),
        "opera":    getattr(bc, "opera",    None),
    }
    fn = fn_map.get(browser_name.lower())
    if fn is None:
        return None, f"Unsupported browser: {browser_name}"

    try:
        kwargs = {"domain_name": domain} if domain else {}
        cookies = list(fn(**kwargs))
        return cookies, f"Extracted {len(cookies)} cookies from {browser_name.title()}"
    except PermissionError:
        return None, (
            f"Permission denied reading {browser_name.title()} cookies. "
            "Close the browser completely and try again."
        )
    except Exception as e:
        return None, f"Extraction failed: {e}"


def save_netscape(cookies, filepath: str):
    """Write cookies as Netscape format so yt-dlp can use them."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n\n")
        for c in cookies:
            domain = getattr(c, "domain", "") or ""
            include_sub = "TRUE" if domain.startswith(".") else "FALSE"
            path = getattr(c, "path", "/") or "/"
            secure = "TRUE" if getattr(c, "secure", False) else "FALSE"
            expires = int(getattr(c, "expires", 0) or 0)
            name = c.name or ""
            value = c.value or ""
            f.write(f"{domain}\t{include_sub}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")


def to_requests_dict(cookies) -> dict:
    return {c.name: c.value for c in cookies if c.name}


def json_to_netscape(json_path: str) -> tuple[str, str]:
    """
    Convert a JSON cookies file to Netscape format.
    Accepts arrays produced by EditThisCookie, Cookie-Editor, DevTools,
    or any tool that exports [{name, value, domain, path, ...}, ...].
    Returns (netscape_path, message).  Raises on unrecognised format.
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of cookie objects.")

    out_path = os.path.splitext(json_path)[0] + "_converted.txt"
    far_future = int(time.time()) + 60 * 60 * 24 * 365 * 10  # 10 years

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n\n")
        for c in data:
            if not isinstance(c, dict):
                continue
            name   = str(c.get("name") or c.get("key") or "")
            value  = str(c.get("value") or "")
            domain = str(c.get("domain") or "")
            if domain and not domain.startswith(".") and not domain.startswith("http"):
                domain = "." + domain
            path   = str(c.get("path") or "/")
            secure = "TRUE" if c.get("secure") else "FALSE"
            flag   = "TRUE" if domain.startswith(".") else "FALSE"
            # expires / expirationDate may be a float Unix timestamp or absent
            raw_exp = c.get("expires") or c.get("expirationDate") or c.get("expiry")
            try:
                expires = int(float(raw_exp)) if raw_exp is not None else far_future
            except (ValueError, TypeError):
                expires = far_future
            if expires <= 0:
                expires = far_future
            f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")

    return out_path, f"Converted {len(data)} cookies → {os.path.basename(out_path)}"


def save_netscape_from_jar(jar, filepath: str):
    """Save a requests.cookies.RequestsCookieJar as a Netscape cookies file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n\n")
        for c in jar:
            domain      = c.domain or ""
            include_sub = "TRUE" if domain.startswith(".") else "FALSE"
            path        = c.path or "/"
            secure      = "TRUE" if c.secure else "FALSE"
            expires     = int(c.expires or 0)
            f.write(
                f"{domain}\t{include_sub}\t{path}\t{secure}\t{expires}"
                f"\t{c.name}\t{c.value}\n"
            )
