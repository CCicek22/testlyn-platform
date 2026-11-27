# Testlyn — Architecture Decision Records

Append-only. Never delete an ADR — supersede it with a new one.

Format:

```markdown
## ADR-NNN: <decision title> — YYYY-MM-DD
**Status:** accepted | superseded by ADR-XXX | rejected
**Context:** what forced the decision
**Decision:** what we chose
**Consequences:** what this commits us to / forecloses
**Alternatives considered:** what we passed on, briefly
```

---

## ADR-001: GCP over AWS for all infra — 2026-05-12
**Status:** accepted
**Context:** Single-cloud decision needed before Phase 1. Both clouds viable.
**Decision:** Google Cloud across the stack.
**Consequences:** Standardize on Cloud Run, Cloud SQL, BigQuery, Identity Platform, Vertex AI. Lock-in is real; mitigated by Terraform abstraction at module boundary.
**Alternatives considered:** AWS (ECS/RDS/Athena/Cognito), Fly.io + Neon + Clickhouse.

## ADR-002: FastAPI over Spring Boot — 2026-05-12
**Status:** accepted
**Context:** API framework choice.
**Decision:** FastAPI with SQLAlchemy 2 async.
**Consequences:** Python ecosystem (Pydantic, pytest, ruff, uv). AI tooling is first-class. Slightly less mature than Spring for very high-concurrency cases — acceptable at Phase 1 scale.
**Alternatives considered:** Spring Boot (Java), Go + chi, Node + tRPC.

## ADR-003: Stock k6 + Python sidecar over xk6 custom build — 2026-05-12
**Status:** accepted
**Context:** k6 is AGPLv3. A custom binary served over the network creates AGPL obligations on Testlyn.
**Decision:** Invoke unmodified `grafana/k6:<pinned-tag>` as a subprocess. A Python sidecar in the same container consumes k6's JSONL output and streams to BigQuery.
**Consequences:** No AGPL exposure. Sidecar is reusable for any future metric-emitting tool. Slight cost of process boundary + JSONL parse — negligible.
**Alternatives considered:** xk6-bigquery extension (rejected: derivative work), commercial load tools (rejected: cost, lock-in).

## ADR-004: Gemini 3.1 Flash-Lite as default LLM — 2026-05-12
**Status:** accepted
**Context:** AI summaries for daily reports + bottleneck explanation.
**Decision:** `gemini-3.1-flash-lite` via Vertex AI SDK (Workload Identity, not API keys).
**Consequences:** Cheap, fast, integrated with GCP IAM. Escalate to Gemini 3.1 Pro only for vision/multi-step reasoning (not Phase 1).
**Alternatives considered:** Claude Sonnet 4.6 (no Anthropic API key available), GPT-5 Mini (separate vendor relationship).

## ADR-005: Example Co GCP project for Phase 1 — 2026-05-12
**Status:** accepted
**Context:** Avoid project creation overhead in Phase 1.
**Decision:** Reuse Example Co project. Every Testlyn resource prefixed `testlyn-` and labeled `app=testlyn`.
**Consequences:** Easy bootstrap; billing aggregation by label. Must migrate to dedicated `testlyn-prod` at Phase 3 (multi-region, compliance posture).
**Alternatives considered:** Dedicated `testlyn-prod` project from day 1 (rejected: friction).

## ADR-006: Identity Platform for auth — 2026-05-12
**Status:** accepted
**Context:** Auth provider choice.
**Decision:** Google Identity Platform (Firebase Auth SDK).
**Consequences:** GCP-native, free tier covers early scale, social + email/password + OIDC. Locks us to GCP for auth — acceptable per ADR-001.
**Alternatives considered:** Auth0 (cost), Supabase Auth (separate vendor), self-hosted (rejected: maintenance).

## ADR-007: Postgres + BigQuery split — 2026-05-12
**Status:** accepted
**Context:** Single DB or transactional + analytical split.
**Decision:** Postgres for OLTP (orgs, tests, runs metadata, billing), BigQuery for OLAP (load test sample stream, cross-test analytics).
**Consequences:** Two systems to operate. Schema migrations in both. Worth it: BQ partitioning + streaming inserts handle k6 sample volume that would crush Postgres.
**Alternatives considered:** Postgres + TimescaleDB (rejected: still Postgres ceiling), Clickhouse (rejected: extra vendor).

## ADR-008: GitHub as canonical source repo — 2026-05-12
**Status:** accepted (supersedes implicit GitLab assumption in initial prompt)
**Context:** The project is hosted under `CCicek22` on GitHub. Original CLAUDE.md draft referenced GitLab.
**Decision:** GitHub `CCicek22/testlyn-platform` is canonical. CI via GitHub Actions for app builds, Cloud Build GitHub trigger for image publish + Terraform.
**Consequences:** No GitLab mirror. Cloud Build connects to GitHub repo. `.github/workflows/` instead of `.gitlab/`.
**Alternatives considered:** GitLab primary (rejected: no existing GitLab account), GitHub + GitLab mirror (rejected: maintenance overhead with zero benefit).

## ADR-009: python:3.13-slim over distroless for engine container base — 2026-05-12
**Status:** accepted
**Context:** The engine container runs two processes: `k6` (binary) and the Python sidecar. Both are supervised by `tini` + `entrypoint.sh` (a shell script). The `gcr.io/distroless/python3-debian12` image has no shell (`/bin/sh`), making it incompatible with shell-script entrypoints and multi-process supervision without an additional supervisor layer (e.g., s6-overlay).
**Decision:** Use `python:3.13-slim` (Debian bookworm slim) as the runtime base. It includes `bash`, `curl`, and standard Python runtime. We install `tini` explicitly for proper PID-1 / SIGTERM forwarding. The AGPL compliance goal (keeping k6 unmodified) is achieved by copying the pre-built binary from `grafana/k6:1.3.0` in a multi-stage build — the base image choice has no effect on this.
**Consequences:** Slightly larger image than distroless (~200 MiB base vs ~60 MiB distroless). Attack surface is marginally larger but acceptable for a short-lived Cloud Run Job that doesn't serve public traffic directly. Image target is <500 MiB total.
**Alternatives considered:** distroless + s6-overlay supervisor (rejected: significant complexity, s6-overlay is a large dependency for a single script), distroless + custom Go init (rejected: overkill), scratch + statically-linked Python (rejected: impractical for CPython).

## ADR-010: Signal-teal theme palette supersedes original indigo tokens — 2026-06-10
**Status:** accepted
**Context:** Deep-review found the implemented web palette (`#18F2C3` teal primary, dark-only surfaces, per-product signal accents) diverged from the frozen CLAUDE.md §4 indigo tokens (`#3730A3` et al.). One palette had to be canonical.
**Decision:** Operator approved the implemented signal palette ("update and merge", 2026-06-10). CLAUDE.md §4 rewritten to match code (tailwind.config.ts + lib/products.ts).
**Consequences:** Teal `#18F2C3` is the brand primary across dashboard, charts, and marketing. Future UI work follows §4 as updated; the indigo set is retired.
**Alternatives considered:** Reverting code to the indigo tokens — rejected; the shipped UI was built on the signal palette.

## ADR-011: pgvector in the existing Postgres over a separate vector database — 2026-11-27
**Status:** accepted
**Context:** The knowledge store (retrieval over org documents) needs vector storage and nearest-neighbour search. Tenancy is enforced by `org_id` everywhere, and document ingest must be atomic (a document and its chunks are written together or not at all).
**Decision:** Store chunk embeddings in the existing Postgres with the pgvector extension (`vector(256)`, HNSW index, cosine). Full-text search uses a generated `tsvector` column in the same table. Access stays in SQLAlchemy and Alembic.
**Consequences:** One datastore to operate and back up. The same `org_id` scoping and FK cascades apply to vectors. Ingest is one transaction. The embedding width is fixed at 256 and is a migration-level constant; changing it means a new migration and re-embedding. HNSW index builds cost time and memory as the table grows. CI and the dev compose database now run pgvector on PostgreSQL 18.
**Alternatives considered:** A dedicated vector database such as Pinecone, Qdrant, or Weaviate (rejected: second system to secure, sync, and pay for; no transactional link to org data), and pgvector with a separate Postgres instance (rejected: same operational cost without a benefit).

## ADR-012: Hybrid search with RRF, optional reranking, filtered HNSW scans — 2026-11-27
**Status:** accepted
**Context:** Knowledge search has to find exact rare terms (identifiers, error codes) that embeddings miss, and also match paraphrases that keyword search misses. Results are tenant-scoped, and a search must never return another org's chunks. The HNSW index is searched before `WHERE` filters apply, so a filter can return fewer rows than `LIMIT`.
**Decision:**
- Hybrid by default: a vector leg (cosine on the HNSW index, same embedding model only) and a keyword leg (`websearch_to_tsquery` on the generated `text_tsv`, ranked by `ts_rank_cd`). Results are fused with Reciprocal Rank Fusion, `score = sum(1 / (60 + rank))`, with ties broken by chunk id. RRF needs no score calibration between legs.
- Each leg fetches `min(max(4 * top_k, 20), 100)` candidates. `top_k` is at most 20, so that is at most 80 per leg and at most 80 fused candidates sent to the reranker. `vector` and `keyword` modes run one leg. `keyword` mode never calls the embedder.
- Query embedding has its own deadline (`KNOWLEDGE_SEARCH_EMBEDDING_DEADLINE_SECONDS`, default 10), separate from ingest. Reranker deadline defaults to 10. Their sum stays below `CHAT_UPSTREAM_TIMEOUT_S` (30).
- Reranker responses must return at least `top_n` and at most the number of documents sent; extra results are cut to the best `top_n`. Fewer than `top_n` is an error that falls back to the fused order.
- Untrusted passages: search text is data, not instructions. The chat tool returns only citation fields, quoted text, and a notice; scores and ranks are not shown to the model. The reports agent sets both `disallow_transfer_to_parent` and `disallow_transfer_to_peers`, so it cannot hand control to another agent. Transfer flags were checked in the ADK source; setting only the peers flag leaves the coordinator reachable as a parent target.
- Reranking is optional. `KNOWLEDGE_RERANKER_URL` empty means off. A failed, timed-out, or invalid rerank response returns the fused order with `reranked: false`. Reranker scores replace RRF scores in the response only when the rerank succeeds.
- Filtered HNSW: the search sets `hnsw.iterative_scan = strict_order` and `hnsw.ef_search = max(40, 2 * candidates)` (capped at 1000) with `set_config(..., is_local => true)` in the same transaction as the vector query. Without this, a tenant with a few chunks far from other tenants' dense chunks could get too few or no results. `hnsw.max_scan_tuples` keeps its default of 20000, which bounds the work per query. A tenant whose chunks are a small fraction of the index and far from the query can still get short results; the tradeoff is accepted for now. Revisit if a real tenant hits this.
- Project scope: chunks are filtered by `org_id` on the chunk row; project scope adds the project's documents and org-wide documents. No role or override can remove a member's project read access, so org-wide search does not exclude any project. No migration: the scope filter joins to the document row, and the generated column is referenced by name without an ORM mapping.
- No raw SQL strings in app code. The tsvector column is a SQLAlchemy `column()` reference; the search language is `cast(literal("english"), REGCONFIG)`, so it reaches Postgres as a bound parameter; `set_config` is called as a function. Test-only `EXPLAIN` checks confirm HNSW and GIN plans on forced settings.
- Prompt injection is a residual risk, not solved: a document can contain text that tries to steer the model. The mitigations above reduce what passage text can do, but do not stop a model from following it. Follow-up (not implemented): require user confirmation before any state-changing tool runs.

**Consequences:** Search needs pgvector 0.8.0 or later (dev and CI run 0.8.7). Each vector query runs `set_config` twice before the search. Reranking adds one outbound call per search when enabled, bounded by its own deadline. Per-org recall for small tenants in large indexes depends on `hnsw.max_scan_tuples`; raising it costs latency. Settings are transaction-local, so a pooled connection keeps its defaults after the search commits (tested with a single-connection pool).
**Alternatives considered:** Vector-only search (rejected: misses exact identifiers). Keyword-only search (rejected: misses paraphrase). Weighted score fusion (rejected: needs score normalisation that changes with the corpus). A denormalised `project_id` on chunks with a partial HNSW index per project (rejected for now: a migration and index per project, without a measured need). Relaxed ordering for iterative scans (rejected: with relaxed order, rows can come back out of distance order, so the vector leg's positions would not match the distance ranking that RRF assumes; strict order keeps those positions true, at some extra scan cost).

## ADR-013: Retrieval evaluation with a synthetic span-gold set; LLM-as-judge as a secondary signal — 2026-11-27
**Status:** accepted
**Context:** ADR-012 defines hybrid search, but nothing measures its quality. Real embedding models and rerankers cannot run in CI without cost or network, so a regression gate needs an offline, repeatable signal. Chunk boundaries change with the chunker, so labels tied to chunk ids would break on every chunking change.
**Decision:**
- Gold set: 12 fictional documents and 48 queries under `apps/api/evals/knowledge/`. A chunk is relevant when it comes from the named document and contains `answer_span`. Each span must occur exactly once in its document and lie inside one chunk, no two queries may share a (document, span) pair, and the loader fails otherwise. Span labels survive chunking changes that keep the span in one chunk.
- Metrics use binary relevance on the top 5: hit@5, recall@5, MRR and nDCG@5. Undefined cases raise, and repeated result ids take no extra rank (see `metrics.py`).
- The CI gate uses the deterministic `HashingEmbedder`. It needs no network and costs nothing. Its thresholds are regression floors for this set: overall rows allow two queries of slack out of 48, kind rows allow one query out of 16. They are not quality targets for a real model.
- The harness re-keys chunks to stable ids after ingest. Search breaks exact RRF ties by chunk id (ADR-012), and random ids would reorder tied chunks on every ingest. The harness therefore relies on stable tie-breaks it does not own. Production has the same property: two ingests of identical text can order exact ties differently. This is a follow-up, not fixed here.
- The judge grades the top 5 passages of each query for relevance. Each (query, chunk) pair is judged once per run, shared across modes. Calls use temperature 0 and a bounded output size. The SDK loads once, before any call's deadline. Its verdicts are compared with span gold on those passages (accuracy, precision, recall and Cohen's kappa). `judge_faithfulness` exists, but the harness does not generate answers, so it is not run.
- Judge output is untrusted. Passages sit in per-call tagged data blocks. Replies must be one JSON object with exact keys and types, bounded in length. Any failure, timeout or client error is recorded per item as `judge_error` and is never a pass.
**Consequences:**
- The hashing gate tests the pipeline (chunking, ingest, legs, fusion, metrics), not embedding quality. Its numbers say nothing about a real model.
- Keyword mode returned no rows for 40 of 48 queries. `websearch_to_tsquery` ANDs the query terms, so a natural-language question matches only chunks that contain every non-stopword. The harness reports this as measured. The gate does not assume keyword beats vector on keyword queries, because it does not in this run (0.438 vs 0.500 hit@5 on `kind=keyword`). Whether to add an OR-style keyword leg is a separate decision.
- The judge is a secondary signal with real limits. Span gold counts any chunk containing the answer span as relevant, even when the surrounding text would not answer the question. A judge can disagree with that for good reasons, so agreement is evidence about both sides, not a score. Tagged blocks make injection harder, but do not stop a model from following text inside a passage. The judge makes paid model calls, so it is only run on request.
- No judge numbers are published yet. No run used a real model. The Vertex adapter is tested against a stub SDK only.
- A session advisory lock serializes runs. A second run is refused before it touches rows.
- Changing the query set or corpus means re-measuring and updating the gate thresholds in the same change. The current measurements are in `README.md`.
**Alternatives considered:** Chunk-id labels (rejected: break when the chunker changes). Model-generated questions (rejected for now: needs a paid model and makes the gold set non-reproducible). A third-party evaluation framework (rejected: a new dependency and a paid judge path by default, for a gate that needs neither). Judging the whole corpus instead of the top 5 (rejected: cost grows with corpus size and the search output is what users see).
