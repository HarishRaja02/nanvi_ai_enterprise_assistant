#!/usr/bin/env python3
"""
AI File Organizer  (Groq + openai/gpt-oss-120b + OCR)
=====================================================
No hard-coded categories. The AI reads each file (text, PDF, DOCX, XLSX, PPTX,
and OCR text from images / scanned PDFs), decides what it is about, and creates
whatever folder is needed:

    Organized / <AI category> / Created_YYYY-MM / Modified_YYYY-MM / file

SETUP (once):
    pip install rapidocr-onnxruntime pymupdf python-docx openpyxl python-pptx pillow
    (all optional - the script skips anything that is not installed)

    Get a free key at https://console.groq.com/keys then set it:
      Windows (PowerShell):   $env:GROQ_API_KEY="your_key_here"
      Windows (permanent):    setx GROQ_API_KEY "your_key_here"
      Mac/Linux:              export GROQ_API_KEY="your_key_here"

USAGE:
    1) Preview (nothing moves):   python organize_files_ai.py "C:\\Users\\You\\Documents"
    2) Do it for real:            python organize_files_ai.py "C:\\Users\\You\\Documents" --apply
    3) Undo a run:                python organize_files_ai.py --undo "<...>\\Organized\\move_log_XXXX.csv"

TWO MODES:
    --mode move   (default) the ORIGINAL files are moved into the organized folders
    --mode copy   originals stay untouched; arranged DUPLICATES are created (needs disk space)
    Undo works for both (move -> files go back, copy -> duplicates are deleted).

GUI:  streamlit run app.py     (same engine, with loading animation + editable review table)

OPTIONS:
    --date-by created|modified|both   date sub-folders (default: both)
    --copy            same as --mode copy
    --no-ocr          do not OCR images / scanned PDFs
    --no-content      send only file names to the AI (more private, less accurate)
    --batch N         files per AI request (default 10)
    --out FOLDER      output folder (default: <source>/Organized)
    --clean-empty     remove empty folders left behind
    --api-key KEY     pass the key directly instead of using the env variable

SAFETY (built in, cannot be turned off):
    - You MUST give the folder path. The script never scans on its own.
    - Refuses drive roots (C:\\ or /), C:\\Users, /Users, /home, /Volumes.
    - Never touches Windows, Program Files, ProgramData, AppData, Recycle Bin,
      System Volume Information; macOS /System, /Library, /Applications, ~/Library,
      .app bundles; Linux /usr, /etc, /bin, /var ...
    - Skips program/system files (.dll .sys .ini .lnk ...), hidden/system-flagged
      files, symlinks, and OneDrive cloud placeholders (so nothing gets downloaded).
    - .exe/.msi/.dmg/.pkg skipped unless you add --include-installers.
    - Every move is re-checked, asks you to type YES, and is logged for undo.

PRIVACY: file names and the first part of each file's text (including OCR text)
are sent to Groq for classification. Use --no-content if that is a concern.
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
OUTPUT_NAME = "Organized"
CACHE_FILE = Path.home() / ".file_organizer_cache.json"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif", ".gif"}
PLAIN_TEXT_EXT = {".txt", ".csv", ".md", ".json", ".xml", ".html", ".htm", ".rtf", ".log",
                  ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".sql", ".php", ".ipynb"}

# ---------------------------------------------------------------------------
# PROTECTED AREAS - the script will NEVER read, move, copy or delete anything
# inside these, even if you point it at them by mistake.
# ---------------------------------------------------------------------------
# Top-level folders of the drive (C:\<name>  or  /<name>)
PROTECTED_TOP_WINDOWS = {
    "windows", "program files", "program files (x86)", "programdata", "$recycle.bin",
    "system volume information", "recovery", "boot", "perflogs", "msocache", "config.msi",
    "$winreagent", "$windows.~bt", "$windows.~ws", "windows.old", "efi", "documents and settings",
}
PROTECTED_TOP_UNIX = {          # macOS + Linux
    "system", "library", "applications", "usr", "bin", "sbin", "etc", "var", "private",
    "opt", "dev", "proc", "sys", "boot", "cores", "lib", "lib32", "lib64", "root",
    "snap", "srv", "run", "lost+found",
}
# Folder names that are protected wherever they appear
PROTECTED_ANYWHERE = {
    "appdata", "$recycle.bin", "system volume information", "windows.old",
    "node_modules", ".git", ".venv", "venv", "site-packages", "__pycache__",
}
# Inside your own home folder
PROTECTED_HOME_SUBDIRS = {
    "library", "applications", "appdata", ".config", ".local", ".ssh", ".gnupg",
    ".cache", ".docker", ".vscode", ".npm",
}
# macOS app bundles / system-managed libraries are folders that must be left alone
PROTECTED_DIR_SUFFIXES = (".app", ".framework", ".bundle", ".kext", ".photoslibrary",
                          ".musiclibrary", ".tvlibrary", ".xcodeproj", ".lproj")
# Too-broad parents: C:\Users, /Users, /home, /Volumes ...
CONTAINER_FOLDERS = {"users", "home", "volumes", "mnt", "media"}

# Program / system file types are never touched
SKIP_EXTENSIONS = {
    ".dll", ".sys", ".ini", ".lnk", ".tmp", ".dat", ".lock", ".so", ".dylib", ".drv",
    ".ocx", ".cpl", ".scr", ".mui", ".cat", ".inf", ".kext", ".plist", ".com", ".msc",
}
INSTALLER_EXTENSIONS = {".exe", ".msi", ".dmg", ".pkg", ".apk", ".deb", ".rpm"}   # skipped unless --include-installers
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}

MAX_READ_BYTES = 60 * 1024 * 1024     # do not open content of files bigger than this
SNIPPET_CHARS = 600                   # text sent to the AI per file


# ----------------------------------------------------------------------------
# 1. CONTENT EXTRACTION  (text files, Office files, PDFs, images via OCR)
# ----------------------------------------------------------------------------
_ocr_engine = None
_ocr_kind = None
_warned = set()
_log = print                                   # the Streamlit app can swap this for its own logger


def set_logger(fn):
    global _log
    _log = fn


def warn_once(msg):
    if msg not in _warned:
        _warned.add(msg)
        _log(f"  [note] {msg}")


def ocr_image(path: str) -> str:
    """OCR an image file. Uses RapidOCR (pip only) or pytesseract as fallback."""
    global _ocr_engine, _ocr_kind
    if _ocr_kind is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine, _ocr_kind = RapidOCR(), "rapid"
        except Exception:
            try:
                import pytesseract  # needs Tesseract program installed too
                _ocr_engine, _ocr_kind = pytesseract, "tess"
            except Exception:
                _ocr_kind = "none"
                warn_once("OCR not available. Run: pip install rapidocr-onnxruntime  (images will be sorted by name only)")
    try:
        if _ocr_kind == "rapid":
            result, _ = _ocr_engine(path)
            return " ".join(r[1] for r in (result or []))
        if _ocr_kind == "tess":
            from PIL import Image
            return _ocr_engine.image_to_string(Image.open(path))
    except Exception:
        pass
    return ""


def read_pdf(path: Path, use_ocr: bool) -> str:
    try:
        import fitz  # PyMuPDF
    except Exception:
        warn_once("PDF reading needs: pip install pymupdf")
        return ""
    text = ""
    try:
        doc = fitz.open(str(path))
        for i, page in enumerate(doc):
            if i >= 3:
                break
            text += page.get_text() + "\n"
        if len(text.strip()) < 40 and use_ocr and len(doc) > 0:   # scanned PDF -> OCR
            for i, page in enumerate(doc):
                if i >= 2:
                    break
                with tempfile.TemporaryDirectory() as td:
                    img = os.path.join(td, "p.png")
                    page.get_pixmap(dpi=150).save(img)
                    text += ocr_image(img) + "\n"
        doc.close()
    except Exception:
        pass
    return text


def extract_text(path: Path, use_ocr: bool) -> str:
    ext = path.suffix.lower()
    try:
        if path.stat().st_size > MAX_READ_BYTES:
            return ""
        if ext in IMAGE_EXT:
            return ocr_image(str(path)) if use_ocr else ""
        if ext == ".pdf":
            return read_pdf(path, use_ocr)
        if ext in PLAIN_TEXT_EXT:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(4000)
        if ext == ".docx":
            import docx
            d = docx.Document(str(path))
            return " ".join(p.text for p in d.paragraphs[:60])
        if ext in {".xlsx", ".xlsm"}:
            import openpyxl
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            out = []
            for ws in wb.worksheets[:2]:
                out.append(f"[sheet {ws.title}]")
                for row in ws.iter_rows(min_row=1, max_row=25, values_only=True):
                    out.append(" ".join(str(c) for c in row if c is not None))
            return "\n".join(out)
        if ext == ".pptx":
            from pptx import Presentation
            prs = Presentation(str(path))
            out = []
            for slide in list(prs.slides)[:5]:
                for shp in slide.shapes:
                    if getattr(shp, "has_text_frame", False):
                        out.append(shp.text_frame.text)
            return " ".join(out)
    except ImportError as e:
        warn_once(f"Missing library for {ext} files: {e.name}  (pip install it to read inside these files)")
    except Exception:
        pass
    return ""


def clean_snippet(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:SNIPPET_CHARS]


# ----------------------------------------------------------------------------
# 2. GROQ / GPT-OSS-120B CLASSIFIER
# ----------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a smart file-organizing assistant. For every file you are given, decide the single best FOLDER NAME it belongs in.

Rules:
- Judge by the actual content (text_snippet / OCR text) first, then file name, then parent folder hints, then file type.
- Folder names: 1-3 words, Title_Case with underscores, e.g. Finance, College, Medical, Travel_Tickets, Resume_Jobs, Screenshots, Family_Photos, Programming, Legal_Documents.
- You are NOT limited to any fixed list. Create a new folder name whenever nothing fits.
- BUT prefer REUSING a name from "existing_categories" when it fits, so similar files land together. Do not create near-duplicates (e.g. do not make "Financial_Docs" if "Finance" exists).
- Keep folders broad enough to hold many files (not one folder per file).
- Images with OCR text: classify by what the text says (a bill photo -> Finance, a lecture slide -> College).
- Images with no text: use the file name / type (e.g. Photos, Screenshots, Wallpapers, Memes).
- If you truly cannot tell, use "Miscellaneous".

Reply with JSON only, exactly in this shape:
{"results":[{"id":0,"category":"Finance","reason":"short reason"}]}"""


def call_groq(api_key: str, messages: list, retries: int = 5) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_completion_tokens": 6000,
        "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
    }
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            GROQ_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "file-organizer/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            if e.code == 401:
                raise PermissionError("Groq rejected the API key (401). Check your GROQ_API_KEY.")
            if e.code == 429 or e.code >= 500:
                wait = float(e.headers.get("retry-after", 0) or 0) or min(5 * attempt, 30)
                print(f"  [api] rate limit / server busy ({e.code}); waiting {wait:.0f}s ...")
                time.sleep(wait)
                continue
            if e.code == 400 and ("reasoning_effort" in payload or "response_format" in payload):
                payload.pop("reasoning_effort", None)      # some accounts reject optional params
                payload.pop("response_format", None)
                continue
            raise RuntimeError(f"Groq error {e.code}: {body[:300]}")
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  [api] network problem ({e}); retrying ...")
            time.sleep(3 * attempt)
    raise RuntimeError("Groq did not respond after several retries")


def parse_json_loose(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON in reply")
    return json.loads(text[start:end + 1])


def safe_folder_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(name or ""))
    name = re.sub(r"\s+", "_", name.strip()).strip("._")
    return name[:40] or "Miscellaneous"


def canonical(cat: str, known: set) -> str:
    """Reuse an existing folder if the AI spelled it slightly differently."""
    key = re.sub(r"[^a-z0-9]", "", cat.lower())
    for k in known:
        if re.sub(r"[^a-z0-9]", "", k.lower()) == key:
            return k
    return cat


def classify_batch(api_key: str, items: list, known: set) -> dict:
    """items: [{id,name,type,folder_hint,text_snippet}] -> {id: (category, reason)}"""
    user_msg = json.dumps({"existing_categories": sorted(known), "files": items}, ensure_ascii=False)
    reply = call_groq(api_key, [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])
    results = parse_json_loose(reply).get("results", [])
    out = {}
    for r in results:
        try:
            cat = canonical(safe_folder_name(r.get("category")), known)
            out[int(r["id"])] = (cat, str(r.get("reason", ""))[:120])
            known.add(cat)
        except Exception:
            continue
    return out


# ----------------------------------------------------------------------------
# 3. FILE SYSTEM HELPERS
# ----------------------------------------------------------------------------
def get_dates(path: Path):
    st = path.stat()
    modified = datetime.fromtimestamp(st.st_mtime)
    birth = getattr(st, "st_birthtime", None)           # macOS
    if birth is None:
        birth = st.st_ctime if os.name == "nt" else min(st.st_ctime, st.st_mtime)
    return datetime.fromtimestamp(birth), modified


def build_destination(out_root: Path, category: str, created, modified, date_by: str) -> Path:
    dest = out_root / category
    if date_by in ("created", "both"):
        dest /= f"Created_{created:%Y-%m}"
    if date_by in ("modified", "both"):
        dest /= f"Modified_{modified:%Y-%m}"
    return dest


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    i = 1
    while True:
        c = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not c.exists():
            return c
        i += 1


def is_protected_path(p: Path) -> bool:
    """True if p is, or is inside, an operating-system / application area."""
    try:
        p = p.resolve()
    except Exception:
        return True                                   # cannot verify -> treat as protected
    parts = [x.lower().rstrip("\\/") for x in p.parts]
    if len(parts) > 1:
        top = PROTECTED_TOP_WINDOWS if os.name == "nt" else PROTECTED_TOP_UNIX
        if parts[1] in top:
            return True
        if any(x in PROTECTED_ANYWHERE for x in parts[1:]):
            return True
        if any(x.endswith(PROTECTED_DIR_SUFFIXES) for x in parts[1:]):
            return True
    try:
        rel = p.relative_to(Path.home().resolve())
        if rel.parts and rel.parts[0].lower() in PROTECTED_HOME_SUBDIRS:
            return True
    except Exception:
        pass
    return False


def source_problem(source: Path):
    """Return a BLOCKED message if the folder is a system area, otherwise None."""
    p = source.resolve()
    if p == Path(p.anchor):
        return "BLOCKED: that is a whole drive (C:\\ or /). Give a specific folder such as Documents or Downloads. Nothing was touched."
    if is_protected_path(p):
        return f"BLOCKED: {p} is (or is inside) a protected Windows/macOS/Linux system or application area. Nothing was touched."
    if len(p.parts) == 2 and p.parts[1].lower() in CONTAINER_FOLDERS:
        return f"BLOCKED: {p} is too broad (it contains other users' / drives' data). Pick your own folder inside it."
    return None


def is_system_flagged(p: Path) -> bool:
    """Skip files marked hidden/system by the OS, and cloud placeholders (so OneDrive does not download them)."""
    try:
        st = p.stat()
    except Exception:
        return True
    # Windows: hidden 0x2, system 0x4, offline 0x1000, recall-on-open 0x40000, recall-on-data-access 0x400000
    if getattr(st, "st_file_attributes", 0) & (0x2 | 0x4 | 0x1000 | 0x40000 | 0x400000):
        return True
    if getattr(st, "st_flags", 0) & 0xFFFF0000:           # macOS system-immutable flags
        return True
    return False


def assert_safe(src: Path, source: Path, dst: Path, out_root: Path):
    """Last check right before every single move/copy."""
    s, d = src.resolve(), dst.resolve()
    if source.resolve() not in s.parents:
        raise RuntimeError("file is outside the folder you chose")
    if is_protected_path(s.parent):
        raise RuntimeError("file is in a protected system location")
    if out_root.resolve() not in d.parents:
        raise RuntimeError("destination is outside the Organized folder")
    if is_protected_path(d.parent):
        raise RuntimeError("destination is in a protected system location")


def scan(source: Path, out_root: Path, include_installers: bool = False):
    out_res = out_root.resolve()
    skip_ext = SKIP_EXTENSIONS if include_installers else (SKIP_EXTENSIONS | INSTALLER_EXTENSIONS)
    for root, dirs, files in os.walk(source):             # does not follow symlinks
        rp = Path(root)
        dirs[:] = [d for d in dirs
                   if not d.startswith(".")
                   and not (rp / d).is_symlink()
                   and (rp / d).resolve() != out_res
                   and not is_protected_path(rp / d)]
        for fname in files:
            if fname.lower() in SKIP_NAMES or fname.startswith("."):
                continue
            p = rp / fname
            if p.suffix.lower() in skip_ext or p.is_symlink():
                continue
            if is_system_flagged(p) or not os.access(p, os.R_OK):
                continue
            yield p


def load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache: dict):
    try:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def cache_key(p: Path) -> str:
    st = p.stat()
    return f"{p}|{st.st_size}|{int(st.st_mtime)}"


# ----------------------------------------------------------------------------
# 4. ENGINE  (used by both the command line and the Streamlit app)
#    progress callback signature:  progress(fraction_0_to_1, message)
# ----------------------------------------------------------------------------
MODES = ("move", "copy")


def summarize(plan: list) -> dict:
    out = {}
    for it in plan:
        out[it["category"]] = out.get(it["category"], 0) + 1
    return dict(sorted(out.items(), key=lambda x: -x[1]))


def finalize_destinations(plan: list, out_root: Path, date_by: str):
    """(Re)compute each file's destination from its category + dates."""
    for it in plan:
        it["category"] = safe_folder_name(it["category"])
        it["dst"] = build_destination(out_root, it["category"], it["created"], it["modified"], date_by) / it["src"].name


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def build_plan(source, out_root=None, api_key="", date_by="both", use_ocr=True, send_content=True,
               include_installers=False, batch=10, delay=1.0, progress=None, log=None):
    """
    Scan + read + classify. NOTHING is moved or copied here.
    Returns (plan, source_path, out_root_path).
    plan = list of dicts: src, dst, category, reason, created, modified, size
    """
    log = log or _log
    prog = progress or (lambda f, m: None)
    if not api_key:
        raise ValueError("No Groq API key provided.")

    source = Path(str(source).strip().strip('"')).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Folder not found: {source}")
    problem = source_problem(source)
    if problem:
        raise ValueError(problem)
    out_root = Path(str(out_root).strip().strip('"')).expanduser().resolve() if out_root else source / OUTPUT_NAME
    if is_protected_path(out_root) or out_root == Path(out_root.anchor):
        raise ValueError(f"BLOCKED: output folder {out_root} is in a protected system location.")

    prog(0.0, "Scanning folders ...")
    files = list(scan(source, out_root, include_installers))
    if not files:
        return [], source, out_root

    cache = load_cache()
    known = set()
    if out_root.is_dir():
        known.update(d.name for d in out_root.iterdir() if d.is_dir())
    known.update(v["category"] for v in cache.values() if isinstance(v, dict) and "category" in v)

    todo = [f for f in files if cache_key(f) not in cache]
    log(f"Found {len(files)} file(s): {len(files) - len(todo)} cached, {len(todo)} to classify.")
    n = max(len(todo), 1)

    for b in range(0, len(todo), batch):
        chunk = todo[b:b + batch]
        items = []
        for i, f in enumerate(chunk):
            prog(0.03 + 0.94 * ((b + i) / n), f"Reading: {f.name}")
            text = "" if not send_content else clean_snippet(extract_text(f, use_ocr))
            items.append({"id": i, "name": f.name, "type": f.suffix.lower() or "(none)",
                          "folder_hint": " / ".join(f.parent.parts[-3:]), "text_snippet": text})
        prog(0.03 + 0.94 * ((b + len(chunk) * 0.9) / n),
             f"AI is classifying files {b + 1}-{b + len(chunk)} of {len(todo)} ...")
        try:
            res = classify_batch(api_key, items, known)
        except PermissionError:
            raise
        except Exception as e:
            log(f"[warn] AI failed for one batch ({e}); those files go to 'Unsorted'.")
            res = {}
        for i, f in enumerate(chunk):
            if i in res:
                cache[cache_key(f)] = {"category": res[i][0], "reason": res[i][1]}
            else:
                cache[cache_key(f)] = {"category": "Unsorted", "reason": "AI gave no answer", "_retry": True}
        save_cache({k: v for k, v in cache.items() if not v.get("_retry")})
        if b + batch < len(todo):
            time.sleep(delay)

    plan = []
    for f in files:
        info = cache.get(cache_key(f), {"category": "Unsorted", "reason": ""})
        created, modified = get_dates(f)
        plan.append({"src": f, "dst": None, "category": info["category"], "reason": info.get("reason", ""),
                     "created": created, "modified": modified, "size": f.stat().st_size})
    finalize_destinations(plan, out_root, date_by)
    prog(1.0, "Classification complete")
    return plan, source, out_root


def execute_plan(plan: list, source, out_root, mode: str = "move", clean_empty: bool = False,
                 progress=None, log=None) -> dict:
    """
    mode = "move": the ORIGINAL files are moved into the organized folders.
    mode = "copy": the originals stay exactly where they are; organized DUPLICATES are created.
    Returns {"log_path", "done", "failed", "errors"}.
    """
    log = log or _log
    prog = progress or (lambda f, m: None)
    if mode not in MODES:
        raise ValueError("mode must be 'move' or 'copy'")
    source, out_root = Path(source).resolve(), Path(out_root).resolve()
    if is_protected_path(out_root):
        raise ValueError("Output folder is in a protected system location.")
    out_root.mkdir(parents=True, exist_ok=True)

    if mode == "copy":                                   # make sure the disk has room for the duplicates
        need = sum(it["size"] for it in plan)
        free = shutil.disk_usage(out_root).free
        if need * 1.05 > free:
            raise RuntimeError(f"Not enough disk space for copies: need {human_size(need)}, only {human_size(free)} free.")

    log_path = out_root / f"{mode}_log_{datetime.now():%Y%m%d_%H%M%S}.csv"
    done, errors = 0, []
    total = max(len(plan), 1)
    verb = "Copying" if mode == "copy" else "Moving"
    with open(log_path, "w", newline="", encoding="utf-8") as lf:
        w = csv.writer(lf)
        w.writerow(["original_path", "new_path", "mode", "category", "reason"])
        for i, it in enumerate(plan):
            src, dst = it["src"], it["dst"]
            prog(i / total, f"{verb}: {src.name}")
            try:
                assert_safe(src, source, dst, out_root)
                dst.parent.mkdir(parents=True, exist_ok=True)
                final = unique_path(dst)
                if mode == "copy":
                    shutil.copy2(str(src), str(final))
                    if final.stat().st_size != src.stat().st_size:      # verify the duplicate is complete
                        final.unlink(missing_ok=True)
                        raise RuntimeError("copy verification failed (size mismatch)")
                else:
                    shutil.move(str(src), str(final))
                w.writerow([str(src), str(final), mode, it["category"], it["reason"]])
                lf.flush()
                done += 1
            except Exception as e:
                errors.append(f"{src}: {e}")

    if clean_empty and mode == "move":
        for root, _, _ in os.walk(source, topdown=False):
            rp = Path(root)
            if rp == source or rp.resolve() == out_root or out_root in rp.resolve().parents:
                continue
            try:
                if not any(rp.iterdir()):
                    rp.rmdir()
            except Exception:
                pass
    prog(1.0, "Finished")
    return {"log_path": log_path, "done": done, "failed": len(errors), "errors": errors}


def undo_log(log_file, progress=None, log=None) -> dict:
    """Reverse a run: moved files go back to where they were; copies are deleted (originals were never touched)."""
    prog = progress or (lambda f, m: None)
    log_file = Path(log_file)
    if not log_file.is_file():
        raise ValueError(f"Log not found: {log_file}")
    with open(log_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    restored, errors = 0, []
    total = max(len(rows), 1)
    for i, row in enumerate(rows):
        new, orig = Path(row["new_path"]), Path(row["original_path"])
        prog(i / total, f"Undoing: {new.name}")
        if not new.exists():
            continue
        try:
            if row["mode"] == "copy":
                new.unlink()
            else:
                orig.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(new), str(unique_path(orig)))
            restored += 1
        except Exception as e:
            errors.append(f"{new}: {e}")
    prog(1.0, "Undo complete")
    return {"restored": restored, "failed": len(errors), "errors": errors}


def find_logs(out_root) -> list:
    out_root = Path(out_root)
    if not out_root.is_dir():
        return []
    return sorted(out_root.glob("*_log_*.csv"), reverse=True)


# ----------------------------------------------------------------------------
# 5. COMMAND LINE
# ----------------------------------------------------------------------------
def cli_progress(frac, msg):
    print(f"  [{int(frac * 100):3d}%] {msg[:90]}")


def run_cli(args):
    api_key = args.api_key or os.environ.get("GROQ_API_KEY")
    mode = "copy" if (args.copy or args.mode == "copy") else "move"
    try:
        plan, source, out_root = build_plan(
            args.source, args.out, api_key, args.date_by, not args.no_ocr, not args.no_content,
            args.include_installers, args.batch, args.delay, cli_progress)
    except (ValueError, PermissionError) as e:
        sys.exit(str(e))
    if not plan:
        print("No files found.")
        return

    print("\nAI-created categories:")
    for cat, n in summarize(plan).items():
        print(f"  {cat:<28} {n} file(s)")
    print(f"  {'TOTAL':<28} {len(plan)} file(s)\n")

    if not args.apply:
        print("PREVIEW (first 30 files):")
        for it in plan[:30]:
            print(f"  {it['src'].name}\n     -> {it['category']}  ({it['reason']})\n     -> {it['dst'].parent}")
        print(f"\nNothing was changed. Add --apply to {mode.upper()} for real "
              f"({'originals stay untouched, duplicates are arranged' if mode == 'copy' else 'originals are moved'}).")
        return

    if not args.yes:
        print("SAFETY CHECK")
        print(f"  Folder to organize : {source}")
        print(f"  Output folder      : {out_root}")
        print(f"  Mode               : {mode.upper()} {len(plan)} file(s)"
              + ("  (originals stay where they are)" if mode == "copy" else "  (originals are moved)"))
        print("  Windows/macOS system folders, AppData/Library, program files are never touched.")
        try:
            ans = input("Type YES to continue: ").strip()
        except EOFError:
            ans = ""
        if ans != "YES":
            print("Cancelled. Nothing was changed.")
            return

    try:
        res = execute_plan(plan, source, out_root, mode, args.clean_empty, cli_progress)
    except (ValueError, RuntimeError) as e:
        sys.exit(str(e))
    for e in res["errors"][:20]:
        print(f"  [failed] {e}")
    print(f"\nDone. {res['done']} file(s) {'copied' if mode == 'copy' else 'moved'}, {res['failed']} failed.")
    print(f"Undo log: {res['log_path']}")
    print(f'To undo:  python organize_files_ai.py --undo "{res["log_path"]}"')


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="AI file organizer (Groq gpt-oss-120b + OCR)")
    ap.add_argument("source", nargs="?", help="Folder to organize")
    ap.add_argument("--apply", action="store_true", help="Really do it (default: preview only)")
    ap.add_argument("--mode", choices=list(MODES), default="move",
                    help="move = arrange the ORIGINAL files; copy = keep originals, arrange DUPLICATES")
    ap.add_argument("--copy", action="store_true", help="same as --mode copy")
    ap.add_argument("--date-by", choices=["created", "modified", "both"], default="both")
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--no-content", action="store_true")
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between AI requests")
    ap.add_argument("--out")
    ap.add_argument("--clean-empty", action="store_true")
    ap.add_argument("--yes", action="store_true", help="skip the 'Type YES' confirmation")
    ap.add_argument("--include-installers", action="store_true",
                    help="also organize .exe/.msi/.dmg/.pkg files (skipped by default)")
    ap.add_argument("--api-key")
    ap.add_argument("--undo", metavar="LOG_CSV")
    args = ap.parse_args()

    if args.undo:
        try:
            r = undo_log(args.undo, cli_progress)
        except ValueError as e:
            sys.exit(str(e))
        print(f"Undo complete. {r['restored']} file(s) restored/removed, {r['failed']} failed.")
    elif args.source:
        run_cli(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
