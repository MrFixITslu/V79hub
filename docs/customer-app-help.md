# Customer app help — development contract

Status: development only; no merge or deployment authorised.

## Scope and choice

All authenticated customers, including viewer accounts, can ask how to use Hub,
Tiquet, POS, FFPRO, Marketing, Academy and CombatZone. Help explains procedures;
it cannot read business records, execute actions, open products with extra access,
send messages, take payments or change permissions. The existing Owner Assistant
remains separate.

Compared fixed FAQs, local retrieval with optional local AI ranking, and cloud RAG.
Choose local retrieval with bounded Ollama ranking. Only reviewed source text can
be returned; the model may select an article ID, never supply customer-visible prose.
If the model fails, return useful manual guidance without claiming an AI answer.
No new database, embeddings service, cloud spend, credentials or runtime dependency.

## Design contract

Compared floating drawer (quick but cramped), dedicated Help page (readable and
discoverable) and command palette (fast but weak for follow-ups). Choose the Help
page. Extend existing V79 typography, light/dark tokens and sidebar/mobile More
navigation. Read mode: quiet surfaces, clear hierarchy, comfortable prose measure.
Desktop pairs the conversation with topic browsing; mobile stacks the same controls.
Sources expand inline, preserving keyboard focus. State changes use no decoration.
Include empty, loading, error, retry, expired session, copied and reset states.
Chats live only in page memory and clear on logout/account change; no browser storage.

## Source review and red team

Source: Google Docs manual v2, last modified 2026-11-05T23:47:40.058Z,
document `1sEBmkgHc4l4MOJ1_alKhGmtrwwsWqQEdfqOJWCVCoNQ`.
Use an explicitly reviewed, versioned customer derivative. Never expose that private
document or its screenshots to customers. Exclude §§1.6–1.9 (owner workforce,
skills, platform administration), §5.11 (owner workforce handoff) and observed owner
records. Rewrite security/billing snapshot details as general customer guidance.
Do not describe a documentation-day issue as current service status. Preserve
unverified walkthrough limits, payment/publishing evidence and currency cautions.
Google edits do not publish automatically: review, version and test the derivative.

Threats: untrusted prompt/history or model output; cross-customer record access;
SSRF/cloud fallback; resource exhaustion; stale or invented workflow. Controls:
allowlisted manual-only responses, strict input schemas and limits, no tools or
private data sources, active Hub session/membership checks, same-origin POST,
bounded per-identity and global inference limits, private configured model host,
timeout/circuit breaker, no redirects, no user-supplied URL/model, no chat logging.

## API contract

`GET /api/help/catalog`: reviewed metadata and topic index.
`GET /api/help/articles/:id`: reviewed customer article, local source reference.
`POST /api/help/chat`: `{message, app?, articleId?, history?}`. History is a bounded
array of user questions only; it never supplies role/system instructions or authority.
Response includes status (`answered`, `clarify`, `not_documented`, `restricted`),
plain-text answer, reviewed article(s), related question buttons, source version and
engine (`manual` or `local-ai`). Browser fields never identify the authenticated user.

## Acceptance / Definition of Done

- A current session can use help regardless of paid app assignment; guidance grants
  no app access. No session/revoked membership gets no help API access.
- Realistic questions across all seven apps return relevant reviewed steps and
  source section; ambiguous requests clarify; greetings and unsupported questions
  are useful; follow-ups retain the selected app without mixing accounts.
- Prompt injection and hostile AI output cannot disclose owner content or execute.
- Source links open reviewed content inside help, never the private owner manual.
- AI timeout, malformed output, oversized body and concurrency/rate limits tested.
- UI keyboard, mobile/tablet/desktop, light/dark and session-expiry checks recorded.
- Appropriate focused tests, TypeScript and production asset build pass.
- Development changes committed on an isolated branch; deployment remains unrun.

## Configuration and operations

Optional `V79_HELP_OLLAMA_URL` points only to a trusted private Ollama service;
`V79_HELP_OLLAMA_MODEL` selects an already installed local model. No model pull or
cloud fallback is performed. Without configuration, help uses the reviewed guide.
Inference only ranks retrieved article IDs; all returned wording comes from the
reviewed customer guide. Configure/review capacity before any future release.
Use Node 22+; `npm ci`, `npm run lint`, `npm run build`, and focused help tests.
No production data/migration or deployment configuration changes are required.

## Validation evidence — 5 November 2026

| Check | Observed result |
|---|---|
| Customer source review | 49 topics across seven apps. Owner-only sections, screenshots, workspace records and private manual links excluded from runtime help. |
| Focused service/router/UI/full-Hub suite | 51 tests passed after the final fixes. Includes 30 realistic task questions, every browsed article, ambiguous/missing answers, follow-ups, prompt injection, model failure/timeout, origin checks and rate/concurrency limits. |
| Navigation | Existing seven navigation regressions passed; new help refresh/role boundary regression passed. |
| Real isolated Hub | Viewer accounts without app assignments can read help; anonymous, revoked and suspended callers denied. Owner/admin endpoints remain forbidden. Real synthetic login/logout checked. |
| Local visual review | Desktop 1363px; viewport frames at 320, 390, 768 and 1024px. No horizontal document overflow at measured frame widths. Light/dark appearance, question, Enter-to-send follow-up, source expansion and copied state inspected. Desktop composer remained visible. |
| Expiry/errors | Chat errors/retry, initial-catalog expiry and later chat expiry exercised in React DOM tests. Expiry browser screenshot not captured. |
| Independent review | Three functional findings fixed: new-task/follow-up confusion, unsupported operation relevance and initial expiry recovery. Reviewer reran three targeted regressions and marked all three resolved; development-review disposition ship. |
| TypeScript / assets | `npm run lint` and `npm run build` passed. Existing large main-bundle advisory remains (about 777 kB uncompressed); this is not a performance certification. No new dependency added. |
| Optional Ollama | Protocol, candidate-only output, timeout, bad output and concurrency verified with isolated responses. Real model inference not run: Acer’s installed model is 5.2 GB, above its roughly 3.7 GB available RAM; server localhost:11434 was unavailable. No model download, cloud use or production configuration change. |
| Deployment | Not run. No merge, service switch, production data write or customer invitation. |

Review screenshots under `docs/review/customer-help/` use a synthetic viewer and
workspace. Phone/tablet captures are viewport frames, not physical devices. The
test-only proxy permits its own same-origin frames; production anti-framing
headers are unchanged. Browser, physical-device, screen-reader, field performance
and real-provider claims are limited to the evidence above.

The development source was based on the exact deployed source tree
`0f8e7ff3cc5a1560400004cf0eddffc38156c638`, read without changing production.
Its local review snapshot is `10f734cc7b1761136ab07934cdd76b8419f9b19c`.
Any future release must reconcile this feature against the then-current live
revision and exercise the chosen local model connection before enabling it.
