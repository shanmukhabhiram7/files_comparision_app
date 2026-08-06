from pathlib import Path
from tempfile import TemporaryDirectory

from comparison_engine import compare_directories, compare_files


def test_directory_comparison() -> None:
    with TemporaryDirectory() as left_tmp, TemporaryDirectory() as right_tmp:
        left = Path(left_tmp)
        right = Path(right_tmp)
        (left / "same.txt").write_text("hello\nworld\n", encoding="utf-8")
        (right / "same.txt").write_text("hello\nworld\n", encoding="utf-8")
        (left / "change.py").write_text("x = 1\n", encoding="utf-8")
        (right / "change.py").write_text("x = 2\n", encoding="utf-8")
        (left / "only_left.txt").write_text("left", encoding="utf-8")
        (right / "only_right.txt").write_text("right", encoding="utf-8")

        result = compare_directories(left, right)
        assert len(result.matched_files) == 1
        assert len(result.mismatched_files) == 1
        assert result.only_in_left_files == ["only_left.txt"]
        assert result.only_in_right_files == ["only_right.txt"]


def test_line_ending_differences_are_ignored() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        left = root / "left.txt"
        right = root / "right.txt"

        left.write_bytes(b"first line\r\nsecond line\r\n")
        right.write_bytes(b"first line\nsecond line")
        result = compare_files(left, right, "line_endings.txt")

        assert result.status == "Matched"
        assert result.is_text
        assert result.message == "Text content matches."


def test_real_extra_blank_line_is_still_detected() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        left = root / "left.txt"
        right = root / "right.txt"

        left.write_text("first line\nsecond line\n", encoding="utf-8")
        right.write_text("first line\nsecond line\n\n", encoding="utf-8")
        result = compare_files(left, right, "blank_line.txt")

        assert result.status == "Mismatched"
        assert result.left_lines == ["first line", "second line"]
        assert result.right_lines == ["first line", "second line", ""]


def test_whitespace_only_message() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        left = root / "left.py"
        right = root / "right.py"
        left.write_text("value = 10\n", encoding="utf-8")
        right.write_text("value=10\n", encoding="utf-8")

        result = compare_files(left, right, "spaces.py")
        assert result.status == "Mismatched"
        assert "spaces or tabs" in result.message.lower()


def test_semantic_json_option() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        left = root / "left.json"
        right = root / "right.json"
        left.write_text('{"a": 1, "b": 2}\n', encoding="utf-8")
        right.write_text('{\n  "b": 2,\n  "a": 1\n}\n', encoding="utf-8")

        semantic = compare_files(left, right, "data.json", semantic_json=True)
        exact = compare_files(left, right, "data.json", semantic_json=False)
        assert semantic.status == "Matched"
        assert exact.status == "Mismatched"


def main() -> None:
    test_directory_comparison()
    test_line_ending_differences_are_ignored()
    test_real_extra_blank_line_is_still_detected()
    test_whitespace_only_message()
    test_semantic_json_option()
    print("All comparison engine tests passed.")


if __name__ == "__main__":
    main()
