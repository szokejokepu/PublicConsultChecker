# Public Consultation Monitor

This project is a proof-of-concept for a public consultation monitoring system. It crawls a given Romanian municipal website
and detects public consultation announcements using natural language processing.

A pipeline that scrapes Romanian municipal websites, detects public consultation announcements using NLP, and sends email digest notifications.

**Workflow overview:**

```
Scraper → SQLite DB → NLP Pipeline → Email Notifier
                ↑
         Trainer (fine-tune BERT classifier)
```

---

## Installation

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) (only required for dataset labeling — `trainer/create_dataset.py`)

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment

```bash
cp .env.example .env
# Edit .env with your SMTP credentials (see .env.example for details)
```

Gmail users: generate an **App Password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (requires 2-Step Verification).

---

## Scripts

### Scraper CLI — `main.py`

The main entry point. Scrapes paginated article listings into a local SQLite database and provides query commands.

```
python main.py [--db PATH] <command>
```

Global option:
- `--db PATH` — path to the SQLite database (default: `articles.db`)

#### Commands

| Command | Description |
|---------|-------------|
| `scrape` | Crawl a paginated listing and save articles |
| `list` | List saved articles |
| `show <id>` | Show a single article by ID |
| `search <query>` | Full-text search across articles |
| `delete <id>` | Delete an article by ID |
| `process` | Run the NLP pipeline on unprocessed articles |
| `stats` | Show database statistics |

**`scrape`** — crawl a website:

```bash
# From URL directly
python main.py scrape https://example.com/anunturi

# From a JSON config file (see configs/bm.json for an example)
python main.py scrape --config configs/bm.json

# With options
python main.py scrape https://example.com/anunturi \
    --selector ".article h2 a" \
    --max-pages 5 \
    --workers 8 \
    --quiet
```

**`process`** — run NLP analysis on scraped articles:

```bash
python main.py process
python main.py process --batch-size 64 --no-keyword-filter
```

**Config file format** (JSON5, see `configs/bm.json`):

```json
{
  "url": "https://www.baiamare.ro/ro/Administratie/...",
  "selector": ".comunicate_presa_right h2 a",
  "max_pages": 2,
  "workers": 8
}
```

---

### REST API — `api/`

FastAPI server exposing the scraper and pipeline over HTTP, with a browser frontend.

```bash
uvicorn api.app:app --reload
```

The frontend is served at `http://localhost:8000/`. Interactive API docs are at `http://localhost:8000/docs`.

### React Frontend — `rag-front/`

A React + TypeScript frontend (Vite). Proxies `/api` to the FastAPI backend at `localhost:8000`.

**Prerequisites:** Node.js 18+

```bash
cd rag-front
npm install
npm run dev
```

Opens at `http://localhost:5173/`. Start the API server first.

**Build for production:**

```bash
npm run build   # outputs to rag-front/dist/
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/articles` | List/search/filter articles |
| `GET` | `/api/articles/{id}` | Get a single article |
| `POST` | `/api/articles/{id}/process` | Process a single article |
| `PATCH` | `/api/articles/{id}/star` | Star/unstar an article |
| `DELETE` | `/api/articles/{id}` | Delete an article |
| `GET` | `/api/stats` | Database statistics |
| `POST` | `/api/scrape` | Start a scrape job (async) |
| `GET` | `/api/scrape/{job_id}` | Poll scrape job status |
| `POST` | `/api/process` | Start a pipeline job (async) |
| `GET` | `/api/process/{job_id}` | Poll pipeline job status |

Query parameters for `GET /api/articles`: `limit`, `offset`, `search`, `processed` (`any`/`yes`/`no`), `consultation` (`any`/`yes`/`no`), `min_score`, `starred` (`any`/`yes`/`no`).

---

### Email Notifier — `notifier/sender.py`

Sends an HTML+text digest email listing newly detected public consultation articles.

```bash
# Send a test email to verify your config
python -m notifier.sender --test

# Send to a different address
python -m notifier.sender --test --to someone@example.com
```

Configure via `.env` (see `.env.example`):

| Variable | Description |
|----------|-------------|
| `NOTIFIER_SMTP_HOST` | SMTP server (default: `smtp.gmail.com`) |
| `NOTIFIER_SMTP_PORT` | Port (default: `587`) |
| `NOTIFIER_SMTP_USER` | Login username |
| `NOTIFIER_SMTP_PASSWORD` | App password |
| `NOTIFIER_FROM` | From address (defaults to `NOTIFIER_SMTP_USER`) |
| `NOTIFIER_TO` | Recipient address |

---

### Trainer — `trainer/`

Tools for building and evaluating the BERT consultation classifier.

#### 1. Label articles — `trainer/create_dataset.py`

Uses a local Ollama LLM to automatically label scraped articles as `0` (press release) or `1` (public consultation). Outputs a JSONL file used for fine-tuning.

**Requires Ollama running locally** with a model pulled (e.g. `ollama pull llama3.1:8b`).

```bash
# Label all articles, resume if interrupted
python -m trainer.create_dataset

# First 200 articles with a lighter model
python -m trainer.create_dataset --limit 200 --model phi3:mini

# Re-label from scratch
python -m trainer.create_dataset --no-resume
```

Options: `--db`, `--output`, `--model`, `--limit`, `--max-chars`, `--no-resume`, `--quiet`

#### 2. Review labels — `trainer/review_dataset.py`

Interactive terminal tool to manually confirm or correct Ollama-assigned labels.

```bash
# Review up to 20 unreviewed articles
python -m trainer.review_dataset --limit 20

# Review only low-confidence labels
python -m trainer.review_dataset --confidence low
```

Keybindings: `y`/`Enter` confirm, `n` flip label, `r` toggle full text, `s` skip, `q` save & quit.

#### 3. Fine-tune — `trainer/finetune.py`

Fine-tunes a Romanian BERT model (`dumitrescustefan/bert-base-romanian-cased-v1` by default) for binary classification. Saves the model to `trainer/output/consultation_classifier/`.

```bash
# Basic fine-tune
python -m trainer.finetune

# Only human-reviewed records, 5 epochs
python -m trainer.finetune --only-reviewed --epochs 5

# Custom model, skip low-confidence labels
python -m trainer.finetune \
    --model bert-base-multilingual-cased \
    --min-confidence medium \
    --output-dir models/my_classifier
```

Options: `--input`, `--output-dir`, `--model`, `--epochs`, `--batch-size`, `--lr`, `--max-length`, `--val-ratio`, `--only-reviewed`, `--min-confidence`

#### 4. Compare classifiers — `trainer/compare.py`

Benchmarks four methods against human-reviewed ground truth: keyword filter, cosine similarity (base BERT), Ollama LLM baseline, and the fine-tuned BERT.

```bash
python -m trainer.compare
python -m trainer.compare --model-dir trainer/output/consultation_classifier
python -m trainer.compare --skip-cosine   # faster, skips embedding pass
```

---

## Project Structure

```
.
├── main.py                  # CLI entry point
├── articles.db              # SQLite database (created on first run)
├── configs/                 # Example scraper config files
├── scraper/                 # Web crawler and database layer
├── pipeline/                # NLP pipeline (keyword filter → BERT classifier → NER)
├── api/                     # FastAPI REST API + job queue
├── frontend/                # Static HTML frontend
├── rag-front/               # React + TypeScript frontend (Vite)
├── notifier/                # Email notification module
└── trainer/                 # Dataset creation, labeling, fine-tuning, evaluation
    └── data/labels.jsonl    # Ollama-generated labels (fine-tuning input)
```
