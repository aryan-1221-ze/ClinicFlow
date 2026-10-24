# ClinicFlow architecture

## Request flow

1. A request reaches `routes.py` (single blueprint). `services/security.py` first checks the CSRF token on any non-GET request and adds security headers to every response.
2. The route validates input (`models/appointments.validate`, `services/csv_import.parse_csv`, `_json_field`) and calls a model function. Models contain the SQL and always use `?` placeholders.
3. State changes write an entry through `models/activity.log` with IDs and counts only, never free text.
4. The route renders a Jinja template (auto-escaped) or returns JSON for the AI endpoints. `static/js/assistant.js` builds the result with `textContent`, never `innerHTML`.

## Folder map

| Path | Role |
|---|---|
| `app.py` | Application factory, error handlers, CLI command |
| `config.py` | Environment-driven settings |
| `routes.py` | All endpoints |
| `database/` | `schema.sql`, connection helpers |
| `models/` | Data access and validation per table, plus `seed.py` |
| `services/csv_import.py` | Pure parser/validator returning an `ImportReport`; inserting is a separate step |
| `services/ai_service.py` | Prompts, LLM transport, redaction, deterministic fallbacks |
| `services/security.py` | CSRF and headers |
| `templates/`, `static/` | UI |
| `tests/` | pytest suite |

## Decisions you should be able to explain

1. **Flask + SQLite + vanilla JS**: fewest moving parts; every layer can be read in one sitting.
2. **App factory** (`create_app`): lets tests build an isolated app with a temporary database.
3. **Stats are `COUNT(*) GROUP BY status` queries**, so the dashboard cannot drift from the records.
4. **Cancel keeps the record; delete removes it.** Both use a server-rendered confirmation page, so confirmation works without JavaScript and a GET never changes data.
5. **CSV parsing is a pure function** (bytes in, report out) so it is easy to test; the database insert is separate. Rows are skipped, not repaired, so supplied values are never altered.
6. **Duplicate rule** = lower-cased, whitespace-collapsed `name|practice`, enforced twice: in the parser and by a UNIQUE index (which also catches races).
7. **No login.** A fake login would be worse than none. The README says the app must stay on localhost until real authentication is added.
8. **AI safety is layered, and mostly outside the model**: clinical keywords short-circuit before any call; contact details are tokenised before sending and restored locally; the patient name and notes never leave the server; model output is validated (JSON shape, category whitelist, length) and anything unusable falls back to a labelled template. Prompts treat user text as data inside tags to reduce prompt-injection risk.
9. **Source labelling**: every AI result carries `source` = `llm` or `fallback`, shown as a badge, so fallback text is never presented as model output.
10. **Strict CSP** forces all JavaScript and CSS into external files, which also keeps the code reviewable.
11. **LLM transport uses `urllib`** to avoid an SDK dependency; the trade-off is hand-written request/response handling for two providers.

## Testing summary

Automated (`python -m pytest -q`): routes, CSRF, appointment CRUD and validation, status changes, dashboard counts, CSV valid/invalid/duplicate/oversize cases, search and filters, AI fallback, mocked live-AI success and failure paths, redaction, clinical short-circuit, activity-log privacy.

**Manual checks still to do (not automated):** look at every page at desktop, tablet and phone widths; tab through the forms with the keyboard; try the copy button in your browser; run one real AI request with your own key and record the outcome; try your real CSV when you receive it.
