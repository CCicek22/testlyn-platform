# sdk-templates

Speakeasy customization overlays for the Testlyn public SDK generation pipeline.

Place language-specific overlay files here. Speakeasy merges them with the
generated output on each CI run via the `--overlay` flag.

## Structure (planned)

```
sdk-templates/
├── python/
│   └── pyproject.toml.overlay    # package metadata, classifiers, extra deps
├── typescript/
│   └── package.json.overlay      # name, description, keywords, publishConfig
└── go/
    └── go.mod.overlay            # module path, go version
```

## Usage

Add `--overlay packages/sdk-templates/<lang>/` to the `speakeasy generate sdk`
call in `.github/workflows/ci-sdks.yml` once the overlay files are populated.

Publishing to PyPI / npm / pkg.go.dev is a Phase 3 follow-up task tracked in
`docs/DECISIONS.md` (ADR-010 when written).
