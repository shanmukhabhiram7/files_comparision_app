from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


TEXT_EXTENSIONS = {
    ".txt", ".py", ".pyi", ".json", ".jsonl", ".html", ".htm", ".css",
    ".scss", ".sass", ".less", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".jsx", ".xml", ".yaml", ".yml", ".md", ".rst", ".csv", ".tsv",
    ".ini", ".cfg", ".conf", ".toml", ".sql", ".java", ".c", ".cpp",
    ".cc", ".h", ".hpp", ".cs", ".go", ".rs", ".sh", ".bash", ".zsh",
    ".bat", ".cmd", ".ps1", ".properties", ".log", ".gradle", ".kt",
    ".kts", ".php", ".rb", ".r", ".tex", ".vue", ".svelte", ".env",
}

TEXT_FILENAMES = {
    ".env", ".gitignore", ".gitattributes", ".dockerignore", ".editorconfig",
    "dockerfile", "makefile", "procfile", "license", "readme",
}


@dataclass
class FileComparison:
    relative_path: str
    status: str
    left_path: Path | None = None
    right_path: Path | None = None
    is_text: bool = False
    message: str = ""
    # Lines are normalized for visual comparison; line-ending style is ignored.
    left_lines: list[str] = field(default_factory=list)
    right_lines: list[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    matched_files: list[FileComparison] = field(default_factory=list)
    mismatched_files: list[FileComparison] = field(default_factory=list)
    only_in_left_files: list[str] = field(default_factory=list)
    only_in_right_files: list[str] = field(default_factory=list)
    only_in_left_folders: list[str] = field(default_factory=list)
    only_in_right_folders: list[str] = field(default_factory=list)

    @property
    def total_common_files(self) -> int:
        return len(self.matched_files) + len(self.mismatched_files)


class ComparisonError(RuntimeError):
    pass


def sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_like_text(decoded: str) -> bool:
    if not decoded:
        return True
    controls = sum(
        1
        for char in decoded
        if ord(char) < 32 and char not in {"\n", "\r", "\t", "\b", "\f"}
    )
    return controls / len(decoded) < 0.02


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower() in TEXT_FILENAMES:
        return True

    try:
        sample = path.read_bytes()[:8192]
    except OSError:
        return False

    if not sample:
        return True

    # UTF-16 text legitimately contains many NUL bytes, so check its BOM first.
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return _looks_like_text(sample.decode("utf-16"))
        except UnicodeDecodeError:
            return False

    if b"\x00" in sample:
        return False

    for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            decoded = sample.decode(encoding)
        except UnicodeDecodeError:
            continue
        if _looks_like_text(decoded):
            return True
    return False


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    # Try plain UTF-8 before utf-8-sig so a UTF-8 BOM remains visible as \ufeff.
    for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_text_for_comparison(text: str) -> str:
    """Normalize invisible text representation differences for content comparison."""
    # Ignore UTF-8 BOM and all line-ending styles. A single final newline is also
    # intentionally ignored by splitlines(), while real extra blank lines remain.
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_text_lines(path: Path) -> list[str]:
    return normalize_text_for_comparison(read_text(path)).splitlines()


def json_semantically_equal(left: Path, right: Path) -> bool:
    try:
        with left.open("r", encoding="utf-8-sig") as lf:
            left_data = json.load(lf)
        with right.open("r", encoding="utf-8-sig") as rf:
            right_data = json.load(rf)
        return left_data == right_data
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False


def collect_tree(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    folders: set[str] = set()
    for current_root, dir_names, file_names in os.walk(root):
        current = Path(current_root)
        for directory in dir_names:
            rel = (current / directory).relative_to(root).as_posix()
            folders.add(rel)
        for filename in file_names:
            rel = (current / filename).relative_to(root).as_posix()
            files.add(rel)
    return files, folders


def _without_horizontal_whitespace(lines: list[str]) -> list[str]:
    return ["".join(char for char in line if char not in {" ", "\t"}) for line in lines]


def compare_files(
    left: Path,
    right: Path,
    relative_path: str,
    semantic_json: bool = True,
) -> FileComparison:
    if sha256(left) == sha256(right):
        return FileComparison(
            relative_path=relative_path,
            status="Matched",
            left_path=left,
            right_path=right,
            is_text=is_probably_text(left),
            message="Files are identical.",
        )

    suffix = left.suffix.lower()
    both_json = suffix == ".json" and right.suffix.lower() == ".json"
    if semantic_json and both_json and json_semantically_equal(left, right):
        return FileComparison(
            relative_path=relative_path,
            status="Matched",
            left_path=left,
            right_path=right,
            is_text=True,
            message="JSON data matches; only formatting or key order differs.",
        )

    text_mode = is_probably_text(left) and is_probably_text(right)
    if text_mode:
        left_lines = read_text_lines(left)
        right_lines = read_text_lines(right)

        # Treat line-ending style, a single final newline, BOM, and byte encoding
        # representation as non-content differences. This prevents mismatches that
        # have no visible line-level change in the side-by-side viewer.
        if left_lines == right_lines:
            return FileComparison(
                relative_path=relative_path,
                status="Matched",
                left_path=left,
                right_path=right,
                is_text=True,
                message="Text content matches.",
            )

        if _without_horizontal_whitespace(left_lines) == _without_horizontal_whitespace(right_lines):
            message = "Text differs only in spaces or tabs. Enable space highlighting to inspect it."
        else:
            message = "Text content differs."

        return FileComparison(
            relative_path=relative_path,
            status="Mismatched",
            left_path=left,
            right_path=right,
            is_text=True,
            message=message,
            left_lines=left_lines,
            right_lines=right_lines,
        )

    return FileComparison(
        relative_path=relative_path,
        status="Mismatched",
        left_path=left,
        right_path=right,
        is_text=False,
        message="Binary content differs. Line-level comparison is unavailable.",
    )


def compare_directories(
    left_root: Path,
    right_root: Path,
    semantic_json: bool = True,
) -> ComparisonResult:
    left_root = left_root.expanduser().resolve()
    right_root = right_root.expanduser().resolve()

    if not left_root.is_dir():
        raise ComparisonError(f"Left folder does not exist: {left_root}")
    if not right_root.is_dir():
        raise ComparisonError(f"Right folder does not exist: {right_root}")

    left_files, left_folders = collect_tree(left_root)
    right_files, right_folders = collect_tree(right_root)

    result = ComparisonResult(
        only_in_left_files=sorted(left_files - right_files),
        only_in_right_files=sorted(right_files - left_files),
        only_in_left_folders=sorted(left_folders - right_folders),
        only_in_right_folders=sorted(right_folders - left_folders),
    )

    for rel in sorted(left_files & right_files):
        comparison = compare_files(
            left_root / rel,
            right_root / rel,
            rel,
            semantic_json=semantic_json,
        )
        if comparison.status == "Matched":
            result.matched_files.append(comparison)
        else:
            result.mismatched_files.append(comparison)

    return result


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if destination != target and destination not in target.parents:
                raise ComparisonError(f"Unsafe ZIP entry detected: {member.filename}")
        archive.extractall(destination)


def unwrap_single_root(folder: Path) -> Path:
    entries = [entry for entry in folder.iterdir() if entry.name not in {"__MACOSX"}]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return folder


def compare_zip_files(
    left_zip_bytes: bytes,
    right_zip_bytes: bytes,
    left_name: str,
    right_name: str,
    semantic_json: bool = True,
) -> ComparisonResult:
    workspace = Path(tempfile.mkdtemp(prefix="compare_tool_"))
    try:
        left_zip = workspace / (Path(left_name).name or "left.zip")
        right_zip = workspace / (Path(right_name).name or "right.zip")
        left_zip.write_bytes(left_zip_bytes)
        right_zip.write_bytes(right_zip_bytes)

        left_extract = workspace / "left"
        right_extract = workspace / "right"
        left_extract.mkdir()
        right_extract.mkdir()

        try:
            safe_extract_zip(left_zip, left_extract)
            safe_extract_zip(right_zip, right_extract)
        except zipfile.BadZipFile as exc:
            raise ComparisonError("One of the uploaded files is not a valid ZIP archive.") from exc

        left_root = unwrap_single_root(left_extract)
        right_root = unwrap_single_root(right_extract)
        return compare_directories(left_root, right_root, semantic_json=semantic_json)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def compare_single_files(
    left_bytes: bytes,
    right_bytes: bytes,
    left_name: str,
    right_name: str,
    semantic_json: bool = True,
) -> ComparisonResult:
    workspace = Path(tempfile.mkdtemp(prefix="compare_files_"))
    try:
        left_path = workspace / f"left{Path(left_name).suffix}"
        right_path = workspace / f"right{Path(right_name).suffix}"
        left_path.write_bytes(left_bytes)
        right_path.write_bytes(right_bytes)
        display_name = f"{left_name} ↔ {right_name}"
        comparison = compare_files(
            left_path,
            right_path,
            display_name,
            semantic_json=semantic_json,
        )
        result = ComparisonResult()
        if comparison.status == "Matched":
            result.matched_files.append(comparison)
        else:
            result.mismatched_files.append(comparison)
        return result
    finally:
        # All required text contents are already copied into the result object.
        shutil.rmtree(workspace, ignore_errors=True)
