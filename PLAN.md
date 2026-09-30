# Relay: Implementation Plan

Relay is a self-hostable LLM gateway built with Python and FastAPI. It sits between client apps (anything that speaks the OpenAI API) and LLM providers (OpenRouter, Anthropic, OpenAI, local llama.cpp). It issues per-user API keys, enforces rate limits and budgets, streams responses, and records the usage and cost of every request.

Goal: a public, portfolio-grade repo that shows async Python, auth, a relational database with migrations, caching/rate limiting, real integration tests, Docker, and CI.

---

## 1. Scope

### In scope (v0.1, MVP)

1. **Accounts and auth**
   - Email + password signup/login (argon2 hashing).
   - JWT access token (short-lived) + refresh token (rotated, stored hashed, revocable).
   - Users create, list, and revoke API keys. Keys are shown once and stored hashed (prefix kept for lookup, e.g. `rly_ab12…`).
2. **OpenAI-compatible proxy**
   - `POST /v1/chat/completions`, authenticated with `Authorization: Bearer <api key>`.
   - Non-streaming and streaming (`stream: true`, Server-Sent Events passthrough).
   - `GET /v1/models`: models allowed by config.
   - Provider selected by a model-name prefix/mapping in config (e.g. `anthropic/…`, `openrouter/…`, `local/…`).
3. **Usage ledger**
   - One row per request: user, key, model, provider, prompt/completion tokens, cost, latency, status, request id.
   - `GET /v1/usage`, filterable by date range, key, and model, with daily aggregates.
4. **Rate limiting**
   - Per-key requests-per-minute in Redis (sliding window).
   - `429 Too Many Requests` with `Retry-After` and `X-RateLimit-*` headers.
5. **Budgets**
   - Optional monthly spend cap per key, checked before forwarding (`402` or `429` when exceeded).
6. **Operability**
   - `/healthz` (liveness) and `/readyz` (DB + Redis reachable).
   - Structured JSON logs with a request id propagated in the `X-Request-ID` header.
   - Consistent error format (RFC 7807-style problem JSON).

### Out of scope for v0.1 (stretch, v0.2+)

- Provider fallback and routing rules (retry on another provider on 5xx/timeouts).
- Response caching for identical non-streaming requests.
- Small admin/usage dashboard (vanilla JS, served as static files).
- Prometheus `/metrics` and an OpenTelemetry tracing example.
- Organizations/teams with shared budgets.
- OAuth login (Google/GitHub).

### Non-goals

- Not a full model-hosting platform; Relay only proxies.
- No billing or payments.

---

## 2. Tech stack

| Concern               | Choice                                                             | Why                                          |
| --------------------- | ------------------------------------------------------------------ | -------------------------------------------- |
| Language              | Python 3.12                                                        | Current, typed                               |
| Package/env manager   | uv                                                                 | Fast, lockfile, already used in EPUB_Catalog |
| Web framework         | FastAPI + Uvicorn                                                  | Async, OpenAPI docs for free                 |
| Validation/config     | Pydantic v2, pydantic-settings                                     | Typed request models and env config          |
| Database              | PostgreSQL 16                                                      | Industry standard                            |
| ORM / driver          | SQLAlchemy 2.0 (async) + asyncpg                                   | Modern async ORM                             |
| Migrations            | Alembic                                                            | Versioned schema changes                     |
| Cache / rate limiting | Redis 7 (redis-py asyncio)                                         | Atomic counters, TTLs                        |
| HTTP client           | httpx (async, streaming)                                           | Upstream provider calls                      |
| Auth                  | PyJWT, argon2-cffi                                                 | Tokens and password hashing                  |
| Logging               | structlog                                                          | JSON logs with context                       |
| Testing               | pytest, pytest-asyncio, httpx `AsyncClient`, respx, testcontainers | Unit + real Postgres/Redis integration tests |
| Quality               | ruff (lint + format), mypy (strict), pre-commit                    | Consistent, typed code                       |
| Containers            | Docker (multi-stage), Docker Compose                               | One-command local start                      |
| CI                    | GitHub Actions                                                     | Lint, types, tests, coverage, image build    |

### Infrastructure

- **Local development:** Docker Compose with `api`, `postgres`, and `redis`. Everything runs offline except calls to real providers (tests mock them).
- **Hosted demo (free tiers):**
  - API on **Fly.io** or **Render** (long-lived process, so streaming works).
  - Postgres on **Supabase** or **Neon** (Supabase free tier pauses after about a week idle).
  - Redis on **Upstash**.
- **Not Vercel:** serverless functions have time limits and short lifetimes, which conflicts with long streaming responses and Redis connections.

---

## 3. Architecture

```
client app ──HTTP/SSE──▶ FastAPI (Relay)
                          │  auth: API key → user/key (DB, cached in Redis)
                          │  rate limit + budget check (Redis / DB)
                          │  provider adapter (httpx, streaming)
                          ▼
             OpenRouter / Anthropic / OpenAI / llama.cpp
                          │
                          ▼
             usage ledger write (Postgres, after response completes)
```

### Proposed layout

```
Relay/
├── PLAN.md
├── README.md
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── alembic.ini
├── migrations/
├── src/relay/
│   ├── main.py            # app factory, middleware, routers
│   ├── config.py          # pydantic-settings
│   ├── db.py              # async engine/session
│   ├── redis.py
│   ├── logging.py
│   ├── errors.py          # problem+json handlers
│   ├── models/            # SQLAlchemy models: User, ApiKey, RefreshToken, UsageRecord
│   ├── schemas/           # Pydantic request/response models
│   ├── auth/              # hashing, JWT, dependencies
│   ├── routers/           # auth.py, keys.py, proxy.py, usage.py, health.py
│   ├── providers/         # base.py, openrouter.py, anthropic.py, openai.py, local.py
│   └── services/          # rate_limit.py, budget.py, pricing.py, usage.py
└── tests/
    ├── conftest.py        # testcontainers fixtures, app client
    ├── unit/
    └── integration/
```

### Data model (initial)

- `users`: id, email (unique), password_hash, created_at, is_active
- `api_keys`: id, user_id, name, prefix, key_hash, monthly_budget_usd, rpm_limit, created_at, revoked_at, last_used_at
- `refresh_tokens`: id, user_id, token_hash, expires_at, revoked_at
- `usage_records`: id, request_id, user_id, api_key_id, provider, model, prompt_tokens, completion_tokens, cost_usd, latency_ms, status_code, created_at (indexed by key + created_at)

---

## 4. Implementation steps

Estimated total: about 45 to 60 hours (rough estimate).

### Phase 0: Project skeleton (about 4 h)

1. `uv init`, set Python 3.12, add dependencies and dev dependencies.
2. Configure ruff, mypy (strict), pre-commit.
3. App factory with `/healthz`, settings from env, `.env.example`.
4. Dockerfile (multi-stage, non-root user) and `docker-compose.yml` with Postgres + Redis.
5. First GitHub Actions workflow: ruff, mypy, pytest.
6. Create the public GitHub repo, push, confirm CI is green.

### Phase 1: Database and migrations (about 4 h)

7. Async SQLAlchemy engine/session dependency.
8. Models for users, api_keys, refresh_tokens, usage_records.
9. Alembic setup with async env; generate and apply the initial migration.
10. testcontainers fixtures: Postgres + Redis per test session, migrations applied, transaction rollback per test.
11. `/readyz` checking DB and Redis.

### Phase 2: Auth and API keys (about 8 h)

12. Password hashing (argon2) and signup/login endpoints.
13. JWT access tokens + rotating refresh tokens, logout/revoke.
14. `current_user` dependency (JWT) for management endpoints.
15. API key create/list/revoke endpoints; key shown once, stored hashed.
16. `api_key_principal` dependency (Bearer API key) with a short Redis cache.
17. Tests: happy paths, bad credentials, expired/revoked tokens and keys.

### Phase 3: Proxy endpoint (about 8 h)

18. Provider adapter interface (`complete`, `stream`) and a model → provider mapping in config.
19. First adapter: OpenRouter (OpenAI-compatible, simplest). Then local llama.cpp.
20. `POST /v1/chat/completions` non-streaming path.
21. Streaming path: `StreamingResponse` relaying SSE chunks, handling client disconnects and upstream errors.
22. `GET /v1/models`.
23. Anthropic adapter (translate the OpenAI request/response shape).
24. Tests with respx mocking upstream, including streaming and upstream 4xx/5xx/timeouts.

### Phase 4: Usage ledger (about 5 h)

25. Pricing table (per-model input/output cost) in config.
26. Capture token counts from the upstream response (or final stream chunk) and write a `usage_records` row after the response ends (background task).
27. `GET /v1/usage` with filters and daily aggregates.
28. Tests for cost calculation and aggregation queries.

### Phase 5: Rate limits and budgets (about 6 h)

29. Redis sliding-window limiter (Lua script or sorted sets) per API key.
30. Middleware/dependency returning 429 + `Retry-After` + `X-RateLimit-*` headers.
31. Monthly spend check against the ledger (cached in Redis, invalidated on write).
32. Tests, including concurrency (many parallel requests against one key).

### Phase 6: Operability and hardening (about 4 h)

33. structlog JSON logging, request-id middleware.
34. Problem+json error handlers for validation, auth, upstream, and rate-limit errors.
35. CORS config, request size limits, timeouts on upstream calls.
36. Coverage report in CI (target 80%+) and a coverage badge.

### Phase 7: Docs and polish (about 6 h)

37. README: what/why, architecture diagram, quickstart (`docker compose up`), curl examples, config reference, design decisions.
38. Seed script creating a demo user and key.
39. Point Chatter at Relay instead of `openrtr.php` as a real-world client example (screenshot/GIF).
40. Tag `v0.1.0` with a changelog.

### Phase 8: Deploy (about 5 h)

41. Provision Postgres (Supabase/Neon) and Redis (Upstash).
42. Deploy the API to Fly.io or Render; run migrations on release.
43. Add a CD job (deploy on tag) and the live demo URL to the README.

### Phase 9: Stretch (optional)

44. Provider fallback, response caching, admin dashboard, Prometheus metrics, teams.

---

## 5. Definition of done (v0.1)

- Public GitHub repo with green CI (lint, types, tests, Docker build).
- `docker compose up` starts a working gateway with a seeded demo user.
- Streaming and non-streaming chat completions work through at least two providers.
- Rate limits and budgets enforced and covered by tests.
- Coverage at or above 80%, integration tests running against real Postgres and Redis.
- README good enough that a recruiter understands the project in two minutes and an engineer can run it in five.
