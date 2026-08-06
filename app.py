"""File, Folder & ZIP Compare — Flask edition.

This is a direct port of the original Streamlit app. The comparison engine, the
CSS, the layout, the wording and the behaviour are unchanged; only the widget
runtime moved from Streamlit to Flask + a small amount of vanilla JavaScript.
"""

from __future__ import annotations

import json
import os
import secrets
import traceback
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session
from werkzeug.exceptions import RequestEntityTooLarge

from comparison_engine import (
    ComparisonError,
    ComparisonResult,
    compare_directories,
    compare_single_files,
    compare_zip_files,
)
from diff_render import build_mismatch_accordion
from result_store import store

# Mirrors [server] maxUploadSize = 500 from the old .streamlit/config.toml.
MAX_UPLOAD_MB = 500
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

app = Flask(__name__)
# Two uploads per request, plus a little headroom for the multipart envelope.
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES * 2 + (8 * 1024 * 1024)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["TEMPLATES_AUTO_RELOAD"] = True


# --------------------------------------------------------------------------
# Session helpers
# --------------------------------------------------------------------------
def session_token(create: bool = True) -> str:
    token = session.get("token")
    if not token and create:
        token = uuid.uuid4().hex
        session["token"] = token
    return token or ""


def _flag(name: str, default: bool = False) -> bool:
    raw = request.form.get(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "on", "yes"}


def _resolve_labels(
    default_left: str = "Left",
    default_right: str = "Right",
) -> tuple[str, str]:
    """Same fallback rules as the Streamlit build."""
    if not _flag("use_custom_labels"):
        return default_left, default_right
    left = (request.form.get("custom_left_label") or "").strip() or default_left
    right = (request.form.get("custom_right_label") or "").strip() or default_right
    return left, right


def _text_input_names(left_text: str, right_text: str, semantic_json: bool) -> tuple[str, str]:
    """Use JSON names only when both pasted values are valid JSON documents."""
    if semantic_json:
        try:
            json.loads(left_text)
            json.loads(right_text)
        except (json.JSONDecodeError, TypeError):
            pass
        else:
            return "Source text.json", "Target text.json"
    return "Source text.txt", "Target text.txt"


# --------------------------------------------------------------------------
# Result rendering
# --------------------------------------------------------------------------
def render_result_html(
    result: ComparisonResult,
    show_spaces: bool,
    left_label: str,
    right_label: str,
) -> str:
    mismatch_html = ""
    if result.mismatched_files:
        mismatch_html = build_mismatch_accordion(
            result,
            show_spaces=show_spaces,
            left_label=left_label,
            right_label=right_label,
        )

    missing_total = (
        len(result.only_in_left_files)
        + len(result.only_in_right_files)
        + len(result.only_in_left_folders)
        + len(result.only_in_right_folders)
    )

    # Identical to the old pandas sort_values(["Status", "File"]) ordering.
    rows = [
        {"file": item.relative_path, "status": "🟢 Matched", "details": item.message}
        for item in result.matched_files
    ] + [
        {"file": item.relative_path, "status": "🔴 Mismatched", "details": item.message}
        for item in result.mismatched_files
    ]
    rows.sort(key=lambda row: (row["status"], row["file"]))

    return render_template(
        "_results.html",
        result=result,
        mismatch_html=mismatch_html,
        missing_total=missing_total,
        rows=rows,
        left_label=left_label,
        right_label=right_label,
    )


def _error(message: str, kind: str = "error"):
    return jsonify({"status": kind, "message": message})


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    # A browser refresh starts a fresh session, matching Streamlit's behaviour
    # where st.session_state is discarded when the page reloads.
    old_token = session.get("token")
    if old_token:
        store.pop(old_token)
    session["token"] = uuid.uuid4().hex

    return render_template("index.html", max_upload_mb=MAX_UPLOAD_MB)


@app.post("/api/compare")
def api_compare():
    mode = request.form.get("mode", "ZIP vs ZIP")
    semantic_json = _flag("semantic_json", True)
    show_spaces = _flag("show_spaces", False)
    if mode == "Text vs Text":
        left_label, right_label = _resolve_labels("Source", "Target")
    else:
        left_label, right_label = _resolve_labels()

    result: ComparisonResult | None = None

    try:
        if mode == "ZIP vs ZIP":
            left_zip = request.files.get("left_zip")
            right_zip = request.files.get("right_zip")
            if not left_zip or not right_zip or not left_zip.filename or not right_zip.filename:
                return _error("Upload both ZIP files before comparing.")

            result = compare_zip_files(
                left_zip.read(),
                right_zip.read(),
                left_zip.filename,
                right_zip.filename,
                semantic_json=semantic_json,
            )

        elif mode == "Folder vs Folder":
            left_folder = request.form.get("left_folder", "")
            right_folder = request.form.get("right_folder", "")
            if not left_folder.strip() or not right_folder.strip():
                return _error("Enter both folder paths before comparing.")

            result = compare_directories(
                Path(left_folder.strip().strip('"')),
                Path(right_folder.strip().strip('"')),
                semantic_json=semantic_json,
            )

        elif mode == "File vs File":
            left_file = request.files.get("left_file")
            right_file = request.files.get("right_file")
            if not left_file or not right_file or not left_file.filename or not right_file.filename:
                return _error("Upload both files before comparing.")

            result = compare_single_files(
                left_file.read(),
                right_file.read(),
                left_file.filename,
                right_file.filename,
                semantic_json=semantic_json,
            )

        elif mode == "Text vs Text":
            left_text = request.form.get("left_text", "")
            right_text = request.form.get("right_text", "")
            left_name, right_name = _text_input_names(
                left_text,
                right_text,
                semantic_json,
            )

            result = compare_single_files(
                left_text.encode("utf-8"),
                right_text.encode("utf-8"),
                left_name,
                right_name,
                semantic_json=semantic_json,
            )

        else:
            return _error(f"Unsupported comparison type: {mode}")

    except ComparisonError as exc:
        return _error(str(exc))
    except PermissionError as exc:
        return _error(f"Permission denied: {exc}")
    except OSError as exc:
        return _error(f"File system error: {exc}")
    except Exception as exc:  # noqa: BLE001 - mirrors st.exception()
        return jsonify(
            {
                "status": "exception",
                "message": f"{type(exc).__name__}: {exc}",
                "traceback": "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ),
            }
        )

    store.set(session_token(), result)
    return jsonify(
        {
            "status": "ok",
            "html": render_result_html(result, show_spaces, left_label, right_label),
        }
    )


@app.post("/api/render")
def api_render():
    """Re-render the stored result when only display options changed."""
    result = store.get(session_token(create=False))
    if result is None:
        return jsonify({"status": "empty", "html": ""})

    show_spaces = _flag("show_spaces", False)
    mode = request.form.get("mode", "ZIP vs ZIP")
    if mode == "Text vs Text":
        left_label, right_label = _resolve_labels("Source", "Target")
    else:
        left_label, right_label = _resolve_labels()
    return jsonify(
        {
            "status": "ok",
            "html": render_result_html(result, show_spaces, left_label, right_label),
        }
    )


@app.errorhandler(RequestEntityTooLarge)
def handle_too_large(_exc):
    return (
        jsonify(
            {
                "status": "error",
                "message": (
                    f"The upload is too large. The limit is {MAX_UPLOAD_MB}MB per file."
                ),
            }
        ),
        413,
    )


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8501"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"\n  File, Folder & ZIP Compare  ->  http://{host}:{port}\n")
    app.run(host=host, port=port, debug=debug, threaded=True)
