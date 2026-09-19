# Phase 0 decisions

Settled 2026-09-19. These are closed. Reopen only with a written reason.

## 1. Encryption scope

TLS in transit, plus application-level encryption at rest.

- Message bodies are encrypted in the application before they reach MySQL, using a
  symmetric key loaded from `ENCRYPTION_KEY` in the environment.
- Questionnaire answers containing free text are treated the same way.
- Photos are stored in private storage (no public bucket, no guessable URL). Served
  through an authorised backend route, never a direct link.
- Not end to end. The server can read messages, which is required because the admin
  dashboard and the email notifications both need plaintext.

Threat model this covers: a stolen database dump or backup. Does not cover: a
compromised running server, since the key is in its environment.

## 2. Email address source

A required field on the questionnaire. The user types it.

- No external lookup, no dependency on any other system.
- A typo means the rejoin link is undeliverable. Mitigation: show the address back to
  the user on the confirmation screen and on the chat page, so the mistake is visible
  while the original link still works in that browser tab.

## 3. Admin scoping

Every admin can see every Station and every Request.

Reasoning: admins work the queue together, so partitioning access would get in the way.
Stations are an organisational grouping, not a permission boundary.

Implementation note: keep `admins.station_id` in the schema as a nullable column meaning
"home station" (used for default filter and for routing, not for access control). This
costs nothing now and leaves room if scoping is ever needed. Access control code must
not read it.

## 4. Questionnaire structure

Fixed fields for now, dynamic-ready storage.

- The intake form is hardcoded: number field, text field, photo upload, plus email.
- Answers are still stored as key/value rows in `questionnaire_answers`, not as columns.
- Adding per-Station configurable fields later means adding a definition table and a
  renderer, with no migration of existing answer data.

## 5. Frontend frameworks

- Widget: plain TypeScript, no framework, mounted into a Shadow DOM so the host page's
  CSS cannot reach it and its own CSS cannot leak out. Built to a single JS file.
- Admin dashboard: React with Vite. Bundle size is not a constraint there.

They are separate codebases. They share nothing except the HTTP and WebSocket contract.
