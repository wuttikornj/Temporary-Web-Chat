# Temporary Web Chat

A short-lived consult chat for radiology study requests.

A doctor submits a study request through a questionnaire. The request is sorted
into a station, and a temporary chat thread opens between that doctor and the
radiology resident covering the station. The thread carries the request details
at the top, so both sides are certainly looking at the same case. Threads are
deleted after 7 days.

This repo is built to be pulled into a host application. It owns the chat, not
the form.

---

## Read this first if you are picking the project up

Two documents matter, in this order:

1. **`DECISIONS.md`** is the source of truth for every design decision, numbered,
   with the reasoning attached. It is not a changelog. If something here looks
   odd, the reason is almost certainly in there. Do not reverse a decision
   without reading its section; several were made after a wrong assumption was
   corrected.
2. This README, for what exists, what does not, and where to plug in.

Conventions used throughout, all from `DECISIONS.md`:

- Business logic lives in `services/`, never in routes. Sending a message is
  triggered from HTTP today and from WebSockets and background jobs later, so it
  must exist in exactly one place.
- All timestamps are naive UTC. MySQL `DATETIME` has no timezone. Convert in the
  browser, never in the database.
- Enums are `VARCHAR` plus a Python `StrEnum`, never MySQL's native `ENUM`.
- Nothing carrying patient data is ever logged. Log request IDs and station
  names only.

---

## Status

| Phase | What | State |
|---|---|---|
| 0 | Design decisions settled | done, `DECISIONS.md` |
| 1 | Config, async engine, `/health` | done |
| 2 | Models and migrations | done |
| 3 | Intake API creates a request plus token | done |
| 4 | Messaging over HTTP, both sides | done |
| 5 | WebSockets replacing the poll | **not started** |
| 6 | Storage abstraction and the pink slip photo | **not started** |
| 7 | Read tracking and the unread email | done |
| 8 | 7-day cleanup job | **not started** |
| 9 | Real admin authentication | **not started**, stub in place |
| 10 | Encryption at rest | **not started** |
| 11 | Embeddable widget | demo page only |
| 12 | Admin dashboard | demo page only |
| 13 | Docker, packaging | **not started** |

Rate limiting, file type and size checks, and input validation are not phases.
They are added alongside the endpoint that needs them.

---

## Running it locally

Requires Python 3.12 or newer and MySQL 8.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill it in, see below
```

Create the schema and a user:

```sql
CREATE DATABASE temp_chat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'temp_chat_app'@'%' IDENTIFIED BY '<password>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES
  ON temp_chat.* TO 'temp_chat_app'@'%';
```

`CREATE, ALTER, DROP, INDEX, REFERENCES` are for Alembic. Without them the app
runs but migrations fail.

```bash
cd backend
alembic upgrade head
python -m scripts.seed_demo    # stations plus one demo consult
uvicorn app.main:app --reload
```

The seed prints a doctor's chat link. The resident's view is at `/admin`.

### Tests

```bash
pip install -r requirements-dev.txt
cd backend && pytest
```

52 tests, about a second, no MySQL server and no `.env` required: the suite
runs against in-memory SQLite. That is a deliberate trade. These cover
application behaviour, not MySQL behaviour, so index use, collation and real
cascade semantics are untested and need a separate integration suite.

`models/types.py` defines `BigIntType`, a `BigInteger` with an `Integer`
variant for SQLite, because SQLite only auto-increments a column declared
exactly `INTEGER PRIMARY KEY`. MySQL DDL is unchanged, so no migration.


### Environment

| Variable | Notes |
|---|---|
| `DB_*` | Stored as separate parts; the URL is built in `config.py` with `quote_plus`, so symbols in the password are safe |
| `SECRET_KEY`, `ENCRYPTION_KEY` | No defaults. The app refuses to start without them. `ENCRYPTION_KEY` is unused until Phase 10 |
| `PUBLIC_BASE_URL` | Used to build chat links. Never derived from the `Host` header, which a caller controls |
| `REQUEST_EXPIRY_DAYS` | Default 7 |
| `UNREAD_EMAIL_DELAY_MINUTES` | Default 5 |
| `SMTP_*` | Empty `SMTP_HOST` logs the email instead of sending it, so local dev needs no mail server |
| `STORAGE_*` | Unused until Phase 6 |
| `DEV_AUTH_STUB` | **Must be false anywhere real.** See Integration below |

---

## Integration

### 1. Identity, and the one thing you must not skip

`backend/app/core/identity.py` is the only place this repo learns who someone
is. It ships as a stub that reads `X-Consultee-Email` and `X-Admin-Email`
headers, and only when `DEV_AUTH_STUB=true`. With the flag off, the default,
both dependencies return 500.

That refusal is deliberate. An unimplemented auth dependency that quietly
returns a default identity is more dangerous than one that errors, because
nothing looks broken until a consult link has been emailed to the wrong person.

To integrate, replace two functions:

- `get_current_consultee` returns a `Consultee(email, name)` from the host
  application's SSO session
- `get_current_admin` returns an `Admin(email, name)` for the resident

Nothing else in the codebase needs to change.

**The consultee's email must come from the server-side session, not from the
request body.** There is deliberately no email field in the intake payload. An
email in a body is client-supplied, so anyone able to reach the endpoint could
create a consult naming someone else's address, and this system would then email
that person a link to patient data. See `DECISIONS.md` section 15.

### 2. Intake API

`POST /api/v1/requests` is a public API contract. A caller outside this repo
depends on the field names and rules in `backend/app/schemas/questionnaire.py`.
Changing them is a breaking change.

The caller owns the form, the cascading Modality > Body region > Study dropdowns,
and the station sorting. This repo does not reimplement any of that: the station
arrives as a string in the payload and is looked up strictly.

```json
{
  "station": "Neuro",
  "patient_name": "...", "sex": "male",
  "age_value": 62, "age_unit": "years",
  "hn": "JX1234", "qshc_hn": "QS00881",
  "modality": "CT", "body_region": "Brain, head and neck",
  "study": "CTA Brain",
  "time_period": "today",
  "patient_history": "...",
  "md_name": "...", "staff_name": "...", "tel": "..."
}
```

Returns 201 with `request_id`, `chat_url`, `expires_at`, `station`. Nothing about
the patient is echoed back, so the response is safe for the caller to log.

Rules worth knowing before wiring a form to it:

- `hn` accepts `^[A-Z]{2}[0-9]{4}$` or `^[0-9]{8}$`, is trimmed and uppercased
  before validation, and is **not unique**. One doctor may open several consults
  under the same HN. It identifies a person, not a thread, and it is not an
  access key.
- `specific_date` is required when `time_period` is `specific`, and rejected
  otherwise.
- `age_value` and `age_unit` are stored separately and never normalised to
  years. A 7-day-old and a 7-year-old are different patients.
- An unknown station returns 422 naming the value. Stations are not created on
  demand: a typo must not silently open a folder nobody is watching. Seed them
  to match exactly what your sorter emits.

### 3. Station names

Seeded by `scripts/seed_demo.py`:

```
Neuro, Chest, CVS, Abdomen, MSK, Ultrasound, PED, Manual sort
```

Strings must match the sorting system's output exactly.

---

## How access works

This is the part most likely to be broken by a well-meaning change.

- The **HN is identification, not authentication.** It is guessable, sequential,
  and known to colleagues.
- The **access token** is a 256-bit secret in the chat link, and it is the only
  thing that grants entry. Generated with `secrets`, never `random`.
- A doctor returning later does **not** get shown their thread for typing an HN.
  The system emails the link to the address on file. The inbox is the second
  factor. (Rejoin endpoint is not built yet; see What is missing.)
- A missing token and a dead token both return 404. Distinguishing them would
  confirm to a guesser that a token was real.

### Email

Exactly one email exists in this system: the unread reply notification. No
confirmation email is sent when a request is created, because the doctor goes
straight into the chat from their browser.

If a resident replies and the doctor has not opened the thread within
`UNREAD_EMAIL_DELAY_MINUTES`, the doctor is emailed a link.

**Every email contains a link and nothing else.** No patient name, no HN, no
study type, not in the body and not in the subject. Hospital mail is forwarded,
quoted and archived outside this system's control. This is the rule most likely
to be broken later by someone making the email "more useful".

`messages.notified_at` is separate from `read_at` so the job is idempotent: it
runs every minute, and a message already notified is never picked up again even
if the job runs late, twice, or in two processes. Multiple replies in a row
collapse into one email per thread.

---

## Layout

```
backend/app/
├── config.py          pydantic-settings, one cached Settings instance
├── database.py        async engine, session factory, Base, get_db
├── main.py            app, lifespan, /health
├── core/identity.py   INTEGRATION POINT: who is calling
├── models/            Station, Request, QuestionnaireAnswer, Message
│   └── types.py       UUID stored as BINARY(16)
├── schemas/           Pydantic contracts
├── services/          all business logic
│   ├── request_service.py   create a consult, resolve a station
│   ├── message_service.py   load a thread, send, mark read
│   ├── summary.py           renders the intake summary both sides see
│   ├── code_generator.py    access tokens
│   └── email.py             SMTP
├── jobs/              APScheduler, unread notifier
├── routes/            thin HTTP wrappers only
└── static/            demo pages, replaced by Phases 11 and 12
```

### Endpoints

```
POST /api/v1/requests                       create a consult (SSO identity)
GET  /api/v1/chat/{token}                   doctor opens a thread
POST /api/v1/chat/{token}/messages          doctor writes
GET  /api/v1/admin/requests?station=Neuro   the queue, unread first
GET  /api/v1/admin/requests/{id}            resident opens a thread
POST /api/v1/admin/requests/{id}/messages   resident replies
GET  /health                                checks the database too
GET  /chat/{token}, /admin                  demo pages
```

---

## What is missing, in the order it should be built

1. **WebSockets (Phase 5).** Both demo pages poll every 4 seconds. Fine for
   testing, wrong for production: a hundred idle tabs is 1,500 queries a minute.
   Because messages already go through `message_service.send_message`, adding a
   socket layer does not touch the existing routes.
2. **Pink slip photo (Phase 6).** Required on the form, so a real consult is
   incomplete without it. Needs the storage abstraction: local disk by default,
   S3-compatible behind an env var. Photos go to private storage, never a public
   bucket or a guessable URL.
3. **Cleanup job (Phase 8).** Threads must actually be deleted after 7 days, and
   the order is not negotiable: read the attachment rows, delete the files, then
   delete the request row. Foreign keys cascade to the database rows; they do
   **not** delete files. Deleting rows first makes those bytes permanently
   unreachable garbage. See `DECISIONS.md` section 10.
4. **Rejoin flow.** With no email at submit, a doctor who closes the tab before
   any reply has no link. Their route back in is typing their HN and having the
   link emailed. This is load-bearing, not a convenience, and it needs per-IP
   rate limiting because HNs can be sprayed.
5. **Admin auth (Phase 9).** Currently a header stub.
6. **Encryption at rest (Phase 10).** Message bodies and questionnaire answers.
   Note the consequence: encrypted bodies cannot be searched with SQL `LIKE`, so
   admin text search would need a separate index. Accepted.
7. **Rate limiting** on the intake and rejoin endpoints.
8. **More tests.** 52 exist, covering the HN rules, the intake contract, the
   chat flow and the notifier. Not covered: anything MySQL-specific (index
   use, collation, real cascade behaviour), because the suite runs on SQLite.
9. **Docker and packaging (Phase 13).**

---

## Patient data

The payload carries patient name, HN, sex, age, clinical history, and a photo of
a pink slip bearing an HN sticker. Treat all of it as identifiable medical
information.

- Application-level encryption at rest is a requirement, not a nice-to-have.
- Emails carry a link and nothing else.
- The 7-day delete is a retention policy. It must be reliable and it must remove
  files as well as rows.
- Do not log payload contents. An application log is the easiest place to leak
  this by accident.

See `DECISIONS.md` sections 12 through 15.
