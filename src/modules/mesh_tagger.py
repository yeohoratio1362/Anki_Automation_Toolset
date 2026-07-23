import os
import sys
import time
import json
import pickle
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Set, Tuple

import torch
import ollama

import config
from src.core.database import get_connection, commit_tag_updates
from src.core.parser import clean_cloze_text, extract_noun_chunks
from src.core.models import Note

# ==========================================
# CONFIGURATION & SETTINGS
# ==========================================

EMBEDDING_MODEL = getattr(config, "EMBEDDING_MODEL", "nomic-embed-text")
SIMILARITY_THRESHOLD = float(getattr(config, "SIMILARITY_THRESHOLD", 0.78))
MESH_XML_PATH = getattr(config, "MESH_XML_PATH", "desc2026.xml")
CACHE_PATH = getattr(config, "CACHE_PATH", "mesh_embeddings_cache.pkl")
HISTORY_FILE = getattr(config, "HISTORY_FILE", "mesh_tag_history.json")

# Mute routine HTTP request logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Hardware Acceleration Setup
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ==========================================
# JSON TAG HISTORY MANAGEMENT
# ==========================================

def load_tag_history() -> Dict[str, List[str]]:
    # Loads the history of tags added
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Could not load tag history file: {e}. Starting fresh.")
    return {}


def save_tag_history(history: Dict[str, List[str]]) -> None:
    # Saves updated script tag history
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        logging.info(f"Updated tag tracking history saved to '{HISTORY_FILE}'.")
    except Exception as e:
        logging.error(f"Failed to save tag tracking history: {e}")


# ==========================================
# MESH XML PARSER
# ==========================================

def parse_mesh_xml(xml_path: str) -> List[str]:
    """Parses NLM MeSH Descriptor XML file to extract standard Descriptor names."""
    if not os.path.exists(xml_path):
        logging.critical(f"MeSH XML file not found at path: {xml_path}")
        sys.exit(1)

    logging.info(f"Parsing MeSH XML descriptor database from '{xml_path}'...")
    descriptors = []
    
    try:
        context = ET.iterparse(xml_path, events=("end",))
        for event, elem in context:
            if elem.tag == "DescriptorRecord":
                name_elem = elem.find("./DescriptorName/String")
                if name_elem is not None and name_elem.text:
                    descriptors.append(name_elem.text.strip())
                elem.clear()
                
        logging.info(f"Successfully extracted {len(descriptors)} unique MeSH terms.")
        return sorted(list(set(descriptors)))
    except Exception as e:
        logging.critical(f"Failed to parse MeSH XML file: {e}")
        sys.exit(1)


# ==========================================
# EMBEDDING GENERATION (OLLAMA PYTHON SDK)
# ==========================================

def get_ollama_embeddings(texts: List[str], batch_size: int = 64) -> torch.Tensor:
    """Generates normalized vector embeddings using the official Ollama Python SDK."""
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            # Native Python Ollama embedding call
            response = ollama.embed(model=EMBEDDING_MODEL, input=batch)
            all_embeddings.extend(response["embeddings"])
        except Exception as e:
            logging.error(f"Ollama Embed API Error: {e}")
            sys.exit(1)

    tensor_embeddings = torch.tensor(all_embeddings, dtype=torch.float32, device=DEVICE)
    # L2 Normalization for Cosine Similarity: ||v|| = 1
    return torch.nn.functional.normalize(tensor_embeddings, p=2, dim=1)


def get_or_create_mesh_cache(descriptors: List[str]) -> Tuple[List[str], torch.Tensor]:
    # Loads cached MeSH descriptor embeddings or computes them using Ollama
    if os.path.exists(CACHE_PATH):
        logging.info(f"Loading cached MeSH embeddings from '{CACHE_PATH}'...")
        with open(CACHE_PATH, "rb") as f:
            cache_data = pickle.load(f)
            if cache_data.get("terms") == descriptors:
                logging.info("MeSH embedding cache validated.")
                return cache_data["terms"], cache_data["vectors"].to(DEVICE)
            logging.info("MeSH dataset modified. Rebuilding vector cache...")

    logging.info(f"Generating embeddings for {len(descriptors)} terms on target device: {DEVICE}...")
    start_time = time.time()
    embeddings = get_ollama_embeddings(descriptors, batch_size=128)
    logging.info(f"Embeddings calculated in {time.time() - start_time:.2f} seconds.")

    with open(CACHE_PATH, "wb") as f:
        pickle.dump({"terms": descriptors, "vectors": embeddings.cpu()}, f)
    logging.info(f"Saved MeSH vector cache to '{CACHE_PATH}'.")

    return descriptors, embeddings


# ==========================================
# COSINE SIMILARITY MATCHING ENGINE
# ==========================================

def format_anki_tag(term: str) -> str:
    """Formats a MeSH descriptor into a standardized Anki tag name."""
    clean_term = term.lower().replace(",", "").replace("'", "")
    clean_term = "-".join(clean_term.split())
    return f"mesh::{clean_term}"


def match_card_concepts(
    card_text: str,
    chunks: List[str],
    mesh_terms: List[str],
    mesh_embeddings: torch.Tensor,
    threshold: float
) -> Set[str]:
    threshold = float(threshold)
    candidates = list(set([card_text] + chunks))
    if not candidates:
        return set()

    candidate_embeddings = get_ollama_embeddings(candidates)

    # Cosine Similarity Matrix: S = C * M^T (Since vectors are L2 normalized)
    similarity_matrix = torch.matmul(candidate_embeddings, mesh_embeddings.T)

    matched_tags = set()
    high_sim_indices = (similarity_matrix >= threshold).nonzero(as_tuple=False)
    
    for _, col_idx in high_sim_indices:
        term = mesh_terms[col_idx.item()]
        matched_tags.add(format_anki_tag(term))

    return matched_tags


# ==========================================
# MAIN EXECUTION PIPELINE
# ==========================================

def main():
    logging.info(f"Initializing Local MeSH Embedding Tagger | Compute Device: {DEVICE}")

    # Parse MeSH Terms & Load Vectors
    descriptors = parse_mesh_xml(MESH_XML_PATH)
    mesh_terms, mesh_embeddings = get_or_create_mesh_cache(descriptors)

    # Load Previous Script Tag History
    tag_history = load_tag_history()

    # Connect to Database
    database, backup_file = get_connection(config.DB_PATH, read_only=False)
    cursor = database.cursor()

    try:
        cursor.execute("SELECT id, tags, flds FROM notes")
        raw_notes = cursor.fetchall()
        logging.info(f"Loaded {len(raw_notes)} notes from database.")

        db_updates_queue = []
        processed_count = 0

        for row in raw_notes:
            note = Note.from_db_row(row)
            nid_str = str(note.nid)
            cleaned_text, _ = clean_cloze_text(note.primary_field)
            
            if len(cleaned_text) < 5:
                continue

            chunks = extract_noun_chunks(cleaned_text)
            
            # Find currently valid script tags based on vector similarity
            current_matched_tags = match_card_concepts(
                card_text=cleaned_text,
                chunks=chunks,
                mesh_terms=mesh_terms,
                mesh_embeddings=mesh_embeddings,
                threshold=SIMILARITY_THRESHOLD
            )

            # Retrieve tags applied by this script in previous runs
            previous_script_tags = set(tag_history.get(nid_str, []))

            # Tags that no longer pass threshold and should be removed
            tags_to_remove = previous_script_tags - current_matched_tags
            
            # Tags to add
            tags_to_add = current_matched_tags - note.tags

            note_modified = False

            # Remove stale script tags if card was edited
            for tag in tags_to_remove:
                if tag in note.tags:
                    note.tags.remove(tag)
                    note_modified = True

            # Add newly matched tags
            for tag in tags_to_add:
                note.tags.add(tag)
                note_modified = True

            # Sync tag state and queue DB update
            if note_modified:
                db_updates_queue.append((note.tags_string, note.nid))

            # Update local history for this note
            if current_matched_tags:
                tag_history[nid_str] = list(current_matched_tags)
            elif nid_str in tag_history:
                del tag_history[nid_str]

            processed_count += 1
            if processed_count % 100 == 0:
                logging.info(f"Evaluated {processed_count}/{len(raw_notes)} notes...")

        # Commit Database Updates & Save Tag History
        if db_updates_queue:
            updated_records = commit_tag_updates(database, db_updates_queue)
            logging.info(f"Updated tags across {updated_records} Anki notes!")
        else:
            logging.info("Pipeline complete. No database changes required.")

        save_tag_history(tag_history)

        # Remove safety backup file upon successful execution
        if backup_file and os.path.exists(backup_file):
            os.remove(backup_file)

    except Exception as e:
        logging.error(f"Pipeline failure encountered: {e}")
        database.rollback()
    finally:
        database.close()


if __name__ == "__main__":
    main()
