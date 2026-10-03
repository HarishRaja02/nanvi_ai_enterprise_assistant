#!/usr/bin/env python3
"""Nanvi Local File Agent for Windows.

Securely indexes and searches user-approved local folders on a Windows PC
and connects them to the cloud Nanvi AI Enterprise Assistant.
"""
from __future__ import annotations

import argparse
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
    Path("/etc").resolve(),
    Path("/sys").resolve(),
    Path("/usr").resolve(),
    Path("/bin").resolve(),
    Path("/sbin").resolve(),
]


class SecurityError(ValueError):
    """Raised when an unauthorized folder or file access is attempted."""
    pass


class NanviLocalAgent:
    """Manages local approved folders, file indexing, filesystem watching, and cloud sync."""

    def __init__(self, server_url: str, token: str, config_path: Path | None = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.config_path = config_path or CONFIG_FILE
        self.approved_folders: dict[str, dict[str, Any]] = {}
        self.file_hashes: dict[str, str] = {}
        self.running = False
        self._sync_lock = threading.Lock()
        self._load_config()

    # -----------------------------------------------------------------------
    # Configuration & State Management
    # -----------------------------------------------------------------------

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
                        self.approved_folders[str(Path(path).resolve())] = {
                            "path": str(Path(path).resolve()),
                            "display_name": f_info.get("display_name") or Path(path).name,
                        }
            except Exception as exc:
                logger.warning("Could not read configuration file: %s", exc)

    def _save_config(self) -> None:
        try:
            payload = {
                "server_url": self.server_url,
                "token": self.token,
                "folders": [
                    {"path": v["path"], "display_name": v["display_name"]}
                    for v in self.approved_folders.values()
                ],
            }
            self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not save configuration: %s", exc)

    # -----------------------------------------------------------------------
    # Security Validation
    # -----------------------------------------------------------------------

    def validate_folder_path(self, folder_path: str | Path) -> Path:
        """Strictly validate that a folder is safe, exists, and is not a restricted system directory."""
        p = Path(folder_path).expanduser().resolve()
        if not p.exists():
            raise SecurityError(f"Folder does not exist: {p}")
        if not p.is_dir():
            raise SecurityError(f"Target is not a directory: {p}")

        # Block root drives directly like C:\ or /
        if len(p.parts) <= 1:
            raise SecurityError(f"Access to raw system drive root '{p}' is restricted. Please select a specific folder.")

        # Check system directory blacklists
        for blocked in BLOCKED_SYSTEM_PATHS:
            is_blocked = False
            try:
                is_blocked = (p == blocked) or p.is_relative_to(blocked)
            except (ValueError, TypeError):
                is_blocked = False
            if is_blocked:
                raise SecurityError(f"Access to protected system folder '{p}' is strictly prohibited.")

        return p

    def add_folder(self, folder_path: str, display_name: str = "") -> Path:
        """Approve and connect a local folder."""
        p = self.validate_folder_path(folder_path)
        path_str = str(p)
        name = display_name or p.name or path_str
        self.approved_folders[path_str] = {
            "path": path_str,
            "display_name": name,
        }
        self._save_config()
        logger.info("Added approved folder: %s (%s)", path_str, name)
        # Trigger index and sync in background
        threading.Thread(target=self.index_and_sync_folder, args=(path_str,), daemon=True).start()
        return p

    def remove_folder(self, folder_path: str) -> bool:
        """Revoke approval for a local folder."""
        target = str(Path(folder_path).expanduser().resolve())
        if target in self.approved_folders:
            del self.approved_folders[target]
            self._save_config()
            logger.info("Removed folder: %s", target)
            return True
        return False

    # -----------------------------------------------------------------------
    # Document Parsing & Chunking Pipeline
    # -----------------------------------------------------------------------

    def _extract_text(self, file_path: Path) -> str:
        """Safely extract plain text from supported document formats."""
        ext = file_path.suffix.casefold()

        # Text, Markdown, CSV, JSON
        if ext in {".txt", ".md", ".csv", ".json"}:
            try:
                return file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return file_path.read_text(encoding="latin-1", errors="replace")

        # PDF parsing
        if ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(file_path))
                pages = [p.extract_text() or "" for p in reader.pages]
                return "\n\n".join(pages)
            except ImportError:
                pass
            try:
                import pdfplumber
                with pdfplumber.open(str(file_path)) as pdf:
                    return "\n\n".join(page.extract_text() or "" for page in pdf.pages)
            except ImportError:
                pass
            # Fallback lightweight raw string extractor
            raw = file_path.read_bytes()
            ascii_strings = re.findall(rb"[\x20-\x7E\t\n\r]{4,}", raw)
            return "\n".join(s.decode("ascii", errors="ignore") for s in ascii_strings[:500])

        # DOCX parsing
        if ext == ".docx":
            try:
                import docx
                doc = docx.Document(str(file_path))
                return "\n".join(p.text for p in doc.paragraphs if p.text)
            except Exception:
                pass
            # Fallback DOCX XML extraction
            import zipfile
            try:
                with zipfile.ZipFile(file_path) as z:
                    xml_content = z.read("word/document.xml").decode("utf-8", errors="ignore")
                    text = re.sub(r"<[^>]+>", " ", xml_content)
                    return re.sub(r"\s+", " ", text).strip()
            except Exception:
                return ""

        # XLSX parsing
        if ext == ".xlsx":
            try:
                import openpyxl
                wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
                lines = []
                for sheet in wb.sheetnames[:5]:
                    lines.append(f"--- Sheet: {sheet} ---")
                    ws = wb[sheet]
                    for row in ws.iter_rows(max_row=100, values_only=True):
                        row_vals = [str(v) for v in row if v is not None]
                        if row_vals:
                            lines.append(" | ".join(row_vals))
                return "\n".join(lines)
            except Exception:
                pass

        # PPTX parsing
        if ext == ".pptx":
            import zipfile
            try:
                with zipfile.ZipFile(file_path) as z:
                    slides = []
                    for name in sorted(z.namelist()):
                        if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                            xml_content = z.read(name).decode("utf-8", errors="ignore")
                            text = re.sub(r"<[^>]+>", " ", xml_content)
                            slides.append(re.sub(r"\s+", " ", text).strip())
                    return "\n\n".join(slides)
            except Exception:
                return ""

        return ""

    def chunk_text(self, text: str, rel_path: str, filename: str, folder_name: str, mtime_iso: str) -> list[dict[str, Any]]:
        """Split document text into overlapping chunks for RAG."""
        clean = re.sub(r"\r\n", "\n", text).strip()
        if not clean:
            return []

        chunks: list[dict[str, Any]] = []
        start = 0
        idx = 0
        total_len = len(clean)

        while start < total_len:
            end = min(start + CHUNK_SIZE_CHARS, total_len)
            # Try to break at newline or space
            if end < total_len:
                last_nl = clean.rfind("\n", start, end)
                if last_nl > start + CHUNK_SIZE_CHARS // 2:
                    end = last_nl
                else:
                    last_space = clean.rfind(" ", start, end)
                    if last_space > start + CHUNK_SIZE_CHARS // 2:
                        end = last_space

            chunk_content = clean[start:end].strip()
            if chunk_content:
                chunk_id = hashlib.sha256(f"{rel_path}:{idx}:{chunk_content[:50]}".encode("utf-8")).hexdigest()[:24]
                chunks.append({
                    "chunk_id": chunk_id,
                    "relative_path": rel_path,
                    "filename": filename,
                    "folder_name": folder_name,
                    "chunk_index": idx,
                    "text": chunk_content,
                    "char_count": len(chunk_content),
                    "modified_at": mtime_iso,
                    "page": None,
                    "sheet": None,
                    "metadata": {"source": "local_file_agent", "file": filename},
                })
                idx += 1

            start = end - CHUNK_OVERLAP_CHARS if end < total_len else total_len

        return chunks

    # -----------------------------------------------------------------------
    # Scanning & Syncing
    # -----------------------------------------------------------------------

    def index_and_sync_folder(self, folder_path_str: str) -> None:
        """Scan one approved folder, index documents, and sync to Nanvi Cloud API."""
        with self._sync_lock:
            folder_path = Path(folder_path_str)
            if not folder_path.exists() or not folder_path.is_dir():
                logger.warning("Folder no longer exists: %s", folder_path)
                return

            display_name = self.approved_folders.get(folder_path_str, {}).get("display_name") or folder_path.name

            logger.info("Scanning local folder: %s ...", folder_path)
            files_meta: list[dict[str, Any]] = []
            all_chunks: list[dict[str, Any]] = []

            for root, dirs, files in os.walk(folder_path):
                # Filter hidden directories
                dirs[:] = [d for d in dirs if not d.startswith(".") and not d.startswith("$")]

                for fname in files:
                    if fname.startswith(".") or fname.startswith("~$"):
                        continue
                    file_p = Path(root) / fname
                    ext = file_p.suffix.casefold()

                    if ext in BLOCKED_EXTENSIONS or ext not in SUPPORTED_EXTENSIONS:
                        continue

                    try:
                        # Security check: ensure strictly relative to approved folder
                        rel_path = str(file_p.relative_to(folder_path)).replace("\\", "/")
                        stat = file_p.stat()

                        if stat.st_size > MAX_FILE_SIZE_BYTES:
                            logger.info("Skipping oversized file (%d MB): %s", stat.st_size // (1024 * 1024), rel_path)
                            continue

                        mtime_iso = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                        file_text = self._extract_text(file_p)
                        chunks = self.chunk_text(file_text, rel_path, fname, display_name, mtime_iso)

                        all_chunks.extend(chunks)
                        files_meta.append({
                            "relative_path": rel_path,
                            "filename": fname,
                            "folder_name": display_name,
                            "file_type": ext.lstrip("."),
                            "size_bytes": stat.st_size,
                            "chunk_count": len(chunks),
                            "modified_at": mtime_iso,
                        })
                    except Exception as exc:
                        logger.warning("Error indexing file %s: %s", fname, exc)

            logger.info("Indexed %d files (%d chunks) from %s", len(files_meta), len(all_chunks), display_name)

            # Transmit to Nanvi Cloud API
            self._push_sync(folder_path_str, display_name, files_meta, all_chunks)

    def _push_sync(self, folder_path: str, display_name: str, files: list[dict], chunks: list[dict]) -> bool:
        """Send folder chunks and metadata to the Nanvi cloud backend."""
        if not self.server_url or not self.token:
            logger.warning("Cannot sync: server_url or token missing.")
            return False

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
                if resp.status == 200:
                    logger.info("✓ Successfully synced '%s' to Nanvi Cloud.", display_name)
                    return True
        except HTTPError as err:
            logger.error("Cloud sync failed (HTTP %s): %s", err.code, err.read().decode("utf-8", errors="replace"))
        except URLError as err:
            logger.error("Cloud sync connection error: %s", err.reason)
        except Exception as exc:
            logger.error("Unexpected sync error: %s", exc)
        return False

    def send_heartbeat(self) -> bool:
        """Notify cloud backend that this agent is online and report connected folders."""
        if not self.server_url or not self.token:
            return False

        url = f"{self.server_url}/api/local-agent/heartbeat"
        folders_list = []
        for path_str, info in self.approved_folders.items():
            folders_list.append({
                "folder_id": path_str,
                "folder_path": path_str,
                "display_name": info.get("display_name") or Path(path_str).name,
                "file_count": 0,
                "chunk_count": 0,
                "status": "connected",
            })

        payload = {
            "agent_version": "1.0.0",
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
                            clean_rf = str(rf).strip()
                            if clean_rf and clean_rf not in self.approved_folders:
                                logger.info(">>> New folder requested from Web UI: %s", clean_rf)
                                try:
                                    self.add_folder(clean_rf)
                                    print(f"\n[Nanvi Web] Automatically connected folder: {clean_rf}")
                                    print("nanvi-agent> ", end="", flush=True)
                                except Exception as err:
                                    logger.warning("Could not add folder '%s': %s", clean_rf, err)
                    except Exception as parse_err:
                        logger.debug("Heartbeat response parse error: %s", parse_err)
                    return True
                return False
        except Exception as exc:
            logger.debug("Heartbeat error: %s", exc)
            return False

    # -----------------------------------------------------------------------
    # Background Daemon & File Watching
    # -----------------------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        """Send a heartbeat every 10 seconds."""
        consecutive_fails = 0
        while self.running:
            ok = self.send_heartbeat()
            if ok:
                if consecutive_fails > 0:
                    logger.info("✓ Reconnected to Nanvi Cloud API.")
                consecutive_fails = 0
            else:
                consecutive_fails += 1
                if consecutive_fails == 1:
                    logger.warning("Cloud connection unreachable. Retrying in background...")
            time.sleep(10)

    def _file_watch_loop(self) -> None:
        """Poll approved folders for file changes (creation, edit, deletion)."""
        while self.running:
            for path_str in list(self.approved_folders.keys()):
                p = Path(path_str)
                if not p.exists():
                    continue

                # Quick snapshot of current file mtimes
                current_snapshot: dict[str, float] = {}
                for root, _, files in os.walk(p):
                    for fname in files:
                        if fname.startswith(".") or fname.startswith("~$"):
                            continue
                        fpath = Path(root) / fname
                        if fpath.suffix.casefold() in SUPPORTED_EXTENSIONS:
                            try:
                                current_snapshot[str(fpath)] = fpath.stat().st_mtime
                            except OSError:
                                pass

                # Check if changed compared to previous snapshot
                last_snap = getattr(self, f"_snap_{path_str}", None)
                if last_snap is not None and current_snapshot != last_snap:
                    logger.info("Detected file change in %s. Re-indexing...", path_str)
                    self.index_and_sync_folder(path_str)

                setattr(self, f"_snap_{path_str}", current_snapshot)

            time.sleep(15)

    def start(self) -> None:
        """Start background heartbeat and watcher threads."""
        self.running = True
        t_hb = threading.Thread(target=self._heartbeat_loop, daemon=True)
        t_watch = threading.Thread(target=self._file_watch_loop, daemon=True)
        t_hb.start()
        t_watch.start()
        logger.info("Nanvi Local Agent started.")
        logger.info("Connected to: %s", self.server_url)

        # Initial index of all approved folders
        for folder_str in list(self.approved_folders.keys()):
            self.index_and_sync_folder(folder_str)

    def stop(self) -> None:
        self.running = False


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------

def run_interactive(agent: NanviLocalAgent) -> None:
    """Provide an interactive terminal console for managing local folders."""
    print("=" * 65)
    print("   NANVI AI ENTERPRISE ASSISTANT — LOCAL FILE AGENT")
    print("=" * 65)
    print("Connected to:", agent.server_url)
    print("\nCommands:")
    print("  add <path>       - Approve and connect a folder (e.g. add C:\\Projects)")
    print("  remove <path>    - Disconnect an approved folder")
    print("  list             - Show all approved folders")
    print("  sync             - Force re-index and sync all folders now")
    print("  status           - Check cloud connection and heartbeat status")
    print("  help             - Show this menu")
    print("  exit / quit      - Stop agent and exit")
    print("=" * 65)

    if not agent.approved_folders:
        print("\nTip: Type 'add <folder_path>' to connect your first folder.")

    while True:
        try:
            line = input("\nnanvi-agent> ").strip()
            if not line:
                continue

            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd in {"exit", "quit"}:
                print("Stopping Nanvi Local Agent...")
                agent.stop()
                break

            elif cmd == "add":
                if not arg:
                    print("Usage: add <folder_path> (e.g. add C:\\Projects or add C:\\CompanyData)")
                    continue
                try:
                    p = agent.add_folder(arg)
                    print(f"✓ Approved and indexing folder: {p}")
                except Exception as exc:
                    print(f"✗ Failed to add folder: {exc}")

            elif cmd == "remove":
                if not arg:
                    print("Usage: remove <folder_path>")
                    continue
                removed = agent.remove_folder(arg)
                if removed:
                    print(f"✓ Removed folder: {arg}")
                else:
                    print(f"✗ Folder not found in approved list: {arg}")

            elif cmd == "list":
                if not agent.approved_folders:
                    print("No folders connected yet. Use 'add <path>' to connect one.")
                else:
                    print(f"Connected Folders ({len(agent.approved_folders)}):")
                    for p, info in agent.approved_folders.items():
                        print(f"  • {p} [{info.get('display_name')}]")

            elif cmd == "sync":
                print("Re-indexing all approved folders...")
                for folder_str in list(agent.approved_folders.keys()):
                    agent.index_and_sync_folder(folder_str)

            elif cmd == "status":
                hb_ok = agent.send_heartbeat()
                print("Server URL:        ", agent.server_url)
                print("Cloud Connection:  ", "ONLINE ✓" if hb_ok else "OFFLINE ✗")
                print("Approved Folders:  ", len(agent.approved_folders))

            elif cmd == "browse" or cmd == "b":
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    selected = filedialog.askdirectory(title="Select folder for Nanvi AI Search")
                    root.destroy()
                    if selected:
                        print(f"Selected: {selected}")
                        agent.add_folder(selected)
                    else:
                        print("No folder selected.")
                except Exception as b_err:
                    print(f"Could not open folder picker ({b_err}). Please use 'add <path>' instead.")

            elif cmd == "help":
                print("Commands: browse (open folder picker), add <path>, remove <path>, list, sync, status, exit")

            else:
                print(f"Unknown command: {cmd}. Type 'help' for options.")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            agent.stop()
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Nanvi Local File Agent for Windows")
    parser.add_argument("--server", help="Nanvi Cloud or local server URL (e.g. https://nanviaienterpriseassistant.vercel.app)")
    parser.add_argument("--token", help="Pairing token generated in Nanvi Web Settings")
    parser.add_argument("--folder", action="append", help="Approved folder path to add immediately")
    parser.add_argument("--daemon", action="store_true", help="Run in background daemon mode without interactive CLI")
    args = parser.parse_args()

    # Load from config or environment if not passed
    config_data = {}
    if LOCAL_CONFIG_FILE.exists():
        try:
            config_data = json.loads(LOCAL_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not config_data and CONFIG_FILE.exists():
        try:
            config_data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    server_url = args.server or os.environ.get("NANVI_SERVER_URL") or config_data.get("server_url") or ""
    token = args.token or os.environ.get("NANVI_AGENT_TOKEN") or config_data.get("token") or ""

    if not server_url:
        print("\n--- Nanvi Local Agent Setup ---")
        server_url = input("Enter Nanvi Server URL [http://127.0.0.1:8000]: ").strip()
        if not server_url:
            server_url = "http://127.0.0.1:8000"

    if not token:
        print("\nPlease generate a Pairing Token from Nanvi Web (Settings -> Company Folder -> Local Agent).")
        token = input("Enter Pairing Token: ").strip()

    if not token:
        print("Error: A pairing token is required to authenticate with the cloud assistant.")
        sys.exit(1)

    agent = NanviLocalAgent(server_url=server_url, token=token)

    # Add folders from arguments
    if args.folder:
        for f in args.folder:
            try:
                agent.add_folder(f)
            except Exception as exc:
                print(f"Error adding folder {f}: {exc}")

    agent.start()

    if args.daemon:
        print("Nanvi Local Agent running in daemon mode. Press Ctrl+C to terminate.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            agent.stop()
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
