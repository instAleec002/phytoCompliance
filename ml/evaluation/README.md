# Evaluation data and runs

Everything the experiments read is in `suites/`; everything they produce is in `runs/`, one folder per run. The commands
are in `backend/src/interfaces/jobs/evaluate.py` (`uv run python -m interfaces.jobs.evaluate <command> --help`).
Before each measurement, the rule that decides it was written down first; the paper reports each result against its rule.

## Suites

| File | What it is | Built by |
|---|---|---|
| `estructurada.jsonl` | S1: 110 structured compliance questions (limits, history, registrations, pre-harvest intervals, mode of action, market comparisons) with the expected value and unit from the official table | `suite-estructurada` |
| `estructurada_genericas.jsonl` | S1b: 31 list and count questions (products against a pest within an interval, counts of products and of ingredients without a limit), built from the graph with queries of their own | `suite-s1b` |
| `estructurada_genericas_2.jsonl` | A second S1b with a new seed, no pest of the first and the ingredient counts at a stated date, for measuring after a change without reusing a suite already seen | `suite-s1b --semilla 20261128 --excluir estructurada_genericas.jsonl` |
| `textual.jsonl` | S2: 60 questions over the guides and theses (40 single-hop, 20 multi-hop), each tied to a document, a page and a literal answer span; written by Qwen3-8B from one page and checked automatically | `suite-textual` |
| `particion_s2.json` | Development (18) and test (42) split of S2, stratified by question type and fixed by a seed | `split_s2` |
| `juicios_s2.jsonl` | Graded relevance judgments (0, 1, 2) of the pooled fragments of S2, by fragment hash; the passage texts are not published | `juicios-s2` |
| `juicios_s2_kappa.json` | Agreement of the relevance judge with the manual sample | `juicios-kappa` |
| `fidelidad_s2_muestra.json`, `fidelidad_s2_verificacion_muestra.json` | Which answers and sentences were annotated by hand, and the reused labels | `fidelidad-muestra`, `fidelidad-muestra-verificacion` |
| `anotaciones_manuales.json` | Labels of the manual annotations (faithfulness per sentence, relevance per fragment), without the passages the workbooks show beside them (public repository only) | `ops/publicar.py` |
| `programas_control.jsonl` | 42 control spray programs: 14 clean and 28 near misses at the edges of the rules, labelled by the rules | `validar-controles` |
| `programas_reales.json` | 5 real spray programs from published theses, transcribed as printed | by hand |
| `programas_reales_hojas/` | The same 5 programs as field sheets (Excel), for the import | `importar-reales` |
| `programas_reales_referencia.xlsx`, `programas_reales_adjudicacion.json` | Manual reference for the real programs, and the disputed rows checked against the official sources | by hand |

Workbooks whose name ends in `anotacion.xlsx` show corpus passages next to each label and stay private.

## Runs

A run folder is named `<date>_<time>_<command>[_<options>]`, for example
`2026-11-27_1456_fidelidad_s2_ver-gemma4-e4b_grafo1_prueba_qwen3-8b` (S2 with a verifier, the graph list, on the test
split, judged by Qwen3-8B). Each folder has `metricas.json` (the configuration and the aggregate numbers) and the
per-item outputs (`respuestas.jsonl`, `por_pregunta.jsonl`, `por_fila.jsonl` or `por_programa.jsonl`). Runs are never
overwritten; a later run that supersedes another says so in its commit message.

| Command | Measures |
|---|---|
| `cumplimiento-s1 --modo herramientas \| sin-guarda \| memoria \| rag [--modelo] [--suite s1b] [--genericas]` | Exact answers on S1 or S1b |
| `recuperacion-juzgada`, `comparar-recuperacion`, `cobertura-documentos [--lista-grafo] [--salto-entidad]` | Retrieval on S2, paired tests, reference documents among the six passages |
| `fidelidad-s2 [--modelo] [--verificador] [--lista-grafo] [--sistema rag]`, `rejuzgar-s2`, `sin-verificar` | Faithfulness per sentence with three judge families, before and after the sentence check |
| `fidelidad-acuerdo`, `fidelidad-acuerdo-verificacion` | Judges against the manual annotation |
| `repetibilidad-s2 [--temperatura] [--semilla]` | Whether the same question gives the same answer twice |
| `validar-controles`, `validar-llm`, `validar-reales`, `reales-acuerdo`, `importar-reales` | The program validator, its language-model baseline, real programs and the field-sheet import |
| `revision-preguntas`, `revision-resultado` | Manual review of a sample of the S2 questions |
