"""Printable PDF badges / flash cards for top performers."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, PageBreak, SimpleDocTemplate, Spacer


def build_top_performer_badges_pdf(
    entries: list[tuple[str, float, str]],
    *,
    document_title: str = "Top performer badges",
) -> bytes:
    """
    Build a multi-page PDF: one stylish badge per entry (name, score %, motivational quote).
    Landscape pages read like printable flash cards.
    """
    if not entries:
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=landscape(letter))
        c.setFont("Helvetica", 14)
        c.drawString(120, 400, "No top performers to display.")
        c.save()
        buf.seek(0)
        return buf.read()

    buf = BytesIO()
    page_size = landscape(letter)
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        title=document_title,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BadgeTitle",
        parent=styles["Title"],
        fontSize=26,
        textColor=colors.HexColor("#1a237e"),
        spaceAfter=14,
        alignment=1,
    )
    name_style = ParagraphStyle(
        "BadgeName",
        parent=styles["Heading1"],
        fontSize=22,
        textColor=colors.HexColor("#0d47a1"),
        spaceAfter=8,
        alignment=1,
    )
    score_style = ParagraphStyle(
        "BadgeScore",
        parent=styles["Normal"],
        fontSize=14,
        textColor=colors.HexColor("#37474f"),
        spaceAfter=20,
        alignment=1,
    )
    quote_style = ParagraphStyle(
        "BadgeQuote",
        parent=styles["Italic"],
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#263238"),
        spaceAfter=12,
        alignment=1,
        leftIndent=12,
        rightIndent=12,
    )
    ribbon = ParagraphStyle(
        "Ribbon",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#bf360c"),
        alignment=1,
        spaceAfter=18,
    )

    story: list = []
    for i, (name, score_pct, quote) in enumerate(entries):
        if i:
            story.append(PageBreak())
        story.append(Spacer(1, 0.35 * inch))
        story.append(Paragraph("&#9733; Top performer &#9733;", ribbon))
        story.append(Paragraph("Outstanding achievement", title_style))
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph(escape(name), name_style))
        story.append(Paragraph(f"Class score: <b>{score_pct:.1f}%</b>", score_style))
        story.append(Spacer(1, 0.2 * inch))
        qsafe = quote or "Keep shining—your persistence makes a difference."
        story.append(Paragraph(f"&ldquo;{escape(qsafe)}&rdquo;", quote_style))
        story.append(Spacer(1, 0.35 * inch))
        story.append(
            Paragraph(
                "<font size=9 color='#78909c'>Cut or fold as a flash card &middot; For classroom use</font>",
                ParagraphStyle("Foot", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#90a4ae"), alignment=1),
            )
        )

    doc.build(story)
    buf.seek(0)
    return buf.read()
