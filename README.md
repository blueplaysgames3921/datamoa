# DataMoA — Multi-Agent Data Entry System

A professional-grade, hybrid local/cloud multi-agent orchestration system that handles data entry end-to-end — from trivial structured records to ambiguous, hard-to-interpret inputs that previously required human operators.

---

## License & Legal

DataMoA is **free to use**, but it is **source-available, not open
source** — you can read and run the code, but you may not copy,
redistribute, resell, or rehost it without permission. The source is
published for transparency and so you can verify what it does, not as
an invitation to fork or repackage it.

It is also provided **with no warranty**, and **all risk and
responsibility for using it sits with you**, the user — including
reviewing any data it produces before relying on it, securing your own
API keys, and covering any third-party API costs you incur.

Read before using:
- [`LICENSE`](./LICENSE) — full legal terms (copying restrictions, no
  warranty, limitation of liability, indemnification)
- [`DISCLAIMER.md`](./DISCLAIMER.md) — plain-language summary of the above
- [`PRIVACY.md`](./PRIVACY.md) — what data this app touches, where it
  goes (your configured AI providers and write destinations — not the
  Licensor), and how it's stored on your machine

---

## Quick Setup

```bash
# 1. Install dependencies
npm run setup

# 2. Pull a local model (optional — for local inference)
ollama pull gemma3:4b

# 3. Launch
npm run dev          # Start Electron + Vite in dev mode
npm run python:dev   # Start Python backend in a separate terminal
```

On first launch, the **Setup wizard** will:
1. Detect your hardware (GPU VRAM, RAM, CPU)
2. Run the Config Agent to recommend optimal models
3. Walk you through adding API keys
4. Apply the best configuration for your setup

---

## Architecture

```
Input (file / text / URL / API)
        ↓
   Intake Agent          — text extraction (PDF, image, CSV, DOCX, XLSX, email)
        ↓
   Parsing Agent         — structured field extraction
        ↓
   Context Agent         — historical memory enrichment
        ↓
   Confidence Agent      — scores record, routes by tier:
        ↓
  ┌─────┴──────┐
Green         Amber/Red
  ↓              ↓
  │         Reasoning Agent  — resolves ambiguity
  │              ↓
  │         HITL (if needed) — human review
  │              ↓
  └─────┬──────┘
        ↓
   Validation Agent      — rule checking, duplicate detection
        ↓
   Enrichment Agent      — fills missing fields via web search
        ↓
   Write Agent           — writes to destination (CSV/Sheets/Airtable/DB/API)
        ↓
   Audit Agent           — immutable audit trail
        ↓
   Learning Agent        — extracts patterns from corrections (batch)
```

---

## Confidence Tiers

| Tier | Default Score | Action |
|---|---|---|
| 🟢 **Green** | ≥ 85% | Auto-write, no review |
| 🟡 **Amber** | ≥ 60% | Reasoning Agent resolves |
| 🔴 **Red** | < 60% | Human review (HITL) |

Thresholds are configurable in **Settings → Pipeline**.

---

## Model Routing

DataMoA uses [LiteLLM](https://github.com/BerriAI/litellm) as a universal model router. Every agent can use any supported model. The **Config Agent** (Gemini or Perplexity) analyzes your hardware on first launch and recommends the optimal configuration.

### Default Assignments

| Agent | Default Model | Why |
|---|---|---|
| Intake | `ollama/gemma3:4b` | Fast, local, privacy |
| Parsing | `groq/llama-3.3-70b-versatile` | Strong extraction, fast |
| Context | `ollama/gemma3:4b` | Local, low latency |
| Confidence | `ollama/gemma3:4b` | Local, fast routing |
| **Reasoning** | `anthropic/claude-opus-4-6` | Most capable model |
| Validation | `ollama/gemma3:4b` | Rule-based, local |
| Enrichment | `perplexity/sonar` | Web search capability |
| HITL † | `ollama/gemma3:4b` | Reserved — not yet called by the pipeline |
| **Write** | `anthropic/claude-haiku-4-5` | Reliable tool use |
| Audit | `deepseek/deepseek-chat` | Analytical, cheap |
| Learning | `ollama/gemma3:4b` | Pattern extraction |
| Orchestrator † | `google/gemini-2.5-flash` | Reserved — not yet called by the pipeline |
| Config Agent | `google/gemini-2.5-flash` | Hardware analysis |

† The Config Agent recommends a model for these roles and they're
assignable in Settings → Models, but no current pipeline code path
actually calls a model for them: HITL question text comes from the
Reasoning Agent or hardcoded validation-failure strings, and the
Orchestrator is, by design, pure coordination with no model calls
of its own (see its docstring in `orchestrator_service.py`). They're
configured for forward compatibility, not active yet.

All assignments are configurable per-agent in **Settings → Models**.

---

## Write Destinations

| Destination | Status | Notes |
|---|---|---|
| CSV File | ✅ Full | Local file append |
| Airtable | ✅ Full | Requires API key |
| REST API | ✅ Full | POST/PUT/PATCH with auth |
| SQLite | ✅ Full | Auto-creates tables/columns |
| PostgreSQL | ✅ Full | Requires `asyncpg` |
| MySQL | ✅ Full | Requires `aiomysql` |
| Google Sheets | ✅ Full | Requires OAuth setup |

---

## Supported Input Types

**Files:** PDF, PNG, JPG, JPEG, WebP, TIFF, BMP, CSV, XLSX, XLS, DOCX, TXT, EML, plain text
**Other:** URLs / web pages (fetched and text-extracted directly), raw pasted text

---

## Configuration

All data stored in `~/.datamoa/`:

```
~/.datamoa/
├── config.json       — model assignments, pipeline settings
├── keys.json         — API keys (encrypted at rest — see PRIVACY.md)
├── .keys.key         — decryption key for keys.json (keep with it)
├── google_tokens.json — Google OAuth tokens
├── memory/           — learned patterns from HITL corrections
├── audit/            — immutable audit logs + batch reports
├── queue/            — pipeline state (survives restarts)
└── datamoa.log       — application log
```

---

## Preset Profiles

| Profile | GPU | Description |
|---|---|---|
| High End Local | 16GB+ | Everything runs locally |
| Cloud Only | Any | All cloud APIs, best quality |
| Balanced | 8GB | Hybrid — light tasks local |
| Privacy First | Varies | Nothing leaves the machine — uses local models for every agent, but its default reasoning model is 27B params, so budget well above the bare minimum to run *something* locally; swap in smaller models per-agent in Settings → Models if your hardware is limited |
| Budget | Any | Minimizes API costs |

---

## Tech Stack

- **Frontend**: Electron 28 + React 18 + TypeScript + Tailwind CSS
- **Backend**: Python 3.11 + FastAPI + WebSocket
- **Model routing**: LiteLLM (25+ models supported out of box)
- **Local models**: Ollama
- **State**: Local JSON + in-memory async queues

---

## Optional Dependencies

```bash
# Google Sheets write support
pip install google-api-python-client google-auth google-auth-oauthlib

# PostgreSQL write support  
pip install asyncpg

# MySQL write support
pip install aiomysql

# SQLite async (faster)
pip install aiosqlite
```
