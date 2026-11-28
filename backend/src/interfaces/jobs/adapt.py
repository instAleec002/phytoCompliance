"""Data for adapting the encoder (OE3.I1: LoRA on BGE-M3).

    uv run python -m interfaces.jobs.adapt datos-codificador [--por-fragmento 1] [--limite 0]

Writes ml/adaptation/bge_m3_lora/data/:
  corpus.jsonl  every embeddable chunk of the current index, with the exact text the index encodes (header + text)
  eval.jsonl    the in-scope questions of the textual pilot suite with their source chunk (the held-out set)
  train.jsonl   synthetic (question, chunk) pairs generated with the cloud generator, only from chunks that are NOT
                the source of any evaluation question, so the comparison base vs adapted does not leak
The training itself runs on the GPU machine (ml/adaptation/bge_m3_lora/train.py, sent with gpu_job.ps1).
"""
from __future__ import annotations

import argparse
import json
import random

from shared.settings import REPO

OUT = REPO / "ml" / "adaptation" / "bge_m3_lora" / "data"
SUITE = REPO / "ml" / "evaluation" / "suites" / "textual_piloto.jsonl"


def datos_codificador(args) -> None:
    from assistant.config import load_assistant_config
    from assistant.generation.generators import build_generator
    from assistant.retrieval.search import latest_signature
    from evaluation.textual import QUESTION_SYSTEM, _json
    from knowledge.corpus.store import connect

    conn = connect()
    sig = latest_signature(conn, "bge-m3")
    rows = conn.execute(
        """SELECT chunk_id, doc_id, encabezado, texto, tokens, tipos FROM fragmentos
           WHERE firma = %s AND rol <> 'parent' ORDER BY doc_id, orden""", (sig,)).fetchall()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "corpus.jsonl", "w", encoding="utf-8") as f:
        for cid, doc, head, text, *_ in rows:
            f.write(json.dumps({"chunk_id": cid, "doc_id": doc, "text": f"{head}\n\n{text}" if head else text},
                               ensure_ascii=False) + "\n")

    evals = [json.loads(line) for line in open(SUITE, encoding="utf-8") if line.strip()]
    evals = [e for e in evals if e.get("in_scope") and e.get("chunk_id")]
    with open(OUT / "eval.jsonl", "w", encoding="utf-8") as f:
        for e in evals:
            f.write(json.dumps({"qid": e["qid"], "question": e["question"], "chunk_id": e["chunk_id"]},
                               ensure_ascii=False) + "\n")
    held_out = {e["chunk_id"] for e in evals}

    cfg = load_assistant_config()
    gen = build_generator(cfg.generator, cfg.generators, "gemini")
    pool = [r for r in rows if r[0] not in held_out and (r[4] or 0) >= 60 and "table" not in (r[5] or [])]
    random.Random(20261110).shuffle(pool)
    if args.limite:
        pool = pool[: args.limite]
    done = set()
    path = OUT / "train.jsonl"
    if path.exists():  # resumable: skip chunks already used
        done = {json.loads(line)["chunk_id"] for line in open(path, encoding="utf-8") if line.strip()}
    n = 0
    with open(path, "a", encoding="utf-8") as f:
        for cid, doc, head, text, *_ in pool:
            if cid in done:
                continue
            for _ in range(args.por_fragmento):
                try:
                    out = _json(gen.generate(QUESTION_SYSTEM, f"Pasaje:\n{text}").text)
                except Exception as e:  # a failed call costs one pair, not the run
                    print("fallo:", cid, e)
                    continue
                if out.get("pregunta"):
                    f.write(json.dumps({"question": out["pregunta"].strip(), "chunk_id": cid, "doc_id": doc},
                                       ensure_ascii=False) + "\n")
                    f.flush()
                    n += 1
            if n and n % 50 == 0:
                print(f"{n} pares")
    total = sum(1 for _ in open(path, encoding="utf-8"))
    print(f"firma {sig}: {len(rows)} fragmentos en corpus.jsonl, {len(evals)} preguntas de evaluación "
          f"(sus {len(held_out)} fragmentos fuera del entrenamiento), {total} pares en train.jsonl")


def main() -> None:
    p = argparse.ArgumentParser(prog="adapt")
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("datos-codificador")
    d.add_argument("--por-fragmento", type=int, default=1)
    d.add_argument("--limite", type=int, default=0, help="máximo de fragmentos (0 = todos)")
    args = p.parse_args()
    {"datos-codificador": datos_codificador}[args.command](args)


if __name__ == "__main__":
    main()
