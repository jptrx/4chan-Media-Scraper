import asyncio
import logging
import os
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tkinter import messagebox, ttk, filedialog
from urllib.parse import urlparse

# Third-party dependencies
# pip install aiohttp Pillow
import aiohttp
from PIL import Image, ImageTk, ImageDraw

# --- Configuration ---
API_BASE = "https://a.4cdn.org"
IMG_BASE = "https://i.4cdn.org"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ChanGUI")

@dataclass
class MediaItem:
    tim: int
    ext: str
    filename: str
    board: str
    
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
        return self.ext.lower() in ['.webm', '.mp4', '.gif']

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

class ChanScraperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("4chan Media Scraper")
        self.geometry("1100x850")
        self.minsize(800, 600)
        
        # Async Setup
        self.loop = asyncio.new_event_loop()
        self.worker = AsyncWorker(self.loop)
        self.thread = threading.Thread(target=self._start_async_loop, daemon=True)
        self.thread.start()
        
        # Data
        self.media_items = []
        self.selected_items = set() # Stores tim (int)
        self.thumbnails = {} # Stores tk images to prevent garbage collection
        self.board = ""
        self.thread_id = ""

        self._init_ui()
        self._run_async(self.worker.init_session())

    def _start_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run_async(self, coro):
        """Schedule a coroutine in the background loop."""
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def _init_ui(self):
        # Styles
        style = ttk.Style()
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("TLabel", font=("Segoe UI", 10))
        
        # 1. Top Control Panel
        control_frame = ttk.Frame(self, padding=10)
        control_frame.pack(fill=tk.X)

        ttk.Label(control_frame, text="Thread URL:").pack(side=tk.LEFT, padx=5)
        self.url_entry = ttk.Entry(control_frame, width=60)
        self.url_entry.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        self.url_entry.bind("<Return>", lambda e: self.load_thread())

        # Auto-load Checkbox
        self.autoload_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(control_frame, text="Auto-load", variable=self.autoload_var).pack(side=tk.LEFT, padx=5)

        # Right-click Menu Setup
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Paste", command=self.paste_from_clipboard)
        self.url_entry.bind("<Button-3>", self.show_context_menu)
        
        # Bind paste event (Ctrl+V)
        self.url_entry.bind("<<Paste>>", self.on_paste_event)

        load_btn = ttk.Button(control_frame, text="Load Thread", command=self.load_thread)
        load_btn.pack(side=tk.LEFT, padx=5)

        # 2. Status & Selection Info
        info_frame = ttk.Frame(self, padding=(10, 0, 10, 5))
        info_frame.pack(fill=tk.X)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(info_frame, textvariable=self.status_var, foreground="gray").pack(side=tk.LEFT)
        
        btn_frame = ttk.Frame(info_frame)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Select All", command=self.select_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Deselect All", command=self.deselect_all).pack(side=tk.LEFT, padx=2)

        # 3. Scrollable Canvas for Thumbnails
        self.canvas_frame = ttk.Frame(self)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#f0f0f0")
        self.scrollbar = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Mousewheel scroll
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # 4. Bottom Action Panel
        action_frame = ttk.Frame(self, padding=15)
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # Left Side: Path & Options
        left_panel = ttk.Frame(action_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.X)

        ttk.Label(left_panel, text="Save to:").pack(side=tk.LEFT)
        self.path_var = tk.StringVar(value=str(Path.home() / "Downloads" / "ChanScraper"))
        ttk.Entry(left_panel, textvariable=self.path_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(left_panel, text="Browse...", command=self.browse_folder).pack(side=tk.LEFT)
        
        # Separator
        ttk.Separator(left_panel, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Directory Structure Option
        self.use_subdirs_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left_panel, text="Create Thread Folder", variable=self.use_subdirs_var).pack(side=tk.LEFT)

        # Right Side: Progress & Download
        right_panel = ttk.Frame(action_frame)
        right_panel.pack(side=tk.RIGHT)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(right_panel, variable=self.progress_var, maximum=100, length=150, mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, padx=10)

        self.download_btn = ttk.Button(right_panel, text="Download Selected (0)", command=self.start_download, state=tk.DISABLED)
        self.download_btn.pack(side=tk.LEFT)

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def paste_from_clipboard(self):
        # Programmatically trigger paste event so our binding catches it
        self.url_entry.event_generate("<<Paste>>")

    def on_paste_event(self, event):
        if self.autoload_var.get():
            # Wait 50ms for text to be inserted, then load
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
            # Silent fail on auto-load if empty/invalid during typing, 
            # but user can see status
            self.status_var.set("Invalid URL format")
            return

        self.status_var.set(f"Fetching thread /{self.board}/{self.thread_id}...")
        
        # Clear existing
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
                        board=self.board
                    )
                    self.media_items.append(item)
                    seen_tim.add(post['tim'])
        
        self.after(0, lambda: self.status_var.set(f"Found {len(self.media_items)} items. Loading thumbnails..."))
        self.after(0, self.render_grid_placeholders)
        
        # Fetch thumbnails in parallel
        await self._fetch_thumbnails()

    def render_grid_placeholders(self):
        """Create the grid structure first."""
        cols = 5
        for i, item in enumerate(self.media_items):
            row = i // cols
            col = i % cols
            
            # Container frame for each image
            frame = tk.Frame(self.scrollable_frame, bg="white", bd=2, relief=tk.FLAT)
            frame.grid(row=row, column=col, padx=5, pady=5)
            frame.item = item # link item to widget
            
            # Click event (Left Click)
            frame.bind("<Button-1>", lambda e, f=frame, it=item: self.toggle_selection(f, it))
            
            # Right Click event (Preview)
            frame.bind("<Button-3>", lambda e, f=frame, it=item: self.open_preview(f, it))
            
            # Placeholder Label
            lbl = tk.Label(frame, text="Loading...", width=20, height=10, bg="#ddd")
            lbl.pack()
            
            # Bind events to label too so they bubble up or work directly
            lbl.bind("<Button-1>", lambda e, f=frame, it=item: self.toggle_selection(f, it))
            lbl.bind("<Button-3>", lambda e, f=frame, it=item: self.open_preview(f, it))
            
            frame.lbl = lbl # store reference

    def open_preview(self, frame_widget, item):
        """Opens a larger preview window for the item."""
        p_win = tk.Toplevel(self)
        p_win.title(f"Preview: {item.filename}{item.ext}")
        p_win.geometry("800x700")
        
        # Image Area
        img_lbl = tk.Label(p_win, text="Loading...", bg="black", fg="white")
        img_lbl.pack(expand=True, fill=tk.BOTH)
        
        # Control Area
        btn_frame = tk.Frame(p_win, padx=10, pady=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Define logic to update button appearance
        def update_btn_state():
            if item.tim in self.selected_items:
                sel_btn.configure(text="DESELECT ITEM", bg="#ffdddd", fg="red")
            else:
                sel_btn.configure(text="SELECT ITEM", bg="#ddffdd", fg="green")

        def toggle_and_update():
            # Toggle in main app
            self.toggle_selection(frame_widget, item)
            # Update local button
            update_btn_state()

        sel_btn = tk.Button(btn_frame, command=toggle_and_update, font=("Segoe UI", 12, "bold"))
        sel_btn.pack(fill=tk.X, ipady=10)
        
        # Set initial state
        update_btn_state()

        # Handle Video Files (WebM, etc)
        if item.is_video:
            # For videos, we can't display the full file in Tkinter easily.
            # We show the thumbnail and an "Open in Browser" button.
            play_btn = tk.Button(btn_frame, text="▶ Play Video in Browser", command=lambda: webbrowser.open(item.full_url))
            play_btn.pack(fill=tk.X, ipady=5, pady=5, side=tk.TOP)
            
            img_lbl.configure(text="Video Preview\n(Showing Thumbnail)")
            
            # Fetch the thumbnail for the preview window
            self._run_async(self._fetch_preview(item.thumb_url, img_lbl, p_win))
        else:
            # Start fetch of full image
            self._run_async(self._fetch_preview(item.full_url, img_lbl, p_win))

    async def _fetch_preview(self, url, label, window):
        data = await self.worker.fetch_image_bytes(url)
        # Pass data to main thread for rendering
        self.after(0, lambda: self._display_preview_image(data, label, window))

    def _display_preview_image(self, data, label, window):
        if not window.winfo_exists(): return
        
        if not data:
            label.configure(text="Failed to load image.")
            return
            
        try:
            pil_img = Image.open(BytesIO(data))
            
            # Smart Resize Logic
            # Default dimensions if window not fully drawn yet
            win_w = window.winfo_width()
            win_h = window.winfo_height() - 120 # subtract button area
            if win_w <= 1: win_w = 800
            if win_h <= 1: win_h = 600
            
            img_w, img_h = pil_img.size
            
            # Scale down if image is larger than window
            ratio = min(win_w/img_w, win_h/img_h)
            
            # Only resize if necessary or if we want to scale up slightly
            if ratio < 1:
                new_size = (int(img_w * ratio), int(img_h * ratio))
                pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
            elif ratio > 1 and img_w < 400: # Scale up tiny thumbnails
                 new_size = (int(img_w * 2), int(img_h * 2))
                 pil_img = pil_img.resize(new_size, Image.Resampling.NEAREST)

            tk_img = ImageTk.PhotoImage(pil_img)
            label.configure(image=tk_img, text="")
            label.image = tk_img # Keep ref preventing GC
            
        except Exception as e:
            logger.error(f"Preview Display Error: {e}")
            label.configure(text="Error displaying image")

    async def _fetch_thumbnails(self):
        # We fetch in batches to not kill the UI or Network
        chunk_size = 10
        for i in range(0, len(self.media_items), chunk_size):
            chunk = self.media_items[i:i+chunk_size]
            tasks = [self.worker.fetch_image_bytes(item.thumb_url) for item in chunk]
            results = await asyncio.gather(*tasks)
            
            # Update UI on main thread
            self.after(0, lambda res=results, idx=i: self.update_thumbnails(res, idx))

    def update_thumbnails(self, image_data_list, start_index):
        children = self.scrollable_frame.winfo_children()
        
        for i, data in enumerate(image_data_list):
            if not data: continue
            
            widget_idx = start_index + i
            if widget_idx >= len(children): break
            
            frame = children[widget_idx]
            
            try:
                # Process image with Pillow
                pil_img = Image.open(BytesIO(data))
                pil_img.thumbnail((150, 150)) 
                
                # Overlay for Video Files
                if frame.item.is_video:
                    draw = ImageDraw.Draw(pil_img)
                    # Draw a small red tag based on extension
                    ext_text = frame.item.ext.upper().lstrip('.')
                    draw.rectangle([0, 0, 40, 15], fill="red")
                    draw.text((2, 1), ext_text, fill="white")

                tk_img = ImageTk.PhotoImage(pil_img)
                
                # Update Label
                frame.lbl.configure(image=tk_img, text="", width=0, height=0, bg="white")
                self.thumbnails[frame.item.tim] = tk_img # Keep ref
            except Exception as e:
                logger.error(f"Error loading thumb: {e}")

        self.status_var.set(f"Loaded {min(start_index + len(image_data_list), len(self.media_items))}/{len(self.media_items)} thumbnails")

    def toggle_selection(self, frame, item):
        if item.tim in self.selected_items:
            self.selected_items.remove(item.tim)
            frame.configure(bg="white", relief=tk.FLAT)
        else:
            self.selected_items.add(item.tim)
            frame.configure(bg="#4CAF50", relief=tk.SOLID) # Green border
        
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

    def update_download_btn(self):
        count = len(self.selected_items)
        self.download_btn.configure(text=f"Download Selected ({count})", state=tk.NORMAL if count > 0 else tk.DISABLED)

    def start_download(self):
        target_dir = Path(self.path_var.get())
        use_subdirs = self.use_subdirs_var.get()
        
        # Determine final save path
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
        
        self.download_btn.configure(state=tk.DISABLED)
        self.status_var.set(f"Starting download...")
        self.progress_var.set(0) # Reset progress
        
        self._run_async(self._download_files(items_to_download, save_path))

    async def _download_files(self, items, save_path):
        success_count = 0
        total_items = len(items)
        
        for i, item in enumerate(items):
            filepath = save_path / item.local_filename
            
            # Check exist
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
            
            # Update Progress Bar
            progress = ((i + 1) / total_items) * 100
            self.after(0, lambda p=progress: self.progress_var.set(p))
            
            # Update Status Text
            self.after(0, lambda c=success_count, t=total_items: self.status_var.set(f"Downloading: {c}/{t}"))
        
        self.after(0, lambda: messagebox.showinfo("Complete", f"Downloaded {success_count} files to:\n{save_path}"))
        self.after(0, lambda: self.status_var.set("Ready"))
        self.after(0, self.update_download_btn)
        self.after(0, lambda: self.progress_var.set(0)) # Reset after complete

    def on_close(self):
        # Graceful shutdown
        if self.worker.session:
            self._run_async(self.worker.close_session())
        self.destroy()

if __name__ == "__main__":
    app = ChanScraperApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()