import asyncio
import logging
import os
import sys
import threading
import tkinter as tk
import webbrowser
import ctypes
import tempfile
import json
import subprocess # Needed for restarting the app
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

# --- New UI Library ---
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox, filedialog 

# Third-party dependencies
import aiohttp
from PIL import Image, ImageTk, ImageDraw, ImageSequence

# --- Video Engine (VLC) ---
try:
    import vlc
    _test_instance = vlc.Instance()
    VIDEO_PLAYER_AVAILABLE = True
except (ImportError, OSError, NameError):
    VIDEO_PLAYER_AVAILABLE = False

# --- Configuration ---
APP_VERSION = "v1.2.0" 
GITHUB_REPO = "jptrx/4chan-Media-Scraper"
API_BASE = "https://a.4cdn.org"
IMG_BASE = "https://i.4cdn.org"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
SETTINGS_FILE = "settings.json"

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ChanGUI")

def get_resource_path(relative_path):
    """ Robustly find the path to a resource file. """
    try:
        # PyInstaller _MEIPASS
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        
        # Nuitka and Dev candidates
        candidates = [
            # 1. Look relative to the script/module (Nuitka __file__)
            os.path.dirname(os.path.abspath(__file__)),
            # 2. Look in the sys.prefix (Nuitka extraction root)
            sys.prefix,
            # 3. Look relative to the executable (if frozen)
            os.path.dirname(sys.executable),
            # 4. Look in current working directory
            os.getcwd()
        ]
        
        for base in candidates:
            check_path = os.path.join(base, relative_path)
            if os.path.exists(check_path):
                return check_path
                
    except Exception:
        pass
        
    # Fallback
    return os.path.abspath(relative_path)

@dataclass
class MediaItem:
    tim: int
    ext: str
    filename: str
    board: str
    fsize: int = 0  # Added file size tracking
    
    @property
    def full_url(self) -> str:
        return f"{IMG_BASE}/{self.board}/{self.tim}{self.ext}"
    
    @property
    def thumb_url(self) -> str:
        return f"{IMG_BASE}/{self.board}/{self.tim}s.jpg"
    
    @property
    def local_filename(self) -> str:
        return f"{self.tim}{self.ext}"
    
    @property
    def is_video(self) -> bool:
        return self.ext.lower() in ['.webm', '.mp4']

    @property
    def is_gif(self) -> bool:
        return self.ext.lower() == '.gif'

class AsyncWorker:
    """Handles async network tasks in a separate thread."""
    def __init__(self, loop):
        self.loop = loop
        self.session = None

    async def init_session(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})

    async def close_session(self):
        if self.session:
            await self.session.close()

    async def fetch_json(self, url):
        async with self.session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return None

    async def fetch_image_bytes(self, url):
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.read()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
        return None

    async def download_to_temp(self, url, suffix):
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.read()
                    fd, path = tempfile.mkstemp(suffix=suffix)
                    with os.fdopen(fd, 'wb') as tmp:
                        tmp.write(data)
                    return path
        except Exception as e:
            logger.error(f"Failed to download temp video: {e}")
        return None

    # --- Updater Logic ---
    async def check_update(self):
        if not self.session: return None
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        try:
            async with self.session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    latest_tag = data.get("tag_name", "").strip()
                    
                    if latest_tag:
                        def parse_version(v_str):
                            try:
                                return tuple(map(int, v_str.lstrip('v').split('.')))
                            except ValueError:
                                return (0, 0, 0)
                        
                        remote_ver = parse_version(latest_tag)
                        local_ver = parse_version(APP_VERSION)

                        if remote_ver > local_ver:
                            return data
        except Exception as e:
            logger.error(f"Update check failed: {e}")
        return None

    async def download_file(self, url, dest_path):
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    with open(dest_path, 'wb') as f:
                        while True:
                            chunk = await response.content.read(1024*1024)
                            if not chunk: break
                            f.write(chunk)
                    return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
        return False

class ChanScraperApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        self.title("4chan Media Scraper")
        self.geometry("1100x850")
        self.minsize(800, 600)
        
        if sys.platform == 'win32':
            try:
                myappid = 'opensource.chanscraper.gui.1.1.0'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

        self.icon_path = get_resource_path("icon.ico")
        try:
            if os.path.exists(self.icon_path):
                self.iconbitmap(self.icon_path)
        except Exception as e:
            logger.error(f"Failed to load icon: {e}")

        self.settings = self.load_settings()

        self.loop = asyncio.new_event_loop()
        self.worker = AsyncWorker(self.loop)
        self.thread = threading.Thread(target=self._start_async_loop, daemon=True)
        self.thread.start()
        
        self.media_items = []
        self.selected_items = set() 
        self.thumbnails = {}
        self.board = ""
        self.thread_id = ""
        self.context_menu_target = None

        self._init_ui()
        self._run_async(self.worker.init_session())

        # Auto-Update Check on Startup
        if self.settings.get("check_updates", True):
            self.after(2000, lambda: self.check_updates(silent=True))

    def _start_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run_async(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def load_settings(self):
        default_settings = {
            "download_path": str(Path.home() / "Downloads" / "4chan Media Scraper"),
            "auto_load": False,
            "use_subdirs": True,
            "check_updates": True 
        }
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f:
                    saved_settings = json.load(f)
                    default_settings.update(saved_settings)
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
        return default_settings

    def save_settings(self):
        settings = {
            "download_path": self.path_var.get(),
            "auto_load": self.autoload_var.get(),
            "use_subdirs": self.use_subdirs_var.get(),
            "check_updates": self.autocheck_var.get()
        }
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def _init_ui(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Thread in Browser", command=self.open_thread_browser) # New Item
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Check for Updates", command=lambda: self.check_updates(silent=False))
        
        self.autocheck_var = tk.BooleanVar(value=self.settings.get("check_updates", True))
        help_menu.add_checkbutton(label="Check on Startup", onvalue=True, offvalue=False, variable=self.autocheck_var, command=self.save_settings)
        
        help_menu.add_separator()
        help_menu.add_command(label="View Help", command=self.show_help)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self.show_about)

        # Shortcuts
        self.bind("<Control-a>", lambda e: self.select_all())
        self.bind("<Control-d>", lambda e: self.deselect_all())

        control_frame = ttk.Frame(self, padding=10)
        control_frame.pack(fill=X)

        ttk.Label(control_frame, text="Thread URL:").pack(side=LEFT, padx=5)
        self.url_entry = ttk.Entry(control_frame, width=60)
        self.url_entry.pack(side=LEFT, padx=5, expand=True, fill=X)
        self.url_entry.bind("<Return>", lambda e: self.load_thread())

        self.autoload_var = tk.BooleanVar(value=self.settings.get("auto_load", False))
        ttk.Checkbutton(control_frame, text="Auto-load", variable=self.autoload_var, bootstyle="round-toggle").pack(side=LEFT, padx=10)

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Paste", command=self.paste_from_clipboard)
        
        self.url_entry.bind("<Button-3>", lambda e: self.show_context_menu(e, self.url_entry))
        self.url_entry.bind("<<Paste>>", self.on_paste_event)

        load_btn = ttk.Button(control_frame, text="Load Thread", command=self.load_thread, bootstyle="primary")
        load_btn.pack(side=LEFT, padx=5)

        info_frame = ttk.Frame(self, padding=(10, 0, 10, 5))
        info_frame.pack(fill=X)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(info_frame, textvariable=self.status_var, bootstyle="secondary").pack(side=LEFT)
        
        btn_frame = ttk.Frame(info_frame)
        btn_frame.pack(side=RIGHT)
        ttk.Button(btn_frame, text="Select All (Ctrl+A)", command=self.select_all, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(btn_frame, text="Deselect All (Ctrl+D)", command=self.deselect_all, bootstyle="secondary-outline").pack(side=LEFT, padx=2)

        self.canvas_frame = ttk.Frame(self)
        self.canvas_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#ffffff", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview, bootstyle="round")
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.scrollbar.pack(side=RIGHT, fill=Y)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        action_frame = ttk.Frame(self, padding=15)
        action_frame.pack(fill=X, side=BOTTOM)

        left_panel = ttk.Frame(action_frame)
        left_panel.pack(side=LEFT, fill=X)

        ttk.Label(left_panel, text="Save to:").pack(side=LEFT)
        self.path_var = tk.StringVar(value=self.settings.get("download_path", ""))
        self.path_entry = ttk.Entry(left_panel, textvariable=self.path_var, width=40)
        self.path_entry.pack(side=LEFT, padx=5)
        self.path_entry.bind("<Button-3>", lambda e: self.show_context_menu(e, self.path_entry))

        ttk.Button(left_panel, text="Browse...", command=self.browse_folder, bootstyle="secondary").pack(side=LEFT)
        ttk.Separator(left_panel, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=15)

        self.use_subdirs_var = tk.BooleanVar(value=self.settings.get("use_subdirs", True))
        ttk.Checkbutton(left_panel, text="Create Thread Folder", variable=self.use_subdirs_var).pack(side=LEFT)

        right_panel = ttk.Frame(action_frame)
        right_panel.pack(side=RIGHT)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(right_panel, variable=self.progress_var, maximum=100, length=150, mode='determinate', bootstyle="success-striped")
        self.progress_bar.pack(side=LEFT, padx=10)

        self.download_btn = ttk.Button(right_panel, text="Download Selected (0)", command=self.start_download, state=DISABLED, bootstyle="success")
        self.download_btn.pack(side=LEFT)

    def open_thread_browser(self):
        url = self.url_entry.get().strip()
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("Info", "No thread URL loaded.")

    # --- Updater Functions ---
    def check_updates(self, silent=False):
        if not silent:
            self.status_var.set("Checking for updates...")
        self._run_async(self._process_update_check(silent))

    async def _process_update_check(self, silent):
        update_data = await self.worker.check_update()
        self.after(0, lambda: self._show_update_ui(update_data, silent))

    def _show_update_ui(self, update_data, silent):
        if update_data:
            self.show_update_dialog(update_data)
        elif not silent:
            # Show custom Up to Date dialog instead of messagebox
            self.show_uptodate_dialog()
            self.status_var.set("Ready")

    def show_uptodate_dialog(self):
        """Custom 'Up to Date' Dialog with correct Icon."""
        up_win = ttk.Toplevel(self)
        up_win.title("Up to Date")
        up_win.geometry("400x200")
        up_win.resizable(False, False)
        
        try:
            if os.path.exists(self.icon_path):
                up_win.iconbitmap(self.icon_path)
        except: pass
        
        # Center Window
        x = self.winfo_x() + (self.winfo_width() // 2) - 200
        y = self.winfo_y() + (self.winfo_height() // 2) - 100
        up_win.geometry(f"+{x}+{y}")

        frame = ttk.Frame(up_win, padding=20)
        frame.pack(fill=BOTH, expand=True)

        try:
            if os.path.exists(self.icon_path):
                with Image.open(self.icon_path) as img:
                    img = img.convert("RGBA")
                    pil_img = img.resize((48, 48), Image.Resampling.LANCZOS)
                    tk_icon = ImageTk.PhotoImage(pil_img)
                    icon_lbl = ttk.Label(frame, image=tk_icon)
                    icon_lbl.image = tk_icon
                    icon_lbl.grid(row=0, column=0, rowspan=2, padx=(0, 15))
            else:
                ttk.Label(frame, text="✅", font=("Segoe UI", 32)).grid(row=0, column=0, rowspan=2, padx=(0, 15))
        except Exception:
            ttk.Label(frame, text="✅", font=("Segoe UI", 32)).grid(row=0, column=0, rowspan=2, padx=(0, 15))

        ttk.Label(frame, text="You are up to date!", font=("Segoe UI", 12, "bold"), bootstyle="success").grid(row=0, column=1, sticky="w")
        ttk.Label(frame, text=f"Version {APP_VERSION} is the latest release.", font=("Segoe UI", 10)).grid(row=1, column=1, sticky="nw")

        ttk.Button(frame, text="OK", command=up_win.destroy, width=10, bootstyle="success-outline").grid(row=2, column=0, columnspan=2, pady=(20, 0))

    def show_update_dialog(self, data):
        upd_win = ttk.Toplevel(self)
        upd_win.title("Update Available")
        upd_win.geometry("500x450")
        
        try:
            if os.path.exists(self.icon_path):
                upd_win.iconbitmap(self.icon_path)
        except: pass
        
        x = self.winfo_x() + (self.winfo_width() // 2) - 250
        y = self.winfo_y() + (self.winfo_height() // 2) - 225
        upd_win.geometry(f"+{x}+{y}")

        frame = ttk.Frame(upd_win, padding=20)
        frame.pack(fill=BOTH, expand=True)

        tag = data.get("tag_name", "New Version")
        ttk.Label(frame, text=f"A new version {tag} is available!", font=("Segoe UI", 12, "bold"), bootstyle="primary").pack(anchor="w", pady=(0, 10))

        ttk.Label(frame, text="Release Notes:", font=("Segoe UI", 10)).pack(anchor="w")

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=BOTH, expand=True, pady=5)
        
        body = data.get("body", "No release notes provided.")
        notes_text = tk.Text(text_frame, height=10, font=("Segoe UI", 9), wrap="word", bg="white", relief="flat")
        notes_text.insert("1.0", body)
        notes_text.configure(state="disabled")
        
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=notes_text.yview)
        notes_text.configure(yscrollcommand=scroll.set)
        
        notes_text.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        ttk.Label(frame, text="Do you want to update now?", font=("Segoe UI", 10)).pack(pady=10)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=X)
        
        def do_update():
            upd_win.destroy()
            self._trigger_update(data)

        ttk.Button(btn_frame, text="Update Now", command=do_update, bootstyle="success").pack(side=LEFT, expand=True, padx=5, fill=X)
        ttk.Button(btn_frame, text="Later", command=upd_win.destroy, bootstyle="secondary").pack(side=LEFT, expand=True, padx=5, fill=X)

    def _trigger_update(self, data):
        self.status_var.set("Downloading update...")
        self._run_async(self._perform_update(data))

    async def _perform_update(self, data):
        is_frozen = getattr(sys, 'frozen', False)
        download_url = None
        target_filename = ""
        
        if is_frozen:
            assets = data.get("assets", [])
            for asset in assets:
                if asset["name"].endswith(".exe"):
                    download_url = asset["browser_download_url"]
                    target_filename = "update.new"
                    break
        else:
            download_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{data['tag_name']}/chan_scraper.py"
            target_filename = "chan_scraper.py"

        if not download_url:
            self.after(0, lambda: messagebox.showerror("Error", "Could not find a suitable update file."))
            self.after(0, lambda: self.status_var.set("Update failed."))
            return

        success = await self.worker.download_file(download_url, target_filename)
        
        if success:
            self.after(0, lambda: self._apply_update(target_filename, is_frozen))
        else:
            self.after(0, lambda: messagebox.showerror("Error", "Failed to download update."))
            self.after(0, lambda: self.status_var.set("Update failed."))

    def _apply_update(self, new_file, is_frozen):
        if is_frozen:
            current_exe = sys.executable
            batch_script = f"""
@echo off
timeout /t 2 /nobreak > NUL
del "{current_exe}"
move "{new_file}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
            with open("updater.bat", "w") as f:
                f.write(batch_script)
            subprocess.Popen("updater.bat", shell=True)
            self.quit()
        else:
            messagebox.showinfo("Update Complete", "The application will now restart.")
            python = sys.executable
            os.execl(python, python, *sys.argv)

    def show_context_menu(self, event, widget):
        self.context_menu_target = widget
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def paste_from_clipboard(self):
        if self.context_menu_target:
            try:
                self.context_menu_target.event_generate("<<Paste>>")
                if self.context_menu_target == self.url_entry and self.autoload_var.get():
                    self.after(50, self.load_thread)
            except Exception as e:
                logger.error(f"Paste failed: {e}")

    def on_paste_event(self, event):
        if self.autoload_var.get():
            self.after(50, self.load_thread)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def parse_url(self, url):
        try:
            parsed = urlparse(url)
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 3 and parts[1] == "thread":
                return parts[0], parts[2]
        except:
            pass
        return None, None

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)

    def load_thread(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.board, self.thread_id = self.parse_url(url)
        if not self.board:
            self.status_var.set("Invalid URL format")
            return
        self.status_var.set(f"Fetching thread /{self.board}/{self.thread_id}...")
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.media_items.clear()
        self.selected_items.clear()
        self.thumbnails.clear()
        self.update_download_btn()
        self.progress_var.set(0)
        self._run_async(self._async_load_thread())

    async def _async_load_thread(self):
        api_url = f"{API_BASE}/{self.board}/thread/{self.thread_id}.json"
        data = await self.worker.fetch_json(api_url)
        if not data:
            self.after(0, lambda: messagebox.showerror("Error", "Thread not found or API error"))
            self.after(0, lambda: self.status_var.set("Error fetching thread"))
            return
        posts = data.get('posts', [])
        seen_tim = set()
        for post in posts:
            if 'tim' in post and 'ext' in post:
                if post['tim'] not in seen_tim:
                    item = MediaItem(
                        tim=post['tim'], 
                        ext=post['ext'], 
                        filename=post.get('filename', ''), 
                        board=self.board, 
                        fsize=post.get('fsize', 0) # Added File Size
                    )
                    self.media_items.append(item)
                    seen_tim.add(post['tim'])
        self.after(0, lambda: self.status_var.set(f"Found {len(self.media_items)} items. Loading thumbnails..."))
        self.after(0, self.render_grid_placeholders)
        await self._fetch_thumbnails()

    def render_grid_placeholders(self):
        cols = 5
        for i, item in enumerate(self.media_items):
            row = i // cols
            col = i % cols
            frame = tk.Frame(self.scrollable_frame, bg="white", bd=2, relief=tk.FLAT)
            frame.grid(row=row, column=col, padx=5, pady=5)
            frame.item = item
            frame.bind("<Button-1>", lambda e, f=frame, it=item: self.toggle_selection(f, it))
            frame.bind("<Button-3>", lambda e, f=frame, it=item: self.open_preview(f, it))
            lbl = tk.Label(frame, text="Loading...", width=20, height=10, bg="#f0f0f0")
            lbl.pack()
            lbl.bind("<Button-1>", lambda e, f=frame, it=item: self.toggle_selection(f, it))
            lbl.bind("<Button-3>", lambda e, f=frame, it=item: self.open_preview(f, it))
            frame.lbl = lbl

    def open_preview(self, frame_widget, item):
        p_win = ttk.Toplevel(self)
        p_win.title(f"Preview: {item.filename}{item.ext}")
        p_win.geometry("900x750")
        try:
            if os.path.exists(self.icon_path):
                p_win.iconbitmap(self.icon_path)
        except: pass
        content_frame = tk.Frame(p_win, bg="black")
        content_frame.pack(fill=BOTH, expand=True)
        status_lbl = tk.Label(content_frame, text="Loading...", bg="black", fg="white", font=("Segoe UI", 12))
        status_lbl.place(relx=0.5, rely=0.5, anchor="center")
        btn_frame = ttk.Frame(p_win, padding=10)
        btn_frame.pack(fill=X, side=BOTTOM)
        def update_btn_state():
            if item.tim in self.selected_items:
                sel_btn.configure(text="DESELECT ITEM", bootstyle="danger")
            else:
                sel_btn.configure(text="SELECT ITEM", bootstyle="success")
        def toggle_and_update():
            self.toggle_selection(frame_widget, item)
            update_btn_state()
        sel_btn = ttk.Button(btn_frame, command=toggle_and_update)
        sel_btn.pack(fill=X, ipady=5)
        update_btn_state()
        if item.is_video:
            status_lbl.configure(text="Initializing VLC...")
            if VIDEO_PLAYER_AVAILABLE:
                self._run_async(self._setup_vlc_player(item.full_url, item.ext, content_frame, status_lbl, p_win))
            else:
                status_lbl.configure(text="VLC Media Player not found!\nPlease install VLC or use the button below.")
                browser_btn = ttk.Button(btn_frame, text="Open in Browser", command=lambda: webbrowser.open(item.full_url), bootstyle="info-outline")
                browser_btn.pack(fill=X, ipady=3, pady=(5,0), side=TOP)
        else:
            status_lbl.pack_forget()
            img_lbl = tk.Label(content_frame, bg="black")
            img_lbl.pack(fill=BOTH, expand=True)
            self._run_async(self._fetch_preview(item.full_url, img_lbl, p_win))

    async def _setup_vlc_player(self, url, ext, video_panel, status_lbl, window):
        temp_path = await self.worker.download_to_temp(url, ext)
        if not temp_path:
            self.after(0, lambda: status_lbl.configure(text="Video Download Failed"))
            return
        self.after(0, lambda: self._embed_vlc(video_panel, status_lbl, temp_path, window))

    def _embed_vlc(self, video_panel, status_lbl, video_path, window):
        if not window.winfo_exists():
            try: os.remove(video_path)
            except: pass
            return
        status_lbl.place_forget()
        try:
            instance = vlc.Instance()
            player = instance.media_player_new()
            if sys.platform == "win32":
                player.set_hwnd(video_panel.winfo_id())
            else:
                player.set_xwindow(video_panel.winfo_id())
            media = instance.media_new(video_path)
            player.set_media(media)
            player.play()
            def cleanup():
                player.stop()
                try:
                    if os.path.exists(video_path):
                        os.remove(video_path)
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
                window.destroy()
            window.protocol("WM_DELETE_WINDOW", cleanup)
        except Exception as e:
            logger.error(f"VLC Error: {e}")
            status_lbl.configure(text=f"Error initializing VLC:\n{e}")
            status_lbl.place(relx=0.5, rely=0.5, anchor="center")

    async def _fetch_preview(self, url, label, window):
        data = await self.worker.fetch_image_bytes(url)
        self.after(0, lambda: self._display_preview_image(data, label, window))

    def _display_preview_image(self, data, label, window):
        if not window.winfo_exists(): return
        if not data:
            label.configure(text="Failed to load image.")
            return
        try:
            pil_img = Image.open(BytesIO(data))
            if getattr(pil_img, "is_animated", False):
                self._animate_gif(pil_img, label, window)
                return
            win_w = window.winfo_width()
            win_h = window.winfo_height() - 120 
            if win_w <= 1: win_w = 800
            if win_h <= 1: win_h = 600
            img_w, img_h = pil_img.size
            ratio = min(win_w/img_w, win_h/img_h)
            if ratio < 1:
                new_size = (int(img_w * ratio), int(img_h * ratio))
                pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
            elif ratio > 1 and img_w < 400:
                 new_size = (int(img_w * 2), int(img_h * 2))
                 pil_img = pil_img.resize(new_size, Image.Resampling.NEAREST)
            tk_img = ImageTk.PhotoImage(pil_img)
            label.configure(image=tk_img, text="")
            label.image = tk_img
        except Exception as e:
            logger.error(f"Preview Display Error: {e}")
            label.configure(text="Error displaying image")

    def _animate_gif(self, pil_img, label, window):
        frames = ImageSequence.Iterator(pil_img)
        def stream(iterator):
            if not window.winfo_exists(): return
            try:
                frame = next(iterator)
            except StopIteration:
                iterator = ImageSequence.Iterator(pil_img)
                frame = next(iterator)
            win_w = window.winfo_width()
            win_h = window.winfo_height() - 120 
            if win_w <= 1: win_w = 800
            if win_h <= 1: win_h = 600
            img_w, img_h = frame.size
            ratio = min(win_w/img_w, win_h/img_h)
            if ratio < 1:
                new_size = (int(img_w * ratio), int(img_h * ratio))
                frame = frame.resize(new_size, Image.Resampling.BOX)
            elif ratio > 1 and img_w < 400:
                 new_size = (int(img_w * 2), int(img_h * 2))
                 frame = frame.resize(new_size, Image.Resampling.BOX)
            tk_img = ImageTk.PhotoImage(frame)
            label.configure(image=tk_img, text="")
            label.image = tk_img
            duration = frame.info.get('duration', 100)
            if duration < 20: duration = 20 
            label.after(duration, lambda: stream(iterator))
        stream(frames)

    async def _fetch_thumbnails(self):
        chunk_size = 10
        for i in range(0, len(self.media_items), chunk_size):
            chunk = self.media_items[i:i+chunk_size]
            tasks = [self.worker.fetch_image_bytes(item.thumb_url) for item in chunk]
            results = await asyncio.gather(*tasks)
            self.after(0, lambda res=results, idx=i: self.update_thumbnails(res, idx))

    def update_thumbnails(self, image_data_list, start_index):
        children = self.scrollable_frame.winfo_children()
        for i, data in enumerate(image_data_list):
            if not data: continue
            widget_idx = start_index + i
            if widget_idx >= len(children): break
            frame = children[widget_idx]
            try:
                pil_img = Image.open(BytesIO(data))
                pil_img.thumbnail((150, 150)) 
                if frame.item.is_video or frame.item.is_gif:
                    draw = ImageDraw.Draw(pil_img)
                    ext_text = frame.item.ext.upper().lstrip('.')
                    color = "#0984e3" if frame.item.is_gif else "red"
                    draw.rectangle([0, 0, 40, 15], fill=color)
                    draw.text((2, 1), ext_text, fill="white")
                tk_img = ImageTk.PhotoImage(pil_img)
                frame.lbl.configure(image=tk_img, text="", width=0, height=0, bg="white")
                self.thumbnails[frame.item.tim] = tk_img
            except Exception as e:
                logger.error(f"Error loading thumb: {e}")
        self.status_var.set(f"Loaded {min(start_index + len(image_data_list), len(self.media_items))}/{len(self.media_items)} thumbnails")

    def toggle_selection(self, frame, item):
        if item.tim in self.selected_items:
            self.selected_items.remove(item.tim)
            frame.configure(bg="white", relief=tk.FLAT)
        else:
            self.selected_items.add(item.tim)
            frame.configure(bg="#4CAF50", relief=tk.SOLID)
        self.update_download_btn()

    def select_all(self):
        for frame in self.scrollable_frame.winfo_children():
            if hasattr(frame, 'item'):
                self.selected_items.add(frame.item.tim)
                frame.configure(bg="#4CAF50", relief=tk.SOLID)
        self.update_download_btn()

    def deselect_all(self):
        self.selected_items.clear()
        for frame in self.scrollable_frame.winfo_children():
            frame.configure(bg="white", relief=tk.FLAT)
        self.update_download_btn()

    # --- UPDATED: Show Size in Button ---
    def update_download_btn(self):
        count = len(self.selected_items)
        
        # Calculate total size in bytes
        total_bytes = sum(item.fsize for item in self.media_items if item.tim in self.selected_items)
        
        # Format size
        if total_bytes < 1024 * 1024:
            size_str = f"{total_bytes / 1024:.1f} KB"
        else:
            size_str = f"{total_bytes / (1024 * 1024):.1f} MB"
            
        if count > 0:
            self.download_btn.configure(text=f"Download Selected ({count}) - {size_str}", state=NORMAL, bootstyle="success")
        else:
            self.download_btn.configure(text=f"Download Selected ({count})", state=DISABLED, bootstyle="success")

    def start_download(self):
        target_dir = Path(self.path_var.get())
        use_subdirs = self.use_subdirs_var.get()
        if use_subdirs:
            save_path = target_dir / self.board / self.thread_id
        else:
            save_path = target_dir
        try:
            save_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not create folder: {e}")
            return
        items_to_download = [i for i in self.media_items if i.tim in self.selected_items]
        self.download_btn.configure(state=DISABLED)
        self.status_var.set(f"Starting download...")
        self.progress_var.set(0)
        self._run_async(self._download_files(items_to_download, save_path))

    async def _download_files(self, items, save_path):
        success_count = 0
        total_items = len(items)
        for i, item in enumerate(items):
            filepath = save_path / item.local_filename
            if filepath.exists():
                success_count += 1
            else:
                data = await self.worker.fetch_image_bytes(item.full_url)
                if data:
                    try:
                        with open(filepath, "wb") as f:
                            f.write(data)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Write error: {e}")
            progress = ((i + 1) / total_items) * 100
            self.after(0, lambda p=progress: self.progress_var.set(p))
            self.after(0, lambda c=success_count, t=total_items: self.status_var.set(f"Downloading: {c}/{t}"))
        self.after(0, lambda: messagebox.showinfo("Complete", f"Downloaded {success_count} files to:\n{save_path}"))
        self.after(0, lambda: self.status_var.set("Ready"))
        self.after(0, self.update_download_btn)
        self.after(0, lambda: self.progress_var.set(0))

    def on_close(self):
        self.save_settings()
        if self.worker.session:
            self._run_async(self.worker.close_session())
        self.destroy()

    def show_about(self):
        about_win = ttk.Toplevel(self)
        about_win.title("About")
        about_win.geometry("450x250")
        about_win.resizable(False, False)
        try:
            if os.path.exists(self.icon_path):
                about_win.iconbitmap(self.icon_path)
        except: pass
        x = self.winfo_x() + (self.winfo_width() // 2) - 225
        y = self.winfo_y() + (self.winfo_height() // 2) - 125
        about_win.geometry(f"+{x}+{y}")
        frame = ttk.Frame(about_win, padding=20)
        frame.pack(fill=BOTH, expand=True)
        try:
            if os.path.exists(self.icon_path):
                with Image.open(self.icon_path) as img:
                    img = img.convert("RGBA")
                    pil_img = img.resize((64, 64), Image.Resampling.LANCZOS)
                    tk_icon = ImageTk.PhotoImage(pil_img)
                    icon_lbl = ttk.Label(frame, image=tk_icon)
                    icon_lbl.image = tk_icon
                    icon_lbl.grid(row=0, column=0, rowspan=4, padx=(0, 20), sticky="n")
            else:
                ttk.Label(frame, text="🍀", font=("Segoe UI", 32)).grid(row=0, column=0, rowspan=4, padx=(0, 20))
        except Exception:
            ttk.Label(frame, text="🍀", font=("Segoe UI", 32)).grid(row=0, column=0, rowspan=4, padx=(0, 20))
        ttk.Label(frame, text="4chan Media Scraper", font=("Segoe UI", 14, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(frame, text=f"Version {APP_VERSION}", font=("Segoe UI", 10)).grid(row=1, column=1, sticky="w")
        ttk.Label(frame, text="\nCopyright © 2025 Juha Tanskanen", font=("Segoe UI", 9)).grid(row=2, column=1, sticky="w")
        ttk.Label(frame, text="Released under MIT License", font=("Segoe UI", 9)).grid(row=3, column=1, sticky="w")
        link_lbl = ttk.Label(frame, text="GitHub Repository", font=("Segoe UI", 9, "underline"), bootstyle="primary", cursor="hand2")
        link_lbl.grid(row=4, column=1, sticky="w", pady=(10, 0))
        link_lbl.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/jptrx/4chan-Media-Scraper"))
        ttk.Button(frame, text="OK", command=about_win.destroy, bootstyle="primary-outline").grid(row=5, column=0, columnspan=2, pady=(20, 0))

    def show_help(self):
        help_win = ttk.Toplevel(self)
        help_win.title("Help & Instructions")
        help_win.geometry("600x500")
        try:
            if os.path.exists(self.icon_path):
                help_win.iconbitmap(self.icon_path)
        except: pass
        help_text = """4chan Media Scraper - User Guide

1. Find a Thread
   - Go to 4chan and copy the URL of a thread you like.
   - Example: https://boards.4chan.org/g/thread/123456

2. Load the Thread
   - Paste the URL into the top box (Right-click > Paste).
   - Click "Load Thread".
   - Tip: Check "Auto-load" to load immediately after pasting.

3. Select Media
   - Thumbnails will appear in the grid.
   - Left-Click an image to Select/Deselect it (Green border = Selected).
   - Right-Click an image to see a Full-Size Preview.
   - Videos now play directly inside the preview window!

4. Download
   - Choose your download folder at the bottom.
   - Click "Download Selected" to save files.
   - "Create Thread Folder" will create a subfolder for organization.

Troubleshooting:
   - If downloads fail, check your internet connection.
   - If the compiled .exe is flagged by Antivirus, this is a false positive due to the unsigned executable.
"""
        text_widget = tk.Text(help_win, wrap=tk.WORD, padx=10, pady=10, font=("Segoe UI", 10), bg="white", relief="flat")
        text_widget.pack(expand=True, fill=BOTH)
        text_widget.insert(tk.END, help_text)
        text_widget.configure(state=DISABLED)

if __name__ == "__main__":
    app = ChanScraperApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()