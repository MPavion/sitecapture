"""
build_media_map.py — populate media_map.json from already-downloaded video files.

Scans all HTML files in the output folder for video embed URLs, fetches the
canonical title for each via platform APIs (Wistia oEmbed, yt-dlp fallback),
then fuzzy-matches that title against the .mp4 files already on disk to build
the source_url → local_relative_path mapping.

Requires: beautifulsoup4, internet access (info queries only, no re-downloading)
Optional: yt-dlp (used as fallback for non-Wistia platforms)

Usage:
    python build_media_map.py "<output_folder>"

Example:
    python build_media_map.py "X:/Educational/Video Production Skills/HookPoint Website Rip"
"""

import os
import sys
import json
import re
import difflib
import urllib.request
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Error: beautifulsoup4 not installed. Run: pip install beautifulsoup4 lxml")

try:
    import yt_dlp as _yt_dlp
except ImportError:
    _yt_dlp = None


# ── video ID helpers (mirrors fix_links.py) ──────────────────────────────────

def _video_id(url: str) -> str | None:
    lurl = url.lower()
    if "wistia" in lurl:
        m = re.search(r"/(?:medias|iframes)/([a-zA-Z0-9]+)", url)
        return f"wistia:{m.group(1)}" if m else None
    if "mediadelivery.net" in lurl:
        m = re.search(r"/(?:embed|play)/(\d+)/([a-zA-Z0-9-]+)", url)
        return f"bunny:{m.group(1)}/{m.group(2)}" if m else None
    if "vimeo.com" in lurl:
        m = re.search(r"/(?:video/)?(\d+)", url)
        return f"vimeo:{m.group(1)}" if m else None
    if "youtube.com" in lurl or "youtu.be" in lurl:
        m = re.search(r"(?:embed/|v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
        return f"youtube:{m.group(1)}" if m else None
    if "jwplatform.com" in lurl or "jwplayer.com" in lurl:
        m = re.search(r"/(?:players|videos)/([a-zA-Z0-9_-]+)", url)
        return f"jw:{m.group(1)}" if m else None
    if "brightcove" in lurl:
        m = re.search(r"/(\d{10,})", url)
        return f"bc:{m.group(1)}" if m else None
    if "vidyard.com" in lurl:
        m = re.search(r"/(?:watch|embed)/([a-zA-Z0-9_-]+)", url)
        return f"vidyard:{m.group(1)}" if m else None
    if "loom.com" in lurl:
        m = re.search(r"/(?:embed|share)/([a-f0-9]+)", url)
        return f"loom:{m.group(1)}" if m else None
    return None


def _find_video_url_in_props(obj) -> str | None:
    if isinstance(obj, str):
        return obj if _video_id(obj) else None
    if isinstance(obj, (list, tuple)):
        for item in obj:
            r = _find_video_url_in_props(item)
            if r:
                return r
    elif isinstance(obj, dict):
        for v in obj.values():
            r = _find_video_url_in_props(v)
            if r:
                return r
    return None


# ── scan HTML for video URLs ──────────────────────────────────────────────────

def collect_video_urls(base_dir: str) -> set[str]:
    """Walk all HTML files and return every unique video source URL found."""
    urls: set[str] = set()
    for root, _dirs, files in os.walk(base_dir):
        for fname in files:
            if not fname.lower().endswith((".html", ".htm")):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, "rb") as f:
                    soup = BeautifulSoup(f.read(), "lxml")
            except Exception:
                continue
            # <iframe src>
            for tag in soup.find_all("iframe", src=True):
                src = tag["src"].strip()
                if _video_id(src):
                    urls.add(src)
            # <astro-island props>
            for tag in soup.find_all("astro-island"):
                raw = tag.get("props", "")
                if not raw:
                    continue
                try:
                    props = json.loads(raw)
                except Exception:
                    continue
                vid_url = _find_video_url_in_props(props)
                if vid_url:
                    urls.add(vid_url)
    return urls


# ── local mp4 index ───────────────────────────────────────────────────────────

def index_local_videos(base_dir: str) -> list[tuple[str, str]]:
    """Return [(stem_lowercase, relative_path), ...] for every .mp4 on disk."""
    results = []
    for root, _dirs, files in os.walk(base_dir):
        for fname in files:
            if fname.lower().endswith(".mp4"):
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, base_dir).replace(os.sep, "/")
                stem = os.path.splitext(fname)[0].lower()
                results.append((stem, rel))
    return results


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation/extra spaces for fuzzy comparison."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r" +", " ", s).strip()


def best_match(title: str, local_videos: list[tuple[str, str]]) -> tuple[str, float] | None:
    """Return (relative_path, score) of best fuzzy match, or None if score < 0.4."""
    if not local_videos:
        return None
    norm_title = _normalize(title)
    candidates = [stem for stem, _rel in local_videos]
    norms = [_normalize(c) for c in candidates]
    matches = difflib.get_close_matches(norm_title, norms, n=1, cutoff=0.4)
    if not matches:
        return None
    idx = norms.index(matches[0])
    score = difflib.SequenceMatcher(None, norm_title, norms[idx]).ratio()
    return local_videos[idx][1], score


# ── title fetchers ────────────────────────────────────────────────────────────

def fetch_wistia_title(media_id: str) -> str | None:
    """Wistia public oEmbed API — no auth needed, no yt-dlp required."""
    try:
        api_url = f"https://fast.wistia.com/oembed?url=https://home.wistia.com/medias/{media_id}"
        with urllib.request.urlopen(api_url, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("title")
    except Exception:
        return None


def fetch_title_ytdlp(url: str) -> str | None:
    """Use yt-dlp in info-only mode (fallback for non-Wistia platforms)."""
    if _yt_dlp is None:
        return None
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    try:
        with _yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title") if info else None
    except Exception:
        return None


def fetch_video_title(url: str) -> str | None:
    """Return the video title, trying platform-specific APIs before yt-dlp."""
    lurl = url.lower()
    if "wistia" in lurl:
        m = re.search(r"/(?:medias|iframes)/([a-zA-Z0-9]+)", url)
        if m:
            return fetch_wistia_title(m.group(1))
    return fetch_title_ytdlp(url)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    base_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(base_dir):
        sys.exit(f"Error: directory not found: {base_dir}")

    map_path = os.path.join(base_dir, "media_map.json")

    # Load any existing entries so we don't re-query URLs already mapped
    existing: dict[str, str] = {}
    if os.path.exists(map_path):
        try:
            with open(map_path, encoding="utf-8") as f:
                existing = json.load(f)
            print(f"Loaded {len(existing)} existing mapping(s) from media_map.json")
        except Exception:
            pass

    print(f"\nScanning HTML files in: {base_dir}")
    video_urls = collect_video_urls(base_dir)
    new_urls = [u for u in sorted(video_urls) if u not in existing]
    print(f"Found {len(video_urls)} unique video URL(s), {len(new_urls)} not yet mapped.\n")

    if not new_urls:
        print("Nothing to do — all video URLs are already in media_map.json.")
        return

    print("Indexing local .mp4 files…")
    local_videos = index_local_videos(base_dir)
    print(f"Found {len(local_videos)} local .mp4 file(s).\n")

    media_map = dict(existing)
    mapped = skipped = failed = 0

    for i, url in enumerate(new_urls, 1):
        print(f"[{i}/{len(new_urls)}] {url}")

        title = fetch_video_title(url)

        if not title:
            print(f"  ✗  Could not fetch title — skipping")
            failed += 1
            continue

        print(f"  title: {title}")
        match = best_match(title, local_videos)
        if not match:
            print(f"  ✗  No matching local file found")
            skipped += 1
            continue

        rel_path, score = match
        print(f"  ✓  {rel_path}  (score={score:.2f})")
        media_map[url] = rel_path
        mapped += 1

        # Save incrementally so progress isn't lost on interruption
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(media_map, f, indent=2)

    print(f"\n{'─'*60}")
    print(f"  {mapped:>4}  mapped successfully")
    print(f"  {skipped:>4}  no local file match")
    print(f"  {failed:>4}  title fetch failed")
    print(f"\nmedia_map.json written to: {map_path}")
    print("\nRun fix_links.py next to apply the video replacements.")


if __name__ == "__main__":
    main()
