# 💽 Auto Drive Transfer

![Platform](https://img.shields.io/badge/platform-Windows-blue?logo=windows)
![Python](https://img.shields.io/badge/python-3.10%2B-green?logo=python)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](https://www.gnu.org/licenses/gpl-3.0)
![Status](https://img.shields.io/badge/status-active-success)

**Auto Drive Transfer** is a Windows utility that **copies files and folders to your USB drive** with optional queuing.  
Think of it as your personal file-transfer assistant, optimized for video collections.  

---

## ✨ Features

- 📤 **One-Click Transfer to USB** — Automatically copies files to your pendrive.
- 📋 **Queue Transfers** — Send multiple files and process them one-by-one in order.
- 🖥 **Clean & Minimal UI** — Easy-to-use interface with clear buttons and no clutter.
- 📁 **Customizable Output Folder** — Choose where renamed files are temporarily stored.
- 🔍 **Smart Detection** — Avoids overwriting existing files in the target drive.

---

## 🛠 Installation

You can **either download the ready-to-use `.exe`** from [Releases](../../releases) or run from source.

### Option 1 — Run Prebuilt `.exe`
1. Go to the [Releases](../../releases) page.
2. Download the latest `AutoDriveTransferSetup.exe`.
3. Double-click to run (no Python installation required).

> **Note:** First launch may take a moment as dependencies load.

---

### Option 2 — Run from Source (Developers)
#### Prerequisites
- Windows 10/11
- [Python 3.10+](https://www.python.org/downloads/windows/)
- [pip](https://pip.pypa.io/en/stable/installation/)

#### Setup
## 1. Clone this repository
<pre>git clone https://github.com/YourUsername/SmartPendriveButler.git
cd SmartPendriveButler</pre>

## 2. Create a virtual environment (recommended)
<pre>python -m venv venv
venv\Scripts\activate</pre>

## 3. Install dependencies
<pre>pip install -r requirements.txt</pre>

## 4. Run the app
<pre>python smart_pendrive_butler.py</pre>

# Building the `.exe` (Advanced, optional)
We can use **Pyinstaller** for packaging:
<pre>pip install pyinstaller
pyinstaller SmartPendriveButler.spec</pre>

The compiled `.exe` will appear in the *dist/SmartPendriveButler/* folder.

# Dependencies
| Package         | Purpose                                                     |
| --------------- | ----------------------------------------------------------- |
| **guessit**     | Extracts metadata (movie/series title, year) from filenames |
| **babelfish**   | Converts and understands language codes                     |
| **PyQt5**       | GUI framework for Windows                                   |
| **PyInstaller** | Bundles app into a standalone `.exe`                        |

Install all dependencies with:
<pre>pip install -r requirements.txt</pre>

📜 License
This project is licensed under the **GNU General Public License, version 3 License** — see the "LICENSE" file for details.

📨 Feedback & Contributions
Found a bug? [Open an issue](../../issues)
Have an idea? Create a feature request!
Pull requests are welcome ❤️
