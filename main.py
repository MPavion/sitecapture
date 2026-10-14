import os
import logging
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox
from datetime import datetime
from urllib.parse import urlparse

import customtkinter as ctk

import config as cfg
import projects as prj
import scraper as sc
import login as lg
import cookie_extractor as ce
import ai_assistant as ai_mod

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VERSION = "1.0.0"

_STATUS_ICON = {
    "active":    ("●", "#4CAF50"),
    "paused":    ("⏸", "#FFC107"),
    "completed": ("✓", "#2196F3"),
    "archived":  ("▣", "#757575"),
}


def _fmt_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


class _Tip:
    """Lightweight hover tooltip for any tkinter/CTk widget."""
    def __init__(self, widget, text: str):
        self._win = None
        widget.bind("<Enter>", lambda e: self._show(widget, text), add="+")
        widget.bind("<Leave>", lambda e: self._hide(), add="+")

    def _show(self, widget, text):
        try:
            x = widget.winfo_rootx() + 14
            y = widget.winfo_rooty() + widget.winfo_height() + 6
            self._win = tk.Toplevel(widget)
            self._win.wm_overrideredirect(True)
            self._win.wm_geometry(f"+{x}+{y}")
            self._win.wm_attributes("-topmost", True)
            tk.Label(self._win, text=text, justify="left",
                     bg="#1c1c1c", fg="#d4d4d4", relief="solid", bd=1,
                     font=("Segoe UI", 9), padx=8, pady=5,
                     wraplength=320).pack()
        except Exception:
            pass

    def _hide(self):
        try:
            if self._win:
                self._win.destroy()
                self._win = None
        except Exception:
            pass


class App(ctk.CTk):

    # ── init ─────────────────────────────────────────────────────────────────

    def __init__(self):
        super().__init__()
        self.title(f"SiteCapture  v{VERSION}")
        self.geometry("1120x780")
        self.minsize(860, 600)

        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        self._cfg            = cfg.load()
        self._active_project = None
        self._running_pid    = None
        self._scraper        = None
        self._running        = False
        self._paused         = False
        self._login_session  = None
        self._file_logger    = None

        self._build_ui()
        self._refresh_sidebar()

        active = [p for p in prj.load_all() if p["status"] != "archived"]
        if active:
            self._select_project(active[0])
        else:
            self._set_status("Create a new project to begin.")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # header
        hdr = ctk.CTkFrame(self, corner_radius=0, height=44)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="SiteCapture",
                     font=ctk.CTkFont(size=17, weight="bold")).pack(side="left", padx=16)
        ctk.CTkLabel(hdr, text=f"v{VERSION}",
                     font=ctk.CTkFont(size=11), text_color="gray55").pack(side="left")
        ctk.CTkButton(hdr, text="About", width=68, height=28,
                      fg_color="transparent", hover_color=("gray75", "gray30"),
                      text_color=("gray20", "gray80"),
                      command=self._show_about).pack(side="right", padx=(0, 12))
        ctk.CTkButton(hdr, text="?  Help", width=76, height=28,
                      fg_color="transparent", hover_color=("gray75", "gray30"),
                      text_color=("gray20", "gray80"),
                      command=self._show_help).pack(side="right", padx=(0, 4))

        self._build_sidebar()
        self._build_right_panel()

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=230, corner_radius=0)
        sb.grid(row=1, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(1, weight=1)
        sb.grid_columnconfigure(0, weight=1)
        self._sidebar = sb

        top = ctk.CTkFrame(sb, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 4))
        ctk.CTkLabel(top, text="PROJECTS",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray55").pack(side="left")
        ctk.CTkButton(top, text="+ New", width=56, height=26,
                      font=ctk.CTkFont(size=12),
                      command=self._new_project).pack(side="right")

        self._proj_scroll = ctk.CTkScrollableFrame(sb, fg_color="transparent")
        self._proj_scroll.grid(row=1, column=0, sticky="nsew", padx=4)
        self._proj_scroll.grid_columnconfigure(0, weight=1)

        self._show_archived = False
        self._arch_toggle = ctk.CTkButton(
            sb, text="📦  Show archived", height=28,
            fg_color="transparent", hover_color=("gray75", "gray25"),
            text_color=("gray40", "gray65"), font=ctk.CTkFont(size=11),
            command=self._toggle_archived)
        self._arch_toggle.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 8))

    def _build_right_panel(self):
        right = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray92", "gray13"))
        right.grid(row=1, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        self._right = right

        # project name bar
        pbar = ctk.CTkFrame(right, corner_radius=0)
        pbar.grid(row=0, column=0, sticky="ew")
        pbar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(pbar, text="Project:",
                     font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=(14, 6), pady=8)
        self._proj_name_var = tk.StringVar(value="No project selected")
        self._proj_name_entry = ctk.CTkEntry(
            pbar, textvariable=self._proj_name_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=30, border_width=0, fg_color="transparent")
        self._proj_name_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._proj_name_entry.bind("<Return>",   lambda e: self._rename_project())
        self._proj_name_entry.bind("<FocusOut>", lambda e: self._rename_project())
        self._proj_name_entry.bind("<FocusIn>",  lambda e: self._proj_name_entry.configure(
            border_width=1, fg_color=("gray85", "gray20")))
        self._tip(self._proj_name_entry,
                  "Click to rename this project\nPress Enter or click away to save")
        self._archive_btn = ctk.CTkButton(
            pbar, text="Archive", width=80, height=28,
            fg_color="gray35", hover_color="gray45",
            command=self._archive_project)
        self._archive_btn.grid(row=0, column=2, padx=(0, 4))
        self._restore_btn = ctk.CTkButton(
            pbar, text="Restore", width=80, height=28,
            fg_color="#1a5276", hover_color="#2980b9",
            command=self._restore_project)
        self._restore_btn.grid(row=0, column=3, padx=(0, 8))
        self._restore_btn.grid_remove()

        # scrollable form + log area
        body = ctk.CTkFrame(right, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        self._build_form(body)
        self._build_log_area(body)

    def _build_form(self, parent):
        form = ctk.CTkFrame(parent, fg_color="transparent")
        form.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        form.grid_columnconfigure(0, weight=1)

        # URL
        r = self._hrow(form, 0)
        ctk.CTkLabel(r, text="URL", width=70, anchor="w").pack(side="left")
        self._url_var = tk.StringVar()
        _ue = ctk.CTkEntry(r, textvariable=self._url_var,
                           placeholder_text="https://example.com", height=32)
        _ue.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._tip(_ue, "Website URL to crawl and download\nMust start with http:// or https://")

        # Save to
        r = self._hrow(form, 1)
        ctk.CTkLabel(r, text="Save to", width=70, anchor="w").pack(side="left")
        self._out_var = tk.StringVar()
        _oe = ctk.CTkEntry(r, textvariable=self._out_var,
                           placeholder_text="Output folder", height=32)
        _oe.pack(side="left", fill="x", expand=True, padx=(6, 6))
        _ob = ctk.CTkButton(r, text="Browse", width=74, height=32,
                            command=self._browse_output)
        _ob.pack(side="left", padx=(0, 4))
        _mv = ctk.CTkButton(r, text="Move", width=56, height=32,
                            fg_color="gray35", hover_color="gray45",
                            command=self._move_folder)
        _mv.pack(side="left")
        self._tip(_oe, "Local folder where downloaded files will be saved")
        self._tip(_ob, "Browse for an output folder")
        self._tip(_mv, "Move the output folder to a new location\n(updates the project record)")

        # Login — username / password / login page URL
        r = self._hrow(form, 2)
        ctk.CTkLabel(r, text="Login", width=70, anchor="w").pack(side="left")
        self._username_var = tk.StringVar()
        _uu = ctk.CTkEntry(r, textvariable=self._username_var,
                           placeholder_text="Username or email",
                           height=32, width=165)
        _uu.pack(side="left", padx=(6, 6))
        self._password_var = tk.StringVar()
        _pw = ctk.CTkEntry(r, textvariable=self._password_var,
                           show="•", placeholder_text="Password",
                           height=32, width=125)
        _pw.pack(side="left", padx=(0, 6))
        self._login_url_var = tk.StringVar()
        _lu = ctk.CTkEntry(r, textvariable=self._login_url_var,
                           placeholder_text="Login page URL  (blank = auto-detect)",
                           height=32, width=222)
        _lu.pack(side="left", padx=(0, 6))
        self._login_btn = ctk.CTkButton(r, text="Login", width=68, height=32,
                                        command=self._do_login)
        self._login_btn.pack(side="left", padx=(0, 8))
        self._ck_label = ctk.CTkLabel(r, text="Not logged in",
                                      text_color="gray55",
                                      font=ctk.CTkFont(size=11))
        self._ck_label.pack(side="left")
        self._tip(_uu, "Your username or email address for the site")
        self._tip(_pw, "Password — used only to log in, never saved to disk")
        self._tip(_lu, "Direct URL of the login page\nLeave blank to auto-detect from the site's homepage")
        self._tip(self._login_btn, "Submit credentials and capture the session cookies\nfor use during scraping")

        # Cookies file — alternative when form login fails (JS sites, 2FA, etc.)
        r = self._hrow(form, 3)
        ctk.CTkLabel(r, text="Cookies", width=70, anchor="w").pack(side="left")
        self._v_ckfile = tk.StringVar()
        _ce = ctk.CTkEntry(r, textvariable=self._v_ckfile,
                           placeholder_text="cookies.txt exported from browser  (optional — use when Login above fails)",
                           height=32)
        _ce.pack(side="left", fill="x", expand=True, padx=(6, 6))
        _cb = ctk.CTkButton(r, text="Browse", width=68, height=32,
                            command=self._browse_cookies_file)
        _cb.pack(side="left", padx=(0, 4))
        _ch = ctk.CTkButton(r, text="?", width=28, height=32,
                            fg_color="gray35", hover_color="gray45",
                            command=self._show_cookie_help)
        _ch.pack(side="left")
        self._tip(_ce, "Path to a cookies.txt or .json file exported from your browser\nUse this when the Login form above doesn't work")
        self._tip(_cb, "Browse for a cookies.txt (Netscape) or .json file\nJSON files are auto-converted to Netscape format")
        self._tip(_ch, "Step-by-step instructions for exporting\ncookies from Chrome, Edge, or Firefox")

        # settings accordion
        self._settings_open = False
        acc = ctk.CTkFrame(form)
        acc.grid(row=4, column=0, sticky="ew", padx=0, pady=(4, 4))
        acc.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(acc, text="⚙  Settings", anchor="w", height=28,
                       fg_color="transparent", hover_color=("gray80", "gray28"),
                       text_color=("gray10", "gray95"),
                       command=self._toggle_settings).grid(
            row=0, column=0, sticky="ew", padx=4)
        self._settings_body = ctk.CTkFrame(acc, fg_color="transparent")
        self._settings_body.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        self._settings_body.grid_remove()
        self._build_settings_body()

        # buttons
        r = self._hrow(form, 5)
        self._start_btn = ctk.CTkButton(
            r, text="▶  Start", width=108, height=34, command=self._start)
        self._start_btn.pack(side="left", padx=(0, 5))
        self._pause_btn = ctk.CTkButton(
            r, text="⏸  Pause", width=108, height=34,
            state="disabled", fg_color="gray40", command=self._pause_resume)
        self._pause_btn.pack(side="left", padx=(0, 5))
        self._stop_btn = ctk.CTkButton(
            r, text="⏹  Stop", width=108, height=34,
            state="disabled", fg_color="#8B2222", command=self._stop_scrape)
        self._stop_btn.pack(side="left", padx=(0, 5))
        self._update_btn = ctk.CTkButton(
            r, text="↺  Update", width=108, height=34,
            fg_color="gray30", hover_color="gray40",
            command=self._update_project)
        self._update_btn.pack(side="left", padx=(0, 18))
        self._analyse_btn = ctk.CTkButton(
            r, text="✦ Analyse", width=108, height=34,
            fg_color="#1a4a6b", hover_color="#1f6091",
            command=self._analyse_site)
        self._analyse_btn.pack(side="left")
        self._tip(self._start_btn,  "Start crawling and downloading the website\nProgress is saved — you can stop and resume at any time")
        self._tip(self._pause_btn,  "Pause the scrape — all progress is saved\nClick again to resume")
        self._tip(self._stop_btn,   "Stop the scrape and save all progress\nInterrupted video downloads will resume next time")
        self._tip(self._update_btn, "Re-crawl the site from scratch\nSkips files already on disk — useful for updated content")
        self._tip(self._analyse_btn,"Use Claude AI to analyse the site structure\nand suggest optimal crawl depth and URL patterns")

        # progress
        r = self._hrow(form, 6)
        r.configure(fg_color="transparent")
        self._prog_bar = ctk.CTkProgressBar(r, height=10)
        self._prog_bar.pack(fill="x", expand=True)
        self._prog_bar.set(0)
        self._tip(self._prog_bar, "Overall download progress\nMay fluctuate as new pages are discovered during crawling")

        self._status_lbl = ctk.CTkLabel(
            form, text="Select or create a project to begin.",
            text_color="gray55", font=ctk.CTkFont(size=11), anchor="w")
        self._status_lbl.grid(row=7, column=0, sticky="ew", padx=12, pady=(2, 0))


    def _build_log_area(self, parent):
        lf = ctk.CTkFrame(parent, fg_color=("gray88", "gray15"))
        lf.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 10))
        lf.grid_columnconfigure(0, weight=1)
        lf.grid_rowconfigure(2, weight=1)

        hdr = ctk.CTkFrame(lf, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        ctk.CTkLabel(hdr, text="Log",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        _of = ctk.CTkButton(hdr, text="Open file", width=72, height=22,
                            fg_color="gray30", hover_color="gray40",
                            command=self._open_log_file)
        _of.pack(side="right")
        _cl = ctk.CTkButton(hdr, text="Clear", width=54, height=22,
                            fg_color="gray30", hover_color="gray40",
                            command=self._clear_log)
        _cl.pack(side="right", padx=(0, 4))
        self._tip(_of, "Open the full log file in a text editor")
        self._tip(_cl, "Clear the log panel\n(the log file on disk is not affected)")

        # stats bar
        sb = ctk.CTkFrame(lf, fg_color=("gray82", "gray20"), corner_radius=6)
        sb.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

        self._stat_widgets = {}
        stat_defs = [
            ("pages",     "Pages"),
            ("videos",    "Videos"),
            ("audio",     "Audio"),
            ("images",    "Images"),
            ("pdfs",      "PDFs"),
            ("documents", "Docs"),
            ("size",      "Downloaded"),
            ("errors",    "Errors"),
        ]
        for col, (key, label) in enumerate(stat_defs):
            sb.grid_columnconfigure(col, weight=1)
            cell = ctk.CTkFrame(sb, fg_color="transparent")
            cell.grid(row=0, column=col, padx=2, pady=6)
            val_lbl = ctk.CTkLabel(cell, text="—",
                                   font=ctk.CTkFont(size=15, weight="bold"))
            val_lbl.pack()
            ctk.CTkLabel(cell, text=label,
                         font=ctk.CTkFont(size=9),
                         text_color="gray55").pack()
            self._stat_widgets[key] = val_lbl

        self._log_box = ctk.CTkTextbox(
            lf, font=ctk.CTkFont(family="Courier New", size=10), wrap="word")
        self._log_box.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _build_settings_body(self):
        f = self._settings_body
        for w in f.winfo_children():
            w.destroy()
        f.grid_columnconfigure(0, weight=1)
        f.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(f, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw", padx=(0, 16))
        ctk.CTkLabel(left, text="Download types",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 4))
        self._v_html  = self._chk(left, "HTML pages",                "download_html",
                                   "Save the HTML of every crawled page")
        self._v_img   = self._chk(left, "Images",                   "download_images",
                                   "Download images (JPG, PNG, WebP, SVG, GIF, etc.)")
        self._v_vid   = self._chk(left, "Videos  (direct + yt-dlp)", "download_videos",
                                   "Download video files and embedded players\n(YouTube, Vimeo, Wistia, etc.) via yt-dlp")
        self._v_aud   = self._chk(left, "Audio   (direct + yt-dlp)", "download_audio",
                                   "Download audio files and embedded audio via yt-dlp")
        self._v_doc   = self._chk(left, "Documents & downloads",    "download_documents",
                                   "Download PDFs, Word, Excel, ZIP, and other attachments")
        self._v_css   = self._chk(left, "CSS / JS / Fonts",         "download_css_js",
                                   "Download stylesheets, scripts, and web font files")
        self._v_dom   = self._chk(left, "Stay on same domain",      "stay_on_domain",
                                   "Only follow links on the same domain as the start URL\nDisable to allow crawling across subdomains")

        right = ctk.CTkFrame(f, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nw")
        ctk.CTkLabel(right, text="Options",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self._v_depth  = self._spin(right, "Crawl depth",    1, "max_depth",
                                    "Levels of links to follow from the start URL\n1 = start page only  3 = default  0 = unlimited (use with care)")
        self._v_conc   = self._spin(right, "Concurrent dls", 2, "concurrent_downloads",
                                    "Number of parallel download threads\nHigher = faster, but heavier on the server")
        self._v_delay  = self._spin(right, "Delay (s)",      3, "delay_between_requests",
                                    "Seconds to wait between requests\n0 = maximum speed  0.5 = polite  1+ = very gentle")

        ctk.CTkLabel(right, text="AI Analysis",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(14, 4))
        ctk.CTkLabel(right, text="API key").grid(row=5, column=0, sticky="w", pady=2)
        self._v_apikey = tk.StringVar()
        api_e = ctk.CTkEntry(right, textvariable=self._v_apikey, show="•",
                              placeholder_text="sk-ant-…", width=188)
        api_e.grid(row=5, column=1, padx=(8, 0))
        api_e.bind("<Button-3>",
                   lambda e: api_e.configure(show="" if api_e.cget("show") else "•"))
        ctk.CTkLabel(right, text="Model").grid(row=6, column=0, sticky="w", pady=2)
        self._v_model = tk.StringVar(value="claude-sonnet-4-6")
        ctk.CTkOptionMenu(right, variable=self._v_model,
                          values=["claude-sonnet-4-6", "claude-opus-4-7"],
                          width=188).grid(row=6, column=1, padx=(8, 0))
        ctk.CTkLabel(right, text="Right-click key field to show/hide",
                     font=ctk.CTkFont(size=10), text_color="gray50").grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(2, 0))

        self._load_settings_from_source()

    # ── sidebar helpers ───────────────────────────────────────────────────────

    def _refresh_sidebar(self):
        for w in self._proj_scroll.winfo_children():
            w.destroy()

        all_p = prj.load_all()
        shown = [p for p in all_p
                 if self._show_archived or p["status"] != "archived"]

        for i, p in enumerate(shown):
            self._make_card(self._proj_scroll, p, i)

        self._arch_toggle.configure(
            text="📦  Hide archived" if self._show_archived else "📦  Show archived")

    def _make_card(self, parent, p: dict, row: int):
        is_sel = (self._active_project and
                  self._active_project.get("id") == p.get("id"))
        is_run = (p.get("id") == self._running_pid)

        status = "running" if is_run else p.get("status", "active")
        icon, color = _STATUS_ICON.get(status, ("○", "#9E9E9E"))
        bg = ("gray78", "gray25") if is_sel else ("gray85", "gray18")

        card = ctk.CTkFrame(parent, fg_color=bg, corner_radius=6)
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=2)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text=icon, text_color=color,
                     font=ctk.CTkFont(size=13), width=22).grid(
            row=0, column=0, padx=(8, 4), pady=(6, 0))

        name = p["name"]
        if len(name) > 23:
            name = name[:22] + "…"
        ctk.CTkLabel(card, text=name,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=0, column=1, sticky="ew", padx=(0, 8))

        lr  = (p.get("last_run") or p.get("created_at", ""))[:16]
        info = f"{lr}  ·  {p.get('pages', 0)}pg  {p.get('files', 0)}f"
        sub_color = "#4CAF50" if is_run else "gray50"
        sub_text  = "● running" if is_run else info
        ctk.CTkLabel(card, text=sub_text,
                     font=ctk.CTkFont(size=10), text_color=sub_color,
                     anchor="w").grid(row=1, column=0, columnspan=2,
                                      sticky="ew", padx=(10, 8), pady=(0, 6))

        def _click(e, proj=p):
            self._select_project(proj)

        for widget in [card] + card.winfo_children():
            widget.bind("<Button-1>", _click)

    def _toggle_archived(self):
        self._show_archived = not self._show_archived
        self._refresh_sidebar()

    # ── project operations ────────────────────────────────────────────────────

    def _new_project(self):
        url = self._url_var.get().strip()
        out = self._out_var.get().strip()
        if not url:
            messagebox.showerror("Missing URL",
                                  "Enter a URL in the URL field before creating a project.")
            return
        if not out:
            messagebox.showerror("Missing folder",
                                  "Select an output folder before creating a project.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self._url_var.set(url)

        p = prj.create(
            url=url,
            output_folder=out,
            settings=self._collect_settings(),
            username=self._username_var.get().strip(),
            login_url=self._login_url_var.get().strip(),
        )
        self._refresh_sidebar()
        self._select_project(p)

    def _select_project(self, p: dict):
        if self._active_project:
            self._save_project_from_ui()
        self._active_project = p
        self._proj_name_var.set(p["name"])
        self._url_var.set(p.get("url", ""))
        self._out_var.set(p.get("output_folder", ""))
        self._username_var.set(p.get("username", ""))
        self._password_var.set("")
        self._login_url_var.set(p.get("login_url", ""))
        self._ck_label.configure(text="Not logged in", text_color="gray55")
        self._login_session = None

        s = p.get("settings", {})
        self._apply_settings(s)
        self._update_stats_label(p)
        self._prog_bar.set(p.get("_progress", 0))

        archived = p.get("status") == "archived"
        self._archive_btn.grid() if not archived else self._archive_btn.grid_remove()
        self._restore_btn.grid() if archived else self._restore_btn.grid_remove()

        self._get_file_logger(p["id"])
        self._load_project_log(p)
        self._refresh_sidebar()

    def _save_project_from_ui(self):
        p = self._active_project
        if not p:
            return
        p["name"]          = self._proj_name_var.get().strip() or p["name"]
        p["url"]           = self._url_var.get().strip()
        p["output_folder"] = self._out_var.get().strip()
        p["username"]      = self._username_var.get().strip()
        p["login_url"]     = self._login_url_var.get().strip()
        p["settings"]      = self._collect_settings()
        prj.save(p)

    def _archive_project(self):
        if not self._active_project:
            return
        if self._running_pid == self._active_project["id"]:
            messagebox.showwarning("Running",
                                    "Stop the scrape before archiving this project.")
            return
        self._save_project_from_ui()
        prj.archive(self._active_project["id"])
        self._active_project["status"] = "archived"
        self._archive_btn.grid_remove()
        self._restore_btn.grid()
        self._refresh_sidebar()
        self._append_log("Project archived.")

    def _rename_project(self):
        if not self._active_project:
            return
        self._proj_name_entry.configure(border_width=0, fg_color="transparent")
        new_name = self._proj_name_var.get().strip()
        if not new_name:
            self._proj_name_var.set(self._active_project["name"])
            return
        if new_name != self._active_project["name"]:
            self._active_project["name"] = new_name
            prj.save(self._active_project)
            self._refresh_sidebar()
            self._set_status(f"Project renamed to \"{new_name}\"")

    def _restore_project(self):
        if not self._active_project:
            return
        prj.restore(self._active_project["id"])
        self._active_project["status"] = "active"
        self._restore_btn.grid_remove()
        self._archive_btn.grid()
        self._refresh_sidebar()
        self._append_log("Project restored.")

    def _move_folder(self):
        if not self._active_project:
            messagebox.showerror("No project", "Select a project first.")
            return
        new = filedialog.askdirectory(
            title="Move output to…",
            initialdir=self._out_var.get() or os.path.expanduser("~"))
        if not new:
            return
        ok, msg = prj.move_output(self._active_project["id"], new)
        if ok:
            self._out_var.set(new)
            self._active_project["output_folder"] = new
            self._append_log(f"✓ {msg}")
        else:
            messagebox.showerror("Move failed", msg)

    # ── settings helpers ──────────────────────────────────────────────────────

    def _collect_settings(self) -> dict:
        s = {
            "download_html":         self._v_html.get(),
            "download_images":       self._v_img.get(),
            "download_videos":       self._v_vid.get(),
            "download_audio":        self._v_aud.get(),
            "download_documents":    self._v_doc.get(),
            "download_css_js":       self._v_css.get(),
            "stay_on_domain":        self._v_dom.get(),
            "cookies_file":          self._v_ckfile.get().strip(),
        }
        for key, var in [("max_depth", self._v_depth),
                         ("concurrent_downloads", self._v_conc)]:
            try:
                s[key] = int(var.get())
            except ValueError:
                s[key] = self._cfg.get(key, 3)
        try:
            s["delay_between_requests"] = float(self._v_delay.get())
        except ValueError:
            s["delay_between_requests"] = 0.5

        self._cfg["anthropic_api_key"] = self._v_apikey.get().strip()
        self._cfg["ai_model"]          = self._v_model.get()
        cfg.save(self._cfg)
        return s

    def _apply_settings(self, s: dict):
        src = {**self._cfg, **s}
        self._v_html.set(src.get("download_html",      True))
        self._v_img.set(src.get("download_images",     True))
        self._v_vid.set(src.get("download_videos",     True))
        self._v_aud.set(src.get("download_audio",      True))
        self._v_doc.set(src.get("download_documents",  True))
        self._v_css.set(src.get("download_css_js",     True))
        self._v_dom.set(src.get("stay_on_domain",      True))
        self._v_depth.set(str(src.get("max_depth",                3)))
        self._v_conc.set(str(src.get("concurrent_downloads",      3)))
        self._v_delay.set(str(src.get("delay_between_requests", 0.5)))
        self._v_ckfile.set(src.get("cookies_file",               ""))
        self._v_apikey.set(self._cfg.get("anthropic_api_key",    ""))
        self._v_model.set(self._cfg.get("ai_model", "claude-sonnet-4-6"))

    def _load_settings_from_source(self):
        s = self._active_project.get("settings", {}) if self._active_project else {}
        self._apply_settings(s)

    # ── scrape actions ────────────────────────────────────────────────────────

    def _start(self, update=False):
        url = self._url_var.get().strip()
        out = self._out_var.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Enter a URL to scrape.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self._url_var.set(url)
        if not out:
            messagebox.showerror("Missing folder", "Select an output folder.")
            return

        # auto-create project if none selected
        if not self._active_project:
            self._new_project()
            if not self._active_project:
                return
        else:
            self._save_project_from_ui()

        settings = self._active_project.get("settings", {})
        combined = {**self._cfg, **settings}

        self._prog_bar.set(0)
        self._running_pid = self._active_project["id"]

        previsited:    set = set()
        pending_media: set = set()
        if not update:
            previsited    = prj.load_visited(self._active_project["id"])
            pending_media = prj.load_media_queue(self._active_project["id"])
            if previsited:
                self._append_log(
                    f"  ↺  Resuming — {len(previsited)} URLs already visited.")
            if pending_media:
                self._append_log(
                    f"  ↺  {len(pending_media)} interrupted video download(s) will resume.")
        else:
            prj.clear_media_queue(self._active_project["id"])

        def _save_vis(urls):
            prj.save_visited(self._running_pid, urls)

        def _save_mq(urls):
            prj.save_media_queue(self._running_pid, urls)

        def _stats(**kw):
            self.after(0, self._on_stats_update, kw)

        self._scraper = sc.Scraper(
            cfg=combined,
            on_log=self._append_log,
            on_progress=self._set_progress,
            on_status=self._set_status,
            on_done=self._on_done,
            on_stats=_stats,
            save_visited_cb=_save_vis,
            save_media_queue_cb=_save_mq,
        )
        if previsited:
            self._scraper.set_previsited(previsited)
        if pending_media:
            self._scraper.set_pending_media(pending_media)
        if self._login_session is not None:
            self._scraper.set_cookies_jar(self._login_session.cookies)

        self._running = True
        self._paused  = False
        self._start_btn.configure(state="disabled")
        self._update_btn.configure(state="disabled")
        self._pause_btn.configure(state="normal", text="⏸  Pause")
        self._stop_btn.configure(state="normal")
        self._refresh_sidebar()

        self._append_log(f"\n{'─'*50}")
        self._append_log(f"  Project : {self._active_project['name']}")
        self._append_log(f"  URL     : {url}")
        self._append_log(f"  Output  : {out}")
        if update:
            self._append_log("  Mode    : Update (re-crawl, skip existing files)")
        elif previsited:
            self._append_log(f"  Mode    : Resume ({len(previsited)} URLs pre-seeded)")
        else:
            self._append_log("  Mode    : Fresh start")
        self._append_log(f"{'─'*50}\n")

        self._scraper.start(url, out)

    def _update_project(self):
        """Re-crawl from scratch but skip already-downloaded files."""
        if not self._active_project:
            messagebox.showerror("No project", "Select a project first.")
            return
        prj.reset_stats(self._active_project["id"])
        prj.clear_media_queue(self._active_project["id"])
        self._active_project["pages"] = self._active_project["files"] = 0
        self._active_project["bytes"] = self._active_project["errors"] = 0
        self._start(update=True)

    def _pause_resume(self):
        if not self._scraper:
            return
        if self._paused:
            self._scraper.resume()
            self._paused = False
            self._pause_btn.configure(text="⏸  Pause")
        else:
            self._scraper.pause()
            self._paused = True
            self._pause_btn.configure(text="▶  Resume")
            if self._active_project:
                self._active_project["status"] = "paused"
                prj.save(self._active_project)
                self._refresh_sidebar()

    def _stop_scrape(self):
        if self._scraper:
            self._scraper.stop()
        if self._active_project:
            self._active_project["status"] = "paused"
            prj.save(self._active_project)
        self._set_idle_buttons()

    def _on_done(self):
        self._running = False
        if self._running_pid:
            p = prj.load(self._running_pid)
            if p:
                p["status"] = "completed"
                prj.save(p)
                if self._active_project and self._active_project["id"] == p["id"]:
                    self._active_project = p
        self._running_pid = None
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
        self.after(0, self._set_idle_buttons)
        self.after(0, self._refresh_sidebar)

    def _on_stats_update(self, kw: dict):
        if not self._active_project:
            return
        pid = self._active_project.get("id")
        if pid == self._running_pid:
            for key in ("pages", "files", "bytes", "errors",
                        "images", "videos", "audio", "pdfs", "documents", "css_js"):
                self._active_project[key] = kw.get(key, 0)
            self._update_stats_label(self._active_project)

    def _set_idle_buttons(self):
        self._running = False
        self._paused  = False
        self._start_btn.configure(state="normal")
        self._update_btn.configure(state="normal")
        self._pause_btn.configure(state="disabled", text="⏸  Pause")
        self._stop_btn.configure(state="disabled")

    # ── login ─────────────────────────────────────────────────────────────────

    def _do_login(self):
        url      = self._url_var.get().strip()
        username = self._username_var.get().strip()
        password = self._password_var.get()
        lurl     = self._login_url_var.get().strip()
        if not url and not lurl:
            messagebox.showerror("Missing URL", "Enter the site URL first.")
            return
        if not username:
            messagebox.showerror("Missing", "Enter your username or email.")
            return
        if not password:
            messagebox.showerror("Missing", "Enter your password.")
            return
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
            self._url_var.set(url)
        self._login_btn.configure(state="disabled", text="Logging in…")
        self._ck_label.configure(text="Connecting…", text_color="gray55")
        ua = self._cfg.get("user_agent", "Mozilla/5.0")

        def _bg():
            import requests as _r
            sess = _r.Session()
            sess.headers["User-Agent"] = ua
            target = lurl
            if not target:
                self.after(0, lambda: self._ck_label.configure(
                    text="Finding login page…", text_color="gray55"))
                target = lg.find_login_url(url, sess)
            if not target:
                self.after(0, lambda: self._on_login_done(
                    False, "Could not find a login page — enter the URL manually.", None))
                return
            self.after(0, lambda: self._ck_label.configure(
                text="Submitting…", text_color="gray55"))
            ok, msg = lg.attempt_login(target, username, password, sess)
            if ok:
                here  = os.path.dirname(os.path.abspath(__file__))
                cpath = os.path.join(here, "_cookies.txt")
                ce.save_netscape_from_jar(sess.cookies, cpath)
                self._v_ckfile.set(cpath)
                self.after(0, lambda: self._on_login_done(True, msg, sess))
            else:
                self.after(0, lambda: self._on_login_done(False, msg, None))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_login_done(self, ok: bool, msg: str, sess):
        self._login_btn.configure(state="normal", text="Login")
        short = msg[:70] + ("…" if len(msg) > 70 else "")
        if ok:
            self._login_session = sess
            self._ck_label.configure(text=f"✓ {short}", text_color="#4CAF50")
            self._append_log(f"  ✓ Login: {msg}")
        else:
            self._login_session = None
            self._ck_label.configure(text=f"✗ {short}", text_color="#F44336")
            self._append_log(f"  ✗ Login failed: {msg}")

    # ── AI analysis ───────────────────────────────────────────────────────────

    def _analyse_site(self):
        url = self._url_var.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Enter a URL to analyse.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self._url_var.set(url)
        api_key = self._v_apikey.get().strip()
        if not api_key:
            messagebox.showerror("No API key",
                                  "Add your Anthropic API key in Settings → AI Analysis.")
            return
        self._analyse_btn.configure(state="disabled", text="Analysing…")
        self._append_log(f"✦ Analysing {url}…")
        model = self._v_model.get()
        ua    = self._cfg.get("user_agent", "Mozilla/5.0")

        def _bg():
            import requests as _r
            try:
                resp = _r.get(url, timeout=15, headers={"User-Agent": ua})
                html = resp.text
            except Exception as e:
                self.after(0, lambda: self._on_analysis(
                    {"error": f"Could not fetch: {e}"}, url))
                return
            result = ai_mod.analyse(url, html, api_key, model)
            self.after(0, lambda: self._on_analysis(result, url))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_analysis(self, result: dict, url: str):
        self._analyse_btn.configure(state="normal", text="✦ Analyse")
        if "error" in result:
            self._append_log(f"  ✗ Analysis: {result['error']}")
            messagebox.showerror("Analysis failed", result["error"])
            return
        self._append_log(f"\n── AI Analysis {'─'*36}")
        self._append_log(f"  Type   : {result.get('site_type','')}  ({result.get('content_confidence','')})")
        if result.get("notes"):
            self._append_log(f"  Notes  : {result['notes']}")
        for w in result.get("warnings", []):
            self._append_log(f"  ⚠  {w}")
        inc = result.get("url_include_patterns", [])
        exc = result.get("url_exclude_patterns", [])
        depth = result.get("recommended_depth")
        if depth:   self._append_log(f"  Depth  : {depth}")
        if inc:     self._append_log(f"  Include: {', '.join(inc)}")
        if exc:     self._append_log(f"  Exclude: {', '.join(exc)}")
        self._append_log("─" * 56 + "\n")
        if depth or inc or exc:
            self._show_apply_dialog(result)

    def _show_apply_dialog(self, result: dict):
        win = ctk.CTkToplevel(self)
        win.title("Apply AI Recommendations")
        win.geometry("500x380")
        win.resizable(False, False)
        win.grab_set()
        win.lift()
        ctk.CTkLabel(win, text="AI Recommendations",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(14, 6))
        box = ctk.CTkTextbox(win, height=220,
                              font=ctk.CTkFont(family="Courier New", size=11))
        box.pack(fill="x", padx=16, pady=(0, 8))
        lines = []
        if result.get("site_type"):
            lines.append(f"Site type:  {result['site_type']}  (conf {result.get('content_confidence','')})")
        if result.get("notes"):
            lines.append(f"\n{result['notes']}")
        for w in result.get("warnings", []):
            lines.append(f"\n⚠  {w}")
        depth = result.get("recommended_depth")
        if depth:
            lines.append(f"\nCrawl depth: {depth}")
        inc = result.get("url_include_patterns", [])
        exc = result.get("url_exclude_patterns", [])
        if inc:
            lines.append("\nFollow patterns:\n  " + "\n  ".join(inc))
        if exc:
            lines.append("\nSkip patterns:\n  " + "\n  ".join(exc))
        box.insert("end", "\n".join(lines))
        box.configure(state="disabled")

        def _apply():
            if depth:
                self._v_depth.set(str(depth))
            if self._active_project is not None:
                self._active_project.setdefault("settings", {})
                self._active_project["settings"]["url_include_patterns"] = inc
                self._active_project["settings"]["url_exclude_patterns"] = exc
                if depth:
                    self._active_project["settings"]["max_depth"] = depth
                prj.save(self._active_project)
            self._append_log("  ✓ AI recommendations applied.")
            win.destroy()

        br = ctk.CTkFrame(win, fg_color="transparent")
        br.pack(pady=8)
        ctk.CTkButton(br, text="Apply", width=160, command=_apply).pack(
            side="left", padx=(0, 8))
        ctk.CTkButton(br, text="Dismiss", width=100, fg_color="gray35",
                       hover_color="gray45", command=win.destroy).pack(side="left")

    # ── log ───────────────────────────────────────────────────────────────────

    def _get_file_logger(self, pid: str):
        lpath = prj.log_path(pid)
        os.makedirs(os.path.dirname(lpath), exist_ok=True)
        logger = logging.getLogger(f"wd.{pid}")
        if not logger.handlers:
            logger.setLevel(logging.DEBUG)
            h = logging.FileHandler(lpath, encoding="utf-8")
            h.setFormatter(logging.Formatter(
                "%(asctime)s  %(levelname)-7s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"))
            logger.addHandler(h)
            logger.propagate = False
        self._file_logger = logger

    def _load_project_log(self, p: dict):
        self._clear_log()
        lpath = prj.log_path(p["id"])
        if os.path.isfile(lpath):
            try:
                with open(lpath, encoding="utf-8") as f:
                    lines = f.readlines()[-600:]
                self._log_box.insert("end", "".join(lines))
                self._log_box.see("end")
            except Exception:
                pass
        else:
            self._log_box.insert("end", "No log entries yet.\n")

    def _append_log(self, msg: str):
        ts  = datetime.now().strftime("%H:%M:%S")
        lvl = ("ERROR  " if ("✗" in msg or "error" in msg[:12].lower())
               else "WARN   " if "⚠" in msg
               else "INFO   ")
        line = f"{ts}  {lvl}  {msg}\n"
        if self._file_logger:
            try:
                if "ERROR" in lvl:
                    self._file_logger.error(msg)
                elif "WARN" in lvl:
                    self._file_logger.warning(msg)
                else:
                    self._file_logger.info(msg)
            except Exception:
                pass
        self.after(0, self._do_append, line)

    def _do_append(self, line: str):
        self._log_box.insert("end", line)
        self._log_box.see("end")

    def _clear_log(self):
        self._log_box.delete("1.0", "end")

    def _open_log_file(self):
        if not self._active_project:
            return
        lpath = prj.log_path(self._active_project["id"])
        if os.path.isfile(lpath):
            os.startfile(lpath)
        else:
            messagebox.showinfo("No log", "No log file yet for this project.")

    def _show_cookie_help(self):
        win = ctk.CTkToplevel(self)
        win.title("How to import cookies from your browser")
        win.geometry("640x560")
        win.resizable(True, True)
        win.grab_set()
        win.lift()
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(ico):
            try: win.iconbitmap(ico)
            except Exception: pass

        ctk.CTkLabel(win, text="Importing cookies from your browser",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(
            pady=(16, 2), padx=20, anchor="w")
        ctk.CTkLabel(win,
                     text="Use this when the Login form doesn't work.  Takes about 2 minutes.",
                     font=ctk.CTkFont(size=11), text_color="gray55").pack(
            padx=20, anchor="w")

        tabs = ctk.CTkTabview(win, height=450)
        tabs.pack(fill="both", expand=True, padx=12, pady=(8, 4))
        for name in ("What & Why", "Chrome & Edge", "Firefox", "Problems?"):
            tabs.add(name)

        def _page(name, text):
            tb = ctk.CTkTextbox(tabs.tab(name),
                                font=ctk.CTkFont(family="Segoe UI", size=11),
                                wrap="word")
            tb.pack(fill="both", expand=True)
            tb.insert("end", text.strip())
            tb.configure(state="disabled")

        _page("What & Why", """
WHAT IS A COOKIE?

When you log in to a website, your browser saves a small "hall pass"
called a cookie.  Every time you open a new page on that site, your
browser silently shows this hall pass to prove you're allowed in.

WHY DOES SITECAPTURE NEED IT?

SiteCapture needs a copy of your hall pass so it can download pages
that only logged-in users can see — course content, member articles,
private dashboards, and so on.

This is safe to do:
  ✓  Your actual password is never stored in the cookie file
  ✓  You are only sharing your own login session
  ✓  The file only works for the specific website it came from
  ✗  Do not share the cookies file with other people
  ✗  Delete it when you are finished downloading

WHEN SHOULD I USE THIS?

  •  The Login tab above tried but still shows "Login failed"
  •  The website uses "Sign in with Google / Apple / Facebook"
  •  You had to enter a code from your phone to log in (2FA)
  •  There was a CAPTCHA ("I am not a robot") test during login

HOW LONG WILL IT TAKE?

About 2 minutes the first time.
After that you can reuse the same file until the website
logs you out (usually after a few days or weeks).
""")

        _page("Chrome & Edge", """
These steps work the same way in Google Chrome and Microsoft Edge.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1  —  Add the free browser extension
           (you only need to do this once)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  In CHROME:
  1. Open a new tab.  In the address bar go to:
       chrome.google.com/webstore
  2. In the search box (top-left) type:
       Get cookies.txt LOCALLY
  3. Click the result — it is free, made by "Kai K"
  4. Click the blue  Add to Chrome  button
  5. A pop-up appears — click  Add extension
     A puzzle-piece icon 🧩 will appear in your toolbar ✓

  In EDGE:
  1. Click  ...  (the three dots, top-right corner)
  2. Click  Extensions  →  Get extensions for Microsoft Edge
  3. Search for:  Get cookies.txt LOCALLY
  4. Click  Get  →  Add extension  ✓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2  —  Log in to the website
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  6. Go to the website you want to download
  7. Log in with your username and password as normal
  8. Click around the site to confirm you are logged in
     and can see the content you want to download

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3  —  Export the cookie file
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  9. Click the  🧩  puzzle-piece icon (top-right of Chrome/Edge)
 10. Click  Get cookies.txt LOCALLY  in the list that appears
     (If you don't see it, click the  📌  pin icon next to it
     to make it permanently visible)
 11. A small pop-up window opens
 12. Click  Export  (or the download/arrow button)
 13. A "Save As" box appears
     → Save the file to your Desktop so it is easy to find
     → The filename will be something like  cookies.txt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4  —  Load the file into SiteCapture
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 14. Switch back to SiteCapture
 15. In the  Cookies  row, click the  Browse  button
 16. Navigate to your Desktop and select the  cookies.txt  file
 17. Click  ▶ Start

SiteCapture will now download the site as if you are logged in!
""")

        _page("Firefox", """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1  —  Add the free browser extension
           (you only need to do this once)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Open Firefox
  2. Click the  ☰  menu icon (top-right, three horizontal lines)
  3. Click  Add-ons and themes
  4. A new tab opens — in the search bar at the top, type:
       cookies.txt
  5. Find the result called  cookies.txt  by  Lennon Hill
  6. Click  Add to Firefox
  7. A pop-up appears — click  Add  to confirm
     A small icon appears near your address bar ✓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2  —  Log in to the website
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  8. Go to the website you want to download
  9. Log in with your username and password as normal
 10. Click around the site to confirm you are logged in
     and can see the content you want to download

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3  —  Export the cookie file
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 11. Look for the extension icon near your address bar
     It may look like a cookie 🍪 or a small grid icon
     If you cannot see it, click the  ☰  menu and look under
     More tools, or click the puzzle-piece 🧩 if visible
 12. Click the  cookies.txt  extension icon
 13. Make sure  Current Site  is shown at the top of the pop-up
 14. Click  Download
     → The file saves automatically to your Downloads folder
     → The filename will be something like  website.com_cookies.txt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4  —  Load the file into SiteCapture
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 15. Switch back to SiteCapture
 16. In the  Cookies  row, click the  Browse  button
 17. Open your Downloads folder and select the cookies file
 18. Click  ▶ Start

SiteCapture will now download the site as if you are logged in!
""")

        _page("Problems?", """
COMMON PROBLEMS AND FIXES

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"The download still shows me as not logged in"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your cookies may have expired (your hall pass ran out).

  → Go back to the website in your browser
  → Make sure you are still logged in — if not, log in again
  → Export fresh cookies by repeating Steps 2 and 3
  → In SiteCapture, click Browse and choose the new file
  → Try starting the download again

Also check: did you export from exactly the right website?
Cookies only work for the site they came from.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"I cannot find the extension icon"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Chrome / Edge:
  → Click the  🧩  puzzle-piece icon (top-right of browser)
    — all your extensions are listed there
  → Click the  📌  pin icon next to the extension name
    to make it always visible in your toolbar

  Firefox:
  → Click  ☰  →  Add-ons and themes  →  Extensions
    and confirm the extension is switched on (blue toggle)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"The file I downloaded is .json, not .txt"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

No problem — SiteCapture accepts .json files too.
Just browse to the .json file and it will be converted
automatically.  Nothing extra to do.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"I don't use Chrome, Edge, or Firefox"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

We recommend downloading one of these (all free):
  Chrome:   google.com/chrome
  Edge:     microsoft.com/edge  (already installed on Windows)
  Firefox:  firefox.com

Mac / Safari users: try the "Cookie Quick Manager" extension
or export cookies via Safari → Develop → Web Inspector
(you will need to enable the Develop menu in Safari settings first).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"Is this safe?"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✓  Your password is NOT in the cookie file
  ✓  You are only sharing your own login session
  ✗  Do not share the .txt file with other people
  ✗  Anyone with the file could access your account
  ✗  Delete the file when you are finished downloading
""")

        ctk.CTkButton(win, text="Close", width=90,
                      command=win.destroy).pack(pady=(0, 10))

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _hrow(self, parent, r):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=r, column=0, sticky="ew", padx=0, pady=3)
        f.grid_columnconfigure(0, weight=1)
        return f

    def _chk(self, parent, text, key, tip: str = ""):
        var = tk.BooleanVar(value=bool(self._cfg.get(key, True)))
        chk = ctk.CTkCheckBox(parent, text=text, variable=var)
        chk.pack(anchor="w", pady=1)
        if tip:
            self._tip(chk, tip)
        return var

    def _spin(self, parent, label, row, key, tip: str = ""):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar(value=str(self._cfg.get(key, "")))
        e = ctk.CTkEntry(parent, textvariable=var, width=70)
        e.grid(row=row, column=1, padx=(8, 0))
        if tip:
            self._tip(e, tip)
        return var

    def _toggle_settings(self):
        if self._settings_open:
            self._settings_body.grid_remove()
        else:
            self._settings_body.grid()
        self._settings_open = not self._settings_open

    def _browse_output(self):
        d = filedialog.askdirectory(
            title="Select output folder",
            initialdir=self._out_var.get() or os.path.expanduser("~"))
        if d:
            self._out_var.set(d)

    def _browse_cookies_file(self):
        p = filedialog.askopenfilename(
            title="Select cookies file",
            filetypes=[("Cookie files", "*.txt *.json"),
                       ("Text files", "*.txt"),
                       ("JSON files", "*.json"),
                       ("All files", "*.*")])
        if not p:
            return
        if p.lower().endswith(".json"):
            try:
                out, msg = ce.json_to_netscape(p)
                self._v_ckfile.set(out)
                self._append_log(f"  ✓  Cookies: {msg}")
            except Exception as e:
                messagebox.showerror("Conversion failed",
                                     f"Could not convert JSON cookies:\n{e}")
        else:
            self._v_ckfile.set(p)

    def _set_progress(self, pct: int):
        self.after(0, lambda: self._prog_bar.set(pct / 100))

    def _set_status(self, text: str):
        self.after(0, lambda: self._status_lbl.configure(text=text))

    def _update_stats_label(self, p: dict):
        def _fmt(n):
            return str(n) if n else "—"

        w = self._stat_widgets
        w["pages"].configure(text=_fmt(p.get("pages", 0)))
        w["videos"].configure(text=_fmt(p.get("videos", 0)))
        w["audio"].configure(text=_fmt(p.get("audio", 0)))
        w["images"].configure(text=_fmt(p.get("images", 0)))
        w["pdfs"].configure(text=_fmt(p.get("pdfs", 0)))
        w["documents"].configure(text=_fmt(p.get("documents", 0)))
        b = p.get("bytes", 0)
        w["size"].configure(text=_fmt_bytes(b) if b else "—")
        errs = p.get("errors", 0)
        w["errors"].configure(
            text=_fmt(errs),
            text_color="#F44336" if errs else ("gray70", "gray70"))

    def _tip(self, widget, text: str):
        _Tip(widget, text)

    def _show_about(self):
        win = ctk.CTkToplevel(self)
        win.title("About SiteCapture")
        win.geometry("400x310")
        win.resizable(False, False)
        win.grab_set()
        win.lift()
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(ico):
            try: win.iconbitmap(ico)
            except Exception: pass

        ctk.CTkLabel(win, text="SiteCapture",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(24, 4))
        ctk.CTkLabel(win, text=f"Version {VERSION}",
                     font=ctk.CTkFont(size=12), text_color="gray55").pack()

        ctk.CTkFrame(win, height=1, fg_color="gray30").pack(fill="x", padx=40, pady=16)

        ctk.CTkLabel(win, text="Developed by Martin Pavion",
                     font=ctk.CTkFont(size=13, weight="bold")).pack()
        ctk.CTkLabel(win, text="Built upon website-downloader by PKHarsimran",
                     font=ctk.CTkFont(size=11), text_color="gray55").pack(pady=(6, 2))
        ctk.CTkLabel(win, text="Released under the MIT License",
                     font=ctk.CTkFont(size=11), text_color="gray55").pack()

        ctk.CTkFrame(win, height=1, fg_color="gray30").pack(fill="x", padx=40, pady=12)

        ctk.CTkLabel(win,
                     text="For lawful personal archiving and offline access only.\n"
                          "Users are responsible for compliance with applicable laws\n"
                          "and the Terms of Service of any site they download.",
                     font=ctk.CTkFont(size=10), text_color="gray50",
                     justify="center").pack(padx=20)

        ctk.CTkFrame(win, height=1, fg_color="gray30").pack(fill="x", padx=40, pady=12)

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack()
        ctk.CTkButton(btn_row, text="Original Project", width=140, height=28,
                      fg_color="gray30", hover_color="gray40",
                      command=lambda: webbrowser.open(
                          "https://github.com/PKHarsimran/website-downloader")
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Legal", width=70, height=28,
                      fg_color="gray30", hover_color="gray40",
                      command=lambda: [win.destroy(), self._show_help()]
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Close", width=70, height=28,
                      command=win.destroy).pack(side="left")

    def _show_help(self):
        win = ctk.CTkToplevel(self)
        win.title("Help — SiteCapture")
        win.geometry("600x520")
        win.resizable(True, True)
        win.grab_set()
        win.lift()
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(ico):
            try: win.iconbitmap(ico)
            except Exception: pass

        tabs = ctk.CTkTabview(win, height=450)
        tabs.pack(fill="both", expand=True, padx=12, pady=(8, 4))
        for name in ("Quick Start", "Settings", "Authentication", "Tips", "Legal"):
            tabs.add(name)

        def _page(name, text):
            tb = ctk.CTkTextbox(tabs.tab(name),
                                font=ctk.CTkFont(family="Segoe UI", size=11),
                                wrap="word")
            tb.pack(fill="both", expand=True)
            tb.insert("end", text.strip())
            tb.configure(state="disabled")

        _page("Quick Start", """
QUICK START

1.  Enter the website URL in the URL field
2.  Choose an output folder with Browse
3.  Click  ▶ Start

The scraper follows every link from the start page and downloads
HTML, images, videos, documents, and other assets into a folder
structure that mirrors the site.

─────────────────────────────────────────────────────────
PROJECTS

Each scrape is saved as a named project. Use the sidebar to
switch between projects. Settings, logs, and progress are kept
separately per project.

─────────────────────────────────────────────────────────
RESUMING

If you Stop a scrape (or the app closes unexpectedly), progress
is saved automatically. Click Start again to pick up exactly
where you left off — already-crawled pages are skipped and
interrupted video downloads resume from the byte they stopped at.

─────────────────────────────────────────────────────────
UPDATING

Click  ↺ Update  to re-crawl the site from scratch but skip any
files already on disk. Use this to grab new content on a site
you've downloaded before.
""")

        _page("Settings", """
DOWNLOAD TYPES

  HTML pages          Save the HTML of each crawled page
  Images              JPG, PNG, WebP, SVG, GIF, etc.
  Videos              Direct video files plus embedded players
                      (YouTube, Vimeo, Wistia, etc.) via yt-dlp
  Audio               MP3, WAV, OGG, and embedded audio
  Documents           PDFs, Word, Excel, ZIP, and other attachments
  CSS / JS / Fonts    Stylesheets, scripts, and web fonts

─────────────────────────────────────────────────────────
CRAWL OPTIONS

  Crawl depth         Link levels to follow from the start URL
                      1 = start page only
                      3 = three hops deep  (default)
                      0 = unlimited  (be careful — large sites!)

  Concurrent dls      Parallel download threads  (default: 3)
                      Higher is faster but heavier on the server.

  Delay (s)           Wait between requests  (default: 0.5 s)
                      0 = maximum speed
                      0.5 = polite
                      1–2 = very gentle, good for slow servers

  Stay on domain      Only follow links on the same domain.
                      Disable to allow crawling across subdomains.

─────────────────────────────────────────────────────────
AI ANALYSIS

Enter an Anthropic API key in Settings and click  ✦ Analyse.
The AI inspects the homepage and recommends:
  • Crawl depth
  • URL patterns to follow or skip
  • Site type and any authentication warnings
Click Apply in the results dialog to set the options automatically.
""")

        _page("Authentication", """
OPTION 1 — LOGIN FORM  (simplest)

Fill in Username and Password, then click  Login.
The app auto-detects the login page on the site.
If auto-detection fails, paste the exact login page URL into the
third field.

Works for:   standard HTML form logins.
Won't work:  JavaScript SPAs, two-factor auth, CAPTCHA.

─────────────────────────────────────────────────────────
OPTION 2 — BROWSER COOKIES  (most reliable)

Log in via your real browser, then hand the session to the app.

  Step 1  Install a browser extension:
            Chrome / Edge:  "Get cookies.txt LOCALLY"
            Firefox:        "cookies.txt"

  Step 2  Log in to the website normally in your browser.

  Step 3  Click the extension icon → export cookies for that
          site.  Netscape .txt format or JSON are both fine.

  Step 4  Click Browse in the Cookies row and select the file.
          JSON files are converted automatically.

  Step 5  Click  ▶ Start  — cookies are applied to every request.

─────────────────────────────────────────────────────────
TROUBLESHOOTING

  Redirect loops     Your cookies may have expired.
                     Re-export fresh cookies and try again.

  Empty pages        The site may use JavaScript rendering.
                     Cookie export usually resolves this too.

  CAPTCHA / 2FA      The Login form cannot handle these.
                     Use browser cookie export instead.
""")

        _page("Tips", """
SPEED

  • Increase Concurrent downloads for faster crawling.
  • Set Delay to 0 for maximum speed on your own servers.
  • Videos download multiple segments in parallel automatically
    — no extra configuration needed.

─────────────────────────────────────────────────────────
LARGE SITES

  • Set Crawl depth to 2–3 to avoid runaway crawling.
  • Enable Stay on same domain to ignore external links.
  • Use  ✦ Analyse  to get AI-suggested URL include/exclude
    patterns — these can cut the crawl to just the content
    you actually want.
  • Use  ↺ Update  to refresh without re-downloading existing
    files.

─────────────────────────────────────────────────────────
JAVASCRIPT-HEAVY SITES

  • Pages may appear empty if the site renders in the browser.
    Browser cookie export (see Authentication) often fixes this.
  • Embedded Wistia / Vimeo / YouTube videos are extracted
    from the page source automatically — even when there are
    no visible <iframe> tags — using yt-dlp.

─────────────────────────────────────────────────────────
LOG FILE

  • Each project has its own log at:  projects/<id>/scrape.log
  • Click  Open file  in the log panel to view it in full.
  • The stats bar at the top of the log panel updates live
    during a scrape.
""")

        _page("Legal", """
IMPORTANT — PLEASE READ BEFORE USE

This software is provided as a tool for lawful personal archiving,
offline access, research, and educational purposes only.

─────────────────────────────────────────────────────────
YOUR RESPONSIBILITY

By using this software you accept full responsibility for how
you use it.  The authors and contributors accept no liability
for any misuse or for any consequences arising from use of
this tool.

─────────────────────────────────────────────────────────
WHAT THIS TOOL IS NOT FOR

  ✗  Downloading, reproducing, or distributing content that
     you do not own or do not have explicit permission to copy

  ✗  Circumventing paywalls or access controls to obtain
     content you have not legitimately paid for or licensed

  ✗  Scraping or harvesting personal data, email addresses,
     or other private information without consent

  ✗  Any activity that violates the target website's
     Terms of Service, Privacy Policy, or applicable law

  ✗  Commercial redistribution of downloaded content
     without the rights holder's permission

─────────────────────────────────────────────────────────
WHAT THIS TOOL IS FOR

  ✓  Archiving websites you own or manage

  ✓  Creating offline copies of content you have licensed
     or have explicit permission to download

  ✓  Web development and testing against a local mirror

  ✓  Personal, non-commercial offline access to freely
     available public content

─────────────────────────────────────────────────────────
ROBOTS.TXT AND RATE LIMITS

Many websites publish a robots.txt file that describes which
parts of the site automated tools should not access.  Please
respect these instructions and use the Delay setting to avoid
placing excessive load on servers.

─────────────────────────────────────────────────────────
COPYRIGHT

Downloaded content remains the intellectual property of its
original owners. Downloading does not transfer any rights.

This software is released under the MIT License.
Copyright (c) 2026 Martin Pavion.
Built upon website-downloader by PKHarsimran.
""")

        ctk.CTkButton(win, text="Close", width=90,
                      command=win.destroy).pack(pady=(0, 10))

    def _on_close(self):
        self._save_project_from_ui()
        if self._scraper and self._running:
            self._scraper.stop()
        self.destroy()


if __name__ == "__main__":
    import make_icon
    make_icon.make()
    app = App()
    app.mainloop()
