"""
check_links.py — audit internal links in offline-downloaded HTML files.

Reports three issue types for every <a href> found:
  BROKEN   — link resolves to a local path that does not exist on disk
  EXTERNAL — link is an absolute URL to a different domain (needs internet)
  ABSOLUTE — same-domain link was not rewritten to a relative path

Usage:
    python check_links.py "<output_folder>"
    python check_links.py "<output_folder>" --save   # also write link_issues.txt

Example:
    python check_links.py "X:/Educational/Video Production Skills/HookPoint Website Rip"
"""

import os
import sys
from urllib.parse import urljoin, urlparse
from collections import defaultdict

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Error: beautifulsoup4 not installed. Run: pip install beautifulsoup4 lxml")


VIDEO_EMBED_DOMAINS = {
    "fast.wistia.com", "wistia.com", "wistia.net",
    "iframe.mediadelivery.net", "mediadelivery.net",
    "player.vimeo.com", "vimeo.com",
    "www.youtube.com", "youtube.com", "youtu.be",
    "jwplatform.com", "cdn.jwplayer.com", "jwplayer.com",
    "brightcove.net", "brightcove.com",
    "play.vidyard.com", "vidyard.com",
    "cdn.loom.com", "loom.com",
}


# ── helpers (mirror scraper.py / fix_links.py) ────────────────────────────────

def _base_domain(netloc: str) -> str:
    return netloc.replace("www.", "")


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


# ── per-file checker ──────────────────────────────────────────────────────────

def check_file(local_path: str, base_dir: str) -> list[dict]:
    """
    Return a list of issue dicts for every problematic <a href> in the file.
    Keys: kind, href, text, resolved
    """
    page_url = _path_to_url(local_path, base_dir)
    if not page_url:
        return []

    page_base = _base_domain(urlparse(page_url).netloc)

    try:
        with open(local_path, "rb") as f:
            soup = BeautifulSoup(f.read(), "lxml")
    except Exception as e:
        return [{"kind": "error", "href": "", "text": str(e), "resolved": ""}]

    issues = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        lh = href.strip().lower()

        # skip non-navigable schemes and pure fragment anchors
        if lh.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
            continue

        link_text = tag.get_text(" ", strip=True)[:60] or "(no text)"

        abs_url = urljoin(page_url, href)
        if not abs_url.startswith(("http://", "https://")):
            continue

        parsed = urlparse(abs_url)
        link_base = _base_domain(parsed.netloc)

        # External domain — will need internet connection offline
        if link_base != page_base and not link_base.endswith("." + page_base):
            issues.append({
                "kind":     "external",
                "href":     href,
                "text":     link_text,
                "resolved": abs_url,
            })
            continue

        # Same domain — check that the local file exists
        target = _url_to_path(abs_url, base_dir)

        if href.startswith(("http://", "https://")):
            # Absolute same-domain URL that was never rewritten
            kind = "absolute" if os.path.exists(target) else "broken"
        else:
            kind = "broken" if not os.path.exists(target) else None

        if kind:
            issues.append({
                "kind":     kind,
                "href":     href,
                "text":     link_text,
                "resolved": target,
            })

    # External video iframes (won't play offline unless replaced by fix_links.py)
    for tag in soup.find_all("iframe", src=True):
        src = tag.get("src", "").strip()
        if not src or src.startswith("#"):
            continue
        abs_src = urljoin(page_url, src)
        iframe_netloc = urlparse(abs_src).netloc.lower()
        if any(d in iframe_netloc for d in VIDEO_EMBED_DOMAINS):
            issues.append({
                "kind":     "embed",
                "href":     src,
                "text":     "(video embed)",
                "resolved": abs_src,
            })

    return issues


# ── reporting ─────────────────────────────────────────────────────────────────

def run(base_dir: str, save: bool = False):
    if not os.path.isdir(base_dir):
        sys.exit(f"Error: directory not found: {base_dir}")

    print(f"Scanning: {base_dir}\n")

    # { local_path: [issue, ...] }
    report: dict[str, list] = {}
    totals = {"broken": 0, "external": 0, "absolute": 0, "embed": 0, "error": 0}

    for root, _dirs, files in os.walk(base_dir):
        for fname in files:
            if not fname.lower().endswith((".html", ".htm")):
                continue
            path = os.path.join(root, fname)
            issues = check_file(path, base_dir)
            if issues:
                report[path] = issues
                for iss in issues:
                    totals[iss["kind"]] = totals.get(iss["kind"], 0) + 1

    lines = []

    if not report:
        msg = "No issues found — all internal links resolve to local files."
        print(msg)
        return

    KIND_LABEL = {
        "broken":   "BROKEN  ",
        "absolute": "ABSOLUTE",
        "external": "EXTERNAL",
        "embed":    "EMBED   ",
        "error":    "ERROR   ",
    }

    for path in sorted(report):
        rel = os.path.relpath(path, base_dir)
        header = f"\n{rel}"
        lines.append(header)
        print(header)

        # Group: broken first, then absolute, then embeds, then external
        grouped = defaultdict(list)
        for iss in report[path]:
            grouped[iss["kind"]].append(iss)

        for kind in ("broken", "absolute", "error", "embed", "external"):
            for iss in grouped.get(kind, []):
                label = KIND_LABEL.get(kind, kind.upper())
                href_col = iss["href"][:70]
                text_col = f'"{iss["text"][:50]}"'

                if kind == "broken":
                    detail = f"→ missing: {os.path.relpath(iss['resolved'], base_dir)}"
                elif kind == "absolute":
                    detail = "(not rewritten — run fix_links.py)"
                elif kind in ("external", "embed"):
                    detail = f"→ {iss['resolved'][:80]}"
                else:
                    detail = iss["resolved"]

                line = f"  {label}  {href_col:<72}  {text_col}"
                lines.append(line)
                print(line)
                if detail:
                    indent = f"           {detail}"
                    lines.append(indent)
                    print(indent)

    embed_note = " (run fix_links.py after next Update scrape)" if totals["embed"] else ""
    summary = (
        f"\n{'─'*60}\n"
        f"Summary\n"
        f"  {totals['broken']:>5}  broken local links    (page not downloaded)\n"
        f"  {totals['absolute']:>5}  absolute same-domain  (run fix_links.py)\n"
        f"  {totals['embed']:>5}  video embeds          (need internet){embed_note}\n"
        f"  {totals['external']:>5}  other external links  (need internet)\n"
    )
    lines.append(summary)
    print(summary)

    if save:
        out_path = os.path.join(base_dir, "link_issues.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"Report saved to: {out_path}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]

    if not args:
        print(__doc__)
        sys.exit(1)

    run(os.path.abspath(args[0]), save="--save" in flags)


if __name__ == "__main__":
    main()
