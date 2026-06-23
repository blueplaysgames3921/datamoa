# DataMoA

**Multi-agent data entry system.** DataMoA takes a document, image, URL, or raw text, runs it through a configurable pipeline of AI agents that extract, score, reason over, validate, enrich, and write structured records to your destination of choice. Records that the system is confident about go straight through automatically. Records it isn't sure about go to a reasoning agent, and only the ones it still can't resolve get escalated to you for human review.

It runs as a local Electron desktop app with a Python backend. You own your data. Nothing goes anywhere except the AI providers and write destinations you configure yourself.

---

## License and Legal

DataMoA is **free to use**, but it is **source-available, not open source.** You can read and run the code, but you may not copy, redistribute, resell, or rehost it without permission.

All risk and responsibility for using it sits with you. Review any data it produces before relying on it. Secure your own API keys. Cover any third-party API costs you incur.

- [`LICENSE`](./LICENSE) - full legal terms
- [`DISCLAIMER.md`](./DISCLAIMER.md) - plain-language summary
- [`PRIVACY.md`](./PRIVACY.md) - what data this app touches and where it goes

---

## Quick Setup

```bash
# 1. Install all dependencies (npm + pip in one command)
npm run setup

# 2. Pull local models (skip if using cloud-only)
ollama pull gemma3:4b      # minimum - used by most agents in Balanced preset
ollama pull gemma3:12b     # recommended for better accuracy
ollama pull gemma3:27b     # used by High End Local and Privacy First presets
ollama pull llama3.3:70b   # used by High End Local for parsing/reasoning/write

# 3. Start the app (two terminals)
npm run python:dev    # terminal 1 - Python backend on port 7532
npm run dev           # terminal 2 - Electron + Vite frontend
```

On first launch the **Setup wizard** walks you through four steps:

1. Hardware detection - reads your GPU VRAM, system RAM, and CPU
2. Config Agent recommendation - a cloud model (Gemini or Perplexity) analyzes your hardware and recommends the optimal model assignment for every agent
3. API key entry - add whichever provider keys you need
4. Preset selection - pick a starting profile (see Preset Profiles below)

If you skip the Setup wizard or don't have a cloud API key yet, you can select a preset manually and fill in keys later in Settings.

---

## How the Pipeline Works

Every record you submit goes through the same sequence of agents. Each agent does one job and passes the record on. You can disable optional agents in Settings - Pipeline.

```
Input (file / text / URL / API)
        |
   Intake Agent          extracts raw text from any source format
        |
   Parsing Agent         pulls structured fields from the raw text
        |
   Context Agent *       enriches with patterns from your history (optional)
        |
   Confidence Agent      scores the record 0-100% and assigns a tier
        |
        +-- Green (>=85%) --------+
        |                         |
   Amber/Red (<85%)               |
        |                         |
   Reasoning Agent       tries to resolve ambiguity, fill gaps
        |                         |
   HITL (if needed)      escalates to you on the Review page
        |                         |
        +-------------------------+
        |
   Validation Agent      checks rules, required fields, duplicates
        |
   Enrichment Agent *    fills remaining empty fields via web search (optional)
        |
   Write Agent           sends the record to your configured destination
        |
   Audit Agent           writes an immutable per-attempt audit file to disk
        |
   Learning Agent *      extracts patterns from HITL corrections in the background (optional)
```

`*` optional - can be toggled off in Settings - Pipeline without affecting the rest of the pipeline.

### Confidence Tiers

The Confidence Agent scores each record and routes it:

| Tier | Default threshold | What happens |
|---|---|---|
| Green | >= 85% | Skips Reasoning Agent, auto-writes if auto-write is on |
| Amber | >= 60% | Goes to Reasoning Agent for resolution |
| Red | < 60% | Goes to Reasoning Agent, then escalates to HITL if still unresolved |

Both thresholds are configurable sliders in Settings - Pipeline. The visual tier bar in that settings panel updates live as you drag them.

---

## The UI

DataMoA has five pages, accessible from the left sidebar.

### Dashboard

The main view. Drag and drop files here, paste text, or enter a URL. You can submit multiple files at once and they queue immediately. The dashboard shows:

- Live agent status row (which agents are currently active and on which records)
- A flow diagram showing where your most recent record is in the pipeline
- The HITL queue badge - if any records are waiting for your review, a count appears here and you can jump to the Review page from the badge
- A live system health bar (CPU %, RAM %)
- A text input for raw pasted data and a separate URL input field

### Queue

A full searchable, filterable, sortable list of every record in the current session.

- **Filter by stage:** All / Active / Complete / Failed / HITL
- **Sort by:** Created date, last updated, confidence score, stage
- **Search:** Filters records by ID or any field value
- **Per-record actions:** Retry a failed record, cancel an in-progress one
- **Export:** Download current view as CSV or JSON
- **Record detail panel:** Click any record to open a side panel with full field values, confidence breakdown, validation errors, write result, and the full agent timeline. The panel updates live as the record advances through the pipeline while you are looking at it.

### Review (HITL)

The human-in-the-loop queue. Records land here when the Reasoning Agent determines it cannot resolve them confidently enough, or when validation fails and cannot be auto-corrected.

Each record shows the questions the Reasoning Agent flagged, the current parsed field values, and a confidence meter. You type your corrections into the resolution fields, add optional notes, and submit. The record then continues from where it paused - back to validation, then write.

The Review page auto-selects the first waiting record when you arrive. If the queue is empty it tells you so.

### Audit

A searchable log of every completed record, across all attempts. Because DataMoA writes a separate audit file per attempt (`{record_id}_attempt{N}.json`), retrying a record does not overwrite its prior history - every attempt is preserved independently.

Each entry shows the record ID, final confidence score, whether the write succeeded, the completed-at timestamp, and an expandable agent timeline with per-agent duration, model used, input summary, output summary, and any errors. Records that were retried show an "attempt N" label so you can distinguish them in the list.

Batch audit reports (periodic quality analysis across groups of completed records) appear separately below the per-record log.

### Settings

Six tabs:

**API Keys** - Add and remove API keys for every provider. Keys are encrypted at rest on disk (see PRIVACY.md for the exact security model).

**Models** - Assign a specific model to each agent role individually. Shows the currently detected hardware and flags models that may not fit your VRAM. Every agent can use any model from any provider - local Ollama, cloud API, or OpenRouter.

**Pipeline** - Configure:
- Green and Amber confidence thresholds (sliders with a live visual tier preview)
- Max concurrent records (1-20, default 5)
- Retry max attempts and retry delay in seconds
- Per-agent feature toggles: Enrichment Agent, Context Agent, Learning Agent, Batch Audit
- Auto-write on Green toggle (when off, even confident records wait for manual export)

**Destinations** - Add and configure write destinations. The first enabled destination is used. You can add multiple and reorder them. Each destination type has its own required fields:
- CSV: file path
- Google Sheets: spreadsheet ID, sheet name (requires OAuth - connect via this tab)
- Airtable: base ID, table name (requires API key)
- Database: connection string (postgresql://, mysql://, or sqlite:///path), table name
- REST API: endpoint URL, Authorization header, HTTP method

Each destination also has optional field mapping (rename extracted fields before writing) and field exclusion (drop fields you don't want written).

**Backups** - Manual and automatic backup of all app data to `~/DataMoA Backups/`. Configurable interval (default 24 hours), with an option to back up automatically on exit. You can restore any listed backup from this tab, or delete old ones. Backups include config, encrypted keys and their decryption key, Google OAuth tokens, learned memory patterns, audit logs, and queue state.

**Performance** - Runtime optimization controls that take effect immediately without restart:
- Speculative decoding (draft model pre-generates tokens for high-complexity agents)
- Prompt caching (Anthropic and Groq prompt cache headers)
- Context trimming (trims long conversation context to stay within token limits)
- Parallel batch window in milliseconds (batches records that arrive close together before dispatching)
- Shows detected inference profile and warm pool slot status

---

## Model Routing

DataMoA uses [LiteLLM](https://github.com/BerriAI/litellm) as a universal model abstraction layer, so every agent can point at any supported provider without code changes. The registry contains 36 models across 11 providers.

### Default Assignments

These are the defaults used when you choose no preset and run the Setup wizard on typical mid-range hardware. Every row is individually reassignable in Settings - Models.

| Agent | Default model | Role |
|---|---|---|
| Intake | `ollama/gemma3:4b` | Text extraction from any format |
| Parsing | `groq/llama-3.3-70b-versatile` | Structured field extraction |
| Context | `ollama/gemma3:4b` | Historical pattern enrichment |
| Confidence | `ollama/gemma3:4b` | Scoring and tier routing |
| Reasoning | `anthropic/claude-opus-4-6` | Ambiguity resolution |
| Validation | `ollama/gemma3:4b` | Rule checking and duplicate detection |
| Enrichment | `perplexity/sonar` | Web search for missing fields |
| Write | `anthropic/claude-haiku-4-5` | Tool-based destination writing |
| Audit | `deepseek/deepseek-chat` | Per-record audit analysis |
| Learning | `ollama/gemma3:4b` | Pattern extraction from corrections |
| Config Agent | `google/gemini-2.5-flash` | Hardware analysis on setup |
| HITL * | `ollama/gemma3:4b` | Reserved - not yet active in the pipeline |
| Orchestrator * | `google/gemini-2.5-flash` | Reserved - not yet active in the pipeline |

`*` The HITL and Orchestrator model fields are configurable and recommended by the Config Agent, but no current pipeline code path calls a model for either role. HITL question text is produced by the Reasoning Agent or from validation error strings. The Orchestrator is pure coordination with no model calls. Both are configured for forward compatibility.

### Supported Providers

Anthropic, Google, Groq, Perplexity, DeepSeek, OpenAI, Moonshot, StepFun, Liquid, OpenRouter, Ollama (local).

---

## Preset Profiles

Select one during the Setup wizard or switch at any time from Settings - Models - Apply Preset. Applying a preset overwrites all agent assignments and the pipeline confidence thresholds.

| Preset | Target hardware | What it does |
|---|---|---|
| High End Local | 16GB+ VRAM GPU | Every agent runs on local Ollama models (llama3.3:70b for parsing, reasoning, write, enrichment; gemma3:27b for intake, context, audit; gemma3:12b for confidence, validation, learning). Green threshold raised to 90%, amber to 65%. Maximum privacy, highest hardware requirement. |
| Cloud Only | Any (no GPU needed) | All agents use cloud APIs - no local models required. Best output quality. Requires API keys for Anthropic, Google, Groq, Perplexity, and DeepSeek. |
| Balanced | 8GB VRAM GPU | Light agents (intake, context, confidence, validation, learning, HITL) run locally on gemma3:4b. Heavy agents (parsing, reasoning, write) use cloud. Good middle ground between cost and quality. |
| Privacy First | Varies | Every agent uses local Ollama only - nothing leaves your machine. Default reasoning model is gemma3:27b, so you need enough VRAM and RAM for that. You can swap individual agents to smaller models (gemma3:4b or gemma3:12b) in Settings - Models if your hardware is more limited. Confidence thresholds slightly relaxed (green 80%, amber 55%). |
| Budget | Any | Uses Groq free tier (llama-3.3-70b-versatile) for parsing and reasoning, local gemma3:4b for everything else, and gemini-2.0-flash for write and orchestrator. Minimizes paid API usage. Max concurrent records reduced to 3. |

---

## Write Destinations

| Destination | Notes |
|---|---|
| CSV File | Appends rows to a local file. Auto-creates the file and header row on first write. |
| Google Sheets | Appends rows. Auto-creates header row on first write. Requires OAuth setup in Settings - Destinations. |
| Airtable | Creates records in a base/table. Requires an Airtable API key in Settings - API Keys. |
| SQLite | Inserts rows. Auto-creates the table and any missing columns. No extra dependencies. |
| PostgreSQL | Inserts rows. Requires `asyncpg` (see Optional Dependencies). |
| MySQL | Inserts rows. Requires `aiomysql` (see Optional Dependencies). |
| REST API | Sends a POST/PUT/PATCH request with the record as JSON. Supports Authorization header. |

All destinations support optional field mapping (rename fields before writing) and field exclusion (drop fields you don't want written). The first enabled destination is used. You can define multiple destinations and reorder them.

---

## Supported Input Types

**Files:** PDF, PNG, JPG, JPEG, WebP, TIFF, BMP, CSV, XLSX, XLS, DOCX, TXT, EML

**Other:** URLs (the page is fetched and text-extracted), raw pasted text

You can drag and drop multiple files at once onto the Dashboard. They queue immediately and process up to `max_concurrent_records` at a time (default 5, configurable up to 20).

---

## Data Directory

All application data lives in `~/.datamoa/` on the machine running the app. Nothing is sent to the author of this software.

```
~/.datamoa/
├── config.json         model assignments, pipeline settings, destinations
├── keys.json           API keys, encrypted at rest
├── .keys.key           decryption key for keys.json - keep this alongside keys.json
├── google_tokens.json  Google Sheets OAuth tokens
├── memory/             learned patterns from HITL corrections
├── audit/              per-attempt audit files (never overwritten)
├── queue/              pipeline state for every record (survives restarts)
└── datamoa.log         application log (stage transitions, errors, timing)
```

Records in `queue/` are restored automatically on restart, so a crash or force-quit mid-pipeline does not lose in-progress work. Records that have completed, failed, or been cancelled remain in memory for the session for export and retry, but their heavy payload (extracted text, base64 image data) is freed from memory after the oldest 200 terminal records to keep long-running sessions from accumulating unbounded memory usage.

---

## Tech Stack

- **Frontend:** Electron 28 + React 18 + TypeScript + Tailwind CSS
- **Backend:** Python 3.11 + FastAPI + WebSocket
- **Model routing:** LiteLLM (36 models, 11 providers)
- **Local inference:** Ollama
- **At-rest encryption:** cryptography (Fernet/AES-128) for API key storage
- **State:** Local JSON on disk + in-memory async queues

---

## Optional Dependencies

The core app works without these. Install the ones matching the destinations or features you want to use.

```bash
# Google Sheets write support
pip install google-api-python-client google-auth google-auth-oauthlib

# PostgreSQL write support
pip install asyncpg

# MySQL write support
pip install aiomysql

# Faster async SQLite (falls back to sync sqlite3 if not installed)
pip install aiosqlite
```

---

## Troubleshooting

**Setup wizard does not detect my GPU**
DataMoA uses `pynvml` for NVIDIA, `sysctl` for Apple Silicon unified memory, and `rocm-smi` for AMD. Make sure the relevant tool is installed and accessible in your PATH. CPU-only inference still works but will be slow for larger models.

**Backend does not start / port conflict**
The Python backend defaults to port 7532. If that port is in use, change it in the `npm run python:dev` script in `package.json` and match the change in the Electron preload config.

**Records stay in "queued" indefinitely**
Check that the Python backend is running (`npm run python:dev` in a separate terminal) and that the Electron app shows a green connection indicator. If the indicator is red, the WebSocket bridge to the backend is not connected.

**A cloud agent returns errors**
Open Settings - API Keys and verify the key for that provider is present and correct. Check that the model assigned to that agent in Settings - Models is still available from that provider (model availability can change without notice).

**Enrichment Agent does not fill fields**
The Enrichment Agent uses Perplexity Sonar by default, which requires a Perplexity API key. If you are on the Privacy First preset, it uses gemma3:12b locally instead, which does not have web search capability and can only infer from context.

**Queue export produces an empty CSV**
The export respects the active stage filter. If you have "Active" selected as the filter, completed records are excluded. Switch the filter to "All" or "Complete" before exporting.

**Keys lost after restoring a backup**
The `keys.json` file is encrypted. Its decryption key lives in `.keys.key` in the same directory. Both files are included in backups. If you restore `keys.json` from a backup without also restoring `.keys.key` from the same backup, the keys cannot be decrypted. Restore both files together, or re-enter your API keys in Settings - API Keys.

---

## License

Source-available, free to use, no redistribution. See [`LICENSE`](./LICENSE).

Copyright (c) 2026 blueplaysgames3921
