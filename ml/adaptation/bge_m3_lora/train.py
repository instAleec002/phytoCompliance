# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "torch>=2.7",
#   "sentence-transformers>=4.1",
#   "peft>=0.15",
#   "datasets>=3",
#   "accelerate>=1.6",
# ]
# [tool.uv.sources]
# torch = { index = "pytorch-cu128" }
# [[tool.uv.index]]
# name = "pytorch-cu128"
# url = "https://download.pytorch.org/whl/cu128"
# explicit = true
# ///
"""LoRA on BGE-M3 for the agronomic vocabulary in Spanish (OE3.I1). Runs on the GPU machine (RTX 5070, 8 GB):

    uv run train.py [--epocas 2] [--rango 16] [--lr 1e-4]

Reads data/corpus.jsonl, data/train.jsonl and data/eval.jsonl (built on the main machine by
`interfaces.jobs.adapt datos-codificador`), measures dense retrieval of the BASE model on the held-out questions, trains
a LoRA adapter with in-batch negatives (CachedMultipleNegativesRankingLoss, so a large effective batch fits in 8 GB),
measures the ADAPTED model the same way, and writes to salida/: adapter/ (the LoRA weights only), metricas.json,
config.json. Progress goes to estado.txt and train.log so the main machine can follow it over SSH.
Indicator OE3.I1: the adapted encoder beats the base one by at least 8 % in Recall@10 and nDCG@10."""
from __future__ import annotations

import argparse
import json
import logging
import math
import time
from pathlib import Path

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "salida"
OUT.mkdir(exist_ok=True)
logging.basicConfig(filename=HERE / "train.log", level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("train")


def estado(texto: str) -> None:
    (HERE / "estado.txt").write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {texto}\n", encoding="utf-8")
    log.info(texto)
    print(texto, flush=True)


def leer(nombre: str) -> list[dict]:
    return [json.loads(l) for l in open(DATA / nombre, encoding="utf-8") if l.strip()]


def evaluar(model, corpus: list[dict], evals: list[dict], k: int = 10) -> dict:
    import torch
    ids = [c["chunk_id"] for c in corpus]
    docs = model.encode([c["text"] for c in corpus], batch_size=16, normalize_embeddings=True, convert_to_tensor=True,
                        show_progress_bar=False)
    qs = model.encode([e["question"] for e in evals], batch_size=16, normalize_embeddings=True, convert_to_tensor=True,
                      show_progress_bar=False)
    top = torch.topk(qs @ docs.T, k=k, dim=1).indices.cpu().tolist()
    r1 = r5 = r10 = mrr = ndcg = 0.0
    for e, fila in zip(evals, top):
        ranked = [ids[i] for i in fila]
        if e["chunk_id"] in ranked:
            pos = ranked.index(e["chunk_id"]) + 1
            r1 += pos <= 1
            r5 += pos <= 5
            r10 += 1
            mrr += 1 / pos
            ndcg += 1 / math.log2(pos + 1)
    n = len(evals)
    return {"n": n, "r1": round(r1 / n, 3), "r5": round(r5 / n, 3), "r10": round(r10 / n, 3),
            "mrr10": round(mrr / n, 3), "ndcg10": round(ndcg / n, 3)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--epocas", type=int, default=2)
    p.add_argument("--rango", type=int, default=16)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--lote", type=int, default=64, help="lote efectivo (negativos en el lote)")
    p.add_argument("--max-tokens", type=int, default=512)
    args = p.parse_args()
    t0 = time.time()
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType
        from sentence_transformers import (SentenceTransformer, SentenceTransformerTrainer,
                                           SentenceTransformerTrainingArguments)
        from sentence_transformers.losses import CachedMultipleNegativesRankingLoss
        from sentence_transformers.training_args import BatchSamplers

        estado(f"preparando: GPU {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NINGUNA'}, "
               f"torch {torch.__version__}")
        corpus, evals, train = leer("corpus.jsonl"), leer("eval.jsonl"), leer("train.jsonl")
        texto = {c["chunk_id"]: c["text"] for c in corpus}
        pares = [{"anchor": t["question"], "positive": texto[t["chunk_id"]]} for t in train if t["chunk_id"] in texto]
        estado(f"datos: {len(corpus)} fragmentos, {len(pares)} pares de entrenamiento, {len(evals)} preguntas de evaluación")

        model = SentenceTransformer("BAAI/bge-m3", device="cuda")
        model.max_seq_length = args.max_tokens
        estado("evaluando el modelo base")
        base = evaluar(model, corpus, evals)
        estado(f"base: {base}")

        model.add_adapter(LoraConfig(task_type=TaskType.FEATURE_EXTRACTION, r=args.rango, lora_alpha=2 * args.rango,
                                     lora_dropout=0.1, target_modules=["query", "key", "value"]))
        loss = CachedMultipleNegativesRankingLoss(model, mini_batch_size=8)
        targs = SentenceTransformerTrainingArguments(
            output_dir=str(HERE / "checkpoints"), num_train_epochs=args.epocas, per_device_train_batch_size=args.lote,
            learning_rate=args.lr, warmup_ratio=0.1, bf16=True, batch_sampler=BatchSamplers.NO_DUPLICATES,
            logging_steps=5, save_strategy="no", report_to="none", seed=20261110)
        estado(f"entrenando: {args.epocas} épocas, rango {args.rango}, lr {args.lr}, lote {args.lote}")
        SentenceTransformerTrainer(model=model, args=targs, train_dataset=Dataset.from_list(pares), loss=loss).train()

        estado("evaluando el modelo adaptado")
        adaptado = evaluar(model, corpus, evals)
        model.save_pretrained(str(OUT / "adapter"))
        mejora = {m: round((adaptado[m] - base[m]) / base[m] * 100, 1) if base[m] else None
                  for m in ("r1", "r5", "r10", "mrr10", "ndcg10")}
        meta = {"r10": mejora["r10"] is not None and mejora["r10"] >= 8,
                "ndcg10": mejora["ndcg10"] is not None and mejora["ndcg10"] >= 8}
        resultado = {"base": base, "adaptado": adaptado, "mejora_relativa_pct": mejora, "meta_8pct": meta,
                     "pares": len(pares), "minutos": round((time.time() - t0) / 60, 1),
                     "gpu": torch.cuda.get_device_name(0), "vram_max_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
                     "config": vars(args)}
        (OUT / "metricas.json").write_text(json.dumps(resultado, indent=1, ensure_ascii=False), encoding="utf-8")
        estado(f"terminado: base {base} -> adaptado {adaptado}; mejora {mejora}")
    except Exception as e:
        log.exception("fallo")
        estado(f"fallo: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
