"""HTML builders for the side-by-side comparison view.

The logic here is identical to the original Streamlit version; the only change is
that each function returns an HTML string instead of pushing it through
``st.markdown(..., unsafe_allow_html=True)``.
"""

from __future__ import annotations

import difflib
import html

from comparison_engine import ComparisonResult


def _render_segment(segment: str, show_spaces: bool, css_class: str = "") -> str:
    rendered: list[str] = []
    for char in segment:
        if char == " " and show_spaces:
            rendered.append("<span class='space-token'>·</span>")
        else:
            rendered.append(html.escape(char))

    content = "".join(rendered) or "&nbsp;"
    if css_class:
        return f"<span class='{css_class}'>{content}</span>"
    return content


def _render_inline_diff(
    left_line: str,
    right_line: str,
    show_spaces: bool,
) -> tuple[str, str]:
    matcher = difflib.SequenceMatcher(None, left_line, right_line, autojunk=False)
    left_parts: list[str] = []
    right_parts: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        left_segment = left_line[i1:i2]
        right_segment = right_line[j1:j2]

        if tag == "equal":
            left_parts.append(_render_segment(left_segment, show_spaces))
            right_parts.append(_render_segment(right_segment, show_spaces))
        elif tag == "replace":
            left_parts.append(
                _render_segment(left_segment, show_spaces, "inline-removed")
            )
            right_parts.append(
                _render_segment(right_segment, show_spaces, "inline-added")
            )
        elif tag == "delete":
            left_parts.append(
                _render_segment(left_segment, show_spaces, "inline-removed")
            )
        elif tag == "insert":
            right_parts.append(
                _render_segment(right_segment, show_spaces, "inline-added")
            )

    return "".join(left_parts) or "&nbsp;", "".join(right_parts) or "&nbsp;"


def build_side_by_side_diff(
    left_lines: list[str],
    right_lines: list[str],
    show_spaces: bool,
    left_label: str,
    right_label: str,
) -> str:
    matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)
    rows: list[str] = []

    def row(
        left_no: str,
        left_html: str,
        right_no: str,
        right_html: str,
        left_class: str,
        right_class: str,
    ) -> None:
        rows.append(
            "<tr>"
            f"<td class='line-no'>{left_no}</td>"
            f"<td class='{left_class}'>{left_html}</td>"
            f"<td class='line-no'>{right_no}</td>"
            f"<td class='{right_class}'>{right_html}</td>"
            "</tr>"
        )

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                row(
                    str(i1 + offset + 1),
                    _render_segment(left_lines[i1 + offset], show_spaces),
                    str(j1 + offset + 1),
                    _render_segment(right_lines[j1 + offset], show_spaces),
                    "same",
                    "same",
                )

        elif tag == "replace":
            max_len = max(i2 - i1, j2 - j1)
            for offset in range(max_len):
                left_exists = i1 + offset < i2
                right_exists = j1 + offset < j2

                if left_exists and right_exists:
                    left_html, right_html = _render_inline_diff(
                        left_lines[i1 + offset],
                        right_lines[j1 + offset],
                        show_spaces,
                    )
                    row(
                        str(i1 + offset + 1),
                        left_html,
                        str(j1 + offset + 1),
                        right_html,
                        "changed-left",
                        "changed-right",
                    )
                elif left_exists:
                    row(
                        str(i1 + offset + 1),
                        _render_segment(
                            left_lines[i1 + offset],
                            show_spaces,
                            "inline-removed",
                        ),
                        "",
                        "&nbsp;",
                        "removed",
                        "missing-cell",
                    )
                else:
                    row(
                        "",
                        "&nbsp;",
                        str(j1 + offset + 1),
                        _render_segment(
                            right_lines[j1 + offset],
                            show_spaces,
                            "inline-added",
                        ),
                        "missing-cell",
                        "added",
                    )

        elif tag == "delete":
            for offset in range(i2 - i1):
                row(
                    str(i1 + offset + 1),
                    _render_segment(
                        left_lines[i1 + offset],
                        show_spaces,
                        "inline-removed",
                    ),
                    "",
                    "&nbsp;",
                    "removed",
                    "missing-cell",
                )

        elif tag == "insert":
            for offset in range(j2 - j1):
                row(
                    "",
                    "&nbsp;",
                    str(j1 + offset + 1),
                    _render_segment(
                        right_lines[j1 + offset],
                        show_spaces,
                        "inline-added",
                    ),
                    "missing-cell",
                    "added",
                )

    legend = (
        "<div class='diff-legend'>"
        "<span><span class='legend-swatch legend-changed'></span>Changed</span>"
        "<span><span class='legend-swatch legend-removed'></span>Removed</span>"
        "<span><span class='legend-swatch legend-added'></span>Added</span>"
        "</div>"
    )

    return (
        legend
        + "<div class='diff-wrap'><table class='diff-table'>"
        + "<colgroup><col class='line-column'><col class='content-column'>"
        + "<col class='line-column'><col class='content-column'></colgroup>"
        + "<thead><tr>"
        + "<th>#</th>"
        + f"<th>{html.escape(left_label)}</th>"
        + "<th>#</th>"
        + f"<th>{html.escape(right_label)}</th>"
        + "</tr></thead>"
        + f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def build_mismatch_accordion(
    result: ComparisonResult,
    show_spaces: bool,
    left_label: str,
    right_label: str,
) -> str:
    """Render old-style mismatch panels as an exclusive HTML accordion."""
    panels: list[str] = ["<div class='mismatch-accordion'>"]

    for index, mismatch in enumerate(result.mismatched_files):
        title = html.escape(mismatch.relative_path)
        message = html.escape(mismatch.message)

        if mismatch.is_text:
            details = build_side_by_side_diff(
                mismatch.left_lines,
                mismatch.right_lines,
                show_spaces=show_spaces,
                left_label=left_label,
                right_label=right_label,
            )
        else:
            details = (
                "<div class='binary-note'>This is a binary file. The tool can detect the "
                "mismatch but cannot show line differences.</div>"
            )

        # The shared name makes modern browsers keep only one panel open at a time.
        open_attribute = " open" if index == 0 else ""
        panels.append(
            f"<details class='mismatch-panel' name='mismatch-comparison'{open_attribute}>"
            f"<summary>🔴 {title}</summary>"
            "<div class='mismatch-content'>"
            f"<div class='mismatch-message'>{message}</div>"
            f"{details}"
            "</div>"
            "</details>"
        )

    panels.append("</div>")
    return "".join(panels)
