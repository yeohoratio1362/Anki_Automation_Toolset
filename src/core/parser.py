import re
import logging
import spacy

# Attempts to load spacy
try:
    nlp = spacy.load("en_core_web_sm")
except Exception:
    logging.warning("spaCy baseline model 'en_core_web_sm' not found. Grammar fallback engine disabled. Run python3 -m spacy download en_core_web_sm")
    nlp = None

def clean_cloze_text(raw_text):
    # Strips formatting boundaries and extracts encapsulated cloze parameters
    clean_html = re.sub(r'<[^>]+>', ' ', raw_text)
    clean_text = re.sub(r'\{\{c\d+::([^:}]+)(?::[^}]+)?\}\}', r'\1', clean_html)
    cloze_terms = re.findall(r'\{\{c\d+::([^:}]+)(?::[^}]+)?\}\}', raw_text)
    return clean_text.strip(), [term.strip().lower() for term in cloze_terms if term]

def extract_noun_chunks(text):
    if not nlp:
        return []
    doc = nlp(text)
    chunks = []
    for chunk in doc.noun_chunks:
        chunk_text = chunk.text.lower().strip()
        if not chunk.root.is_stop and len(chunk_text) > 3:
            chunks.append(chunk_text)
    return chunks
