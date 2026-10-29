"""The only module that talks to a model API. Swapping providers is a change to this file (and config.yaml)."""
import json
import logging
import os
import re
import time

import httpx
from dotenv import load_dotenv

from digest.common import DATA, load_config, today_ist

log = logging.getLogger(__name__)

# Scripts that should never appear in our English output unless the prompt had them (Cyrillic, CJK, Hangul).
STRAY_SCRIPT = re.compile(r"[Ѐ-ӿ぀-ヿ一-鿿가-힯]+")
ENGLISH_ONLY = "Write only in English. Your previous answer slipped in a word from another language."


def _env(name):
    load_dotenv()
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set (put it in .env or the environment)")
    return value


def _log_usage(tag, model, usage, seconds):
    """Append one line per call to data/llm_usage.jsonl: what called the model, tokens, and estimated cost."""
    usage = usage or {}
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    prompt, completion = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    price = (load_config()["model"].get("prices") or {}).get(model)
    usd = None
    if price:
        usd = round(((prompt - cached) * price["input"] + cached * price["cached_input"]
                     + completion * price["output"]) / 1e6, 6)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "run_date": today_ist(), "tag": tag, "model": model,
           "prompt_tokens": prompt, "cached_tokens": cached, "completion_tokens": completion,
           "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
           "seconds": round(seconds, 1), "usd": usd}
    with open(DATA / "llm_usage.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def log_note(tag, **fields):
    """A non-call row in data/llm_usage.jsonl, e.g. how many proposals a verify pass dropped."""
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "run_date": today_ist(), "tag": tag, "kind": "note", **fields}
    with open(DATA / "llm_usage.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _call(messages, tag="untagged", model=None, **extra):
    """Try `model` (if a step overrides it), then the configured model and each fallback, with backoff on each."""
    cfg = load_config()["model"]
    models = list(dict.fromkeys(m for m in [model, cfg["name"], *cfg.get("fallbacks", [])] if m))
    base_url = _env("FOUNDRY_BASE_URL").rstrip("/")
    headers = {"Authorization": f"Bearer {_env('FOUNDRY_TOKEN')}:{cfg.get('project', 'l1l2l3')}"}
    last_err = None
    prompt_has_stray = bool(STRAY_SCRIPT.search(" ".join(m["content"] for m in messages)))
    for model in models:
        body = {"model": model, "messages": messages, **cfg.get("params", {}), **extra}
        for attempt in range(cfg.get("max_retries", 4)):
            try:
                # Without a timeout an overloaded model can hang a request indefinitely and stall the cron run.
                t0 = time.time()
                r = httpx.post(f"{base_url}/chat/completions", json=body, headers=headers, timeout=180)
                r.raise_for_status()
                data = r.json()
                choice = data["choices"][0]
                if not choice["message"].get("content"):
                    raise ValueError(f"empty response (finish reason: {choice.get('finish_reason')})")
                log.info("%s [%s] usage: %s", model, tag, data.get("usage"))
                _log_usage(tag, model, data.get("usage"), time.time() - t0)
                content = choice["message"]["content"]
                if not prompt_has_stray and STRAY_SCRIPT.search(content):
                    # Seen once: a Russian word in an English answer. Ask again with an explicit instruction,
                    # which also changes the request so the gateway can't hand back a cached copy.
                    body = {**body, "messages": messages + [{"role": "system", "content": ENGLISH_ONLY}]}
                    raise ValueError(f"answer contains non-English script: {STRAY_SCRIPT.search(content).group(0)!r}")
                return content
            except Exception as e:  # 429/5xx from the API, empty or truncated output, stray script
                last_err = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (400, 401, 403, 404):
                    log.warning("%s rejected the request (%s): %s", model, status, e.response.text[:200])
                    break  # bad model name or auth: retrying won't help
                wait = 2 ** attempt * 3
                log.warning("%s attempt %d failed: %s; retrying in %ds", model, attempt + 1, str(e)[:200], wait)
                time.sleep(wait)
        log.warning("giving up on %s, trying next model", model)
    raise RuntimeError(f"all models failed; last error: {last_err}")


def _strict(schema):
    """Strict mode guarantees the shape, but needs every object closed and every property required."""
    if isinstance(schema, dict):
        schema = {k: _strict(v) for k, v in schema.items()}
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            schema["required"] = list(schema.get("properties", {}))
    elif isinstance(schema, list):
        schema = [_strict(v) for v in schema]
    return schema


def generate_json(prompt, schema, tag="untagged", **params):
    """Return a dict that matches `schema` (a JSON Schema dict). `tag` names the caller in the usage log;
    `params` override config, e.g. reasoning_effort."""
    fmt = {"type": "json_schema", "json_schema": {"name": "result", "schema": _strict(schema), "strict": True}}
    return json.loads(_call([{"role": "user", "content": prompt}], tag=tag, response_format=fmt, **params))


def generate_text(prompt, tag="untagged", **params):
    return _call([{"role": "user", "content": prompt}], tag=tag, **params)
