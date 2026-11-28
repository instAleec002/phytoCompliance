# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "torch>=2.7",
#   "transformers>=4.45",
#   "numpy>=2",
# ]
# [tool.uv.sources]
# torch = { index = "pytorch-cu128" }
# [[tool.uv.index]]
# name = "pytorch-cu128"
# url = "https://download.pytorch.org/whl/cu128"
# explicit = true
# ///
"""Encodes the corpus chunks with BGE-M3 on the GPU machine, exactly as assistant.retrieval.embeddings.BgeM3 does on
the main machine: CLS of the last hidden state, L2-normalised, fp16 on CUDA, up to 1024 tokens. Only the vectors travel
back; the database never leaves the main machine.

    uv run encode.py [--lote 32] [--max-tokens 1024]

Reads textos.jsonl ({"chunk_id", "text"}); writes salida/vectores.npy (float32, one row per chunk), salida/ids.json and
salida/meta.json. Progress in estado.txt for gpu_job.ps1. Texts are sorted by length so each batch pads little."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "salida"


def estado(t: str) -> None:
    (HERE / "estado.txt").write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {t}\n", encoding="utf-8")
    print(t, flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--modelo", default="BAAI/bge-m3")
    p.add_argument("--lote", type=int, default=32)
    p.add_argument("--max-tokens", type=int, default=1024)
    args = p.parse_args()
    t0 = time.time()
    try:
        import numpy as np
        import torch
        from transformers import AutoModel, AutoTokenizer

        rows = [json.loads(l) for l in open(HERE / "textos.jsonl", encoding="utf-8") if l.strip()]
        estado(f"preparando: {len(rows)} fragmentos, GPU {torch.cuda.get_device_name(0)}")
        tok = AutoTokenizer.from_pretrained(args.modelo)
        model = AutoModel.from_pretrained(args.modelo, dtype=torch.float16).to("cuda").eval()
        order = sorted(range(len(rows)), key=lambda i: len(rows[i]["text"]))
        vecs = np.zeros((len(rows), model.config.hidden_size), dtype=np.float32)
        with torch.inference_mode():
            for k in range(0, len(order), args.lote):
                idx = order[k:k + args.lote]
                batch = tok([rows[i]["text"] for i in idx], padding=True, truncation=True, max_length=args.max_tokens,
                            return_tensors="pt").to("cuda")
                cls = model(**batch).last_hidden_state[:, 0]
                cls = torch.nn.functional.normalize(cls.float(), dim=-1)
                vecs[idx] = cls.cpu().numpy()
                if (k // args.lote) % 20 == 0:
                    estado(f"codificando: {min(k + args.lote, len(order))}/{len(order)}")
        OUT.mkdir(exist_ok=True)
        np.save(OUT / "vectores.npy", vecs)
        (OUT / "ids.json").write_text(json.dumps([r["chunk_id"] for r in rows]), encoding="utf-8")
        meta = {"modelo": args.modelo, "pooling": "cls", "normalizado": True, "dtype": "float16", "max_tokens": args.max_tokens,
                "fragmentos": len(rows), "segundos": round(time.time() - t0, 1), "gpu": torch.cuda.get_device_name(0),
                "vram_max_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2)}
        (OUT / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        estado(f"terminado: {len(rows)} vectores en {meta['segundos']} s")
    except Exception as e:
        estado(f"fallo: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
