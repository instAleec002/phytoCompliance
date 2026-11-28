"""Generators, by name. Each takes a system instruction and a user prompt and returns the text plus usage.

- ``gemini``: Gemini Flash ("modo nube"). With ``GEMINI_API_KEY`` (Google AI Studio) it uses that key; otherwise
  Vertex AI with the machine's ADC credentials (``VERTEX_PROJECT``, ``VERTEX_LOCATION``). ``backend`` forces one.
- ``local``: any OpenAI-compatible server (Ollama, llama.cpp, vLLM) serving Qwen3-8B, for the local mode on the GPU.
- ``extractive``: no language model; returns the top passages with their citation marks. For tests and as the honest
  floor when no model is reachable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from knowledge.documents.registry import Registry, register
from shared.settings import settings

GENERATORS = Registry("generador")


@dataclass
class Generation:
    text: str
    model: str
    seconds: float
    usage: dict = field(default_factory=dict)


@register(GENERATORS, "gemini")
class GeminiGenerator:
    def __init__(self, model: str = "gemini-2.5-flash", temperature: float = 0.1, max_output_tokens: int = 1024,
                 backend: str = "auto", thinking_level: str | None = "low", **_):
        self.thinking_level = thinking_level
        from google import genai

        use_key = backend == "ai_studio" or (backend == "auto" and settings.gemini_api_key)
        if use_key:
            self.client = genai.Client(api_key=settings.gemini_api_key)
            self.backend = "ai_studio"
        else:
            self.client = genai.Client(vertexai=True, project=settings.vertex_project, location=settings.vertex_location)
            self.backend = "vertex"
        self.model, self.temperature, self.max_output_tokens = model, temperature, max_output_tokens
        self.name = f"gemini:{model}@{self.backend}"

    def generate(self, system: str, prompt: str) -> Generation:
        from google.genai import types

        t0 = time.perf_counter()
        # thinking tokens count against max_output_tokens: with a small budget the visible answer is cut mid-sentence
        thinking = types.ThinkingConfig(thinking_level=self.thinking_level) if self.thinking_level else None
        r = self.client.models.generate_content(
            model=self.model, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system, temperature=self.temperature,
                                               max_output_tokens=self.max_output_tokens, thinking_config=thinking))
        u = r.usage_metadata
        finish = r.candidates[0].finish_reason if r.candidates else None
        usage = {"prompt_tokens": getattr(u, "prompt_token_count", None),
                 "output_tokens": getattr(u, "candidates_token_count", None),
                 "thinking_tokens": getattr(u, "thoughts_token_count", None),
                 "finish_reason": getattr(finish, "name", finish)} if u else {}
        return Generation(text=(r.text or "").strip(), model=self.name, seconds=round(time.perf_counter() - t0, 2),
                          usage=usage)


@register(GENERATORS, "local")
class LocalGenerator:
    """OpenAI-compatible chat endpoint (``/v1/chat/completions``)."""

    def __init__(self, base_url: str = "http://localhost:11434/v1", model: str = "qwen3:8b", temperature: float = 0.1,
                 max_output_tokens: int = 1024, timeout_s: float = 300, think: bool | None = None,
                 seed: int | None = None, **_):
        """``think=False`` turns Qwen3's reasoning off. The OpenAI-compatible endpoint of Ollama ignores «/no_think»
        (measured 11/11/2026: 324 tokens to answer «{"entra": true}»), so it goes through Ollama's native /api/chat with
        ``think: false`` (7 tokens)."""
        self.base_url, self.model = base_url.rstrip("/"), model
        self.temperature, self.max_output_tokens, self.seed = temperature, max_output_tokens, seed
        self.http = httpx.Client(timeout=timeout_s)
        self.think = think
        self.name = f"local:{model}" + (":sin-razonamiento" if think is False else "")

    def generate(self, system: str, prompt: str) -> Generation:
        t0 = time.perf_counter()
        if self.think is False:
            native = self.base_url.removesuffix("/v1")
            r = self.http.post(f"{native}/api/chat", json={
                "model": self.model, "stream": False, "think": False,
                "options": {"temperature": self.temperature, "num_predict": self.max_output_tokens,
                            **({"seed": self.seed} if self.seed is not None else {})},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt.replace(" /no_think", "")}]})
            r.raise_for_status()
            data = r.json()
            return Generation(text=data["message"]["content"].strip(), model=self.name,
                              seconds=round(time.perf_counter() - t0, 2),
                              usage={"prompt_tokens": data.get("prompt_eval_count"), "output_tokens": data.get("eval_count")})
        r = self.http.post(f"{self.base_url}/chat/completions", json={
            "model": self.model, "temperature": self.temperature, "max_tokens": self.max_output_tokens,
            **({"seed": self.seed} if self.seed is not None else {}),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        r.raise_for_status()
        data = r.json()
        return Generation(text=data["choices"][0]["message"]["content"].strip(), model=self.name,
                          seconds=round(time.perf_counter() - t0, 2), usage=data.get("usage", {}))


@register(GENERATORS, "extractive")
class ExtractiveGenerator:
    """Reads the numbered passages back out of the prompt and returns the first ``take`` with their marks."""

    name = "extractive"

    def __init__(self, take: int = 3, **_):
        self.take = take

    def generate(self, system: str, prompt: str) -> Generation:
        parts = [p for p in prompt.split("\n[") if p[:1].isdigit()]
        lines = []
        for p in parts[: self.take]:
            n, _, body = p.partition("]")
            text = body.split("\n", 2)[-1].strip().split("\n")[0][:300]
            lines.append(f"{text} [{n}]")
        return Generation(text="\n\n".join(lines), model=self.name, seconds=0.0)


def build_generator(cfg, generators_cfg: dict, name: str | None = None):
    name = name or cfg.name
    params = {"temperature": cfg.temperature, "max_output_tokens": cfg.max_output_tokens,
              **({"seed": cfg.seed} if getattr(cfg, "seed", None) is not None else {}), **generators_cfg.get(name, {})}
    return GENERATORS.create(name, **params)
