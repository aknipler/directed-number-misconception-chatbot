# Directed Number Misconception Chatbot

A Streamlit research application in which an AI plays **Tegan**, a fictional 14-year-old
student holding a specific, consistent misconception about directed-number arithmetic.
Participants (typically pre-service or in-service teachers) log in with a study identifier
and attempt to teach Tegan out of the misconception. Every conversation is transcribed to
MongoDB for later analysis.

Adapted from the earlier decimal misconceptions chatbot; the prompt, the conversation type
recorded in the database, and the login/transcript logging were reworked for this study.

## The misconception

Tegan overgeneralises sign rules. Characteristic responses, held consistently:

| Question   | Tegan answers |
| ---------- | ------------- |
| `-1 + -3`  | 4             |
| `1 - -3`   | 4             |
| `-1 - 3`   | 4             |
| `-1 - -3`  | genuine confusion, not a confident rule |

Tegan does **not** abandon the misconception merely because the teacher says an answer is
wrong, supplies the right answer, or explains a different sign rule. She switches to correct
reasoning only once the teacher explicitly communicates that *subtracting a negative is
equivalent to addition*. This gating is the experimental manipulation — edit
[prompts/prompt.txt](prompts/prompt.txt) with care.

## Setup

1. **Install dependencies**

   With uv (the project pins Python 3.13 in `.python-version` — Streamlit Community Cloud
   does not yet support 3.14):

   ```bash
   uv sync
   ```

   Or with pip:

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure secrets**

   Copy the template and fill in real values. `.streamlit/secrets.toml` is gitignored and
   must never be committed:

   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

   | Key | Purpose |
   | --- | --- |
   | `ANTHROPIC_API_KEY` | Anthropic API key used to generate Tegan's replies |
   | `MONGODB_CONNECTION_STRING` | MongoDB Atlas connection string |
   | `MONGODB_DATABASE_NAME` | Database holding the three collections below |

   All configuration is read from `secrets.toml` — there is no `.env` file. Standalone
   scripts read it through [utils/config.py](utils/config.py).

3. **Load participant identifiers** (once per cohort)

   ```bash
   python scripts/generate_and_load_identifiers.py
   ```

   The script prompts for a CSV of participant data and an identifier prefix, writes a
   local `*_with_identifiers.csv` mapping file, and uploads **only** the generated
   identifiers to MongoDB — no personal data leaves the machine. The mapping CSV is
   gitignored; keep it wherever your ethics approval requires.

4. **Run the app**

   ```bash
   streamlit run app.py
   ```

## Usage

1. **Log in** with an identifier that exists in the `valid_identifiers` collection.
2. **Teach Tegan.** Ask her directed-number questions and respond to her answers. The
   session is capped at 50 assistant responses.
3. **Log out** when finished. This marks the transcript `completed: true`.

The transcript is saved after every turn, not only at logout, because Streamlit has no
disconnect hook — a participant who closes the tab still leaves a complete record. Each
save rewrites the full message list, so a failed save is repaired by the next successful
one. Save failures surface as a non-blocking warning and never interrupt the chat.

## Data model

Three collections in `MONGODB_DATABASE_NAME`:

| Collection | Written by | Contents |
| ---------- | ---------- | -------- |
| `valid_identifiers` | `scripts/generate_and_load_identifiers.py` | `identifier`, `created_at` |
| `login_events` | every login attempt | `timestamp`, `identifier`, `outcome`, `session_id`, `conversation_type` |
| `transcripts` | login and every turn | `session_id`, `identifier`, `conversation_type`, `messages`, `message_count`, `completed`, `timestamp`, `updated_at` |

`conversation_type` is `"directed_number_misconception_chatbot"` throughout, so this study's
data is separable from the decimal study if both share a database.

Login outcomes are recorded as `success`, `too_short`, `not_found`, or `db_error`. The
`db_error` case is deliberately distinct from `not_found`: an unreachable cluster used to
tell participants "invalid identifier", which could silently lock out a whole cohort.
Transcripts are keyed on `session_id`, so records written before session IDs existed can
never be matched or overwritten.

## Layout

```
app.py                                    Login page, chat page, session state
prompts/prompt.txt                        Tegan's system prompt (the manipulation)
utils/mongodb.py                          Identifier validation, transcript + login writes
utils/config.py                           Single source of configuration (secrets.toml)
scripts/generate_and_load_identifiers.py  Generate identifiers and upload them
scripts/load_identifiers.py               Legacy loader — superseded, see Known issues
.streamlit/secrets.toml.example           Template for secrets.toml
```

## Known issues

- **`scripts/load_identifiers.py` does not run.** It imports `python-dotenv`, which is not a
  project dependency, reads `os.getenv` rather than `secrets.toml`, and assigns
  `db = database_name` before calling `db.valid_identifiers` on that string. Superseded by
  `generate_and_load_identifiers.py`; delete it or repair it. It also still carries the
  inverted `("yes" or "y")` database-name confirmation — that expression evaluates to
  `"yes"`, so answering *yes* exits and anything else proceeds to a possible
  `delete_many({})` on the wrong database. Fixed in the script that replaced it.
- **`pandas` is a script-only dependency** and is declared in `pyproject.toml` but not
  `requirements.txt`, which keeps the Streamlit Cloud deployment lean. Install via `uv sync`
  before running anything in `scripts/`.
