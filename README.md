# Testlyn

Developer-first AI test platform. Phase 1 ships load testing.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 async, Pydantic v2, Alembic, uv |
| Frontend | Node 24 LTS, Next.js 15, React 19, TypeScript, Tailwind v4, shadcn/ui |
| Database | Postgres 18 + pgvector (dev and CI); Terraform `cloud_sql` module still pins Postgres 16, not moved yet; BigQuery (`testlyn_metrics`) |
| Queue | Cloud Tasks, Cloud Scheduler |
| Load engine | Stock `grafana/k6` + Python BigQuery sidecar (AGPL-safe) |
| Auth | Identity Platform |
| Payments | Stripe |
| Email | SendGrid |
| LLM | Gemini 3.1 Flash-Lite via Vertex AI |
| IaC | Terraform |

## Layout

```
apps/
  api/            FastAPI backend
  web/            Next.js (marketing + dashboard)
  engine/         k6 worker container (stock k6 + Python sidecar)
  report-builder/ PDF + AI summary
packages/
  shared/         TS types (generated from OpenAPI)
  ui/             shadcn/ui components
infra/terraform/  GCP IaC
docs/             Specs, ADRs, build log
```

## Quickstart

See [SETUP.md](./SETUP.md).

## Hard rules

Most important:

- k6 binary is **unmodified**, invoked as subprocess. Never xk6 / custom build.
- `tests` and `test_runs` carry a `product` discriminator column.
- All Postgres access through SQLAlchemy + Alembic. No raw SQL in app code.
- Secrets in Secret Manager only.

## Phase roadmap

- **Phase 1 (active):** Load Testing MVP
- Phase 2: Functional + accessibility
- Phase 3: Synthetic data + security + multi-region
- Phase 4: Mobile + RUM + RBAC + enterprise

## Knowledge store

Text is stored as documents, split into chunks, and each chunk gets a 256-dimension embedding in Postgres (pgvector). Documents are scoped to an org and optionally to a project. Search is hybrid (see [Searching](#searching)); reranking is optional.

Endpoints, prefix `/v1/orgs/{org_id}/knowledge`:

- `POST /documents` takes `title`, `source`, `text`, and optional `project_id`. Returns 201 for a new document, or 200 with the existing one when identical text is already stored in the same project (or, with no project, in the org). The same text in two different projects creates two documents.
  - 422 for empty text, text over `KNOWLEDGE_MAX_DOCUMENT_CHARS`, text that makes more than `KNOWLEDGE_MAX_CHUNKS` chunks (default 2000), NUL bytes, or lone surrogates.
  - 503 with a generic message when the embedder fails or does not answer within `KNOWLEDGE_EMBEDDING_DEADLINE_SECONDS` (default 120). Nothing is stored in that case.
- `GET /documents` lists newest first. Supports `limit`, `offset`, and `project_id`.
- `GET /documents/{document_id}` returns the document, `chunk_count`, and one page of chunks. Pages use `chunk_limit` (default 100, max 500) and `chunk_offset`. Embeddings are not returned.
- `DELETE /documents/{document_id}` returns 204 and removes its chunks.
- `POST /search` runs a search and returns citations. See [Searching](#searching).

Choosing an embedder with `KNOWLEDGE_EMBEDDING_PROVIDER`:

- `hashing` (default): offline and deterministic, for tests and CI. It matches shared words only and does not understand meaning.
- `openai_compat`: POSTs to `{KNOWLEDGE_EMBEDDING_BASE_URL}/embeddings` in the OpenAI format. Every returned vector must have 256 dimensions, or the request fails. Requires `KNOWLEDGE_EMBEDDING_BASE_URL`.

The dev compose Postgres is PostgreSQL 18 with pgvector. Its volume mounts at `/var/lib/postgresql` (PG 18 keeps data under `18/docker`). A volume made with an older mount, or from Postgres 16, must be removed first (`docker compose -f infra/docker-compose.dev.yml down -v`).

### Searching

`POST /v1/orgs/{org_id}/knowledge/search` takes `query` (at most 4000 characters before trimming, 1 to 1000 after), optional `project_id`, `top_k` (1 to 20, default 5), and `mode`:

- `hybrid` (default): nearest chunks by cosine distance on the HNSW index, plus Postgres full-text matches (`websearch_to_tsquery` with `ts_rank_cd`). The two lists are fused with Reciprocal Rank Fusion (k = 60). Each leg fetches `min(max(4 * top_k, 20), 100)` candidates.
- `vector`: the embedding leg only.
- `keyword`: the full-text leg only. The embedder is not called.

Scope: with `project_id`, results come from that project and from org-wide documents. Without it, every document of the org is searched. The vector leg compares only chunks embedded with the current embedder's model name.

Each result is a citation: `chunk_id`, `document_id`, `document_title`, `source`, `heading`, `text`, `char_start`, `char_end`, `score`, `vector_rank`, and `keyword_rank`. A rank is `null` when that leg did not return the chunk. The response is `{results, mode, reranked}`. `score` is the fused RRF score, or the reranker's score when `reranked` is `true`.

Filters apply after the HNSW index is scanned, so a query can return fewer rows than it asks for. The search enables pgvector iterative scans for each vector query (`hnsw.iterative_scan = strict_order`, `hnsw.ef_search = min(max(40, 2 * candidates), 1000)`). This needs pgvector 0.8.0 or later. Scans stop after `hnsw.max_scan_tuples` (default 20000), so a tenant whose chunks are a small share of the index and sit far from the query can still get short results. See ADR-012.

Query embedding has its own deadline, `KNOWLEDGE_SEARCH_EMBEDDING_DEADLINE_SECONDS` (default 10), separate from the ingest deadline. Embedder failure or timeout returns 503 with a generic message. Embedding and reranking run with no database transaction open. Both deadlines together stay below `CHAT_UPSTREAM_TIMEOUT_S` (default 30).

Residual risk: search passages are untrusted. Documents can contain text that reads like instructions. The chat tool returns passages as quoted data with a notice, and the reports agent cannot transfer control, but a model can still be steered by passage text. Confirmation before state-changing tools is not implemented yet and is a follow-up. See ADR-012.

#### Reranker (optional, off by default)

Set `KNOWLEDGE_RERANKER_URL` to the full URL of a rerank endpoint that accepts `{model, query, documents, top_n}` and returns `{results: [{index, relevance_score}]}`. Any server that implements that shape works. Then set `KNOWLEDGE_RERANKER_MODEL` to the model name the server expects, `KNOWLEDGE_RERANKER_API_KEY` if it requires a bearer token, and `KNOWLEDGE_RERANKER_DEADLINE_SECONDS` (default 10) for the per-call timeout:

```sh
KNOWLEDGE_RERANKER_URL=http://localhost:8081/v1/rerank
KNOWLEDGE_RERANKER_MODEL=your-rerank-model
```

At most 80 fused candidates are sent for reranking (`top_k` is capped at 20, so the pool is at most `min(max(4 * 20, 20), 100)` = 80). The reranker must return at least `top_n` results and no more than the documents sent; extra results are cut to the best `top_n`. If the call fails, times out, or returns an invalid body (too few results, bad or duplicate index, bool or non-finite score, oversized response over 1 MB), the fused order is returned with `reranked: false` and a warning is logged.

`CREATE EXTENSION vector` needs superuser. Migration 0015 runs it, so the migration role must either be a superuser or find the extension already installed. An admin can pre-create it with `CREATE EXTENSION vector;` in the target database. The `IF NOT EXISTS` clause then makes the migration a no-op.

Postgres-only tests (skipped without `TEST_POSTGRES_URL`):

```sh
docker run -d --rm --name testlyn-pgvector-test -e POSTGRES_PASSWORD=localdev \
  -e POSTGRES_DB=testlyn_test -p 127.0.0.1:55432:5432 pgvector/pgvector:0.8.7-pg18
cd apps/api
TEST_POSTGRES_URL=postgresql+asyncpg://postgres:localdev@127.0.0.1:55432/testlyn_test \
  uv run --frozen pytest -m postgres
```

These tests drop and recreate the `public` schema of the database they point at. Use a throwaway database.

### Evaluating retrieval

`apps/api/evals/knowledge/` holds a synthetic gold set: 12 fictional Markdown documents and 48 queries (16 `paraphrase`, 16 `keyword`, 16 `mixed`). A chunk is relevant to a query when it comes from the named document and its text contains `answer_span`. Each span occurs exactly once in its document and lies inside one chunk; the loader enforces both. Invented names only; `example.com` for hosts.

Run it against an empty, migrated Postgres 18 with pgvector (for example the dev database in `infra/docker-compose.dev.yml` after `alembic upgrade head`). The run creates one org, `knowledge-evaluation`, ingests the corpus, runs every query in `hybrid`, `vector` and `keyword` mode at top_k 5, and deletes what it created, also on failure. It refuses to start when that org already holds documents.

```sh
cd apps/api
TEST_POSTGRES_URL=postgresql+asyncpg://testlyn_api:localdev@127.0.0.1:5432/testlyn \
  uv run --frozen python -m testlyn_api.knowledge.evaluation --json-out eval-report.json
```

`--embedder openai-compat` points the same run at an OpenAI-style `/embeddings` server. Set `--embedding-base-url` and `--embedding-model`; the API key comes from `KNOWLEDGE_EMBEDDING_API_KEY`. `--embedding-dim` must be 256, the width of the vector column. Query embedding uses `KNOWLEDGE_SEARCH_EMBEDDING_DEADLINE_SECONDS`.

`--judge --judge-model <name>` also grades each retrieved passage with a Gemini model on Vertex AI (project from `GCP_PROJECT_ID`, location from `VERTEX_AI_LOCATION`). This makes paid model calls. It is off by default. See ADR-013 for what it measures.

Metrics, per query, on the top 5 results. Duplicate result ids take no extra rank.

- `hit@5`: 1 if any of the top 5 is relevant.
- `recall@5`: share of the gold entries covered by the top 5.
- `MRR`: 1 / rank of the first relevant result within the top 5, else 0.
- `nDCG@5`: binary-gain discounted cumulative gain over the top 5, divided by the ideal value for the query.

Measured with the hashing embedder on 2026-11-27 (`hashing-256-v1`, 12 documents, 48 queries, top_k 5):

| mode | scope | queries | hit@5 | recall@5 | MRR | nDCG@5 |
|---|---|---:|---:|---:|---:|---:|
| hybrid | overall | 48 | 0.542 | 0.542 | 0.382 | 0.421 |
| hybrid | keyword | 16 | 0.688 | 0.688 | 0.552 | 0.585 |
| hybrid | mixed | 16 | 0.750 | 0.750 | 0.530 | 0.583 |
| hybrid | paraphrase | 16 | 0.188 | 0.188 | 0.065 | 0.095 |
| vector | overall | 48 | 0.479 | 0.479 | 0.249 | 0.305 |
| vector | keyword | 16 | 0.500 | 0.500 | 0.195 | 0.269 |
| vector | mixed | 16 | 0.750 | 0.750 | 0.489 | 0.552 |
| vector | paraphrase | 16 | 0.188 | 0.188 | 0.065 | 0.095 |
| keyword | overall | 48 | 0.167 | 0.167 | 0.167 | 0.167 |
| keyword | keyword | 16 | 0.438 | 0.438 | 0.438 | 0.438 |
| keyword | mixed | 16 | 0.062 | 0.062 | 0.062 | 0.062 |
| keyword | paraphrase | 16 | 0.000 | 0.000 | 0.000 | 0.000 |

What these numbers show, and what they do not:

- The hashing embedder is a bag-of-words hash. Its paraphrase scores are low by design. **These numbers say nothing about the quality of a real embedding model.**
- Keyword mode returned no rows for 40 of 48 queries. `websearch_to_tsquery` requires every non-stopword of the query to appear in the chunk, so a natural-language question rarely matches. Hybrid still returns the vector leg's results, so the hybrid row is not hurt the same way.
- On `kind=keyword`, vector beat keyword mode in this run (0.500 vs 0.438 hit@5). The expectation that keyword wins on exact tokens does not hold for this set and this query style.
- No judge numbers are included. The judge has not been run against a real model.

The gate (`tests/postgres/test_knowledge_eval.py`, run by the CI `postgres` job) asserts: hybrid hit@5 at least 0.50, hybrid nDCG@5 at least 0.38, hybrid keyword-kind hit@5 at least 0.65, hybrid mixed-kind hit@5 at least 0.70, and hybrid hit@5 no more than 0.05 below the better single leg. Each threshold is 0.04 to 0.06 below its measured value. The gate also checks that two runs give identical metrics.

## License

© 2026 Mack Cicek. All rights reserved. Source is published for review; no licence is granted.
