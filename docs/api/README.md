# docs/api — OpenAPI Snapshot

## openapi-v1.yaml

Committed snapshot of the Testlyn public API, version 1.0.0.

Generated from the FastAPI application via:

```bash
# From repo root
python scripts/export-openapi.py
```

The script boots the FastAPI app in test mode (`TESTING=1`), calls
`app.openapi()`, patches in `info.version: "1.0.0"` and `servers`, then writes
YAML here. It is idempotent — re-running produces the same output for the same
app code.

### When to regenerate

Run the script (and commit the diff) whenever you:

- Add, remove, or change a route path, method, or schema
- Change a Pydantic model that appears in a route's request/response body
- Change `app.title`, `app.description`, or route tags

CI enforces this via `ci-sdks.yml`: any push to `main` that changes this file
triggers the Speakeasy SDK generation pipeline.

### Versioning policy

| Version bump | When |
|---|---|
| Patch (`1.0.x`) | Additive changes: new optional fields, new endpoints |
| Minor (`1.x.0`) | New required fields on existing requests (with migration note) |
| Major (`x.0.0`) | Breaking changes: removed/renamed endpoints, incompatible schema changes |

Breaking changes require a new file (`openapi-v2.yaml`) and a deprecation notice
on v1 before removal. The v1 routes stay live for at least one full billing cycle
after v2 ships.

### SDK sibling repos (scaffold — publishing deferred to Phase 3 ship)

| Language | Repo |
|---|---|
| Python | `github.com/CCicek22/testlyn-sdk-python` |
| TypeScript | `github.com/CCicek22/testlyn-sdk-ts` |
| Go | `github.com/CCicek22/testlyn-sdk-go` |

SDK generation is handled by `.github/workflows/ci-sdks.yml` using
[Speakeasy](https://speakeasy.com). See that file for setup instructions.
