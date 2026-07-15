import sqlite3
import time
import os
import logging
import config
from src.core.database import get_connection

def main():
    logging.info("Initializing performance-based card metric calculations...")
    
    database, backup_file = get_connection(config.DB_PATH, read_only=False)
    cursor = database.cursor()

    try:
        slow_threshold_ms = config.SLOW_THRESHOLD_SECONDS * 1000
        fast_threshold_ms = config.FAST_THRESHOLD_SECONDS * 1000

        logging.info("Scanning database review logs ('revlog') to compute performance metrics...")
        cursor.execute("""
            SELECT 
                c.nid,
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
        for nid, total, fails, avg_time in raw_rows:
            if nid not in expected_note_tags:
                expected_note_tags[nid] = set()
                
            if total >= config.MIN_REVIEW_COUNT:
                fail_rate = fails / total
                if fail_rate >= config.FAIL_RATE_THRESHOLD:
                    expected_note_tags[nid].add(config.TAG_DIFFICULT)
                if fail_rate <= config.EASY_RATE_THRESHOLD:
                    expected_note_tags[nid].add(config.TAG_EASY)
                if avg_time >= slow_threshold_ms:
                    expected_note_tags[nid].add(config.TAG_SLOW)
                if avg_time <= fast_threshold_ms:
                    expected_note_tags[nid].add(config.TAG_FAST)

        # Scan for existing tags
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
            # Print update every 500 notes
            if (idx + 1) % 500 == 0 or (idx + 1) == total_notes:
                logging.info(f"  -> Audit Progress: Checkpoint reached at {idx + 1}/{total_notes} notes processed.")

            cursor.execute("SELECT tags FROM notes WHERE id = ?", (nid,))
            row = cursor.fetchone()
            if not row:
                continue
                
            current_tags_str = row[0]
            tag_list = [t for t in current_tags_str.split(" ") if t]
            original_tags = list(tag_list)
            
            for tag in [config.TAG_DIFFICULT, config.TAG_EASY, config.TAG_SLOW, config.TAG_FAST]:
                if tag in tag_list:
                    tag_list.remove(tag)
                    
            target_tags = expected_note_tags.get(nid, set())
            for tag in target_tags:
                if tag not in tag_list:
                    tag_list.append(tag)
            
            tag_list.sort()
            original_tags.sort()
            
            if tag_list != original_tags:
                new_tags_str = f" {' '.join(tag_list)} " if tag_list else ""
                cursor.execute("""
                    UPDATE notes 
                    SET tags = ?, mod = ?, usn = -1 
                    WHERE id = ?
                """, (new_tags_str, current_timestamp, nid))
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
