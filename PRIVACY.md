# Privacy Policy — DataMoA

Last updated: 2026-06-16

DataMoA is a local-first desktop application. There is no DataMoA server,
account system, or telemetry endpoint operated by the Licensor. This
policy explains what data the Software touches, where it goes, and what
that means for you, based on how the Software is actually built.

This policy is informational. It is not a substitute for your own legal
or compliance review, and it does not override the LICENSE or
DISCLAIMER files, which take precedence on all liability matters.


## 1. What data this Software handles

When you run DataMoA, it can process:

- documents, files, or URLs you submit (PDF, PNG/JPG/WebP/TIFF/BMP
  images, CSV, XLSX, DOCX, TXT, EML, plain text, or a web page URL to be
  fetched and read) and any personal, financial, or business data
  contained in them;
- text and structured data extracted, scored, reasoned over, enriched,
  or validated by AI models on your behalf;
- API keys and credentials you enter for AI providers and write
  destinations;
- configuration you set (model assignments, confidence thresholds,
  destinations, presets).


## 2. Where your data goes

### 2.1 Stored locally on your machine

By default, all application data is stored in `~/.datamoa/` on the
computer running the Software:

- `config.json` — your model assignments and pipeline settings
- `keys.json` — your API keys, **encrypted at rest** using a key stored
  alongside it in `.keys.key` (see Section 5 below for exactly what this
  does and doesn't protect against)
- `google_tokens.json` — OAuth tokens for Google Sheets, if connected
- `memory/` — patterns learned from your human-in-the-loop corrections
- `audit/` — a local audit trail of processed records
- `queue/` — pipeline state, including submitted record content, kept so
  records can be retried after a restart
- `datamoa.log` — application log: record IDs (truncated), stage
  transitions, timing, and error messages. This is not a dump of your
  document content, but error messages are occasionally verbose enough
  to include a fragment of malformed input (e.g. a snippet from a JSON
  parse failure).

If you use the backup feature, a copy of the above is zipped into
`~/DataMoA Backups/` on your machine. Backups are not uploaded anywhere
by the Software itself.

None of this data is sent to the Licensor. The Licensor does not operate
any server that this Software talks to, and has no access to your data,
your API keys, or your usage.

### 2.2 Sent to third parties you configure

DataMoA is a router: depending on how you configure it, the content you
submit (including the documents/data described in Section 1) can be sent
to:

- **AI model providers** you configure per agent — e.g. Anthropic,
  Google, Groq, Perplexity, DeepSeek, or a local Ollama instance running
  entirely on your own machine. Cloud providers receive whatever content
  is sent to them as part of generating a response (this can include the
  full text/image content of a submitted document).
- **Write destinations** you configure — e.g. a local CSV file, Google
  Sheets, Airtable, your own database (SQLite/PostgreSQL/MySQL), or a
  REST API endpoint you specify. Extracted/resolved record data is sent
  there once a record completes the pipeline.

Each of these third parties has its own privacy policy, terms of
service, and data retention practices, which govern what happens to data
once it reaches them. The Licensor has no control over, and no
responsibility for, how third-party services handle data you choose to
send them. You are responsible for reviewing those third parties'
policies and for choosing providers appropriate for the sensitivity of
your data (see also Section 6, "Privacy First" profile).


## 3. AI model usage

Submitted content can be sent to one or more AI models as part of
extraction, reasoning, validation, enrichment, and write-formatting
steps. If you configure a cloud-hosted model (rather than a local Ollama
model), that provider may process, log, and — depending on their own
policies — retain the content you send, including for purposes such as
abuse monitoring or model improvement, subject to their terms. If you do
not want any data leaving your machine, configure DataMoA to use
local-only models (see the "Privacy First" preset in the README).


## 4. No telemetry, no analytics, no tracking by the Licensor

This Software does not phone home to the Licensor. It does not include
usage analytics, crash reporting, or telemetry sent to the Licensor or
any service operated by the Licensor. Any network activity you observe
is the Software talking directly to the AI providers, write
destinations, or other services you yourself configured.


## 5. Security of stored data

You are responsible for the security of the machine running DataMoA and
the `~/.datamoa/` directory on it. Specifically:

- **API keys are encrypted at rest.** `keys.json` is encrypted with a
  symmetric key (Fernet/AES, via the `cryptography` library) stored in a
  separate file, `.keys.key`, in the same `~/.datamoa/` directory. This
  means someone who gets a copy of `keys.json` alone — for example, a
  stray file from a misconfigured cloud-sync folder, or a partial backup
  — gets an unreadable encrypted blob, not your actual API keys.
- **This is not protection against full access to your machine or
  account.** Because the Software needs to decrypt your keys on launch
  without asking you for a master password every time, the decryption
  key necessarily lives on the same disk, in the same directory, as the
  encrypted file. Anyone with full read access to your user account —
  including a copy of your entire `~/.datamoa/` directory or a complete
  backup — has both pieces and can decrypt your keys. If you need
  protection against that threat model, rely on your operating system's
  full-disk encryption and account security, not on this app-level
  encryption alone.
- Backups created by the Software (in `~/DataMoA Backups/`) include both
  `keys.json` and `.keys.key` together, so a backup can be restored and
  still decrypt correctly. This also means a backup zip carries the same
  risk profile as the live `~/.datamoa/` directory — protect your backup
  folder the same way.
- The Software does not implement OS keychain integration (e.g. macOS
  Keychain, Windows Credential Manager) or a user-supplied master
  password. A stronger guarantee than "encrypted alongside its own key"
  would require one of those to be added to the Software itself.


## 6. Your choices

- Choose local-only models (e.g. via the "Privacy First" preset) to keep
  document content from ever leaving your machine.
- Choose which write destinations are enabled; nothing is written
  anywhere you have not configured.
- Delete `~/.datamoa/` and `~/DataMoA Backups/` at any time to remove all
  locally stored application data. This does not retract data already
  sent to a third-party AI provider or write destination in the past.


## 7. Children's privacy

This Software is not directed at children and is not designed to
process data about children specifically. Do not use it to process data
you are not authorized to process, including data about minors, without
appropriate legal basis.


## 8. Changes to this policy

Because this is a self-hosted, source-available project rather than a
hosted service, this file is updated by editing it in the repository.
Check the file history for changes. Your continued use of the Software
after a change constitutes acceptance of the updated policy, to the
extent permitted by applicable law.


## 9. Relationship to the LICENSE and DISCLAIMER

This Privacy Policy describes data flows; it does not expand the
Licensor's obligations or limit the disclaimers, warranty exclusions, or
liability limitations set out in `LICENSE` and `DISCLAIMER.md`, which
remain controlling.
