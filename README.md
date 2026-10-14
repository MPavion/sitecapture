# SiteCapture

A desktop app for downloading entire websites — HTML, images, videos, audio, PDFs, and other assets — for fully offline use. Includes post-processing tools to rewrite links, replace embedded video players, and fix JavaScript-driven navigation so downloaded sites work without an internet connection.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

---

## Features

- **Full site crawl** — mirrors a website's folder structure to disk
- **Video downloads** — embedded YouTube, Vimeo, Wistia, Bunny, and more via yt-dlp
- **Offline post-processing** — rewrites internal links and JavaScript navigation to relative paths so pages work under `file://` without a web server
- **Embedded video replacement** — swaps external video iframes and Astro/React component embeds with local `<video>` tags pointing to downloaded files
- **Accordion/interactive component fix** — patches ES-module-dependent UI components that break under `file://` with self-contained inline scripts
- **Authentication** — HTML form login, or browser cookie import (`.txt` / `.json`)
- **Project management** — per-project settings, logs, stats, and visited-URL tracking
- **Auto-resume** — interrupted scrapes and video downloads pick up where they left off
- **AI analysis** — Claude-powered site analysis with depth and URL-pattern recommendations
- **Live stats panel** — pages, videos, images, PDFs, docs, audio, and total bytes downloaded
- **Completion sound** — audio notification when a scrape finishes

---

## Installation

### Windows

**Requirements:** Windows 10/11, [Python 3.10+](https://python.org)

1. Download or clone this repository
2. Double-click **`setup.bat`** — installs all dependencies and creates a Desktop shortcut
3. Launch via the **SiteCapture** shortcut or double-click **`run.bat`**

#### Manual install (Windows)

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### macOS

**Requirements:** macOS 11+, [Python 3.10+](https://python.org) (or via `brew install python`)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

---

## Usage

1. Enter the website URL in the **URL** field
2. Choose an output folder with **Browse**
3. (Optional) Expand **Settings** to configure crawl depth, file types, and thread count
4. Click **▶ Start**

Click **?  Help** inside the app for detailed instructions on every feature.

---

## Making a downloaded site work offline

After scraping, run the three post-processing tools in order:

### Step 1 — Build the video map (first time only)

If videos were downloaded before `media_map.json` existed, or after a fresh scrape:

```bash
python build_media_map.py "path/to/output/folder"
```

Scans HTML files for video embed URLs, fetches titles via platform APIs (Wistia oEmbed, yt-dlp fallback for others), fuzzy-matches them against local `.mp4` files, and writes `media_map.json`. Requires internet — no re-downloading.

On subsequent scrapes the scraper builds `media_map.json` automatically.

### Step 2 — Fix links and replace video embeds

```bash
python fix_links.py "path/to/output/folder"
```

Runs three passes:

| Pass | What it does |
|------|-------------|
| 1 | Rewrites all internal `href`/`src` attributes and JavaScript navigation variables (e.g. `const nextUrl`) from absolute URLs to relative local paths |
| 2 | Injects a self-contained accordion toggle script into pages whose interactive expand/collapse components rely on ES module imports (blocked under `file://`) |
| 3 | Replaces external video iframes and Astro/React component embeds with `<video>` tags pointing to local `.mp4` files, using `media_map.json` |

### Step 3 — Audit links (optional)

```bash
python check_links.py "path/to/output/folder"
python check_links.py "path/to/output/folder" --save   # also writes link_issues.txt
```

Reports broken local links, unrewritten absolute URLs, external links, and unresolved video embeds.

---

## Authentication

For sites that require login:

**Option A — Login form**
Enter your username, password, and click **Login**. The app auto-detects the login page. Enter the login page URL manually if auto-detection fails.

**Option B — Browser cookies (most reliable)**
Works for JavaScript SPAs, two-factor auth, and any site where the form login doesn't work.

1. Install a browser extension:
   - Chrome / Edge: *Get cookies.txt LOCALLY*
   - Firefox: *cookies.txt*
2. Log in to the site in your browser
3. Click the extension → export cookies (Netscape `.txt` or `.json` — both accepted)
4. Click **Browse** in the Cookies row and select the exported file
5. Click **▶ Start**

---

## Settings

| Setting | Description |
|---|---|
| Crawl depth | Link hops to follow from the start URL (1 = homepage only, 3 = default) |
| Concurrent downloads | Parallel threads — higher is faster but heavier on the server |
| Delay (s) | Wait between requests — 0.5 is polite, 0 is maximum speed |
| Stay on domain | Only follow links on the same domain as the start URL |
| Videos | Download direct video files + embedded players via yt-dlp |
| Documents | PDFs, Word, Excel, ZIP, and other attachments |
| AI Analysis | Anthropic API key for AI-powered site analysis |

---

## Supported video platforms

The scraper and post-processing tools handle embeds from:

Wistia · YouTube · Vimeo · Bunny (mediadelivery.net) · JW Player · Brightcove · Vidyard · Loom

Wistia embeds delivered via Astro/React component islands (`<astro-island>`) are also detected and replaced.

---

## Building a standalone executable

### Windows (.exe installer)

```bat
build.bat
```

Creates a portable folder at `dist\SiteCapture\`. To build a full installer `.exe`, install [Inno Setup 6](https://jrsoftware.org/isdl.php) — the build script will detect it and produce `installer_output\SiteCapture_Setup_v1.0.0.exe`.

### macOS (.app + .dmg)

```bash
chmod +x build_mac.sh
./build_mac.sh
```

Produces `dist/SiteCapture.app` and `SiteCapture.dmg`. On first launch, **right-click → Open** to bypass macOS Gatekeeper.

---

## File overview

| File | Purpose |
|------|---------|
| `main.py` | Desktop GUI (customtkinter) |
| `scraper.py` | Crawl engine, media downloader, media_map builder |
| `fix_links.py` | Post-processor: link rewriting, accordion fix, video replacement |
| `build_media_map.py` | One-time tool to populate media_map.json from existing downloads |
| `check_links.py` | Link auditor — reports broken, absolute, and external links |
| `config.py` | Shared configuration constants |
| `login.py` | Form-based login helper |
| `ai_assistant.py` | Claude API integration for site analysis |

---

## What's new vs. the original CLI tool

This project started from [website-downloader](https://github.com/PKHarsimran/website-downloader) by PKHarsimran — a Python CLI script for downloading websites. It has been substantially extended:

| Feature | Original | SiteCapture |
|---|---|---|
| Interface | CLI | Desktop GUI |
| Media downloads | No | YouTube, Vimeo, Wistia, and more via yt-dlp |
| Offline post-processing | No | Link rewriting, JS nav patching, video replacement |
| Authentication | No | Login form + browser cookie import |
| Project management | No | Per-project settings, logs, stats, resume |
| Auto-resume | No | Pages and video downloads resume from interruption |
| Stats tracking | No | Live counters for pages, videos, images, PDFs, bytes |
| AI analysis | No | Claude-powered crawl recommendations |
| Completion sound | No | Audio notification on finish |

---

## Legal disclaimer

This software is intended for **lawful personal archiving, offline access, research, and educational use only**.

**Do not use this tool to:**
- Download, reproduce, or distribute content you do not own or have permission to copy
- Circumvent paywalls or access controls to obtain content you have not licensed
- Scrape or harvest personal data without consent
- Violate a website's Terms of Service, robots.txt, or applicable law

**Users are solely responsible** for ensuring their use of this tool complies with all applicable laws and the terms of any website they download. The authors accept no liability for misuse.

Downloaded content remains the intellectual property of its original owners. Downloading does not transfer any rights.

---

## Credits

Developed by **Martin Pavion**

Built upon [website-downloader](https://github.com/PKHarsimran/website-downloader) by [PKHarsimran](https://github.com/PKHarsimran).

---

## License

[MIT](LICENSE) — free to use, modify, and distribute.
