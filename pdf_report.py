from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from comparison_engine import ComparisonResult


def _safe(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_safe(value), style)


def _rows_for_result(result: ComparisonResult) -> list[tuple[str, str, str]]:
    rows = [
        (item.relative_path, "Matched", item.message)
        for item in result.matched_files
    ] + [
        (item.relative_path, "Mismatched", item.message)
        for item in result.mismatched_files
    ]
    return sorted(rows, key=lambda row: (row[1], row[0]))


def build_overview_pdf(
    result: ComparisonResult,
    *,
    mode: str,
    left_label: str,
    right_label: str,
) -> bytes:
    """Create an overview-only PDF. No source code or diff contents are included."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="File Comparison Report",
        author="File Comparison Application",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    heading = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
    )
    small = ParagraphStyle(
        "ReportSmall",
        parent=body,
        fontSize=7.5,
        leading=9.5,
    )

    story: list[object] = [
        Paragraph("File Comparison Report", title),
        Paragraph(
            f"Comparison type: <b>{_safe(mode)}</b> &nbsp;&nbsp; | &nbsp;&nbsp; "
            f"{_safe(left_label)} vs {_safe(right_label)}",
            body,
        ),
        Spacer(1, 7),
        Paragraph("Mismatch Details", heading),
    ]

    mismatch_data = [["File / path", "Details"]]
    if result.mismatched_files:
        mismatch_data.extend(
            [
                _paragraph(item.relative_path, small),
                _paragraph(item.message or "Content differs.", small),
            ]
            for item in result.mismatched_files
        )
    else:
        mismatch_data.append([
            _paragraph("No mismatches", small),
            _paragraph("No content mismatches were found in the common files.", small),
        ])

    mismatch_table = LongTable(mismatch_data, colWidths=[72 * mm, 102 * mm], repeatRows=1)
    mismatch_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    story.extend([mismatch_table, Paragraph("Home / Comparison Summary", heading)])

    missing_total = (
        len(result.only_in_left_files)
        + len(result.only_in_right_files)
        + len(result.only_in_left_folders)
        + len(result.only_in_right_folders)
    )
    summary_data = [
        ["Matched files", "Mismatched files", "Missing files/folders", "Common files compared"],
        [
            str(len(result.matched_files)),
            str(len(result.mismatched_files)),
            str(missing_total),
            str(result.total_common_files),
        ],
    ]
    summary = Table(summary_data, colWidths=[43.5 * mm] * 4)
    summary.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, 1), 14),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(summary)

    missing_groups = [
        (f"Only in {left_label} - Files", result.only_in_left_files),
        (f"Only in {left_label} - Folders", result.only_in_left_folders),
        (f"Only in {right_label} - Files", result.only_in_right_files),
        (f"Only in {right_label} - Folders", result.only_in_right_folders),
    ]
    if any(items for _, items in missing_groups):
        story.append(Spacer(1, 7))
        missing_rows = [["Missing item group", "Path"]]
        for group, items in missing_groups:
            for item in items:
                missing_rows.append([_paragraph(group, small), _paragraph(item, small)])
        missing_table = LongTable(missing_rows, colWidths=[62 * mm, 112 * mm], repeatRows=1)
        missing_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(missing_table)

    story.append(Paragraph("File Results", heading))
    file_rows = [["File / path", "Status", "Details"]]
    for path, status, details in _rows_for_result(result):
        file_rows.append([
            _paragraph(path, small),
            _paragraph(status, small),
            _paragraph(details, small),
        ])
    if len(file_rows) == 1:
        file_rows.append([
            _paragraph("-", small),
            _paragraph("-", small),
            _paragraph("There are no common files to compare.", small),
        ])

    file_table = LongTable(file_rows, colWidths=[65 * mm, 27 * mm, 82 * mm], repeatRows=1)
    file_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(file_table)

    doc.build(story)
    return buffer.getvalue()
