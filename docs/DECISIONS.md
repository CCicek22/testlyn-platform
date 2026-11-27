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
- Each leg fetches `min(max(4 * top_k, 20), 100)` candidates. `vector` and `keyword` modes run one leg. `keyword` mode never calls the embedder.
- Reranking is optional. `KNOWLEDGE_RERANKER_URL` empty means off. A failed, timed-out, or invalid rerank response returns the fused order with `reranked: false`. Reranker scores replace RRF scores in the response only when the rerank succeeds.
- Filtered HNSW: the search sets `hnsw.iterative_scan = strict_order` and `hnsw.ef_search = max(40, 2 * candidates)` (capped at 1000) with `set_config(..., is_local => true)` in the same transaction as the vector query. Without this, a tenant with a few chunks far from other tenants' dense chunks could get too few or no results. `hnsw.max_scan_tuples` keeps its default of 20000, which bounds the work per query. A tenant whose chunks are a small fraction of the index and far from the query can still get short results; the tradeoff is accepted for now. Revisit if a real tenant hits this.
- Project scope: chunks are filtered by `org_id` on the chunk row; project scope adds the project's documents and org-wide documents. No role or override can remove a member's project read access, so org-wide search does not exclude any project. No migration: the scope filter joins to the document row, and the generated column is referenced by name without an ORM mapping.
- No raw SQL in app code: the tsvector column is a SQLAlchemy `column()` reference; `set_config` is called as a function.
**Consequences:** Search needs pgvector 0.8.0 or later (dev and CI run 0.8.7). Each vector query runs `set_config` twice before the search. Reranking adds one outbound call per search when enabled, bounded by its own deadline. Per-org recall for small tenants in large indexes depends on `hnsw.max_scan_tuples`; raising it costs latency.
**Alternatives considered:** Vector-only search (rejected: misses exact identifiers). Keyword-only search (rejected: misses paraphrase). Weighted score fusion (rejected: needs score normalisation that changes with the corpus). A denormalised `project_id` on chunks with a partial HNSW index per project (rejected for now: a migration and index per project, without a measured need). Relaxed ordering for iterative scans (rejected: results are already ranked by RRF, and strict ordering keeps the leg ranks exact).
