# Anki Advanced Automation Toolset

A python software toolkit designed to enable greater Anki flashcard tagging, analysis and study. Specially engineered to handle the intense scaling demands of medical undergraduate degrees.

Toolkit contains semantic medical tagging (Based on a MeSH API interface), card log analytics optimization, and automated cross-platform Markdown knowledge.

---

## Architecture

Workspace is organized to eliminate structural duplication:

```
anki-toolkit/
│
├── config.py                 # Centralized configuration manager (.env loader)
├── requirements.txt          # Third-party dependency registry
├── env.example              # Blueprint template for local environmental setup
├── tag_preferences.json      # Dynamic cache storing user interactive tag choices
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/                 # Shared infrastructure
│   │   ├── __init__.py
│   │   ├── database.py       # Transaction handling, safe backups, & lock prevention
│   │   └── parser.py         # Standardized text HTML text & cloze parsing utilities
│   │
│   └── modules/              # Independent, pluggable execution engines
│       ├── __init__.py
│       ├── mesh_tagger.py    # Semantic processing & NLM MeSH API interface
│       ├── performance.py    # Historical card analytics tracker & tagger
│       └── report.py         # .md analytical reporter
│
└── run.py                    # Unified entry point / CLI subcommand router
```
## Initialization commands 
Configure env.example, critically the following: 
  ANKI_DB_PATH="/Users/YOUR_NAME/Library/Application Support/Anki2/User 1/collection.anki2"
  JOURNAL_DIR="/Users/YOUR_NAME/Desktop/"
  Others variables are optional and may be adjusted based on user preference

Clone environment
```
cp env.example .env
```
Install dependencies
```
pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
```

---
## Execution commands

For tagging cards based difficulty statistics (Fail rate and speed)
```
python3 run.py tag-stats
```
For MeSH API based tagging
```
python3 run.py tag-mesh
```
For .md daily report
```
python3 run.py export-report
```
### To Do:

- Refactor API
- Embeeding based tagging
