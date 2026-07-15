import os
import sys
import json
import time
import logging
from collections import Counter
import requests

import config
from src.core.database import get_connection, commit_tag_updates
from src.core.parser import clean_cloze_text, extract_noun_chunks

def query_mesh_on_demand(text):
    #Submits payload text straight to the National Library of Medicine API (Thanks NIH)
    if not text or len(text) < 10:
        return []
    url = "https://meshb.nlm.nih.gov/modapi/mesh/ondemand"
    headers = {"Content-Type": "application/json"}
    payload = {"text": text}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            concepts = data.get('concepts', data.get('results', []))
            return [item['text'].lower() if isinstance(item, dict) else item.lower() for item in concepts]
    except Exception as e:
        logging.debug(f"NLM Rest Endpoint connection drop: {e}")
    return []

def load_preferences():
    # Load tag preferences from .json
    if os.path.exists(config.PREFS_PATH):
        try:
            with open(config.PREFS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to read user tag tracking JSON cache: {e}")
    return {"accepted": {}, "denied": []}

def save_preferences(prefs):
    # Save tag preferences to .json
    try:
        with open(config.PREFS_PATH, 'w', encoding='utf-8') as f:
            json.dump(prefs, f, indent=4)
        logging.info("User tag cache preferences successfully updated on disk.")
    except Exception as e:
        logging.error(f"Failed to commit user session metrics to disk: {e}")

def main():
    logging.info("Starting MeSH semantic medical tag optimization run...")
    prefs = load_preferences()
    
    # Establish database window
    database, backup_file = get_connection(config.DB_PATH, read_only=False)
    cursor = database.cursor()
    
    try:
        cursor.execute("SELECT id, tags, flds FROM notes")
        raw_notes = cursor.fetchall()
        
        concept_counter = Counter()
        processed_notes_cache = []
        
        for idx, (note_id, existing_tags, flds) in enumerate(raw_notes):
            primary_field = flds.split('\x1f')[0]
            cleaned_text, cloze_terms = clean_cloze_text(primary_field)
            
            if idx > 0 and idx % 3 == 0:
                time.sleep(0.2)
                
            mesh_terms = query_mesh_on_demand(cleaned_text)
            
            for term in mesh_terms:
                concept_counter[term] += 5
            for term in cloze_terms:
                if len(term) > 2:
                    concept_counter[term] += 2
            if not mesh_terms:
                for chunk in extract_noun_chunks(cleaned_text):
                    concept_counter[chunk] += 1
                    
            processed_notes_cache.append({
                'id': note_id, 'existing_tags': existing_tags,
                'cleaned_text': cleaned_text, 'cloze_terms': cloze_terms, 'mesh_terms': mesh_terms
            })
            
            if (idx + 1) % 50 == 0 or (idx + 1) == len(raw_notes):
                logging.info(f"MeSH Processing Checkpoint: {idx + 1}/{len(raw_notes)} records parsed.")

        most_common = concept_counter.most_common(config.MAX_TAGS_PER_RUN)
        tags_to_apply = {}
        prefs_changed = False

        print("\n--- INTERACTIVE VOCABULARY ASSIGNMENT PHASE ---")
        for concept, count in most_common:
            if concept in prefs["denied"]: continue
            if concept in prefs["accepted"]:
                tags_to_apply[concept] = prefs["accepted"][concept]
                continue
                
            print(f"\nDiscovered Concept: '{concept}' [Weight: {count}]")
            user_input = input("  -> Bind to Tag? (y = accept / n = skip forever / or type custom tag name): ").strip()
            
            if user_input.lower() == 'y':
                tag_name = concept.replace(" ", "-")
                tags_to_apply[concept] = tag_name
                prefs["accepted"][concept] = tag_name
                prefs_changed = True
            elif user_input.lower() == 'n':
                prefs["denied"].append(concept)
                prefs_changed = True
            elif user_input:
                custom_tag = user_input.replace(" ", "-")
                tags_to_apply[concept] = custom_tag
                prefs["accepted"][concept] = custom_tag
                prefs_changed = True

        if prefs_changed:
            save_preferences(prefs)

        # Build update arrays
        db_updates_queue = []
        for note in processed_notes_cache:
            new_tags_to_add = []
            for concept, tag in tags_to_apply.items():
                if concept in note['mesh_terms'] or concept in note['cleaned_text'].lower() or concept in note['cloze_terms']:
                    if tag not in note['existing_tags']:
                        new_tags_to_add.append(tag)
                        
            if new_tags_to_add:
                current_tags_list = [t for t in note['existing_tags'].split(" ") if t]
                updated_tags_list = list(set(current_tags_list + new_tags_to_add))
                updated_tags_str = f" {' '.join(updated_tags_list)} "
                db_updates_queue.append((updated_tags_str, note['id']))

        # Direct execution handover to the shared database core function
        updated_records = commit_tag_updates(database, db_updates_queue)
        logging.info(f"Database sync finalized. Modified semantic tags across {updated_records} notes.")
        
        if backup_file and os.path.exists(backup_file):
            os.remove(backup_file)

    except Exception as e:
        logging.error(f"Execution error crashed the process: {e}")
        database.rollback()
    finally:
        database.close()
