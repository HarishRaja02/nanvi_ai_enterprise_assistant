# Nanvi Local File Agent for Windows

The **Nanvi Local File Agent** allows you to securely search files and documents directly from your Windows computer inside Nanvi AI Enterprise Assistant (whether running locally or deployed on Vercel/Cloud).

---

## Architecture & Security

```
[ Your Windows PC ]                     [ Nanvi Cloud API / Web ]
  User-Approved Folders                   Vercel / AWS
  (e.g. C:\Projects, C:\abc)                  │
          │                                   │
          ▼                                   ▼
 [ Nanvi Local Agent ] <── HTTPS / Token ──> [ Unified RAG ]
```

* **Zero Unrestricted Filesystem Access**: Cloud servers can never browse your computer or read arbitrary files. Only folders explicitly approved by you are indexed.
* **Strict Sandboxing**:
  - Rejects system root folders (`C:\Windows`, `C:\Program Files`, `/bin`, etc.).
  - Path traversal protection (`..` prevention).
  - Executable/binary blocking (`.exe`, `.dll`, `.bat`, `.ps1`, etc.).
* **Continuous Synchronization**: Watches approved folders for new, edited, or deleted files and automatically updates the assistant.
* **Preserves Relative Paths**: Search citations look like:
  `Projects/Chennai_Bridge/Inspection_Report.pdf`

---

## Quick Start (3 Steps)

### 1. Get Your Pairing Token
1. Open Nanvi Web Assistant (e.g. `https://nanviaienterpriseassistant.vercel.app` or `http://localhost:5173`).
2. Go to **Settings** &rarr; **Company Folder** &rarr; **Local Computer Agent**.
3. Click **Generate Pairing Token** and copy your token.

### 2. Run the Agent on Windows
Open Command Prompt or PowerShell in the `local_agent` directory and run:
```cmd
python nanvi_local_agent.py --server https://nanviaienterpriseassistant.vercel.app --token <YOUR_TOKEN>
```
*(Or simply double-click `run_local_agent.bat` and follow the on-screen prompt).*

### 3. Connect Any Local Folder
In the interactive terminal:
```text
nanvi-agent> add C:\Users\haris\Downloads\companydata_bridge_construction_120_files\companydata_bridge_construction\CompanyData
nanvi-agent> add D:\Projects
nanvi-agent> add C:\abc
```

You will see:
```text
✓ Approved and indexing folder: C:\Users\haris\Downloads\...
Indexed 496 files (946 chunks).
✓ Successfully synced to Nanvi Cloud.
```

Your files are now instantly searchable in the Nanvi Chat!

---

## Interactive CLI Commands

| Command | Description |
| :--- | :--- |
| `add <path>` | Connect and index any folder on your computer. |
| `list` | Show all currently approved folders and their paths. |
| `remove <path>` | Disconnect a folder and remove its indexed chunks. |
| `sync` | Force an immediate re-index and sync of all connected folders. |
| `status` | View cloud connectivity and heartbeat status. |
| `exit` | Stop the local agent. |
