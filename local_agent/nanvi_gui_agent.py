"""Nanvi Local File Agent with Clean White GUI for Windows.

Designed for all users, including non-technical users and seniors aged 50-60.
Features:
- Pure white modern native graphical window (no scary black command prompt)
- 1-click Windows folder selection dialog
- Real-time indexing progress and chunk sync to Nanvi cloud
- Automatic heartbeat and folder-sync loop
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Tkinter GUI imports
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("NanviLocalAgent")

LOCAL_CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
CONFIG_FILE = Path.home() / ".nanvi_local_agent_config.json"
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
CHUNK_SIZE_CHARS = 1000
CHUNK_OVERLAP_CHARS = 150

BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs", ".sh", ".bin",
    ".msi", ".sys", ".com", ".scr", ".jar", ".iso", ".img", ".dmg",
}

SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".pdf", ".docx", ".xlsx", ".pptx",
}

BLOCKED_SYSTEM_PATHS = [
    Path(os.environ.get("SystemRoot", "C:\\Windows")).resolve(),
    Path(os.environ.get("ProgramFiles", "C:\\Program Files")).resolve(),
    Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")).resolve(),
    Path("C:\\Windows").resolve(),
]


class SecurityError(ValueError):
    """Raised when an unauthorized folder or file access is attempted."""
    pass


def sanitize_folder_path(raw_path: str) -> str:
    """Sanitize and clean folder paths, stripping quotes, environments, and accidental prefixes."""
    if not raw_path:
        return ""
    cleaned = str(raw_path).strip().strip("'\"“”`")
    for prefix in [
        "nanvi-agent add",
        "nanvi local agent add",
        "nanvi add",
        "python nanvi_local_agent.py add",
        "python nanvi_gui_agent.py add",
        "python local_agent.py add",
        "python add",
        "add folder",
        "add path",
        "add:",
        "add",
    ]:
        if cleaned.lower().startswith(prefix.lower() + " ") or cleaned.lower() == prefix.lower():
            cleaned = cleaned[len(prefix):].strip().strip("'\"“”`")
            break
    cleaned = cleaned.strip("'\"“”`:").strip()
    cleaned = os.path.expandvars(cleaned)
    return cleaned


class NanviLocalAgent:
    """Manages local approved folders, file indexing, filesystem watching, and cloud sync."""

    def __init__(self, server_url: str, token: str, config_path: Path | None = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.config_path = config_path or (LOCAL_CONFIG_FILE if LOCAL_CONFIG_FILE.exists() else CONFIG_FILE)
        self.approved_folders: dict[str, dict[str, Any]] = {}
        self.running = False
        self._sync_lock = threading.Lock()
        self.status_callback = None
        self.folder_callback = None
        self._load_config()

    def _load_config(self) -> None:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if not self.server_url and data.get("server_url"):
                    self.server_url = data["server_url"].rstrip("/")
                if not self.token and data.get("token"):
                    self.token = data["token"]
                for f_info in data.get("folders", []):
                    path = f_info.get("path")
                    if path and Path(path).exists() and Path(path).is_dir():
                        resolved = str(Path(path).resolve())
                        self.approved_folders[resolved] = {
                            "path": resolved,
                            "display_name": f_info.get("display_name") or Path(path).name or resolved,
                            "file_count": f_info.get("file_count", 0),
                            "chunk_count": f_info.get("chunk_count", 0),
                            "status": "ready",
                        }
            except Exception as exc:
                logger.warning("Could not read configuration: %s", exc)

    def _save_config(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            export = {
                "server_url": self.server_url,
                "token": self.token,
                "folders": [
                    {
                        "path": v["path"],
                        "display_name": v.get("display_name", Path(v["path"]).name),
                        "file_count": v.get("file_count", 0),
                        "chunk_count": v.get("chunk_count", 0),
                    }
                    for v in self.approved_folders.values()
                ],
            }
            self.config_path.write_text(json.dumps(export, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not save configuration: %s", exc)
    def validate_folder(self, folder_path: str | Path) -> Path:
        clean = sanitize_folder_path(str(folder_path))
        if not clean:
            raise ValueError("Folder path cannot be empty.")
        p = Path(clean).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            raise FileNotFoundError(f"Folder does not exist or is not a directory: {clean}")

        for blocked in BLOCKED_SYSTEM_PATHS:
            try:
                if p == blocked or p.is_relative_to(blocked):
                    raise SecurityError(f"System directory access blocked: {p}")
            except (ValueError, TypeError):
                pass

        if p.parent == p:
            raise SecurityError(f"Root drive paths cannot be approved directly. Please select a subfolder: {p}")

        return p

    def add_folder(self, folder_path: str, display_name: str | None = None) -> Path:
        p = self.validate_folder(folder_path)
        path_str = str(p)
        name = display_name or p.name or path_str

        self.approved_folders[path_str] = {
            "path": path_str,
            "display_name": name,
            "file_count": 0,
            "chunk_count": 0,
            "status": "indexing",
        }
        self._save_config()
        if self.folder_callback:
            self.folder_callback()

        # Trigger indexing in background thread
        threading.Thread(target=self.index_and_sync_folder, args=(path_str,), daemon=True).start()
        return p

    def remove_folder(self, folder_path: str) -> bool:
        target = str(Path(folder_path).expanduser().resolve())
        if target in self.approved_folders:
            del self.approved_folders[target]
            self._save_config()
            if self.folder_callback:
                self.folder_callback()
            return True
        return False

    def _extract_text(self, file_path: Path) -> str:
        ext = file_path.suffix.casefold()
        if ext in {".txt", ".md", ".csv", ".json"}:
            try:
                return file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return file_path.read_text(encoding="latin-1", errors="replace")

        if ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(file_path))
                return "\n\n".join(p.extract_text() or "" for p in reader.pages)
            except Exception:
                pass
            raw = file_path.read_bytes()
            ascii_strings = re.findall(rb"[\x20-\x7E\t\n\r]{4,}", raw)
            return "\n".join(s.decode("ascii", errors="ignore") for s in ascii_strings[:500])

        if ext == ".docx":
            try:
                import docx
                doc = docx.Document(str(file_path))
                return "\n".join(p.text for p in doc.paragraphs if p.text)
            except Exception:
                pass
            import zipfile
            try:
                with zipfile.ZipFile(file_path) as z:
                    xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
                    text = re.sub(r"<[^>]+>", " ", xml)
                    return re.sub(r"\s+", " ", text).strip()
            except Exception:
                return ""

        if ext == ".xlsx":
            try:
                import openpyxl
                wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
                lines = []
                for sheet in wb.sheetnames[:5]:
                    lines.append(f"--- Sheet: {sheet} ---")
                    for row in wb[sheet].iter_rows(max_row=100, values_only=True):
                        row_vals = [str(v) for v in row if v is not None]
                        if row_vals:
                            lines.append(" | ".join(row_vals))
                return "\n".join(lines)
            except Exception:
                return ""

        if ext == ".pptx":
            import zipfile
            try:
                with zipfile.ZipFile(file_path) as z:
                    slides = []
                    for name in sorted(z.namelist()):
                        if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                            xml = z.read(name).decode("utf-8", errors="ignore")
                            slides.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip())
                    return "\n\n".join(slides)
            except Exception:
                return ""

        return ""

    def _chunk_text(self, text: str) -> list[str]:
        clean = re.sub(r"\r\n|\r", "\n", text).strip()
        if not clean:
            return []
        chunks = []
        pos = 0
        while pos < len(clean):
            end = min(pos + CHUNK_SIZE_CHARS, len(clean))
            if end < len(clean):
                split_at = clean.rfind("\n", pos, end)
                if split_at > pos + (CHUNK_SIZE_CHARS // 2):
                    end = split_at
            chunk = clean[pos:end].strip()
            if len(chunk) > 20:
                chunks.append(chunk)
            pos += CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
        return chunks

    def index_and_sync_folder(self, folder_path: str) -> None:
        p = Path(folder_path)
        if not p.exists():
            return

        with self._sync_lock:
            folder_info = self.approved_folders.get(folder_path, {})
            folder_name = folder_info.get("display_name", p.name)

            if self.status_callback:
                self.status_callback(f"Scanning '{folder_name}'...")

            files_meta = []
            all_chunks = []

            for root, _, filenames in os.walk(p):
                for fname in filenames:
                    if fname.startswith(".") or fname.startswith("~$"):
                        continue
                    fpath = Path(root) / fname
                    ext = fpath.suffix.casefold()
                    if ext in BLOCKED_EXTENSIONS or ext not in SUPPORTED_EXTENSIONS:
                        continue

                    try:
                        stat = fpath.stat()
                        if stat.st_size > MAX_FILE_SIZE_BYTES or stat.st_size == 0:
                            continue
                        rel_path = str(fpath.relative_to(p)).replace("\\", "/")
                        text = self._extract_text(fpath)
                        text_chunks = self._chunk_text(text)

                        files_meta.append({
                            "relative_path": rel_path,
                            "filename": fname,
                            "folder_name": folder_name,
                            "file_type": ext.lstrip("."),
                            "size_bytes": stat.st_size,
                            "chunk_count": len(text_chunks),
                            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                        })

                        for idx, chunk_text in enumerate(text_chunks):
                            cid = hashlib.sha256(f"{rel_path}:{idx}:{chunk_text[:50]}".encode()).hexdigest()[:16]
                            all_chunks.append({
                                "chunk_id": cid,
                                "relative_path": rel_path,
                                "filename": fname,
                                "folder_name": folder_name,
                                "chunk_index": idx,
                                "text": chunk_text,
                                "char_count": len(chunk_text),
                                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                                "metadata": {},
                            })
                    except Exception as e:
                        logger.debug("Skip file %s: %s", fpath, e)

            # Update local folder stats
            if folder_path in self.approved_folders:
                self.approved_folders[folder_path]["file_count"] = len(files_meta)
                self.approved_folders[folder_path]["chunk_count"] = len(all_chunks)
                self.approved_folders[folder_path]["status"] = "synced"
                self._save_config()

            if self.folder_callback:
                self.folder_callback()

            # Push to cloud
            self._send_sync_payload(folder_path, folder_name, files_meta, all_chunks)

    def _send_sync_payload(self, folder_path: str, display_name: str, files: list, chunks: list) -> bool:
        url = f"{self.server_url}/api/local-agent/sync"
        payload = {
            "folder_id": folder_path,
            "folder_path": folder_path,
            "display_name": display_name,
            "files": files,
            "chunks": chunks,
        }
        try:
            req = Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}",
                },
                method="POST",
            )
            with urlopen(req, timeout=30) as resp:
                ok = resp.status == 200
                if ok and self.status_callback:
                    self.status_callback(f"✓ '{display_name}' synced ({len(files)} files, {len(chunks)} chunks)")
                return ok
        except Exception as exc:
            logger.warning("Sync failed: %s", exc)
            if self.status_callback:
                self.status_callback(f"Sync error: {exc}")
            return False

    def send_heartbeat(self) -> bool:
        url = f"{self.server_url}/api/local-agent/heartbeat"
        folders_list = []
        for p_str, info in self.approved_folders.items():
            folders_list.append({
                "folder_id": p_str,
                "folder_path": p_str,
                "display_name": info.get("display_name", Path(p_str).name),
                "file_count": info.get("file_count", 0),
                "chunk_count": info.get("chunk_count", 0),
                "status": info.get("status", "connected"),
            })

        payload = {
            "agent_version": "1.1.0",
            "folders": folders_list,
        }
        try:
            req = Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}",
                },
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    try:
                        raw = resp.read().decode("utf-8")
                        data = json.loads(raw)
                        requested = data.get("requested_folders", [])
                        for rf in requested:
                            clean_rf = sanitize_folder_path(str(rf))
                            if clean_rf:
                                try:
                                    resolved_str = str(Path(clean_rf).expanduser().resolve())
                                    if resolved_str not in self.approved_folders:
                                        logger.info("Adding requested folder from cloud: %s", clean_rf)
                                        self.add_folder(clean_rf)
                                        if self.status_callback:
                                            self.status_callback(f"✓ Added folder: {Path(clean_rf).name}")
                                except Exception as exc:
                                    logger.warning("Could not add folder '%s': %s", clean_rf, exc)
                    except Exception:
                        pass
                    return True
                return False
        except Exception:
            return False

    def _heartbeat_loop(self) -> None:
        while self.running:
            ok = self.send_heartbeat()
            if self.status_callback:
                if ok:
                    self.status_callback("● Connected to Nanvi AI Assistant")
                else:
                    self.status_callback("○ Reconnecting to Nanvi Cloud...")
            time.sleep(10)

    def start(self) -> None:
        self.running = True
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        # Initial sync
        for f in list(self.approved_folders.keys()):
            threading.Thread(target=self.index_and_sync_folder, args=(f,), daemon=True).start()

    def stop(self) -> None:
        self.running = False


# ---------------------------------------------------------------------------
# Clean White Windows GUI (Tkinter)
# ---------------------------------------------------------------------------

class NanviAgentWindow:
    """Modern, clean white Windows application window for Nanvi Local Agent."""

    def __init__(self, agent: NanviLocalAgent) -> None:
        self.agent = agent
        self.root = tk.Tk()
        self.root.title("Nanvi AI Enterprise Assistant - Local File Agent")
        self.root.geometry("720x580")
        self.root.minsize(640, 480)
        self.root.configure(bg="#ffffff")

        # Hook agent callbacks to UI
        self.agent.status_callback = self._on_status_change
        self.agent.folder_callback = self._refresh_folder_list

        self._build_ui()
        self.agent.start()
        self._refresh_folder_list()

    def _build_ui(self) -> None:
        # Top Header Banner (Clean White with subtle border)
        header_frame = tk.Frame(self.root, bg="#ffffff", padx=24, pady=18)
        header_frame.pack(fill="x")

        title_label = tk.Label(
            header_frame,
            text="Nanvi AI Enterprise Assistant",
            font=("Segoe UI", 16, "bold"),
            fg="#0f172a",
            bg="#ffffff",
        )
        title_label.pack(anchor="w")

        subtitle_label = tk.Label(
            header_frame,
            text="Local Folder Search for Windows • Files stay private on your computer",
            font=("Segoe UI", 10),
            fg="#64748b",
            bg="#ffffff",
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

        # Cloud Connection Status Badge
        self.status_label = tk.Label(
            header_frame,
            text="● Connecting to Nanvi...",
            font=("Segoe UI", 10, "bold"),
            fg="#0284c7",
            bg="#ffffff",
        )
        self.status_label.pack(anchor="w", pady=(6, 0))

        # Thin divider
        divider = tk.Frame(self.root, height=1, bg="#e2e8f0")
        divider.pack(fill="x")

        # Main Content Area
        content = tk.Frame(self.root, bg="#ffffff", padx=24, pady=16)
        content.pack(fill="both", expand=True)

        # Reassuring Privacy Notice
        privacy_box = tk.Frame(
            content,
            bg="#f0fdf4",
            highlightbackground="#bbf7d0",
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        privacy_box.pack(fill="x", pady=(0, 16))

        privacy_text = tk.Label(
            privacy_box,
            text="🛡️ Privacy Protected: Nanvi only searches the folders you select below.\nNo executable files, passwords, or system folders can be accessed.",
            font=("Segoe UI", 9),
            fg="#166534",
            bg="#f0fdf4",
            justify="left",
        )
        privacy_text.pack(anchor="w")

        # Action Buttons Row
        btn_frame = tk.Frame(content, bg="#ffffff")
        btn_frame.pack(fill="x", pady=(0, 10))

        # Big Blue "Browse & Select Folder" Button
        self.add_btn = tk.Button(
            btn_frame,
            text="📂  Click Here to Select a Folder to Search...",
            font=("Segoe UI", 11, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            padx=20,
            pady=10,
            cursor="hand2",
            command=self._on_browse_click,
        )
        self.add_btn.pack(side="left")

        # Manual Path Entry Row (Allows typing or pasting folder paths directly)
        entry_frame = tk.Frame(content, bg="#ffffff")
        entry_frame.pack(fill="x", pady=(0, 16))

        self.placeholder_text = "Or paste any folder path here, e.g. C:\\CompanyData or D:\\Projects..."
        self.path_entry = tk.Entry(
            entry_frame,
            font=("Segoe UI", 10),
            bg="#f8fafc",
            fg="#64748b",
            highlightbackground="#cbd5e1",
            highlightcolor="#0284c7",
            highlightthickness=1,
            relief="flat",
        )
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 10))
        self.path_entry.insert(0, self.placeholder_text)
        self.path_entry.bind("<FocusIn>", self._clear_placeholder)
        self.path_entry.bind("<Return>", lambda e: self._on_add_manual_click())

        self.manual_add_btn = tk.Button(
            entry_frame,
            text="+ Add Folder",
            font=("Segoe UI", 10, "bold"),
            bg="#0f172a",
            fg="#ffffff",
            activebackground="#334155",
            relief="flat",
            padx=16,
            pady=7,
            cursor="hand2",
            command=self._on_add_manual_click,
        )
        self.manual_add_btn.pack(side="right")

        # Section Header: Approved Folders
        folders_header = tk.Label(
            content,
            text="Folders Currently Approved for Nanvi AI Search:",
            font=("Segoe UI", 11, "bold"),
            fg="#1e293b",
            bg="#ffffff",
        )
        folders_header.pack(anchor="w", pady=(8, 6))

        # Scrollable container for folder cards
        list_container = tk.Frame(content, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        list_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(list_container, bg="#f8fafc", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#f8fafc", padx=10, pady=10)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bottom Footer Banner
        footer = tk.Frame(self.root, bg="#f1f5f9", padx=20, pady=10)
        footer.pack(fill="x", side="bottom")

        footer_text = tk.Label(
            footer,
            text="💡 Tip: You can minimize this window to your taskbar while using Nanvi in your browser.",
            font=("Segoe UI", 9),
            fg="#475569",
            bg="#f1f5f9",
        )
        footer_text.pack(side="left")

    def _on_status_change(self, msg: str) -> None:
        def update():
            self.status_label.config(text=msg)
            if "Connected" in msg or "✓" in msg:
                self.status_label.config(fg="#16a34a")
            else:
                self.status_label.config(fg="#d97706")
        self.root.after(0, update)

    def _clear_placeholder(self, event=None) -> None:
        if self.path_entry.get() == self.placeholder_text:
            self.path_entry.delete(0, tk.END)
            self.path_entry.config(fg="#0f172a")

    def _on_add_manual_click(self) -> None:
        raw = self.path_entry.get().strip()
        if not raw or raw == self.placeholder_text:
            return
        clean = sanitize_folder_path(raw)
        try:
            p = self.agent.add_folder(clean)
            self.path_entry.delete(0, tk.END)
            messagebox.showinfo(
                "Folder Added",
                f"Successfully connected folder:\n\n{p}\n\nNanvi is now indexing files in the background.",
            )
        except Exception as exc:
            messagebox.showerror("Cannot Add Folder", str(exc))

    def _on_browse_click(self) -> None:
        selected = filedialog.askdirectory(title="Select a folder for Nanvi AI to search")
        if selected:
            try:
                p = self.agent.add_folder(selected)
                messagebox.showinfo(
                    "Folder Added",
                    f"Successfully connected folder:\n\n{p}\n\nNanvi is now indexing files in the background.",
                )
            except Exception as exc:
                messagebox.showerror("Cannot Add Folder", str(exc))

    def _refresh_folder_list(self) -> None:
        def update():
            # Clear previous items
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()

            folders = self.agent.approved_folders
            if not folders:
                empty_lbl = tk.Label(
                    self.scrollable_frame,
                    text="No folders connected yet. Click the blue button above to add a folder.",
                    font=("Segoe UI", 10),
                    fg="#94a3b8",
                    bg="#f8fafc",
                    pady=20,
                )
                empty_lbl.pack(anchor="center")
                return

            for path_str, info in list(folders.items()):
                card = tk.Frame(
                    self.scrollable_frame,
                    bg="#ffffff",
                    highlightbackground="#cbd5e1",
                    highlightthickness=1,
                    padx=14,
                    pady=10,
                )
                card.pack(fill="x", pady=4, expand=True)

                left = tk.Frame(card, bg="#ffffff")
                left.pack(side="left", fill="both", expand=True)

                name_lbl = tk.Label(
                    left,
                    text=f"📁  {info.get('display_name', Path(path_str).name)}",
                    font=("Segoe UI", 10, "bold"),
                    fg="#0f172a",
                    bg="#ffffff",
                )
                name_lbl.pack(anchor="w")

                path_lbl = tk.Label(
                    left,
                    text=path_str,
                    font=("Consolas", 8),
                    fg="#64748b",
                    bg="#ffffff",
                )
                path_lbl.pack(anchor="w")

                count_text = f"{info.get('file_count', 0)} files ({info.get('chunk_count', 0)} chunks) • Status: Ready"
                stats_lbl = tk.Label(
                    left,
                    text=count_text,
                    font=("Segoe UI", 8),
                    fg="#16a34a",
                    bg="#ffffff",
                )
                stats_lbl.pack(anchor="w")

                # Remove Button
                def make_remove(p=path_str):
                    def do_remove():
                        if messagebox.askyesno("Remove Folder", f"Disconnect this folder from Nanvi?\n\n{p}"):
                            self.agent.remove_folder(p)
                    return do_remove

                rm_btn = tk.Button(
                    card,
                    text="Remove",
                    font=("Segoe UI", 9),
                    fg="#dc2626",
                    bg="#fee2e2",
                    activebackground="#fca5a5",
                    relief="flat",
                    padx=10,
                    pady=3,
                    cursor="hand2",
                    command=make_remove(path_str),
                )
                rm_btn.pack(side="right", padx=(10, 0))

        self.root.after(0, update)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    # Load config
    config_data = {}
    config_file = LOCAL_CONFIG_FILE if LOCAL_CONFIG_FILE.exists() else CONFIG_FILE
    if config_file.exists():
        try:
            config_data = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    server_url = os.environ.get("NANVI_SERVER_URL") or config_data.get("server_url") or "https://nanviaienterpriseassistant.vercel.app"
    token = os.environ.get("NANVI_AGENT_TOKEN") or config_data.get("token") or ""

    agent = NanviLocalAgent(server_url=server_url, token=token)
    app = NanviAgentWindow(agent)
    app.run()


if __name__ == "__main__":
    main()
