import sqlite3
import time
import os
import logging
import config
from src.core.database import get_connection
from src.core.models import Card, Note

def main():
    logging.info("Initializing performance-based card metric calculations...")
    
    database, backup_file = get_connection(config.DB_PATH, read_only=False)
    cursor = database.cursor()

    try:
        logging.info("Scanning database review logs ('revlog') to compute performance metrics...")
        # Modified select query structure to perfectly satisfy Card.from_db_row expectations
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
        
        raw_rows = cursor.fetchall()
        logging.info(f"Successfully calculated historic metrics for {len(raw_rows)} individual cards.")

        expected_note_tags = {}
        for row in raw_rows:
            # Instantiate type-safe operational domain Card object model
            card = Card.from_db_row(row)
            
            if card.nid not in expected_note_tags:
                expected_note_tags[card.nid] = set()
                
            if card.reviews >= config.MIN_REVIEW_COUNT:
                if card.fail_rate >= config.FAIL_RATE_THRESHOLD:
                    expected_note_tags[card.nid].add(config.TAG_DIFFICULT)
                if card.fail_rate <= config.EASY_RATE_THRESHOLD:
                    expected_note_tags[card.nid].add(config.TAG_EASY)
                if card.avg_time_sec >= config.SLOW_THRESHOLD_SECONDS:
                    expected_note_tags[card.nid].add(config.TAG_SLOW)
                if card.avg_time_sec <= config.FAST_THRESHOLD_SECONDS:
                    expected_note_tags[card.nid].add(config.TAG_FAST)

        # Scan for existing tracking instances
        cursor.execute("""
            SELECT id FROM notes 
            WHERE tags LIKE ? OR tags LIKE ? OR tags LIKE ? OR tags LIKE ?
        """, (
            f"%{config.TAG_DIFFICULT}%", f"%{config.TAG_EASY}%", 
            f"%{config.TAG_SLOW}%", f"%{config.TAG_FAST}%"
        ))
        
        nids_to_check = set(expected_note_tags.keys())
        for (nid,) in cursor.fetchall():
            nids_to_check.add(nid)

        updated_count = 0
        current_timestamp = int(time.time())
        
        total_notes = len(nids_to_check)
        logging.info(f"Evaluating tag delta allocations across {total_notes} unique notes...")

        for idx, nid in enumerate(nids_to_check):
            if (idx + 1) % 500 == 0 or (idx + 1) == total_notes:
                logging.info(f"  -> Audit Progress: Checkpoint reached at {idx + 1}/{total_notes} notes processed.")

            # Requesting complete row signature block to securely fuel the Note factory parser
            cursor.execute("SELECT id, tags, flds FROM notes WHERE id = ?", (nid,))
            row = cursor.fetchone()
            if not row:
                continue
                
            note = Note.from_db_row(row)
            original_tags_string = note.tags_string
            
            # Clear old automated performance metrics tags via set subtraction
            system_tags = {config.TAG_DIFFICULT, config.TAG_EASY, config.TAG_SLOW, config.TAG_FAST}
            note.tags -= system_tags
            
            # Inject new calculated targeting thresholds
            target_tags = expected_note_tags.get(note.nid, set())
            note.tags.update(target_tags)
            
            # Commit mutations only if an actual tag change occurs
            if note.tags_string != original_tags_string:
                cursor.execute("""
                    UPDATE notes 
                    SET tags = ?, mod = ?, usn = -1 
                    WHERE id = ?
                """, (note.tags_string, current_timestamp, note.nid))
                updated_count += 1

        database.commit()
        logging.info(f"Database sync complete! Mutated and verified performance tags for {updated_count} notes.")
        
        if backup_file and os.path.exists(backup_file):
            os.remove(backup_file)
            logging.info("Temporary pre-execution backup file cleaned up successfully.")

    except Exception as e:
        logging.error(f"Execution error interrupted database run: {e}")
        database.rollback()
    finally:
        database.close()
