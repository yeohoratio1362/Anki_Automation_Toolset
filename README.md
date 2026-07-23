# Anki Advanced Automation Toolset

A python software toolkit designed to enable greater Anki flashcard tagging, analysis and study. Specially engineered to handle the intense scaling demands of medical undergraduate degrees.

Toolkit contains semantic medical tagging (Based on a local MeSH xml and a local embedding model), card log analytics optimization, and automated pdf reports.

---

## Architecture

Workspace is organized to eliminate structural duplication:

```
anki-toolkit/
│
├── config.py                 # Centralized configuration manager (.env loader)
├── requirements.txt          # Third-party dependency registry
├── env.example               # Blueprint template for local environmental setup
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
│       └── report.py         # .pdf analytical reporter
│
└── run.py                    # Unified entry point / CLI subcommand router
```
## Initialization commands 
Configure env.example, in particular the following: 
- Anki database path (ANKI_DB_PATH)
  - Windows: "\Users\YOUR_NAME\AppData\Roaming\Anki2\User 1\collection.anki2"
  - Mac: "/Users/YOUR_NAME/Library/Application Support/Anki2/User 1/collection.anki2"

Others variables are optional and may be adjusted based on user preference

## Setup Instructions

1. **Configure Environment Variables**:
Copy the example configuration file:

```
cp env.example .env
```
2. Create a virtual environment
```
python3 -m venv venv
```
Activate the virtual environment:
  On macOS / Linux:
```
source venv/bin/activate
```
  On Windows (Command Prompt):
```
venv\Scripts\activate.bat
```
  On Windows (PowerShell):
```
.\venv\Scripts\Activate.ps1
```
3. Install dependencies

```
python3 -m pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
ollama pull nomic-embed-text
```
4. Obtain MeSH data as XML, drag and drop into the -main folder


## Execution commands

For tagging cards based difficulty statistics (Fail rate and speed)
```
python3 run.py tag-stats
```
For MeSH embedding based tagging
```
python3 run.py tag-mesh
```
For .pdf daily report
```
python3 run.py export-report
```

