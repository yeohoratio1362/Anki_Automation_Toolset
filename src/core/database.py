import sqlite3
import shutil
import sys
import time
import logging

# Anki uses unicase collation for some columns, basically undoes text capitalisation
def _unicase_compare(a, b):
    a_low, b_low = a.lower(), b.lower()
    if a_low < b_low:
        return -1
    if a_low > b_low:
        return 1
    return 0

def get_connection(db_path, read_only=False):
    # Returns database connection and backup path
    try:
        if read_only:
            # Connect in secure read-only mode for script
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
            return conn, None
        
        # Write actions require creating a backup copy first to prevent profile corruption
        backup_path = f"{db_path}.toolkit_backup"
        shutil.copy2(db_path, backup_path)
        logging.info(f"Database backup securely saved at: {backup_path}")
        
        conn = sqlite3.connect(db_path, timeout=30)
        conn.create_collation("unicase", _unicase_compare)
        return conn, backup_path
    # Logs database status if database is locked
    except sqlite3.OperationalError as e:
        if "locked" in str(e):
            logging.critical("Database Locked! Anki Desktop is open. Close Anki and retry.")
        else:
            logging.critical(f"SQLite operational failure: {e}")
        sys.exit(1)


def commit_tag_updates(database, updates):
    # Shared write function used by both mesh_tagger and performance modules
    # Injects tags, updates 'mod' history flags, sets 'usn = -1' to force sync
    if not updates:
        logging.info("No tag modifications required. Skipping transaction.")
        return 0
        
    cursor = database.cursor()
    current_time_secs = int(time.time())
    current_time_ms = int(time.time() * 1000)
    updated_count = 0
    
    for updated_tags_str, note_id in updates:
        cursor.execute(
            "UPDATE notes SET tags = ?, mod = ?, usn = -1 WHERE id = ?", 
            (updated_tags_str, current_time_secs, note_id)
        )
        updated_count += 1
        
    if updated_count > 0:
        cursor.execute("UPDATE col SET mod = ?", (current_time_ms,))
        
    database.commit()
    return updated_count
