# ListingAssistants Windows Quickstart Guide
### Cold-Start Installation, Touchscreen Verification & Test Data Ingestion
**Platform:** Windows 10 / Windows 11 (Standard PC, All-in-One, or Laptop)  
**Target Environment:** Clean machine or fresh developer workstation  
**Official Repository:** `https://github.com/QuietFireAI/listing-assistants`  
**Official Production Domain:** [ListingAssistants.com](https://ListingAssistants.com)

---

## 1. Prerequisites (2 Minutes)

Before installing ListingAssistants, ensure the machine has Python installed:

### Step 1: Install Python (if not present)
1. Download **Python 3.12** (or 3.10+) from [python.org/downloads/windows](https://www.python.org/downloads/windows/).
2. Run the installer.
3. **CRITICAL:** Check the box at the bottom: **`[x] Add python.exe to PATH`** before clicking **Install Now**.
4. *(Optional)* Click "Disable path length limit" at the end of setup.

### Step 2: Open PowerShell
Press the `Windows Key`, type `powershell`, and launch **Windows PowerShell**.

Allow local virtual environments to run (one-time command):
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
*(Press `Y` to confirm if prompted).*

---

## 2. Download & Install (3 Commands)

You can install either via `git` or by downloading the official release archive:

### Option A: Using Git (Recommended)
```powershell
git clone https://github.com/QuietFireAI/listing-assistants.git
cd listing-assistants
```

### Option B: Without Git (Release ZIP Download)
1. In your web browser, navigate to:  
   `https://github.com/QuietFireAI/listing-assistants/releases/tag/archetype-v1.0.0`
2. Download **`listingassistants-archetype-v1.0.0.zip`**.
3. Right-click the zip file, select **Extract All...**, and extract to your desired folder (e.g. `C:\ListingAssistants`).
4. In PowerShell, `cd` into the extracted folder.

### Step 3: Create Virtual Environment & Install Dependencies
```powershell
# 1. Create a dedicated isolated virtual environment
python -m venv venv

# 2. Activate the virtual environment
.\venv\Scripts\Activate.ps1

# 3. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. The 3-Step Verification Matrix

Once dependencies are installed, run these three commands to verify 100% operational integrity on your machine:

### Step 1: Health & Compliance Verification (12 Seconds)
Run the automated test suite covering all 21 agents, 24 playbooks, and security firewalls:
```powershell
python -m pytest tests_listing/
```
*Expected Result:*
```text
============================ 570 passed in 11.20s =============================
```
*(Guaranteed: 570 passed, 0 failures, 0 warnings).*

---

### Step 2: Six-Act End-to-End Swarm Simulation
Run the full lifecycle demo simulating a live transaction from lead intake to closing:
```powershell
python tools/run_demo.py
```
*What this exercises:*
* Act 1: Lead capture & rubric qualification (Agent 01 & 02 via JEV AI).
* Act 2: Listing agreement onboarding & compliant MLS remarks (Agents 04, 05, 17).
* Act 3: Showing scheduling with conflict arbitration (Agent 06).
* Act 4: Escrow contingency tracking (Agent 07 & 08).
* Act 5: Wire fraud attempt detection (immediate conversation freeze & P14 alert).
* Act 6: Commission disbursement audit (Agent 15 reconciliation to $0.00).

---

### Step 3: Launch Touchscreen Funnel Dashboard
Launch the non-technical web portal tailored for brokers and touchscreen workstations:
```powershell
python tools/dashboard.py --html
```
*Then open your browser to the generated dashboard file:*
```powershell
Start-Process dashboard.html
```
*On your touchscreen display:*
* Inspect real client drawers (`drawers/<client_id>/`).
* View the 6-stage sales funnel (`INTAKE` -> `QUALIFICATION` -> `PRE-MARKET` -> `ACTIVE MLS` -> `IN ESCROW` -> `CLOSED`).
* Monitor pending broker approval gates in real time.

---

## 4. Ingesting Your Custom / Hypothetical Test Data

ListingAssistants strictly isolates all property and client records inside the **Client Drawer Vault** (`drawers/<client_id>/`).

### How to Create a New Test Listing:
1. **Choose a Client/Property Identifier:** (e.g. `listing_oak_terrace_101`).
2. **Provision the Drawer:**
   ```powershell
   python -c "from dispatcher.client_drawer import ClientDrawerManager; mgr = ClientDrawerManager(); mgr.provision_drawer('listing_oak_terrace_101')"
   ```
   This creates an isolated folder hierarchy:
   ```text
   drawers/listing_oak_terrace_101/
   ├── raw/         <-- Drop your incoming docs here (tax records, seller disclosures, photos)
   ├── working/     <-- Where Agent 04 drafts remarks and Agent 05 compiles MLS fields
   ├── delivered/   <-- Executed forms, signed agreements, final counteroffers
   ├── audit/       <-- activity.log (non-repudiable transaction log)
   └── metadata/    <-- client_state.json and funnel status
   ```

3. **Drop Files in `raw/`:**
   Copy your hypothetical real estate data (PDFs, text files, JSON notes) directly into `drawers/listing_oak_terrace_101/raw/`.

4. **Fingerprint & Verify File Hashes:**
   ```powershell
   python -c "from dispatcher.client_drawer import ClientDrawerManager; mgr = ClientDrawerManager(); mgr.index_file('listing_oak_terrace_101', 'raw/property_disclosure.txt')"
   ```
   Every file is SHA-256 hashed and registered with zero risk of cross-client commingling.

---

## 5. Connecting a Local LLM via Ollama (Optional)

ListingAssistants runs 100% deterministically out-of-the-box using built-in rule engines. If you want to connect a local LLM (like **Nous Hermes 3** or **Qwen 2.5**) for live text generation:

1. Install **Ollama** for Windows from [ollama.com](https://ollama.com/).
2. Pull your desired model:
   ```powershell
   # High-speed conversational agent model (Recommended for 16GB-32GB RAM machines):
   ollama run hermes3:8b
   # or
   ollama run qwen2.5:14b
   ```
3. Ollama runs as a local background service at `http://localhost:11434`.
4. The system's cognitive seam (`dispatcher/hermes_seam.py`) connects directly to Ollama to capture and inspect internal `<think>` tokens.

---

## 6. Daily Operator Checklist

| Frequency | Action | Command |
| :--- | :--- | :--- |
| **Morning (08:00 AM)** | Generate morning intelligence briefing | `python tools/run_sweeps.py --morning` |
| **Start-of-Day** | Capture daily warm restore point | `python tools/restore_point.py --snapshot` |
| **Mid-Day** | Inspect funnel & active wait states | `python tools/dashboard.py` |
| **Real-Time** | Tail live plain-English activity stream | `python tools/show_logs.py --tail` |
| **Rollback (if needed)** | Instant fallback to golden factory baseline | `python tools/restore_point.py --restore baseline` |
