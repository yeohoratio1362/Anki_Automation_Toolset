# Anki Advanced Automation Toolset

A python software toolkit designed to enable greater Anki flashcard tagging, analysis and study. Specially engineered to handle the intense scaling demands of medical undergraduate degrees.

The toolkit contains semantic medical auto-tagging (Based on a MeSH API interface), card log analytics optimization, and automated cross-platform Markdown knowledge.

---

## Architecture

The workspace is organized to eliminate structural duplication:

```
anki-toolkit/
│
├── config.py                 # Centralized configuration manager (.env loader)
├── requirements.txt          # Third-party dependency registry
├── .env.example              # Blueprint template for local environmental setup
├── tag_preferences.json      # Dynamic cache storing user interactive tag choices
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/                 # Shared infrastructure (DRY design engine)
│   │   ├── __init__.py
│   │   ├── database.py       # Transaction handling, safe backups, & lock prevention
│   │   └── parser.py         # Standardized text HTML text & cloze parsing utilities
│   │
│   └── modules/              # Independent, pluggable execution engines
│       ├── __init__.py
│       ├── mesh_tagger.py    # Semantic processing & NLM MeSH API interface
│       ├── performance.py    # Historical card analytics tracker & tagger
│       └── obsidian.py       # Vault syncing pipeline & analytical reporter
│
└── run.py                    # Unified entry point / CLI subcommand router
