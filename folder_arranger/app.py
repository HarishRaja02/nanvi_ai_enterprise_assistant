"""
AI File Organizer - Streamlit app
Run:   streamlit run app.py
(keep this file in the same folder as organize_files_ai.py)
"""
import html
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

import organize_files_ai as core

st.set_page_config(page_title="AI File Organizer", page_icon="🗂️", layout="wide")

# ----------------------------------------------------------------------------
# Loading animation (spinner + shimmering progress bar + live message)
# ----------------------------------------------------------------------------
st.markdown("""
<style>
.fo-card{display:flex;gap:16px;align-items:center;padding:18px 20px;border-radius:14px;
  border:1px solid rgba(128,128,128,.25);
  background:linear-gradient(135deg,rgba(255,75,75,.08),rgba(255,166,43,.08));}
.fo-ring{flex:0 0 38px;width:38px;height:38px;border-radius:50%;
  border:4px solid rgba(128,128,128,.25);border-top-color:#ff4b4b;border-right-color:#ffa62b;
  animation:fo-spin .8s linear infinite;}
.fo-body{flex:1;min-width:0}
.fo-title{font-weight:600;font-size:1.05rem;margin-bottom:2px}
.fo-msg{font-size:.88rem;opacity:.75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:10px}
.fo-track{height:10px;border-radius:10px;background:rgba(128,128,128,.2);overflow:hidden}
.fo-fill{height:100%;border-radius:10px;
  background:linear-gradient(90deg,#ff4b4b,#ffa62b,#ff4b4b);background-size:200% 100%;
  animation:fo-shimmer 1.1s linear infinite;transition:width .25s ease;}
.fo-pct{font-variant-numeric:tabular-nums;font-weight:600;min-width:48px;text-align:right}
@keyframes fo-spin{to{transform:rotate(360deg)}}
@keyframes fo-shimmer{to{background-position:-200% 0}}
</style>
""", unsafe_allow_html=True)


def _esc(text: str) -> str:
    # escape HTML and "$" (Streamlit would treat $...$ in file names as math)
    return html.escape(str(text)).replace("$", "&#36;")


class Loader:
    """Animated progress card. Pass loader.update as the `progress` callback of the engine."""

    def __init__(self, title: str):
        self.title = title
        self.ph = st.empty()
        self._last = 0.0
        self.update(0.0, "Starting ...", force=True)

    def update(self, frac: float, msg: str, force: bool = False):
        now = time.time()
        if not force and frac < 1 and now - self._last < 0.08:     # do not flood the browser
            return
        self._last = now
        pct = int(max(0.0, min(1.0, frac)) * 100)
        self.ph.markdown(
            f'<div class="fo-card"><div class="fo-ring"></div><div class="fo-body">'
            f'<div class="fo-title">{_esc(self.title)}</div><div class="fo-msg">{_esc(msg)}</div>'
            f'<div class="fo-track"><div class="fo-fill" style="width:{pct}%"></div></div></div>'
            f'<div class="fo-pct">{pct}%</div></div>',
            unsafe_allow_html=True)

    def done(self):
        self.ph.empty()


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def pick_folder() -> str:
    """Open the operating system's folder picker (works when the app runs on your own laptop)."""
    code = ("import tkinter as tk\nfrom tkinter import filedialog\n"
            "r=tk.Tk();r.withdraw();r.attributes('-topmost',True)\n"
            "print(filedialog.askdirectory(title='Choose the folder to organize'))")
    try:
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
        return out.stdout.strip()
    except Exception:
        return ""


def browse_callback():
    p = pick_folder()
    if p:
        st.session_state.folder = p


def free_space(path: Path) -> int:
    p = path
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def wide_table(df, **kw):
    try:
        return st.data_editor(df, width="stretch", **kw)
    except TypeError:                                   # older Streamlit versions
        return st.data_editor(df, use_container_width=True, **kw)


st.session_state.setdefault("folder", "")
st.session_state.setdefault("outdir", "")
st.session_state.setdefault("plan", None)
st.session_state.setdefault("meta", None)
st.session_state.setdefault("result", None)
st.session_state.setdefault("logs", [])
st.session_state.setdefault("run_id", 0)
core.set_logger(lambda m: st.session_state.logs.append(str(m)))

# ----------------------------------------------------------------------------
# Sidebar settings
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("Groq API key", value=os.environ.get("GROQ_API_KEY", ""), type="password",
                            help="Free key from console.groq.com/keys. It is only kept in this browser session.")
    st.caption(f"AI model: `{core.MODEL}`")
    date_by = st.selectbox("Date sub-folders", ["both", "created", "modified"],
                           format_func={"both": "Created + Modified", "created": "Created date only",
                                        "modified": "Modified date only"}.get)
    use_ocr = st.checkbox("OCR images & scanned PDFs", True)
    send_content = st.checkbox("Let the AI read file contents", True,
                               help="Turn off to send only file names to Groq (more private, less accurate).")
    include_installers = st.checkbox("Include installers (.exe .msi .dmg .pkg)", False)
    clean_empty = st.checkbox("Remove empty folders left behind (Move mode)", False)
    batch = st.slider("Files per AI request", 5, 20, 10)
    delay = st.slider("Pause between AI requests (sec)", 0.0, 5.0, 1.0, 0.5,
                      help="Raise this if you hit Groq's free-tier rate limit.")
    st.divider()
    st.caption("🔒 Windows / macOS system folders, AppData, Library and program files are never touched.")

st.title("🗂️ AI File Organizer")
st.caption("Groq · gpt-oss-120b · OCR — sorts files into AI-created folders, then by created / modified date.")

tab_org, tab_undo, tab_about = st.tabs(["📁 Organize", "↩️ Undo", "🛡️ Safety & help"])

# ============================================================================
# TAB 1 - ORGANIZE
# ============================================================================
def render_organize():
    # ---------- finished-run screen ----------
    res = st.session_state.result
    if res:
        verb = "copied" if res["mode"] == "copy" else "moved"
        if res["failed"] == 0:
            st.success(f"✅ Done! {res['done']} file(s) {verb}.")
        else:
            st.warning(f"Finished: {res['done']} file(s) {verb}, {res['failed']} failed.")
            with st.expander("Show errors"):
                st.code("\n".join(res["errors"][:100]))
        if res["mode"] == "copy":
            st.info("Your original files were not touched. The arranged duplicates are in:")
        else:
            st.info("Your original files were moved into:")
        st.code(str(res["out_root"]))
        st.caption(f"Undo log saved: {res['log_path']}  (use the Undo tab)")
        if st.button("Start a new run"):
            st.session_state.result = None
            st.rerun()
        return

    # ---------- step 1: folder ----------
    st.subheader("1 · Choose the folder to organize")
    c1, c2 = st.columns([6, 1], vertical_alignment="bottom")
    c1.text_input("Folder path", key="folder",
                  placeholder=r"C:\Users\YourName\Documents   or   /Users/yourname/Downloads")
    c2.button("📂 Browse", on_click=browse_callback, help="Opens a folder picker on this computer")
    st.text_input("Output folder (optional)", key="outdir",
                  placeholder="Leave empty to create  <chosen folder>/Organized")

    # ---------- step 2: mode ----------
    st.subheader("2 · Choose a mode")
    mode = st.radio(
        "Mode", ["move", "copy"], horizontal=True, label_visibility="collapsed",
        format_func={"move": "🚚  Move originals  (arrange the real files)",
                     "copy": "📄  Copy first  (keep originals, arrange duplicates)"}.get)
    if mode == "move":
        st.info("**Move mode** — your original files are moved into the new folders. "
                "Nothing is duplicated and no extra disk space is used. Fully undoable.")
    else:
        st.info("**Copy mode** — your original files stay exactly where they are. "
                "Duplicates are created and arranged in the Organized folder. Needs extra disk space. "
                "Undo just deletes the duplicates.")

    # ---------- step 3: scan ----------
    st.subheader("3 · Scan & classify")
    scan_clicked = st.button("🔍 Scan & classify with AI", type="primary",
                             disabled=not st.session_state.folder.strip())
    if scan_clicked:
        st.session_state.plan = None
        st.session_state.logs = []
        loader = Loader("Scanning & classifying with AI")
        try:
            plan, src, out_root = core.build_plan(
                st.session_state.folder, st.session_state.outdir or None, api_key, date_by,
                use_ocr, send_content, include_installers, batch, delay, progress=loader.update)
            loader.done()
            if not plan:
                st.warning("No organizable files found in that folder.")
            else:
                st.session_state.plan = plan
                st.session_state.meta = {"source": str(src), "out_root": str(out_root)}
        except (ValueError, PermissionError) as e:
            loader.done()
            st.error(str(e))
        except Exception as e:
            loader.done()
            st.error(f"Unexpected error: {e}")

    # ---------- results ----------
    plan, meta = st.session_state.plan, st.session_state.meta
    if plan:
        summary = core.summarize(plan)
        total_size = sum(it["size"] for it in plan)
        m1, m2, m3 = st.columns(3)
        m1.metric("Files", len(plan))
        m2.metric("AI-created folders", len(summary))
        m3.metric("Total size", core.human_size(total_size))
        st.bar_chart(pd.Series(summary, name="files"))

        st.markdown("**Review the AI's choices** — you can edit any *Category* cell before applying.")
        df = pd.DataFrame([{
            "File": it["src"].name,
            "Category": it["category"],
            "Why (AI)": it["reason"],
            "Size": core.human_size(it["size"]),
            "Created": it["created"].strftime("%Y-%m-%d"),
            "Modified": it["modified"].strftime("%Y-%m-%d"),
            "Current location": str(it["src"].parent),
        } for it in plan])
        edited = wide_table(df, disabled=[c for c in df.columns if c != "Category"],
                            hide_index=True, height=360, key="editor")

        # ---------- step 4: apply ----------
        st.subheader("4 · Apply")
        out_root = Path(meta["out_root"])
        if mode == "copy":
            free = free_space(out_root)
            if total_size * 1.05 > free:
                st.error(f"Not enough free disk space for duplicates: need {core.human_size(total_size)}, "
                         f"free {core.human_size(free)}. Choose another output folder or use Move mode.")
            else:
                st.caption(f"Copy mode will use about {core.human_size(total_size)} "
                           f"({core.human_size(free)} free).")
        st.write(f"**{'Copy' if mode == 'copy' else 'Move'} {len(plan)} file(s)** from `{meta['source']}` "
                 f"into `{meta['out_root']}`")
        confirm = st.text_input("Type YES to confirm", key=f"confirm_{st.session_state.run_id}")
        go = st.button(("📄 Copy & arrange" if mode == "copy" else "🚚 Move & arrange"),
                       type="primary", disabled=confirm.strip() != "YES")
        if go:
            for it, cat in zip(plan, edited["Category"]):
                it["category"] = cat or "Unsorted"
            core.finalize_destinations(plan, out_root, date_by)
            loader = Loader("Copying files ..." if mode == "copy" else "Moving files ...")
            try:
                r = core.execute_plan(plan, meta["source"], out_root, mode, clean_empty, loader.update)
                loader.done()
                r.update(mode=mode, out_root=str(out_root))
                st.session_state.result = r
                st.session_state.plan = None
                st.session_state.run_id += 1
                st.balloons()
                st.rerun()
            except (ValueError, RuntimeError) as e:
                loader.done()
                st.error(str(e))

    if st.session_state.logs:
        with st.expander("Activity log"):
            st.code("\n".join(st.session_state.logs[-50:]))

with tab_org:
    render_organize()

# ============================================================================
# TAB 2 - UNDO
# ============================================================================
with tab_undo:
    st.subheader("Undo a previous run")
    st.write("**Move** logs put the files back where they came from. "
             "**Copy** logs delete the duplicates (your originals were never touched).")
    default_out = (st.session_state.outdir.strip() or
                   (str(Path(st.session_state.folder.strip().strip('"')) / core.OUTPUT_NAME)
                    if st.session_state.folder.strip() else ""))
    logs = core.find_logs(default_out) if default_out else []
    chosen = st.selectbox("Logs found in the output folder", [str(p) for p in logs]) if logs else ""
    manual = st.text_input("…or paste the path of a log file (.csv)")
    log_path = manual.strip().strip('"') or chosen
    ok = st.checkbox("I understand this will reverse that run")
    if st.button("↩️ Undo this run", disabled=not (log_path and ok)):
        loader = Loader("Undoing ...")
        try:
            r = core.undo_log(log_path, loader.update)
            loader.done()
            st.success(f"Undo complete: {r['restored']} file(s) restored / removed, {r['failed']} failed.")
            if r["errors"]:
                st.code("\n".join(r["errors"][:50]))
        except ValueError as e:
            loader.done()
            st.error(str(e))

# ============================================================================
# TAB 3 - ABOUT
# ============================================================================
with tab_about:
    st.markdown("""
### How it works
1. **Scan** — only the folder you choose is read.
2. **Read** — text, PDF, Word, Excel, PowerPoint; images and scanned PDFs are OCR'd on your computer.
3. **Classify** — file name + a short text snippet go to Groq's `gpt-oss-120b`, which invents the folder
   names itself and re-uses existing ones so similar files stay together.
4. **Arrange** — `Organized / <Category> / Created_YYYY-MM / Modified_YYYY-MM / file`

### Two modes
| | Move | Copy |
|---|---|---|
| Original files | moved | **stay untouched** |
| Extra disk space | none | needs room for duplicates |
| Undo | files go back | duplicates are deleted |

### Safety (cannot be turned off)
- You must give the folder path; nothing is scanned on its own.
- Refuses drive roots, `C:\\Users`, `/Users`, `/home`, `/Volumes`.
- Never touches Windows, Program Files, ProgramData, AppData, `/System`, `/Library`, `/Applications`,
  `~/Library`, `.app` bundles, `/usr`, `/etc`, `/bin`, `/var` …
- Skips program/system files, hidden/system-flagged files, symlinks and OneDrive cloud-only placeholders.
- Every move/copy is re-checked, needs you to type YES, and is logged for undo.

### Privacy
File names and the first part of each file's text (including OCR text) are sent to Groq.
Switch off *“Let the AI read file contents”* to send only file names.
""")
