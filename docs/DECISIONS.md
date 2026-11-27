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
- Hybrid by default: a vector leg (cosine on the HNSW index, same embedding model only) and a keyword leg (any-term match on the generated `text_tsv`, ranked by `ts_rank_cd`; see ADR-014). Results are fused with Reciprocal Rank Fusion, `score = sum(1 / (60 + rank))`, with ties broken by chunk id. RRF needs no score calibration between legs.
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
- **UPDATE (2026-11-27):** Keyword mode returned no rows for 40 of 48 queries under the AND keyword leg (`websearch_to_tsquery`). The OR-style leg is decided in ADR-014. The gate does not assume keyword beats vector on keyword queries.
- The judge is a secondary signal with real limits. Span gold counts any chunk containing the answer span as relevant, even when the surrounding text would not answer the question. A judge can disagree with that for good reasons, so agreement is evidence about both sides, not a score. Tagged blocks make injection harder, but do not stop a model from following text inside a passage. The judge makes paid model calls, so it is only run on request.
- No judge numbers are published yet. No run used a real model. The Vertex adapter is tested against a stub SDK only.
- A session advisory lock serializes runs. A second run is refused before it touches rows.
- Changing the query set or corpus means re-measuring and updating the gate thresholds in the same change. The current measurements are in `README.md`.
**Alternatives considered:** Chunk-id labels (rejected: break when the chunker changes). Model-generated questions (rejected for now: needs a paid model and makes the gold set non-reproducible). A third-party evaluation framework (rejected: a new dependency and a paid judge path by default, for a gate that needs neither). Judging the whole corpus instead of the top 5 (rejected: cost grows with corpus size and the search output is what users see).

## ADR-014: Keyword leg matches any term, capped and timed out, ranked by ts_rank_cd — 2026-11-27
**Status:** accepted
**Context:** `websearch_to_tsquery` ANDs every non-stopword. Keyword mode returned no rows for 40 of 48 gold queries (natural-language questions), so keyword-only hit@5 was 0.167 on the hashing embedder. The hybrid row hid this because the vector leg still filled the list. The eval harness (ADR-013) makes the change measurable. OR over every term of a long query matches most of an org, and `ts_rank_cd` then scores a query tree with one node per term on every match, so the change needs a term cap and a statement timeout.
**Decision:**
- Keyword leg: `plainto_tsquery(lang, query)` as text, split on ` & `, the first `KEYWORD_MAX_TERMS` = 32 elements kept (`array[1:32]`), joined with ` | `, cast to `TSQUERY`. `plainto_tsquery` joins lexemes with ` & ` and never puts a space inside one, so each element is exactly one lexeme. Verified on Postgres 18.7 (probes below). The earlier `replace(' & ', ' | ')` form is gone.
- The tsquery is a scalar subquery, built once per use. The WHERE predicate and the ORDER BY each reference it, and Postgres evaluates each as an InitPlan. The GIN plan test passes with it, and the language stays a bound `REGCONFIG` parameter.
- Statement timeout: `keyword_candidates` reads `statement_timeout`, sets it to `knowledge_search_keyword_timeout_ms` (`KNOWLEDGE_SEARCH_KEYWORD_TIMEOUT_MS`, default 3000) with `set_config(..., true)`, runs the statement, and restores the previous value. On SQLSTATE 57014 it rolls back and raises `KeywordSearchTimeout`. The route maps it to 503 `Search timed out, try a shorter query` and logs only the error type. `run_search` takes `keyword_timeout_ms` as a keyword-only argument; the eval runner passes nothing, so the harness has no timeout. The chat tool already turns a non-2xx reply into `{"ok": false, "status": 503, "error": ...}`; it returns no traceback.
- Ranking stays `ts_rank_cd(text_tsv, query)`, flag 0. Stopword-only and punctuation-only queries return no keyword rows, with a NOTICE from Postgres, and do not raise.
- Syntax: `or` is an English stopword and is dropped, like `the`. Quote characters, `|`, `&`, `:*` and `!` are separators and are dropped. `-` is not an exclusion operator: a leading minus is dropped from a word, but kept in numbers (`2026-11-27` gives `'2026' & '-11' & '-27'`, and the any-term form joins those with `|`). Pinned by tests in `tests/postgres/test_knowledge_search.py`.
- Vector tie-break (27f9f2c): vector candidates with equal distance are ordered by chunk id. Reason: one hashing eval run in six gave different hybrid numbers, because equal-distance chunks came back in arbitrary order. After the fix ten consecutive hashing runs gave identical JSON.

**Measured (top 5, 48 queries, hybrid overall; keyword-only hit@5 last).** Hashing and EmbeddingGemma rows for AND and flag-1 were measured twice each before the tie-break, identical each time; they were not re-measured after it. The shipped row was measured twice before the tie-break and then three times (hashing) and twice (EmbeddingGemma) after it.

| embedder | variant | hybrid hit@5 | hybrid recall@5 | hybrid MRR | hybrid nDCG@5 | keyword-only hit@5 | measured |
|---|---|---:|---:|---:|---:|---:|---|
| hashing | AND (before) | 0.604 | 0.604 | 0.448 | 0.486 | 0.167 | before tie-break, 2 runs |
| hashing | any-term, capped (shipped) | 0.812 | 0.812 | 0.598 | 0.649 | 0.896 | after tie-break, 3 runs |
| hashing | any-term + length norm (flag 1) | 0.812 | 0.812 | 0.612 | 0.660 | 0.875 | before tie-break, 2 runs |
| EmbeddingGemma | AND (before) | 0.917 | 0.906 | 0.790 | 0.815 | 0.167 | before tie-break, 2 runs |
| EmbeddingGemma | any-term, capped (shipped) | 0.896 | 0.896 | 0.832 | 0.845 | 0.896 | after tie-break, 2 runs |
| EmbeddingGemma | any-term + length norm (flag 1) | 0.896 | 0.896 | 0.814 | 0.832 | 0.875 | before tie-break, 2 runs |

The cap does not change these numbers: the largest gold query has 9 lexemes (`max lexeme count over the 48 gold queries = 9`, measured with Postgres plainto), so no query reaches 32. The shipped rows match the README tables line for line.

Hybrid paraphrase (16 queries): hashing 0.188 (AND) to 0.562 (shipped); EmbeddingGemma 0.812 (AND) to 0.688 (shipped and flag 1). Hybrid keyword kind on hashing: 0.750 to 0.938.

**Why this variant:** On the real embedder, shipped any-term beats AND on MRR (+0.042) and nDCG@5 (+0.030). It loses one query on hit@5 (1/48 = 0.021) and two on paraphrase hit@5 (2/16 = 0.125). Length normalisation lowers EmbeddingGemma MRR and nDCG and gains 0.012 nDCG on hashing, so it is not shipped. `ts_rank_cd(..., 32)` is a monotonic map of the rank and cannot change order, so it was not measured as a variant.

**Timing (cap and timeout evidence).** Method: Postgres 18 in the pgvector container, a TEMP table `bench` with 120,000 rows and 4 orgs (30,000 rows in the org filtered) of 40 tokens each, from a 3,020-word vocabulary with 20 English words. Columns and indexes mimic the chunk table: stored generated tsvector, GIN on it, btree on `org_id`, then ANALYZE. Statement shape is the compiled app statement. One `EXPLAIN (ANALYZE, TIMING OFF)` run per row, on a freshly seeded table; these are single runs, not averages. Not the production schema or hardware.

| query | variant | execution ms | rows returned | heap rows | plan |
|---|---|---:|---:|---:|---|
| 107 words | AND (`websearch_to_tsquery`) | 16.4 | 0 | 0 | Limit, top-N sort, Bitmap Heap Scan, BitmapAnd |
| 107 words | any-term, uncapped | 5,238 | 20 | 28,808 | same |
| 107 words | any-term, capped at 32 (shipped) | 421.6 | 20 | 12,716 | same |
| 12 words | AND | 4.0 | 0 | 0 | same |
| 12 words | any-term, uncapped | 68.2 | 20 | 4,767 | same |
| 12 words | any-term, capped (shipped) | 71.1 | 20 | 4,767 | same |

The uncapped 107-word query exceeds the 3,000 ms default; the capped one does not. Both plans have two InitPlans (one per subquery reference, each a Result node), a Bitmap Index Scan on the org btree, and a Bitmap Index Scan on the GIN index. The AND rows are not comparable: they return nothing for these queries. The capped and uncapped 12-word rows return identical hits, so the cap costs nothing measurable at this size.

**Consequences:**
- Gate (`tests/postgres/test_knowledge_eval.py`, hashing embedder, measured values in brackets, slack in queries): hybrid overall hit@5 at least 37/48 (39; 2 queries of slack); hybrid overall nDCG@5 at least 0.607 (0.649 minus 2/48 = 0.042; 2 queries of slack); hybrid keyword-kind hit@5 at least 14/16 (15; 1 query of slack); hybrid mixed-kind hit@5 at least 14/16 (15; 1 query of slack); keyword-only overall hit@5 at least 41/48 (43; 2 queries of slack); hybrid overall hit@5 at least vector-only overall hit@5 (39/48 against 25/48). The earlier `hybrid >= best single - 0.10` bound is removed: it had under one query of headroom and failed if keyword-only improved by a query.
- Keyword-only on `kind=keyword` is 16/16 on both embedders, so its gate rows are not the regression risk. The risk is hybrid falling behind keyword on hashing, which is now a 4-query gap (39 vs 43 on overall hit@5 for hashing: 0.812 against 0.896).
- Queries longer than 32 words are answered from their first 32 words. A word past the 32nd cannot match, so a long query can miss a chunk that only contains a later word. Current gold queries are at most 9 words.
- Users cannot use phrase, exclusion or boolean syntax in keyword mode. Those characters are read as separators, as above. No caller in this repo relied on websearch syntax.
- A query past the timeout returns 503, not a partial result.
- Hashing numbers test the pipeline only. The EmbeddingGemma numbers are the ones to read for quality. They show a one-query drop on hit@5 against the AND leg, and hybrid hit@5 now equals vector-only.

**Alternatives considered:**
- Keep AND (rejected: keyword-only hit@5 0.167, hybrid hashing 0.604).
- Per-word `plainto_tsquery` combined with `||` (not shipped: it is a different query and was not measured; it would also need a Python split of user text).
- `websearch_to_tsquery` with `or` between words (rejected: callers would have to write `or`).
- `replace(' & ', ' | ')` on the whole text (replaced by the array form: the same result, but it has no cap).
- Length normalisation, flag 1 (measured, not shipped: see above).

**Probe outputs on Postgres 18.7 (psql, `-At`):**
- `plainto_tsquery('english', 'well-known jobs & queues')` = `'well-known' & 'well' & 'known' & 'job' & 'queue'`
- `plainto_tsquery('english', 'the and of')` = empty (NOTICE: contains only stop words)
- `plainto_tsquery('english', '!!! ...')` = empty (NOTICE)
- `plainto_tsquery('english', 'alpha or beta')` = `'alpha' & 'beta'` (`or` is a stopword)
- `plainto_tsquery('english', 'alpha\beta')` = `'alpha' & 'beta'`; with `E'alpha\x07beta'` = `'alpha' & 'beta'`
- `plainto_tsquery('english', 'a:b *c d<->e (x) !y')` = `'b' & 'c' & 'd' & 'e' & 'x' & 'y'`
- `plainto_tsquery('english', '2026-11-27')` = `'2026' & '-11' & '-27'`; `plainto_tsquery('english', '-5')` = `'-5'`
- `plainto_tsquery('english', 'x.com/it''s/ok')` = `'x.com/it''s/ok' & 'x.com' & '/it''s/ok'`; `to_tsvector('english', 'see x.com/it''s/ok here')` contains `'x.com/it''s/ok':2 'x.com':3 '/it''s/ok':4`, so the query matches
- `plainto_tsquery('english', '/a&b')` = `'/a' & 'b'`; `to_tsvector('english', 'route /a&b is slow')` contains `'/a':2 'b':3`, so the query matches
- Capped array form, `array_to_string((string_to_array(plainto::text, ' & '))[1:32], ' | ')`: empty input gives `''` and numnode 0; one word gives `'gate'` and numnode 1; a 40-word input keeps 32 lexemes and numnode 63 (= 2 * 32 - 1); a 1000-character input with compounds and punctuation has 63 nodes after the cap.
