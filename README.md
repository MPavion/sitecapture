# SiteCapture

A desktop app for downloading entire websites — HTML, images, videos, audio, PDFs, and other assets — with authentication, project management, and auto-resume.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

---

## Features

- **Full site crawl** — mirrors a website's folder structure to disk
- **Video downloads** — embedded YouTube, Vimeo, and Wistia videos via yt-dlp, with parallel fragment downloading
- **Authentication** — HTML form login, or browser cookie import (.txt / .json)
- **Project management** — per-project settings, logs, stats, and visited-URL tracking
- **Auto-resume** — interrupted scrapes and video downloads resume where they left off
- **AI analysis** — Claude-powered site analysis with depth and URL-pattern recommendations
- **Live stats panel** — pages, videos, images, PDFs, docs, audio, and total bytes downloaded

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

Click **?** next to the Cookies row for step-by-step instructions inside the app.

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

## Building a standalone executable

### Windows (.exe installer)

```bat
build.bat
```

Creates a portable folder at `dist\SiteCapture\`.

To build a full installer `.exe`, install [Inno Setup 6](https://jrsoftware.org/isdl.php) — the build script will detect it automatically and produce `installer_output\SiteCapture_Setup_v1.0.0.exe`.

### macOS (.app + .dmg)

```bash
chmod +x build_mac.sh
./build_mac.sh
```

Produces `dist/SiteCapture.app` and `SiteCapture.dmg`.

Open the `.dmg` and drag SiteCapture into your Applications folder to install. On first launch, **right-click the app → Open** to bypass macOS Gatekeeper (required for apps that are not notarized with Apple).

---

## What's new vs. the original CLI tool

This project started from [website-downloader](https://github.com/PKHarsimran/website-downloader) by PKHarsimran — a Python CLI script for downloading websites. It has been substantially extended into a full desktop GUI application with the following additions:

| Feature | Original | This app |
|---|---|---|
| Interface | CLI (command line) | Desktop GUI |
| Media downloads | No | Yes — embedded YouTube, Vimeo, Wistia via yt-dlp |
| Authentication | No | Login form + browser cookie import (.txt / .json) |
| Project management | No | Per-project settings, logs, stats, resume |
| Auto-resume | No | Pages and video downloads resume from interruption |
| Stats tracking | No | Live counters for pages, videos, images, PDFs, bytes |
| AI analysis | No | Claude-powered crawl recommendations |
| Concurrent media | No | Parallel fragment downloading for faster video |

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
