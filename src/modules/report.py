import os
import sys
import io
import logging
from datetime import datetime
from typing import List, Dict, Any

import matplotlib
matplotlib.use('Agg')  # Headless backend for PDF chart rendering
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
)

import config
from src.core.database import get_connection
from src.core.models import Card

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ==========================================
# DATA AGGREGATION & ANALYTICS
# ==========================================

def get_mesh_tag_stats(cursor) -> List[Dict[str, Any]]:
    """Aggregates review count, failure rate, and response time grouped by MeSH tags."""
    cursor.execute("""
        SELECT 
            n.tags,
            COUNT(r.id) as total_reviews,
            SUM(CASE WHEN r.ease = 1 THEN 1 ELSE 0 END) as fails,
            AVG(r.time) as avg_time
        FROM notes n
        JOIN cards c ON n.id = c.nid
        JOIN revlog r ON c.id = r.cid
        GROUP BY c.id, n.id, n.tags
    """)
    rows = cursor.fetchall()
    
    mesh_stats = {}
    for tags_str, total, fails, avg_time in rows:
        if not tags_str:
            continue
            
        # Filter for MeSH tags added by mesh_tagger
        mesh_tags = [t for t in tags_str.split(" ") if t.startswith("mesh::")]
        
        for tag in mesh_tags:
            clean_name = tag.replace("mesh::", "").replace("-", " ").title()
            if clean_name not in mesh_stats:
                mesh_stats[clean_name] = {"reviews": 0, "fails": 0, "total_time": 0.0, "card_count": 0}
            
            mesh_stats[clean_name]["reviews"] += total
            mesh_stats[clean_name]["fails"] += fails
            mesh_stats[clean_name]["total_time"] += (avg_time or 0) * total
            mesh_stats[clean_name]["card_count"] += 1

    min_reviews = getattr(config, "MIN_REVIEW_COUNT", 5)
    results = []
    
    for concept, data in mesh_stats.items():
        if data["reviews"] < min_reviews:
            continue
            
        fail_rate = data["fails"] / data["reviews"] if data["reviews"] > 0 else 0.0
        avg_time_sec = (data["total_time"] / data["reviews"]) / 1000.0 if data["reviews"] > 0 else 0.0
        
        results.append({
            "concept": concept,
            "reviews": data["reviews"],
            "fails": data["fails"],
            "fail_rate": fail_rate,
            "fail_percentage": fail_rate * 100.0,
            "avg_time_sec": avg_time_sec,
            "card_count": data["card_count"]
        })

    results.sort(key=lambda x: x["fail_rate"], reverse=True)
    return results


def get_deck_difficulty(cursor) -> Dict[int, Dict[str, Any]]:
    """Computes failure rate percentages per individual deck."""
    cursor.execute("""
        SELECT
            c.did,
            COUNT(*) as total,
            SUM(CASE WHEN r.ease = 1 THEN 1 ELSE 0 END) as fails
        FROM revlog r
        JOIN cards c ON r.cid = c.id
        GROUP BY c.did
    """)
    rows = cursor.fetchall()
    
    min_reviews = getattr(config, "MIN_REVIEW_COUNT", 5)
    deck_difficulty = {}
    for did, total, fails in rows:
        if total < min_reviews:
            continue
        deck_difficulty[did] = {
            "fail_rate": fails / total,
            "total": total
        }
    return deck_difficulty


def get_problem_cards(cursor, id_to_deck) -> List[Card]:
    """Retrieves top 20 problem cards exceeding historical failure thresholds."""
    cursor.execute("""
        SELECT 
            r.cid,
            c.nid,
            c.did,
            COUNT(*) as total,
            SUM(CASE WHEN r.ease = 1 THEN 1 ELSE 0 END) as fails,
            AVG(r.time) as avg_time
        FROM revlog r
        JOIN cards c ON r.cid = c.id
        GROUP BY r.cid
    """)
    rows = cursor.fetchall()

    problem_cards = []
    min_reviews = getattr(config, "MIN_REVIEW_COUNT", 5)
    
    for row in rows:
        did = row[2]
        deck_full = id_to_deck.get(did, "Unknown")
        deck_leaf = deck_full.split("\x1f")[-1]
        
        card = Card.from_db_row(row, deck_name=deck_leaf)
        
        if card.reviews < min_reviews:
            continue
        if card.fail_rate > 0.3:
            problem_cards.append(card)
    
    problem_cards.sort(key=lambda x: x.fail_rate, reverse=True)
    return problem_cards[:20]


def get_deck_names(cursor) -> Dict[int, str]:
    """Maps deck IDs to deck names."""
    cursor.execute("SELECT id, name FROM decks")
    return {did: name for did, name in cursor.fetchall()}


def get_today_stats(cursor) -> tuple:
    """Computes review counts and retention rate recorded today."""
    start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start_of_day.timestamp() * 1000)

    cursor.execute("SELECT ease FROM revlog WHERE id >= ?", (start_ms,))
    rows = cursor.fetchall()

    if not rows:
        return 0, 0.0

    total = len(rows)
    correct = sum(1 for r in rows if r[0] > 1)
    return total, (correct / total)


# ==========================================
# CHART GENERATION (MATPLOTLIB)
# ==========================================

def create_mesh_chart_buffer(mesh_stats: List[Dict[str, Any]]) -> io.BytesIO:
    """Generates a horizontal bar chart of the hardest MeSH Medical concepts."""
    top_mesh = mesh_stats[:10]
    top_mesh.reverse()  # Reverse for ascending bar chart order
    
    concepts = [m["concept"][:25] + "..." if len(m["concept"]) > 25 else m["concept"] for m in top_mesh]
    fail_rates = [m["fail_percentage"] for m in top_mesh]

    fig, ax = plt.subplots(figsize=(7, 3.5), dpi=200)
    bars = ax.barh(concepts, fail_rates, color='#E53935', edgecolor='none', height=0.6)

    ax.set_xlabel('Failure Rate (%)', fontsize=9, fontweight='bold', color='#333333')
    ax.set_title('Top Hardest MeSH Medical Concepts', fontsize=11, fontweight='bold', pad=10)
    ax.set_xlim(0, 100)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#CCCCCC')
    ax.spines['bottom'].set_color('#CCCCCC')
    ax.tick_params(axis='both', which='both', labelsize=8)

    # Add percentage labels to bars
    for bar in bars:
        width = bar.get_width()
        ax.text(width + 1.5, bar.get_y() + bar.get_height()/2, f'{width:.1f}%',
                va='center', ha='left', fontsize=8, color='#333333', fontweight='bold')

    plt.tight_layout()
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    plt.close(fig)
    buffer.seek(0)
    return buffer


# ==========================================
# PDF BUILDER (REPORTLAB)
# ==========================================

def build_pdf_report(
    output_path: str,
    today_reviews: int,
    retention: float,
    mesh_stats: List[Dict[str, Any]],
    weak_decks: List[Dict[str, Any]],
    problem_cards: List[Card]
):
    """Compiles analytical tables and charts into a formatted PDF document."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Palette & Typography
    PRIMARY_COLOR = colors.HexColor("#1A237E")
    SECONDARY_COLOR = colors.HexColor("#303F9F")
    TEXT_COLOR = colors.HexColor("#212121")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=PRIMARY_COLOR,
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#666666"),
        spaceAfter=15
    )
    section_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=SECONDARY_COLOR,
        spaceBefore=12,
        spaceAfter=8
    )
    table_text_style = ParagraphStyle(
        'TableText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=TEXT_COLOR
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white
    )

    story = []

    # 1. Header
    today_str = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph("Anki MeSH Medical Analytics Report", title_style))
    story.append(Paragraph(f"Generated on {today_str} | Active MeSH Medical Taxonomy Engine", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY_COLOR, spaceAfter=15))

    # 2. KPI Summary Banner
    kpi_data = [
        [
            Paragraph("<b>Reviews Today</b>", table_header_style),
            Paragraph("<b>Daily Retention</b>", table_header_style),
            Paragraph("<b>Tracked MeSH Concepts</b>", table_header_style)
        ],
        [
            Paragraph(f"<font size=12><b>{today_reviews}</b></font>", table_text_style),
            Paragraph(f"<font size=12><b>{retention*100:.1f}%</b></font>", table_text_style),
            Paragraph(f"<font size=12><b>{len(mesh_stats)}</b></font>", table_text_style)
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[180, 180, 180])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_COLOR),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#F5F5F5")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 15))

    # 3. MeSH Concept Chart Section
    if mesh_stats:
        story.append(Paragraph("MeSH Medical Performance Visualization", section_style))
        chart_buffer = create_mesh_chart_buffer(mesh_stats)
        story.append(Image(chart_buffer, width=500, height=250))
        story.append(Spacer(1, 10))

        # 4. Hardest MeSH Terms Table
        story.append(Paragraph("Hardest MeSH Medical Terms", section_style))
        mesh_table_data = [[
            Paragraph("<b>MeSH Concept</b>", table_header_style),
            Paragraph("<b>Fail Rate</b>", table_header_style),
            Paragraph("<b>Reviews</b>", table_header_style),
            Paragraph("<b>Cards</b>", table_header_style),
            Paragraph("<b>Avg Time</b>", table_header_style)
        ]]
        
        for item in mesh_stats[:10]:
            mesh_table_data.append([
                Paragraph(item["concept"], table_text_style),
                Paragraph(f"{item['fail_percentage']:.1f}%", table_text_style),
                Paragraph(str(item["reviews"]), table_text_style),
                Paragraph(str(item["card_count"]), table_text_style),
                Paragraph(f"{item['avg_time_sec']:.2f}s", table_text_style)
            ])

        mesh_table = Table(mesh_table_data, colWidths=[200, 80, 80, 80, 100])
        mesh_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), SECONDARY_COLOR),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(mesh_table)
        story.append(Spacer(1, 15))

    # 5. Weak Decks Section
    if weak_decks:
        story.append(Paragraph("Weakest Deck Structures", section_style))
        deck_table_data = [[
            Paragraph("<b>Deck Name</b>", table_header_style),
            Paragraph("<b>Fail Rate</b>", table_header_style),
            Paragraph("<b>Total Reviews</b>", table_header_style)
        ]]
        
        for d in weak_decks[:10]:
            deck_table_data.append([
                Paragraph(d['deck'], table_text_style),
                Paragraph(f"{d['fail_rate']*100:.1f}%", table_text_style),
                Paragraph(str(d['reviews']), table_text_style)
            ])

        deck_table = Table(deck_table_data, colWidths=[300, 120, 120])
        deck_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), SECONDARY_COLOR),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(deck_table)
        story.append(Spacer(1, 15))

    # 6. Top Problem Cards Section
    if problem_cards:
        story.append(Paragraph("Top Problem Cards", section_style))
        card_table_data = [[
            Paragraph("<b>Card ID</b>", table_header_style),
            Paragraph("<b>Deck</b>", table_header_style),
            Paragraph("<b>Fail Rate</b>", table_header_style),
            Paragraph("<b>Reviews</b>", table_header_style),
            Paragraph("<b>Avg Time</b>", table_header_style)
        ]]
        
        for card in problem_cards[:10]:
            card_table_data.append([
                Paragraph(str(card.cid), table_text_style),
                Paragraph(card.deck_name, table_text_style),
                Paragraph(f"{card.fail_percentage:.1f}%", table_text_style),
                Paragraph(str(card.reviews), table_text_style),
                Paragraph(f"{card.avg_time_sec:.2f}s", table_text_style)
            ])

        card_table = Table(card_table_data, colWidths=[80, 220, 80, 80, 80])
        card_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), SECONDARY_COLOR),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(card_table)

    # Build Document
    doc.build(story)


# ==========================================
# MAIN PIPELINE EXECUTION
# ==========================================

def main():
    logging.info("Initializing MeSH Performance Analytics Engine...")
    
    if not getattr(config, "JOURNAL_DIR", None):
        logging.critical("JOURNAL_DIR path is not configured.")
        sys.exit(1)
        
    os.makedirs(config.JOURNAL_DIR, exist_ok=True)

    database, _ = get_connection(config.DB_PATH, read_only=True)
    cursor = database.cursor()

    try:
        logging.info("Mapping collection structure and localized decks...")
        id_to_deck = get_deck_names(cursor)
        deck_names = list(id_to_deck.values())
        
        logging.info("Aggregating card performance data by MeSH concepts...")
        mesh_stats = get_mesh_tag_stats(cursor)
        
        logging.info("Analyzing card failure histories and deck metrics...")
        problem_cards = get_problem_cards(cursor, id_to_deck)
        deck_stats = get_deck_difficulty(cursor)
        
        weak_decks = []
        for did, stats in deck_stats.items():
            deck = id_to_deck.get(did, None)
            if not deck:
                continue
            if any(d != deck and d.startswith(deck + "::") for d in deck_names):
                continue

            leaf_deck = deck.split("\x1f")[-1]
            weak_decks.append({
                "deck": leaf_deck,
                "fail_rate": stats["fail_rate"],
                "reviews": stats["total"]
            })

        weak_decks.sort(key=lambda x: x["fail_rate"], reverse=True)

        logging.info("Evaluating daily retention statistics...")
        today_reviews, retention = get_today_stats(cursor)

        # Generate output PDF file path
        today_str = datetime.now().strftime("%Y-%m-%d")
        output_pdf_path = os.path.join(config.JOURNAL_DIR, f"MeSH_Performance_Report_{today_str}.pdf")

        logging.info("Compiling visual PDF performance report...")
        build_pdf_report(
            output_path=output_pdf_path,
            today_reviews=today_reviews,
            retention=retention,
            mesh_stats=mesh_stats,
            weak_decks=weak_decks,
            problem_cards=problem_cards
        )
        
        logging.info(f"PDF Report generated successfully at: {output_pdf_path}")

    except Exception as e:
        logging.error(f"Failed to generate performance PDF report: {e}")
    finally:
        database.close()


if __name__ == "__main__":
    main()
