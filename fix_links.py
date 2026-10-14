"""
fix_links.py — rewrite internal links and replace video iframes in downloaded HTML files.

Usage:
    python fix_links.py "<output_folder>"

Example:
    python fix_links.py "X:/Educational/Video Production Skills/HookPoint Website Rip"

Runs two passes:
  1. Rewrite all same-domain hrefs (anchors, images, CSS, JS) to relative local paths.
  2. Replace external video iframes with <video> tags pointing to locally downloaded files
     (requires media_map.json — generated automatically by the scraper on each run).
"""

import os
import re
import sys
import json
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Error: beautifulsoup4 is not installed. Run: pip install beautifulsoup4 lxml")


# ── helpers ───────────────────────────────────────────────────────────────────

def _base_domain(netloc: str) -> str:
    return netloc.replace("www.", "")


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


def _path_to_url(local_path: str, base_dir: str) -> str:
    """Reconstruct the original URL from a local file path (reverse of _url_to_path)."""
    rel = os.path.relpath(local_path, base_dir).replace(os.sep, "/")
    parts = rel.split("/")
    if len(parts) < 2:
        return None
    domain = parts[0]
    path_parts = parts[1:]
    if path_parts and path_parts[-1].lower() == "index.html":
        path_parts = path_parts[:-1]
    if not path_parts:
        return f"https://{domain}/"
    return f"https://{domain}/" + "/".join(path_parts) + "/"


def _find_video_url_in_props(obj) -> str | None:
    """Recursively walk a deserialised props object and return the first video URL found."""
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


def _video_id(url: str) -> str | None:
    """Extract a normalised 'platform:id' key from a video embed URL."""
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


# ── pass 1: link rewriting ────────────────────────────────────────────────────

def rewrite_file(local_path: str, base_dir: str) -> bool:
    """Rewrite internal links in one HTML file. Returns True if the file was changed."""
    page_url = _path_to_url(local_path, base_dir)
    if not page_url:
        return False

    with open(local_path, "rb") as f:
        original = f.read()

    try:
        soup = BeautifulSoup(original, "lxml")
        p_dir = os.path.dirname(local_path)
        page_base = _base_domain(urlparse(page_url).netloc)

        def _rel(href: str):
            if not href:
                return None
            lh = href.strip().lower()
            if lh.startswith(("data:", "javascript:", "#", "mailto:", "tel:")):
                return None
            abs_url = urljoin(page_url, href)
            if not abs_url.startswith(("http://", "https://")):
                return None
            try:
                return os.path.relpath(_url_to_path(abs_url, base_dir), p_dir).replace(os.sep, "/")
            except ValueError:
                return None

        # CSS & JS
        for tag in soup.find_all("link", href=True):
            r = _rel(tag["href"])
            if r:
                tag["href"] = r
        for tag in soup.find_all("script", src=True):
            r = _rel(tag["src"])
            if r:
                tag["src"] = r

        # Images
        for tag in soup.find_all(["img", "source"]):
            for attr in ("src", "data-src", "data-lazy-src"):
                val = tag.get(attr, "")
                if val:
                    r = _rel(val)
                    if r:
                        tag[attr] = r
            val = tag.get("srcset", "")
            if val:
                entries = []
                for entry in val.split(","):
                    parts = entry.strip().split()
                    if parts:
                        r = _rel(parts[0])
                        if r:
                            parts[0] = r
                        entries.append(" ".join(parts))
                tag["srcset"] = ", ".join(entries)

        # Anchor links
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            lh = href.strip().lower()
            if lh.startswith(("data:", "javascript:", "mailto:", "tel:")):
                continue
            abs_url = urljoin(page_url, href)
            if not abs_url.startswith(("http://", "https://")):
                continue
            link_base = _base_domain(urlparse(abs_url).netloc)
            if link_base != page_base and not link_base.endswith("." + page_base):
                continue
            ext = _url_ext(abs_url)
            if not ext or ext in {".html", ".htm", ".php", ".asp", ".aspx", ".cfm"}:
                r = _rel(href)
                if r:
                    tag["href"] = r

        # Inline scripts: rewrite JS navigation variables that hold absolute paths
        # (e.g. `const nextUrl = "/course/.../lesson/slug"` → relative path)
        for tag in soup.find_all("script"):
            txt = tag.string
            if not txt or "nextUrl" not in txt:
                continue

            def _sub_js_url(m, _rel=_rel):
                r = _rel(m.group(1))
                return f'const nextUrl = "{r}"' if r else m.group(0)

            new_txt = re.sub(r'const nextUrl = "(/[^"]+)"', _sub_js_url, txt)
            if new_txt != txt:
                tag.string.replace_with(new_txt)

        rewritten = soup.encode("utf-8")
    except Exception as e:
        print(f"  ✗  Parse error [{local_path}]: {e}")
        return False

    if rewritten == original:
        return False

    with open(local_path, "wb") as f:
        f.write(rewritten)
    return True


# ── pass 2: video embed replacement ──────────────────────────────────────────

def _replace_video_embeds(local_path: str, base_dir: str, id_map: dict) -> int:
    """Replace external video iframes with <video> tags. Returns count of replacements."""
    with open(local_path, "rb") as f:
        original = f.read()

    try:
        soup = BeautifulSoup(original, "lxml")
    except Exception:
        return 0

    page_dir = os.path.dirname(local_path)
    replaced = 0

    for tag in soup.find_all("iframe", src=True):
        src = tag.get("src", "")
        vid_id = _video_id(src)
        if not vid_id or vid_id not in id_map:
            continue

        rel_media = id_map[vid_id]
        media_abs = os.path.join(base_dir, rel_media.replace("/", os.sep))
        if not os.path.exists(media_abs):
            continue

        rel_to_page = os.path.relpath(media_abs, page_dir).replace(os.sep, "/")

        # Preserve aspect ratio from iframe width/height attributes
        width  = tag.get("width",  "")
        height = tag.get("height", "")
        if width and height:
            style = f"width:100%;max-width:{width}px;aspect-ratio:{width}/{height}"
        else:
            style = "width:100%;max-width:100%;aspect-ratio:16/9"

        video_tag = soup.new_tag("video", controls=True, preload="metadata")
        video_tag["style"] = style
        video_tag.append(soup.new_tag("source", src=rel_to_page, type="video/mp4"))
        tag.replace_with(video_tag)
        replaced += 1

    # Astro/React component islands that embed videos via JSON props
    for tag in soup.find_all("astro-island"):
        props_raw = tag.get("props", "")
        if not props_raw:
            continue
        try:
            props = json.loads(props_raw)
        except Exception:
            continue
        vid_url = _find_video_url_in_props(props)
        if not vid_url:
            continue
        vid_id = _video_id(vid_url)
        if not vid_id or vid_id not in id_map:
            continue

        rel_media = id_map[vid_id]
        media_abs = os.path.join(base_dir, rel_media.replace("/", os.sep))
        if not os.path.exists(media_abs):
            continue

        rel_to_page = os.path.relpath(media_abs, page_dir).replace(os.sep, "/")
        style = "width:100%;max-width:100%;aspect-ratio:16/9"

        video_tag = soup.new_tag("video", controls=True, preload="metadata")
        video_tag["style"] = style
        video_tag.append(soup.new_tag("source", src=rel_to_page, type="video/mp4"))
        tag.replace_with(video_tag)
        replaced += 1

    if replaced:
        with open(local_path, "wb") as f:
            f.write(soup.encode("utf-8"))

    return replaced


def fix_video_embeds(base_dir: str) -> tuple[int, int]:
    """
    Replace external video iframes with local <video> tags using media_map.json.
    Returns (files_changed, total_replacements).
    """
    map_path = os.path.join(base_dir, "media_map.json")
    if not os.path.exists(map_path):
        print("  ⚠  No media_map.json found.")
        print("     Run an Update scrape first — the scraper now builds this map automatically.")
        return 0, 0

    with open(map_path, encoding="utf-8") as f:
        media_map = json.load(f)

    if not media_map:
        print("  ⚠  media_map.json is empty — no videos were tracked yet.")
        return 0, 0

    # Build video-ID → local relative path lookup
    id_map: dict[str, str] = {}
    for src_url, rel_path in media_map.items():
        vid_id = _video_id(src_url)
        if vid_id:
            id_map[vid_id] = rel_path

    print(f"  Loaded {len(id_map)} video mapping(s) from media_map.json")

    files_changed = total = 0
    for root, _dirs, files in os.walk(base_dir):
        for fname in files:
            if not fname.lower().endswith((".html", ".htm")):
                continue
            path = os.path.join(root, fname)
            n = _replace_video_embeds(path, base_dir, id_map)
            if n:
                files_changed += 1
                total += n
                print(f"  ✓  {os.path.relpath(path, base_dir)} ({n} video{'s' if n > 1 else ''} replaced)")

    return files_changed, total


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    base_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(base_dir):
        sys.exit(f"Error: directory not found: {base_dir}")

    print(f"Scanning: {base_dir}\n")

    # ── Pass 1: rewrite links ──
    print("Pass 1: rewriting internal links…")
    total = link_changed = errors = 0
    for root, _dirs, files in os.walk(base_dir):
        for fname in files:
            if not fname.lower().endswith((".html", ".htm")):
                continue
            path = os.path.join(root, fname)
            total += 1
            try:
                if rewrite_file(path, base_dir):
                    link_changed += 1
                    print(f"  ✓  {os.path.relpath(path, base_dir)}")
            except Exception as e:
                errors += 1
                print(f"  ✗  {os.path.relpath(path, base_dir)}: {e}")
    print(f"  {total} files scanned, {link_changed} rewritten, {errors} errors.\n")

    # ── Pass 2: replace video embeds ──
    print("Pass 2: replacing video iframes with local players…")
    vid_files, vid_total = fix_video_embeds(base_dir)
    if vid_total:
        print(f"  {vid_total} iframe(s) replaced across {vid_files} file(s).")
    elif os.path.exists(os.path.join(base_dir, "media_map.json")):
        print("  No replaceable video iframes found.")

    print("\nDone.")


if __name__ == "__main__":
    main()
