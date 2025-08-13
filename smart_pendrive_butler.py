# Smart Pendrive Butler — Manual Destination Picker (TMDb removed)
# code: python
"""
Updated Smart Pendrive Butler

Changes in this revision:
 - 'Monitor folder' is OFF by default.
 - Auto mode removed.
 - Added a search box to filter files/folders (searches subfolders too).
 - Added an "Add File" button to add single files manually.
 - Fixed ZIP extraction: extracted files are processed immediately so temporary directory isn't deleted before processing.
 - Added horizontal scrollbar for the source-tree view.
 - Allows transferring entire folders (you can add a folder to the queue; its files will be processed recursively).
 - Destination can be any folder (choose a removable drive from Refresh Drives or pick any destination folder via "Choose Destination...").

Dependencies:
    pip install guessit psutil

"""

import os
import sys
import time
import threading
import queue
import tempfile
import zipfile
import logging
import ctypes
import shutil
from pathlib import Path
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except Exception:
    raise RuntimeError("Tkinter is required")

# External deps (ensure installed)
try:
    import psutil
    from guessit import guessit
except Exception as e:
    raise RuntimeError(f"Missing dependency: {e}. Run: pip install guessit psutil")

# ---------------- configuration ----------------
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.ts', '.mpeg'}
ARCHIVE_EXTS = {'.zip'}
POLL_INTERVAL = 2.0
PROCESSING_WORKERS = 1    # single worker -> queue processed one-by-one

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ---------------- drive / destination helpers ----------------

def get_removable_drives():
    drives = []
    try:
        if sys.platform.startswith('win'):
            kernel32 = ctypes.windll.kernel32
            for letter in range(ord('A'), ord('Z') + 1):
                # construct a path like 'E:\' (escaped backslash)
                drive = chr(letter) + ':\\'
                if os.path.exists(drive):
                    dt = kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive))
                    # DRIVE_REMOVABLE = 2
                    if dt == 2:
                        drives.append(drive)
        else:
            parts = psutil.disk_partitions(all=False)
            for p in parts:
                mp = p.mountpoint
                if mp.startswith('/media') or mp.startswith('/run/media') or mp.startswith('/mnt'):
                    drives.append(mp)
            for p in parts:
                if 'removable' in p.opts:
                    drives.append(p.mountpoint)
    except Exception as e:
        logging.debug(f"Drive detection issue: {e}")
    drives = sorted(list(dict.fromkeys(drives)))
    return drives
def is_drive_writable(root_path: str) -> bool:
    try:
        test_path = Path(root_path)
        for i in range(3):
            try:
                with tempfile.NamedTemporaryFile(prefix='spb_test_', dir=test_path, delete=True) as tmp:
                    tmp.write(b'x')
                    tmp.flush()
                return True
            except (PermissionError, OSError):
                time.sleep(0.1)
                continue
        return False
    except Exception as e:
        logging.debug(f"Drive writable check failed: {e}")
        return False

# ---------------- copy with progress ----------------

def copy_with_progress(src: Path, dest: Path, progress_callback=None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = src.stat().st_size
    copied = 0
    buf = 1024 * 1024
    tmp = dest.with_suffix(dest.suffix + '.tmp')
    try:
        with open(src, 'rb') as fsrc, open(tmp, 'wb') as fdst:
            while True:
                chunk = fsrc.read(buf)
                if not chunk:
                    break
                fdst.write(chunk)
                copied += len(chunk)
                if progress_callback:
                    progress_callback(copied, total)
        os.replace(str(tmp), str(dest))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass

# ---------------- worker thread ----------------
class Worker(threading.Thread):
    def __init__(self, task_queue: 'queue.Queue[dict]', get_target_drive, ui_callback_log, ui_progress_cb):
        super().__init__(daemon=True)
        self.q = task_queue
        self._stop = threading.Event()
        self.get_target_drive = get_target_drive
        self.log = ui_callback_log
        self.ui_progress_cb = ui_progress_cb

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                task = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.process_task(task)
            except Exception as e:
                self.log(f"Task error: {e}")
            finally:
                self.q.task_done()

    def process_task(self, task: dict):
        path = Path(task['path'])
        # If directory, enqueue all files inside (recursively)
        if path.is_dir():
            for p in sorted(path.rglob('*')):
                if p.is_file() and p.suffix.lower() in VIDEO_EXTS.union(ARCHIVE_EXTS):
                    # enqueue each file as separate task
                    self.q.put({'path': str(p)})
            return

        if not path.exists():
            self.log(f"Item missing: {path}")
            return

        # handle zip: extract and process extracted files immediately (so temp dir exists)
        if path.suffix.lower() in ARCHIVE_EXTS:
            self.log(f"Extracting {path.name}")
            td = tempfile.mkdtemp(prefix='spbzip_')
            try:
                with zipfile.ZipFile(path, 'r') as zf:
                    zf.extractall(td)
            except Exception as e:
                self.log(f"Failed to extract {path.name}: {e}")
                try:
                    shutil.rmtree(td)
                except Exception:
                    pass
                return
            # process extracted files synchronously so temp directory stays until processed
            try:
                for root, _, files in os.walk(td):
                    for f in files:
                        fp = Path(root) / f
                        if fp.suffix.lower() in VIDEO_EXTS:
                            # process this media file right away
                            try:
                                self._process_media(fp)
                            except Exception as e:
                                self.log(f"Error processing extracted file {fp}: {e}")
            finally:
                # cleanup extracted temp dir
                try:
                    shutil.rmtree(td)
                except Exception as e:
                    logging.debug(f"Failed to remove temp dir {td}: {e}")
            return

        # For normal media files
        self._process_media(path)

    def _process_media(self, path: Path):
        # ensure drive / destination is available
        drive = self.get_target_drive()
        if not drive:
            self.log("No target destination selected. Item requeued.")
            self.q.put({'path': str(path)})
            time.sleep(1)
            return
        if not is_drive_writable(drive):
            self.log(f"Selected destination {drive} appears not writable or occupied. Item requeued.")
            self.q.put({'path': str(path)})
            time.sleep(1)
            return

        info = guessit(path.name)
        target_dir = Path(drive)
        dest_name = path.name

        # TV episode
        if info.get('type') == 'episode' or info.get('episodeNumber'):
            series = info.get('series') or info.get('title') or path.stem
            season = info.get('season') or info.get('seasonNumber') or info.get('season-identifier')
            episode = info.get('episodeNumber') or info.get('episode')
            if season and episode:
                try:
                    season = int(season)
                    episode = int(episode)
                except Exception:
                    season = None
                    episode = None
            if season and episode:
                dest_dir = target_dir / sanitize_filename(series) / f"Season {season:02d}"
                dest_name = f"{sanitize_filename(series)} - S{season:02d}E{episode:02d}{path.suffix}"
            else:
                dest_dir = target_dir / sanitize_filename(series)
        else:
            # Movie
            title = info.get('title') or path.stem
            year = info.get('year')
            if year:
                try:
                    y = int(year)
                    dest_name = f"{sanitize_filename(title)} ({y}){path.suffix}"
                except Exception:
                    dest_name = f"{sanitize_filename(title)}{path.suffix}"
            else:
                dest_name = f"{sanitize_filename(title)}{path.suffix}"
            dest_dir = target_dir / 'Movies'

        dest_path = dest_dir / dest_name
        self.log(f"Copying to: {dest_path}")

        def pcb(copied, total):
            pct = int(copied * 100 / total) if total else 0
            self.ui_progress_cb(dest_path.name, pct)

        try:
            copy_with_progress(path, dest_path, pcb)
            self.log(f"Copied: {dest_path}")
        except Exception as e:
            self.log(f"Failed copy: {e}")
        finally:
            self.ui_progress_cb(dest_path.name, 0)

# ---------------- UI ----------------
class AppUI:
    def __init__(self, root):
        self.root = root
        self.master = root
        root.title('Smart Pendrive Butler — No TMDb')
        root.geometry('980x620')

        # variables
        self.source_folder = tk.StringVar(master=root, value=str(Path.home()))
        self.detected_drive = tk.StringVar(master=root, value='(none)')
        self.monitor_enabled = tk.BooleanVar(master=root, value=False)  # OFF by default
        self.drive_var = tk.StringVar(master=root, value='')

        # top controls
        top = ttk.Frame(root, padding=8)
        top.pack(fill='x')
        ttk.Label(top, text='Source folder:').grid(row=0, column=0, sticky='w')
        ttk.Entry(top, textvariable=self.source_folder, width=52).grid(row=0, column=1, sticky='w')
        ttk.Button(top, text='Browse', command=self.browse_source).grid(row=0, column=2, padx=6)
        ttk.Button(top, text='Refresh tree', command=self.refresh_tree).grid(row=0, column=3)
        ttk.Button(top, text='Add File', command=self.add_file_dialog).grid(row=0, column=4, padx=6)

        # search box
        ttk.Label(top, text='Search:').grid(row=1, column=0, sticky='w')
        self.search_var = tk.StringVar(master=root, value='')
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=52)
        self.search_entry.grid(row=1, column=1, sticky='w')
        ttk.Button(top, text='Search', command=self.apply_search).grid(row=1, column=3)
        self.search_entry.bind('<KeyRelease>', lambda e: self.apply_search())

        ttk.Checkbutton(top, text='Monitor folder (auto-queue)', variable=self.monitor_enabled).grid(row=1, column=4, sticky='w')

        # middle split: treeview (left) and queue/log (right)
        middle = ttk.Frame(root, padding=8)
        middle.pack(fill='both', expand=True)

        # left: treeview
        left = ttk.Frame(middle)
        left.pack(side='left', fill='both', expand=True)
        ttk.Label(left, text='Source folder contents').pack(anchor='w')
        # horizontal and vertical scrollbars
        self.tree = ttk.Treeview(left)
        vsb = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(left, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(fill='both', expand=True, side='left')
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.tree.bind('<Double-1>', self.on_tree_double)

        # right: queue and controls
        right = ttk.Frame(middle)
        right.pack(side='right', fill='both', expand=False)
        ttk.Label(right, text='Queue').pack(anchor='w')
        self.lst_queue = tk.Listbox(right, width=60, height=15)
        self.lst_queue.pack(fill='both')
        qbtnf = ttk.Frame(right)
        qbtnf.pack(fill='x', pady=4)
        ttk.Button(qbtnf, text='Add Selected', command=self.add_selected_to_queue).pack(side='left', padx=4)
        ttk.Button(qbtnf, text='Remove Selected', command=self.remove_selected_from_queue).pack(side='left')
        ttk.Button(qbtnf, text='Clear Queue', command=self.clear_queue).pack(side='left', padx=4)

        ttk.Label(right, text='Per-file progress:').pack(anchor='w', pady=(8,0))
        self.progress_var = tk.IntVar(master=root, value=0)
        self.progress = ttk.Progressbar(right, maximum=100, variable=self.progress_var)
        self.progress.pack(fill='x', padx=4)
        self.lbl_progress_name = ttk.Label(right, text='(idle)')
        self.lbl_progress_name.pack(anchor='w')

        # bottom: drive picker, status/log & controls
        bottom = ttk.Frame(root, padding=8)
        bottom.pack(fill='x')
        ttk.Label(bottom, text='Target (drive or folder):').pack(side='left')
        self.drive_combo = ttk.Combobox(bottom, textvariable=self.drive_var, values=[], width=44, state='readonly')
        self.drive_combo.pack(side='left', padx=6)
        ttk.Button(bottom, text='Refresh Drives', command=self.refresh_drives).pack(side='left')
        ttk.Button(bottom, text='Choose Destination...', command=self.choose_destination).pack(side='left', padx=4)

        ttk.Label(bottom, text='Selected:').pack(side='left', padx=(16,4))
        ttk.Label(bottom, textvariable=self.detected_drive).pack(side='left')
        ttk.Button(bottom, text='Start', command=self.start).pack(side='right')
        ttk.Button(bottom, text='Stop', command=self.stop).pack(side='right', padx=4)

        self.txt_log = tk.Text(root, height=8, state='disabled')
        self.txt_log.pack(fill='both', padx=8, pady=6)

        # internal
        self.task_queue = queue.Queue()
        self.worker = Worker(self.task_queue, self.get_target_drive, self.ui_log, self.ui_progress)
        self._monitor_thread = None
        self._stop = False
        self._queued_paths = []
        self._current_destination = None

        # set global root_ui for worker callbacks
        global root_ui
        root_ui = root

        # initial populate tree and drives
        self.refresh_tree()
        self.refresh_drives()

    # ---------------- UI helpers ----------------
    def browse_source(self):
        d = filedialog.askdirectory(initialdir=self.source_folder.get())
        if d:
            self.source_folder.set(d)
            self.refresh_tree()

    def add_file_dialog(self):
        f = filedialog.askopenfilename(initialdir=self.source_folder.get(), filetypes=[('Video files','*.mp4;*.mkv;*.avi;*.mov;*.wmv;*.flv;*.ts;*.mpeg'),('All files','*.*')])
        if f:
            self.add_path_to_queue(f)

    def apply_search(self):
        term = self.search_var.get().strip().lower()
        self.refresh_tree(filter_term=term)

    def refresh_tree(self, filter_term: str = ''):
        self.tree.delete(*self.tree.get_children())
        base = Path(self.source_folder.get())
        if not base.exists():
            return

        def node_matches(path: Path, term: str) -> bool:
            if not term:
                return True
            # check name and path
            if term in path.name.lower() or term in str(path).lower():
                return True
            if path.is_dir():
                for child in path.rglob('*'):
                    try:
                        if term in child.name.lower() or term in str(child).lower():
                            return True
                    except Exception:
                        continue
            return False

        def insert_node(parent, path: Path):
            try:
                text = path.name
                iid = str(path)
                # if filtering, only insert nodes that match or have descendants that match
                if filter_term and not node_matches(path, filter_term):
                    return False
                self.tree.insert(parent, 'end', iid=iid, text=text)
                if path.is_dir():
                    try:
                        for child in sorted(path.iterdir()):
                            insert_node(iid, child)
                    except Exception:
                        pass
                return True
            except Exception as e:
                logging.debug(f"Insert node error: {e}")
                return False

        insert_node('', base)

    def on_tree_double(self, event):
        sel = self.tree.focus()
        if not sel:
            return
        p = Path(sel)
        if p.is_file():
            self.add_path_to_queue(str(p))
        elif p.is_dir():
            # add entire folder
            self.add_path_to_queue(str(p))

    def add_selected_to_queue(self):
        sel = self.tree.selection()
        for s in sel:
            p = Path(s)
            if p.exists():
                self.add_path_to_queue(str(p))

    def add_path_to_queue(self, path: str):
        if path in self._queued_paths:
            self.ui_log(f"Already queued: {path}")
            return
        self._queued_paths.append(path)
        self.lst_queue.insert('end', Path(path).name)
        self.task_queue.put({'path': path})
        self.ui_log(f"Queued: {path}")

    def remove_selected_from_queue(self):
        sel = list(self.lst_queue.curselection())
        for i in reversed(sel):
            name = self.lst_queue.get(i)
            for p in list(self._queued_paths):
                if Path(p).name == name:
                    self._queued_paths.remove(p)
                    break
            self.lst_queue.delete(i)
        self.ui_log('Removed selected from queue')

    def clear_queue(self):
        self.lst_queue.delete(0, 'end')
        self._queued_paths.clear()
        with self.task_queue.mutex:
            self.task_queue.queue.clear()
        self.ui_log('Cleared queue')

    def ui_log(self, text):
        ts = datetime.now().strftime('%H:%M:%S')
        self.txt_log.configure(state='normal')
        # insert a single-line string with an explicit newline escape
        self.txt_log.insert('end', f"[{ts}] {text}\n")
        self.txt_log.see('end')
        self.txt_log.configure(state='disabled')
        logging.info(text)


    def ui_progress(self, name, percent):
        def _update():
            self.progress_var.set(percent)
            self.lbl_progress_name.config(text=f"{name} — {percent}%")
            if percent == 0:
                self.lbl_progress_name.config(text='(idle)')
        self.root.after(1, _update)

    # --------------- destination getters / pickers ---------------
    def get_target_drive(self):
        return getattr(self, '_current_destination', None)

    def refresh_drives(self):
        drives = get_removable_drives()
        self.drive_combo['values'] = drives
        if drives and not self.drive_var.get():
            self.drive_combo.set(drives[0])
        self.ui_log(f"Found drives: {', '.join(drives) if drives else '(none)'}")

    def choose_destination(self):
        d = filedialog.askdirectory()
        if d:
            self._current_destination = d
            self.detected_drive.set(d)
            self.ui_log(f"Destination chosen: {d}")

    def select_drive(self):
        sel = self.drive_var.get()
        if not sel:
            messagebox.showwarning('Select drive', 'No drive selected from the list. Click Refresh Drives and choose one.')
            return
        self._current_destination = sel
        self.detected_drive.set(sel)
        self.ui_log(f"Drive selected: {sel}")

    # ---------------- control start/stop and background tasks ----------------
    def start(self):
        if getattr(self, '_running', False):
            self.ui_log('Already running')
            return
        self._running = True
        self.ui_log('Starting service...')
        # start worker
        self.worker = Worker(self.task_queue, self.get_target_drive, self.ui_log, self.ui_progress_bridge)
        self.worker.start()
        # start folder monitor if enabled
        if self.monitor_enabled.get():
            self._monitor_thread = threading.Thread(target=self._folder_monitor, daemon=True)
            self._monitor_thread.start()

    def stop(self):
        if not getattr(self, '_running', False):
            self.ui_log('Not running')
            return
        self._running = False
        self.ui_log('Stopping service...')
        try:
            if self.worker:
                self.worker.stop()
        except Exception:
            pass

    def ui_progress_bridge(self, name, percent):
        self.root.after(1, lambda: self.ui_progress(name, percent))

    def _folder_monitor(self):
        base = Path(self.source_folder.get())
        seen = set()
        while getattr(self, '_running', True) and self.monitor_enabled.get():
            try:
                if not base.exists():
                    time.sleep(POLL_INTERVAL)
                    continue
                for p in base.rglob('*'):
                    if p.is_file() and p.suffix.lower() in VIDEO_EXTS.union(ARCHIVE_EXTS):
                        s = str(p)
                        if s not in seen:
                            seen.add(s)
                            if s not in self._queued_paths:
                                self.add_path_to_queue(s)
                time.sleep(POLL_INTERVAL)
            except Exception as e:
                self.ui_log(f"Folder monitor error: {e}")
                time.sleep(POLL_INTERVAL)

# ---------------- misc utils ----------------

def sanitize_filename(name: str) -> str:
    invalid = '<>:"/\\|?*'
    out = ''.join(c for c in name if c not in invalid)
    out = out.strip()
    out = ' '.join(out.split())
    return out or 'unnamed'


# ---------------- entrypoint ----------------

def main():
    root = tk.Tk()
    app = AppUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
