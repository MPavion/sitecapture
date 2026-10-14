import os
import re
import time
import queue
import threading
from urllib.parse import urljoin, urlparse

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False

try:
    import yt_dlp
    YTDLP_OK = True
except ImportError:
    YTDLP_OK = False


class _YtdlpSilent:
    """Discard all yt-dlp console output — quiet/no_warnings don't suppress errors."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


VIDEO_EXTS  = {".mp4", ".webm", ".avi", ".mkv", ".mov", ".flv", ".wmv", ".m4v", ".3gp", ".ogv", ".ts"}
AUDIO_EXTS  = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma", ".opus", ".mid", ".ra"}
IMAGE_EXTS  = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tiff", ".avif"}
DOC_EXTS    = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
               ".zip", ".rar", ".7z", ".tar", ".gz", ".epub", ".mobi", ".csv"}
CSSJS_EXTS  = {".css", ".js", ".json", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".map"}

_LOGOUT_PATTERNS = {
    "/logout", "/log-out", "/signout", "/sign-out",
    "/logoff", "/log-off", "/sign_out", "/deauth",
    "/session/destroy", "/users/sign_out", "/auth/logout",
    "action=logout", "action=signout", "action=log-out",
}

EMBED_DOMAINS = {
    "youtube.com", "youtu.be", "vimeo.com", "dailymotion.com",
    "twitch.tv", "soundcloud.com", "bandcamp.com", "mixcloud.com",
    "facebook.com", "instagram.com", "tiktok.com", "rumble.com",
    # course / professional video platforms
    "wistia.com", "fast.wistia.com", "wistia.net",
    "mediadelivery.net", "bunnycdn.com", "stream.bunnycdn.com",
    "jwplatform.com", "jwplayer.com", "cdn.jwplayer.com",
    "brightcove.com", "brightcove.net",
    "kaltura.com", "cdnapisec.kaltura.com",
    "vidyard.com", "play.vidyard.com",
    "loom.com", "cdn.loom.com",
    "vzaar.com",
}

# Patterns in raw HTML that indicate a video platform even when the player
# is loaded via JavaScript (no <iframe>/<video> tag in initial HTML).
_VIDEO_PLATFORM_HINTS = {
    "player.vimeo.com", "vimeo.com/video",
    "wistia.com", "wistia_async", "wistia_embed",
    "fast.wistia",
    "mediadelivery.net", "bunnycdn",
    "jwplatform", "jwplayer",
    "brightcove",
    "kaltura",
    "vidyard",
    "loom.com/embed",
    "vzaar",
}

# (regex, url_builder) pairs — extract video URLs from raw HTML even when
# the player is injected by JavaScript or embedded in JSON component props.
_EMBEDDED_VIDEO_PATTERNS: list[tuple] = [
    # Wistia  (JSON props: "wistia.com/medias/HASH" or wistia_async_HASH)
    (re.compile(r'wistia\.com/medias/([a-zA-Z0-9]+)', re.I),
     lambda m: f'https://fast.wistia.com/embed/medias/{m.group(1)}'),
    (re.compile(r'wistia_async_([a-zA-Z0-9]+)', re.I),
     lambda m: f'https://fast.wistia.com/embed/medias/{m.group(1)}'),
    # Vimeo  (iframe src or JSON "vimeoId"/"video_id")
    (re.compile(r'player\.vimeo\.com/video/(\d+)', re.I),
     lambda m: f'https://player.vimeo.com/video/{m.group(1)}'),
    (re.compile(r'"vimeo(?:Id|_id|VideoId)"\s*:\s*["\[]?0?,?\s*"?(\d+)"?', re.I),
     lambda m: f'https://vimeo.com/{m.group(1)}'),
    # YouTube  (iframe embed or JSON "youtubeId")
    (re.compile(r'youtube\.com/embed/([a-zA-Z0-9_-]{11})', re.I),
     lambda m: f'https://www.youtube.com/watch?v={m.group(1)}'),
    (re.compile(r'"youtube(?:Id|_id|VideoId)"\s*:\s*"([a-zA-Z0-9_-]{11})"', re.I),
     lambda m: f'https://www.youtube.com/watch?v={m.group(1)}'),
    # Bunny Stream  (iframe src mediadelivery.net/embed/LIBRARY/ID)
    (re.compile(r'mediadelivery\.net/embed/\d+/([a-zA-Z0-9-]+)', re.I),
     lambda m: f'https://iframe.mediadelivery.net/play/{m.group(0).split("/embed/")[1]}'),
]


def _extract_embedded_videos(html: str) -> list[str]:
    """Return deduplicated list of direct video platform URLs found in raw HTML."""
    seen: set[str] = set()
    urls: list[str] = []
    for pattern, builder in _EMBEDDED_VIDEO_PATTERNS:
        for m in pattern.finditer(html):
            url = builder(m)
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _url_ext(url: str) -> str:
    return os.path.splitext(urlparse(url).path)[1].lower()


def _url_to_path(url: str, base_dir: str) -> str:
    p = urlparse(url)
    domain = p.netloc
    parts = [part for part in p.path.split("/") if part]
    if not parts:
        parts = ["index.html"]
    elif not os.path.splitext(parts[-1])[1]:
        parts.append("index.html")
    return os.path.join(base_dir, domain, *parts)


def _base_domain(netloc: str) -> str:
    return netloc.replace("www.", "")


class Scraper:
    def __init__(self, cfg, on_log=None, on_progress=None, on_status=None,
                 on_done=None, on_stats=None, save_visited_cb=None,
                 save_media_queue_cb=None):
        self._cfg = cfg
        self._log                = on_log                or print
        self._progress           = on_progress           or (lambda v: None)
        self._status             = on_status             or (lambda s: None)
        self._done               = on_done               or (lambda: None)
        self._on_stats           = on_stats              or (lambda **kw: None)
        self._save_visited       = save_visited_cb       or (lambda urls: None)
        self._save_media_queue   = save_media_queue_cb   or (lambda urls: None)
        self._stats         = {
            "pages": 0, "files": 0, "bytes": 0, "errors": 0,
            "images": 0, "videos": 0, "audio": 0,
            "pdfs": 0, "documents": 0, "css_js": 0,
        }
        self._visited_ticks = 0

        self._pause = threading.Event()
        self._pause.set()
        self._stop  = threading.Event()

        self._visited      = set()
        self._visited_lock = threading.Lock()
        self._q            = queue.Queue()
        self._cnt_lock     = threading.Lock()
        self._queued       = 0
        self._finished     = 0

        self._session        = None
        self._cookies_file   = None
        self._start_url      = None
        self._pending_jar    = None
        self._pending_media  = set()
        self._media_lock     = threading.Lock()
        self._media_sem      = threading.Semaphore(2)

    # ── public API ────────────────────────────────────────────────────────────

    def set_previsited(self, urls: set):
        """Pre-seed visited set for resume — skips already-crawled pages."""
        with self._visited_lock:
            self._visited.update(urls)

    def set_pending_media(self, urls: set):
        """Pre-load interrupted media URLs to re-download on next start."""
        with self._media_lock:
            self._pending_media.update(urls)

    def set_cookies_list(self, cookies):
        self._pending_jar = cookies

    def set_cookies_jar(self, jar):
        """Accept a requests.cookies.RequestsCookieJar from a login session."""
        self._pending_jar = jar

    def pause(self):
        self._pause.clear()
        self._status("Paused")
        self._flush_visited()
        self._flush_media_queue()

    def resume(self):
        self._pause.set()
        self._status("Resumed…")

    def stop(self):
        self._stop.set()
        self._pause.set()
        self._flush_visited()
        self._flush_media_queue()

    def _flush_visited(self):
        with self._visited_lock:
            snap = set(self._visited)
        self._save_visited(snap)

    def _flush_media_queue(self):
        with self._media_lock:
            snap = set(self._pending_media)
        self._save_media_queue(snap)

    def start(self, start_url: str, output_dir: str):
        self._stop.clear()
        self._pause.set()
        with self._visited_lock:
            self._visited.clear()
        while not self._q.empty():
            try: self._q.get_nowait()
            except queue.Empty: break
        with self._cnt_lock:
            self._queued   = 1
            self._finished = 0

        self._session = requests.Session()
        self._session.headers["User-Agent"] = self._cfg.get("user_agent", "Mozilla/5.0")

        if self._pending_jar is not None:
            for c in self._pending_jar:
                self._session.cookies.set(
                    c.name, c.value,
                    domain=getattr(c, "domain", None),
                    path=getattr(c, "path", "/"),
                )
            self._pending_jar = None

        self._cookies_file = self._cfg.get("cookies_file") or None
        if self._cookies_file and os.path.exists(self._cookies_file):
            try:
                loaded = 0
                with open(self._cookies_file, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split("\t")
                        if len(parts) >= 7:
                            name, value = parts[5], parts[6]
                            if name:
                                # Set without domain restriction so every
                                # request to this site receives the cookie.
                                self._session.cookies.set(name, value)
                                loaded += 1
                self._log(f"   Loaded {loaded} cookies from {os.path.basename(self._cookies_file)}")
            except Exception as e:
                self._log(f"   ⚠  Could not load cookies file: {e}")
        self._start_url    = start_url

        base = urlparse(start_url).netloc
        depth = int(self._cfg.get("max_depth", 3))
        self._q.put((start_url, depth))

        # Re-queue any media URLs that were interrupted in a previous run
        with self._media_lock:
            pending = set(self._pending_media)
            self._pending_media.clear()
        if pending:
            self._log(f"   ↺  Resuming {len(pending)} interrupted video download(s).")
            for murl in pending:
                with self._cnt_lock:
                    self._queued += 1
                self._q.put((murl, -1))

        self._log(f"▶  Starting scrape: {start_url}")
        self._log(f"   Output: {output_dir}")
        if not YTDLP_OK:
            self._log("   ⚠  yt-dlp not found — embedded video extraction disabled.")
        if not BS4_OK:
            self._log("   ⚠  BeautifulSoup not found — link crawling disabled.")

        n = max(1, int(self._cfg.get("concurrent_downloads", 3)))
        self._media_sem = threading.Semaphore(max(1, n - 1))
        for _ in range(n):
            t = threading.Thread(target=self._worker, args=(output_dir, base), daemon=True)
            t.start()

        threading.Thread(target=self._monitor, daemon=True).start()

    # ── internals ─────────────────────────────────────────────────────────────

    def _monitor(self):
        self._q.join()
        if not self._stop.is_set():
            self._progress(100)
            self._status("Complete!")
            self._log("✔  Scrape finished.")
        self._flush_visited()
        self._flush_media_queue()
        self._done()

    def _worker(self, output_dir: str, base_netloc: str):
        while not self._stop.is_set():
            try:
                url, depth = self._q.get(timeout=3)
            except queue.Empty:
                return
            try:
                self._pause.wait()
                if self._stop.is_set():
                    self._q.task_done()
                    return
                if depth == -1:
                    self._ytdlp_url(url, output_dir)
                else:
                    self._process(url, depth, output_dir, base_netloc)
            except Exception as e:
                self._log(f"  ✗  Worker error [{url[:60]}]: {e}")
            finally:
                self._q.task_done()
                with self._cnt_lock:
                    self._finished += 1
                    pct = min(99, int(self._finished / max(self._queued, 1) * 100))
                self._progress(pct)

    def _enqueue(self, url: str, depth: int):
        url = urlparse(url)._replace(fragment="").geturl()
        url_lower = url.lower()
        if any(p in url_lower for p in _LOGOUT_PATTERNS):
            return
        with self._visited_lock:
            if url in self._visited:
                return
            self._visited.add(url)
        with self._cnt_lock:
            self._queued += 1
        self._q.put((url, depth))

    def _same_domain(self, netloc: str, base: str) -> bool:
        n = _base_domain(netloc)
        b = _base_domain(base)
        return n == b or n.endswith("." + b)

    # ── per-URL processing ────────────────────────────────────────────────────

    def _process(self, url: str, depth: int, out: str, base: str):
        scheme = urlparse(url).scheme
        if scheme not in ("http", "https"):
            return
        if self._cfg.get("stay_on_domain") and not self._same_domain(urlparse(url).netloc, base):
            return

        ext = _url_ext(url)

        # ── AI-recommended URL pattern filtering (pages only, not assets) ──
        if not ext and url != self._start_url:
            path = urlparse(url).path.lower()
            for pat in self._cfg.get("url_exclude_patterns", []):
                if pat and pat.lower() in path:
                    return
            incl = [p for p in self._cfg.get("url_include_patterns", []) if p]
            if incl and not any(p.lower() in path for p in incl):
                return

        self._status(f"{url[:90]}")

        # ── static asset by extension ──
        if ext in VIDEO_EXTS:
            if self._cfg.get("download_videos"):
                self._direct(url, out)
            return
        if ext in AUDIO_EXTS:
            if self._cfg.get("download_audio"):
                self._direct(url, out)
            return
        if ext in IMAGE_EXTS:
            if self._cfg.get("download_images"):
                self._direct(url, out)
            return
        if ext in DOC_EXTS:
            if self._cfg.get("download_documents"):
                self._direct(url, out)
            return
        if ext in CSSJS_EXTS:
            if self._cfg.get("download_css_js"):
                self._direct(url, out)
            return

        # ── HTML page ──
        try:
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.TooManyRedirects:
            self._stats["errors"] += 1
            self._log(
                f"  ✗  {url[:70]}: redirect loop detected — "
                "cookies are likely expired or invalid. "
                "Re-export fresh cookies from your browser and try again."
            )
            return
        except Exception as e:
            self._stats["errors"] += 1
            self._log(f"  ✗  {url[:70]}: {e}")
            return

        ctype = resp.headers.get("content-type", "")
        if "text/html" not in ctype:
            # binary resource with no extension (e.g., PHP serving a PDF)
            self._write(out, url, resp.content)
            return

        if self._cfg.get("download_html"):
            self._write(out, url, resp.content)
            self._log(f"  ✓  {url}")

        self._stats["pages"] += 1
        self._visited_ticks  += 1
        if self._visited_ticks % 20 == 0:
            self._flush_visited()
        self._on_stats(**self._stats)

        if not BS4_OK:
            return

        soup = BeautifulSoup(resp.text, "lxml")

        # ── video extraction ──────────────────────────────────────────────────
        if self._cfg.get("download_videos") or self._cfg.get("download_audio"):
            # 1. Extract video platform URLs embedded in JSON/props (Wistia, Vimeo, etc.)
            embedded = _extract_embedded_videos(resp.text)
            for vurl in embedded:
                self._ytdlp_url(vurl, out)

            # 2. Fall back to full-page yt-dlp scan for standard iframe/video tags
            if not embedded:
                html_lower = resp.text.lower()
                has_media = bool(
                    soup.find(["video", "audio"])
                    or soup.find("iframe", src=True)
                    or any("video" in (tag.get("type") or "")
                           for tag in soup.find_all("source"))
                    or any(hint in html_lower for hint in _VIDEO_PLATFORM_HINTS)
                )
                if has_media:
                    self._ytdlp_page(url, out)

        # ── images ──
        if self._cfg.get("download_images"):
            for tag in soup.find_all(["img", "source"]):
                for attr in ("src", "data-src", "data-lazy-src", "srcset"):
                    val = tag.get(attr, "")
                    if not val:
                        continue
                    # srcset may contain multiple space-separated entries
                    for entry in val.split(","):
                        src = entry.strip().split()[0]
                        if src:
                            self._enqueue(urljoin(url, src), 0)

        # ── video / audio tags ──
        if self._cfg.get("download_videos") or self._cfg.get("download_audio"):
            for tag in soup.find_all(["video", "audio", "source", "track"]):
                src = tag.get("src")
                if src:
                    self._enqueue(urljoin(url, src), 0)

        # ── CSS / JS ──
        if self._cfg.get("download_css_js"):
            for tag in soup.find_all("link", href=True):
                rel = " ".join(tag.get("rel", []))
                if "stylesheet" in rel or "preload" in rel:
                    self._enqueue(urljoin(url, tag["href"]), 0)
            for tag in soup.find_all("script", src=True):
                self._enqueue(urljoin(url, tag["src"]), 0)

        # ── iframes (embedded players on other domains) ──
        for tag in soup.find_all("iframe", src=True):
            src = urljoin(url, tag["src"])
            netloc = urlparse(src).netloc
            if any(d in netloc for d in EMBED_DOMAINS):
                if self._cfg.get("download_videos") or self._cfg.get("download_audio"):
                    self._ytdlp_url(src, out)

        # ── links to other pages / downloadable files ──
        if depth > 0:
            for tag in soup.find_all("a", href=True):
                href = urljoin(url, tag["href"])
                h_ext = _url_ext(href)
                if h_ext in DOC_EXTS:
                    if self._cfg.get("download_documents"):
                        self._enqueue(href, 0)
                elif h_ext in VIDEO_EXTS:
                    if self._cfg.get("download_videos"):
                        self._enqueue(href, 0)
                elif h_ext in AUDIO_EXTS:
                    if self._cfg.get("download_audio"):
                        self._enqueue(href, 0)
                elif not h_ext or h_ext in {".html", ".htm", ".php", ".asp", ".aspx", ".cfm"}:
                    self._enqueue(href, depth - 1)

        delay = float(self._cfg.get("delay_between_requests", 0.5))
        if delay > 0:
            time.sleep(delay)

    # ── download helpers ──────────────────────────────────────────────────────

    def _direct(self, url: str, out: str):
        path = _url_to_path(url, out)
        if os.path.exists(path):
            return
        try:
            resp = self._session.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            total = 0
            with open(path, "wb") as f:
                for chunk in resp.iter_content(16384):
                    if self._stop.is_set():
                        return
                    self._pause.wait()
                    f.write(chunk)
                    total += len(chunk)
            self._stats["files"] += 1
            self._stats["bytes"] += total
            ext = _url_ext(url)
            if ext in IMAGE_EXTS:
                self._stats["images"] += 1
            elif ext in VIDEO_EXTS:
                self._stats["videos"] += 1
            elif ext in AUDIO_EXTS:
                self._stats["audio"] += 1
            elif ext == ".pdf":
                self._stats["pdfs"] += 1
            elif ext in DOC_EXTS:
                self._stats["documents"] += 1
            elif ext in CSSJS_EXTS:
                self._stats["css_js"] += 1
            self._log(f"  ↓  {url}")
        except Exception as e:
            self._stats["errors"] += 1
            self._log(f"  ✗  {url[:70]}: {e}")

    def _write(self, out: str, url: str, data: bytes):
        path = _url_to_path(url, out)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        except Exception as e:
            self._log(f"  ✗  Write error: {e}")

    def _ytdlp_opts(self, out: str, domain: str) -> dict:
        """Shared yt-dlp options with a throttled progress hook."""
        tmpl = os.path.join(out, domain, "media", "%(title)s.%(ext)s")

        _last: list[float] = [0.0]   # mutable cell for last-update timestamp

        def _hook(d):
            status = d.get("status")
            now = time.monotonic()

            if status == "downloading":
                # Throttle to one update every 0.75 s to avoid flooding tkinter
                if now - _last[0] < 0.75:
                    return
                _last[0] = now
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                done  = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                if total:
                    pct = int(done / total * 100)
                    mb  = f"{done/1048576:.1f}/{total/1048576:.1f} MB"
                    spd = (f"  {speed/1048576:.1f} MB/s" if speed >= 1048576
                           else f"  {speed/1024:.0f} KB/s") if speed else ""
                    self._status(f"  ▶  {pct}%  {mb}{spd}")
                else:
                    self._status(f"  ▶  {done/1048576:.1f} MB downloaded…")

            elif status == "finished":
                self._status("  ▶  Finalising…")

        opts = {
            "outtmpl":           tmpl,
            "quiet":             True,
            "no_warnings":       True,
            "ignoreerrors":      True,
            "logger":            _YtdlpSilent(),
            "progress_hooks":    [_hook],
            "continuedl":                   True,
            "retries":                      5,
            "fragment_retries":             5,
            "concurrent_fragment_downloads": 4,
        }
        if self._cookies_file and os.path.exists(self._cookies_file):
            opts["cookiefile"] = self._cookies_file
        return opts

    def _ytdlp_page(self, page_url: str, out: str):
        if not YTDLP_OK:
            return
        domain = urlparse(page_url).netloc
        opts   = self._ytdlp_opts(out, domain)
        with self._media_sem:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(page_url, download=True)
                    if info:
                        entries = info.get("entries") or ([info] if info.get("title") else [])
                        for entry in entries:
                            if not entry:
                                continue
                            self._stats["files"] += 1
                            if entry.get("vcodec") != "none":
                                self._stats["videos"] += 1
                            else:
                                self._stats["audio"] += 1
                            self._on_stats(**self._stats)
                            self._log(f"  ▶  [media] {entry.get('title', '')}")
            except Exception:
                pass

    def _ytdlp_url(self, url: str, out: str):
        if not YTDLP_OK:
            return
        domain = urlparse(url).netloc
        opts   = self._ytdlp_opts(out, domain)
        with self._media_lock:
            self._pending_media.add(url)
        self._flush_media_queue()
        self._log(f"  ▶  Downloading: {url}")
        with self._media_sem:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info:
                        self._stats["files"] += 1
                        if info.get("vcodec") != "none":
                            self._stats["videos"] += 1
                        else:
                            self._stats["audio"] += 1
                        self._on_stats(**self._stats)
                        self._log(f"  ▶  Done: {info.get('title', url)}")
                        with self._media_lock:
                            self._pending_media.discard(url)
                        self._flush_media_queue()
            except Exception:
                pass
