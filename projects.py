"""
Per-scrape project persistence.
Each project lives under  ./projects/<id>/
  project.json  – metadata + settings snapshot
  scrape.log    – timestamped log (appended each run)
  visited.txt   – URLs already crawled (enables resume)
"""
import json, os, shutil, uuid
from datetime import datetime
from urllib.parse import urlparse

_HERE    = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(_HERE, "projects")


# ── path helpers ──────────────────────────────────────────────────────────────

def _pdir(pid):           return os.path.join(PROJ_DIR, pid)
def _pfile(pid):          return os.path.join(_pdir(pid), "project.json")
def log_path(pid):        return os.path.join(_pdir(pid), "scrape.log")
def _visited_path(pid):      return os.path.join(_pdir(pid), "visited.txt")
def _media_queue_path(pid):  return os.path.join(_pdir(pid), "media_queue.txt")
def _now():               return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _domain(url):         return urlparse(url).netloc or url[:40]


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create(url: str, output_folder: str, settings: dict,
           name: str = "", username: str = "", login_url: str = "") -> dict:
    os.makedirs(PROJ_DIR, exist_ok=True)
    pid  = uuid.uuid4().hex[:10]
    os.makedirs(_pdir(pid), exist_ok=True)
    p = {
        "id":            pid,
        "name":          name or _domain(url),
        "url":           url,
        "output_folder": output_folder,
        "login_url":     login_url,
        "username":      username,
        "status":        "active",
        "created_at":    _now(),
        "last_run":      None,
        "pages": 0, "files": 0, "bytes": 0, "errors": 0,
        "images": 0, "videos": 0, "audio": 0,
        "pdfs": 0, "documents": 0, "css_js": 0,
        "settings":      settings,
    }
    _write(p)
    return p


def load_all() -> list:
    os.makedirs(PROJ_DIR, exist_ok=True)
    out = []
    for entry in sorted(os.listdir(PROJ_DIR)):
        f = _pfile(entry)
        if os.path.isfile(f):
            try:
                with open(f, encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except Exception:
                pass
    return out


def load(pid: str) -> dict | None:
    f = _pfile(pid)
    if os.path.isfile(f):
        with open(f, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def save(p: dict):
    _write(p)


def archive(pid: str):
    p = load(pid)
    if p:
        p["status"] = "archived"
        _write(p)


def restore(pid: str):
    p = load(pid)
    if p:
        p["status"] = "active"
        _write(p)


def delete(pid: str):
    d = _pdir(pid)
    if os.path.isdir(d):
        shutil.rmtree(d)


# ── stats ─────────────────────────────────────────────────────────────────────

def add_stats(pid: str, pages=0, files=0, bytes_dl=0, errors=0):
    p = load(pid)
    if p:
        p["pages"]  += pages
        p["files"]  += files
        p["bytes"]  += bytes_dl
        p["errors"] += errors
        p["last_run"] = _now()
        _write(p)


def reset_stats(pid: str):
    p = load(pid)
    if p:
        for k in ("pages", "files", "bytes", "errors",
                  "images", "videos", "audio", "pdfs", "documents", "css_js"):
            p[k] = 0
        _write(p)


# ── visited URLs (resume support) ─────────────────────────────────────────────

def save_visited(pid: str, urls: set):
    path = _visited_path(pid)
    os.makedirs(_pdir(pid), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(urls)))


def load_visited(pid: str) -> set:
    path = _visited_path(pid)
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}


def save_media_queue(pid: str, urls: set):
    os.makedirs(_pdir(pid), exist_ok=True)
    with open(_media_queue_path(pid), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(urls)))


def load_media_queue(pid: str) -> set:
    path = _media_queue_path(pid)
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}


def clear_media_queue(pid: str):
    path = _media_queue_path(pid)
    if os.path.isfile(path):
        os.remove(path)


# ── folder management ─────────────────────────────────────────────────────────

def move_output(pid: str, new_folder: str) -> tuple:
    p = load(pid)
    if not p:
        return False, "Project not found."
    old = p["output_folder"]
    try:
        if os.path.isdir(old):
            shutil.move(old, new_folder)
        p["output_folder"] = new_folder
        _write(p)
        return True, f"Moved to: {new_folder}"
    except Exception as e:
        return False, str(e)


# ── internal ──────────────────────────────────────────────────────────────────

def _write(p: dict):
    os.makedirs(_pdir(p["id"]), exist_ok=True)
    with open(_pfile(p["id"]), "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2)
