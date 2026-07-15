import os
import sys
import logging
from datetime import datetime
import config
from src.core.database import get_connection

def get_deck_difficulty(cursor):
    # Computes historical failure rate percentages per individual deck structure
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
    
    deck_difficulty = {}
    for did, total, fails in rows:
        if total < config.MIN_REVIEW_COUNT:
            continue
        deck_difficulty[did] = {
            "fail_rate": fails / total,
            "total": total
        }
    return deck_difficulty

def get_problem_cards_sql(cursor):
    # Retrieves top 50 cards exceeding historical fail thresholds
    cursor.execute("""
        SELECT 
            r.cid,
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
    for cid, did, total, fails, avg_time in rows:
        if total < config.MIN_REVIEW_COUNT:
            continue
        fail_rate = fails / total
        if fail_rate > 0.3:
            problem_cards.append({
                "cid": cid, "did": did, "fail_rate": fail_rate,
                "reviews": total, "avg_time": avg_time
            })
    
    problem_cards.sort(key=lambda x: x["fail_rate"], reverse=True)
    return problem_cards[:50]

def get_deck_names(cursor):
    # Deck ids to deck names
    cursor.execute("SELECT id, name FROM decks")
    return {did: name for did, name in cursor.fetchall()}

def get_leaf_deck(deck_name):
    # Strips parent decks to isolate subdeck names
    return deck_name.split("\x1f")[-1]

def get_today_stats(cursor):
    # Computes execution counts and total correct responses since midnight
    start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start_of_day.timestamp() * 1000)

    cursor.execute("SELECT ease FROM revlog WHERE id >= ?", (start_ms,))
    rows = cursor.fetchall()

    if not rows:
        return 0, 0.0

    total = len(rows)
    correct = sum(1 for r in rows if r[0] > 1)
    return total, (correct / total)

def main():
    logging.info("Starting data synchronization pipeline...")
    
    if not config.JOURNAL_DIR:
        logging.critical("Configuration Error: JOURNAL_DIR path is not set in your environment file.")
        sys.exit(1)
        
    if not os.path.exists(config.JOURNAL_DIR):
        logging.warning(f"Target vault directory does not exist. Creating directories at: {config.JOURNAL_DIR}")
        os.makedirs(config.JOURNAL_DIR, exist_ok=True)

    # Establish secure read-only analytics thread connection
    database, _ = get_connection(config.DB_PATH, read_only=True)
    cursor = database.cursor()

    try:
        logging.info("Analyzing user card performance histories and collection patterns...")
        problem_cards = get_problem_cards_sql(cursor)
        deck_stats = get_deck_difficulty(cursor)
        id_to_deck = get_deck_names(cursor)
        deck_names = list(id_to_deck.values())
        
        logging.info("Evaluating collection structure to filter out parent categories...")
        weak_decks = []
        for did, stats in deck_stats.items():
            deck = id_to_deck.get(did, None)
            if not deck:
                continue
            # Ensure we only track functional leaf subdecks
            if any(d != deck and d.startswith(deck + "::") for d in deck_names):
                continue

            weak_decks.append({
                "deck": get_leaf_deck(deck),
                "fail_rate": stats["fail_rate"],
                "reviews": stats["total"]
            })

        weak_decks.sort(key=lambda x: x["fail_rate"], reverse=True)

        logging.info("Compiling active retention statistics recorded for today...")
        total_reviews, retention = get_today_stats(cursor)

        # Generate standard production Markdown data matrices
        yaml_frontmatter = f"""---
Anki_Count: {total_reviews}
Anki_Retention: {retention*100:.1f}
SelfCare:
---
"""
        markdown_body = yaml_frontmatter
        
        # Build Weak Topics Matrix
        markdown_body += "### Weak Topics\n|Deck|Fail rate|Review Count|\n|-|-|-|\n"
        for d in weak_decks[:20]:
            markdown_body += f"|[[{d['deck']}]]|{d['fail_rate']*100:.1f}%|{d['reviews']}|\n"

        # Build Problem Cards Matrix
        markdown_body += "\n### Problem Cards\n|CID|Deck|Fail rate|Review Count|\n|-|-|-|-|\n"
        for c in problem_cards:
            deck_full = id_to_deck.get(c["did"], "Unknown")
            deck_leaf = get_leaf_deck(deck_full)
            markdown_body += f"|{c['cid']}|[[{deck_leaf}]]|{c['fail_rate']*100:.1f}%|{c['reviews']}|\n"

        # Safe programmatic save execution
        today_str = datetime.now().strftime("%Y-%m-%d")
        output_file_path = os.path.join(config.JOURNAL_DIR, f"{today_str}.md")
        
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_body)
            
        logging.info(f"Report sync successful! Daily analytical journal generated at: {output_file_path}")

    except Exception as e:
        logging.error(f"Analytical compilation failed due to pipeline interrupt: {e}")
    finally:
        database.close()

if __name__ == "__main__":
    main()
