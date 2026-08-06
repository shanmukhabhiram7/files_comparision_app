# File, Folder & ZIP Compare (Flask)

A local **Flask** app for comparing:

- ZIP vs ZIP
- Folder vs Folder
- File vs File
- Text vs Text

This is the Flask version of the original Streamlit tool. The user interface,
the wording, the styling and the comparison behaviour are unchanged — only the
runtime moved from Streamlit to Flask.

## Features

- Recursively compares matching folder structures and file names.
- Shows **Mismatch Details first**, before the summary and file-status table.
- Shows missing files and folders in the comparison summary.
- Continues comparing all common files even when items are missing.
- Displays matched files in green and mismatched files in red.
- Shows side-by-side, line-numbered differences for text files.
- Uses a white comparison background with light Notepad++-style highlights for changed, removed, and added lines.
- Highlights the exact changed characters within changed lines.
- Shows the first mismatched file expanded automatically in the **Mismatch Details** list.
- Keeps only one mismatch comparison expanded at a time.
- Provides optional custom labels instead of `Left` and `Right`.
- Includes a **Show spaces** checkbox:
  - spaces display as `·`
  - no newline or line-ending markers are displayed
- Supports JSON, Python, TXT, HTML, CSS, JavaScript, TypeScript, YAML, XML, SQL, Markdown, CSV, configuration files, and many other text formats.
- Ignores LF, CRLF, CR, and final-newline-only differences for text files.
- Detects binary mismatches using SHA-256.
- Optionally treats JSON files as matched when parsed data is equal but formatting or key order differs.
- Safely rejects ZIP path-traversal entries.

## Project layout

```text
app.py                  Flask routes and request handling
comparison_engine.py    Comparison logic (unchanged from the Streamlit build)
diff_render.py          Side-by-side diff and mismatch accordion HTML
result_store.py         Per-session result cache (replaces st.session_state)
templates/              index.html, _results.html, _macros.html
static/css/style.css    All styling, including the original app CSS
static/js/app.js        Uploaders, reactive re-render, table sorting
test_engine.py          Comparison engine tests
requirements.txt
```

## Run on Windows using VS Code

### 1. Open the project folder

Extract the downloaded ZIP and open the inner folder containing these files:

```text
app.py
comparison_engine.py
requirements.txt
```

In VS Code:

```text
File → Open Folder → zip_folder_file_compare_flask
```

### 2. Open the terminal

```text
Terminal → New Terminal
```

Confirm that the terminal is inside the correct folder:

```cmd
dir
```

### 3. Create the virtual environment

```cmd
py -m venv .venv
```

If `py` is unavailable:

```cmd
python -m venv .venv
```

### 4. Activate it

For Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

For PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

### 5. Install dependencies

```cmd
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 6. Start the app

```cmd
python app.py
```

Or use the helper script:

```cmd
run.bat
```

The app opens at:

```text
http://localhost:8501
```

Press `Ctrl + C` in the terminal to stop it.

## Run on Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Or use the helper script:

```bash
chmod +x run.sh
./run.sh
```

## Configuration

The app reads these optional environment variables:

| Variable       | Default     | Purpose                                        |
| -------------- | ----------- | ---------------------------------------------- |
| `HOST`         | `127.0.0.1` | Bind address. Use `0.0.0.0` to expose on a LAN. |
| `PORT`         | `8501`      | Port number.                                    |
| `SECRET_KEY`   | random      | Session cookie key. Set it to keep sessions across restarts. |
| `FLASK_DEBUG`  | `0`         | Set to `1` for auto-reload during development. |

Example:

```cmd
set PORT=9000
python app.py
```

## Serving it with a production WSGI server

`python app.py` uses Flask's development server, which is fine for local use.
For a longer-running deployment inside the virtual environment:

Windows or Linux (waitress, already in `requirements.txt`):

```cmd
waitress-serve --host=127.0.0.1 --port=8501 --threads=8 app:app
```

Linux (gunicorn, install separately):

```bash
pip install gunicorn
gunicorn -w 1 --threads 8 --timeout 300 -b 127.0.0.1:8501 app:app
```

> **Important:** run a **single worker process**. Comparison results are held in
> that process's memory so the browser only ever receives rendered HTML. Use
> threads (`--threads`) rather than multiple workers to handle concurrent users.
> The long timeout matters because large ZIP comparisons can take a while.

## Tests

```cmd
python test_engine.py
```

## Notes

- ZIP mode uploads two ZIP files through the interface.
- File mode uploads two files through the interface.
- Text mode accepts pasted source and target text and uses the same comparison results and side-by-side mismatch view.
- Folder mode accepts two local folder paths because browser uploads do not reliably retain recursive folder structures. The paths are read on the machine **running the app**, so keep the app bound to `127.0.0.1` unless you trust everyone who can reach it.
- Uploads are limited to 500MB per file, matching the old Streamlit setting.
- Refreshing the page clears the current result, exactly as the Streamlit version did.
- Very large text-file differences may require more browser memory.
