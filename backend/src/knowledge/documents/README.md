# Corpus documental: de un archivo a fragmentos citables

Turns a PDF, DOCX or XLSX into a `NormalizedDocument` (typed blocks with page and section) and then into chunks
ready to index. Every stage that a benchmark may want to compare is a **named, swappable piece chosen in
`config/documents.yaml`**, and each can be overridden for one run with an environment variable or a CLI flag.
Nothing downstream of a stage knows which implementation produced its input.

```
file ─► route ─────────────────────────────► NormalizedDocument ─► steps ─────────────► chunker ─► contextual header ─► chunks
        markdown:   extractor.markdown() ─► markdown.parse          text, furniture,      structural
        structured: extractor.structured()                          outline, sections     fixed
        mixed:      text from markdown + tables from structured                           page
```

## Swap points

| What | Key in `config/documents.yaml` | Env override | Options |
|---|---|---|---|
| Route (how the file becomes blocks) | `route` | `DOCS_ROUTE` | `markdown` (default), `structured`, `mixed` |
| Extractor per format | `extractors.pdf`, `.docx`, `.xlsx` | `DOCS_EXTRACTOR_PDF`, `_DOCX`, `_XLSX` | pdf: `opendataloader`, `docling`, `pymupdf`; docx: `docx`, `docling`; xlsx: `xlsx`, `docling` |
| Steps after extraction, in order | `steps` | `DOCS_STEPS` (comma list) | `text`, `furniture`, `outline`, `sections` |
| Chunker | `chunker.name` and its parameters | `DOCS_CHUNKER`, `DOCS_MAX_TOKENS` | `structural`, `fixed`, `page` |
| Contextual header | `contextual_header` | `DOCS_CONTEXTUAL_HEADER` | `on`, `off` |
| Token counter | `tokens` | `DOCS_TOKENS` | `approx` |

`python -m interfaces.jobs.documents procesar <file> --route structured --pdf docling --chunker fixed` runs one
file with any combination and writes the normalized blocks, the Markdown rendering and the chunks next to each
other, so two configurations can be compared side by side. That is also what the extractor benchmark (D4 in
`pendientes/25`) will call.

## Why a block model instead of Markdown or the raw engine output

- **Markdown** loses the page of each block and the shape of tables, and the citation needs both. It stays as a
  route (the default: many engines are strongest at their Markdown export) and as a rendering for people and for the
  generator, but it is parsed back into blocks, with `<!-- page N -->` anchors keeping the pages.
- **The raw output of one engine** would tie chunking to that engine. Each extractor is an adapter that returns the
  same `NormalizedDocument`, so changing engine is a configuration value.
- **PDF and DOCX differ, then converge.** A PDF has pages but its structure is inferred from layout; a DOCX has exact
  structure (heading styles, real tables) but no pages, so its blocks carry `page=None` and are cited by section. After
  the adapter, both are the same kind of object, and steps, chunkers and the index treat them alike.

## Folders

| Path | Holds |
|---|---|
| `model.py` | `Block`, `Cell`, `NormalizedDocument`, `Chunk`: frozen dataclasses, the only contract between stages |
| `config.py` | `PipelineConfig`: reads `config/documents.yaml`, applies `DOCS_*` overrides, validates names against the registries |
| `registry.py` | Named registries (`EXTRACTORS`, `STEPS`, `CHUNKERS`, `TOKENIZERS`) and the `register` decorator |
| `pipeline.py` | `Pipeline`: route, steps, chunker and header, as configured |
| `routes.py` | The three routes, including the merge used by `mixed` |
| `extractors/` | One adapter per engine; heavy engines (Docling) are imported only when chosen |
| `markdown/` | `render` (blocks to Markdown with page anchors) and `parse` (Markdown back to blocks) |
| `steps/` | Engine-independent fixes on blocks: text normalization, repeated headers and footers, outline (heading levels from numbering, tables of contents), section paths |
| `chunkers/` | Chunking strategies and the contextual header |
| `tokens.py` | Token counters |

Adding an implementation is one file with `@register(EXTRACTORS, "name")` (or `STEPS`, `CHUNKERS`) imported in its
package `__init__`; the configuration can then name it.

Late chunking is not implemented: BGE-M3 pools with CLS and late chunking is validated for mean pooling (decision of
06/11/2026, `pendientes/25`, D3). The contextual header gives each chunk its document and section instead.
