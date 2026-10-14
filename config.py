import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_HERE, "config.json")

DEFAULTS = {
    "output_folder": os.path.join(os.path.expanduser("~"), "Downloads", "scraped_sites"),
    "browser": "chrome",
    "max_depth": 3,
    "concurrent_downloads": 3,
    "delay_between_requests": 0.5,
    "download_html": True,
    "download_images": True,
    "download_videos": True,
    "download_audio": True,
    "download_documents": True,
    "download_css_js": True,
    "stay_on_domain": True,
    "cookies_file": "",
    "last_url": "",
    "username": "",
    "login_url": "",
    "anthropic_api_key": "",
    "ai_model": "claude-sonnet-4-6",
    "url_include_patterns": [],
    "url_exclude_patterns": [],
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def load():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = DEFAULTS.copy()
            merged.update(saved)
            return merged
        except Exception:
            pass
    return DEFAULTS.copy()


def save(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Config save failed: {e}")
