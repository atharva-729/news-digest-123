"""The only module that talks to a model API. Swapping providers is a change to this file (and config.yaml)."""
import json
import logging
import os
import time

import httpx
import truststore
from dotenv import load_dotenv

from digest.common import load_config

# Python 3.13+ rejects the corporate TLS-inspection CA unless we use the OS trust store.
truststore.inject_into_ssl()

log = logging.getLogger(__name__)


def _env(name):
    load_dotenv()
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set (put it in .env or the environment)")
    return value


def _call(messages, **extra):
    """Try the configured model, then each fallback, with exponential backoff on each."""
    cfg = load_config()["model"]
    models = [cfg["name"], *cfg.get("fallbacks", [])]
    base_url = _env("FOUNDRY_BASE_URL").rstrip("/")
    headers = {"Authorization": f"Bearer {_env('FOUNDRY_TOKEN')}:{cfg.get('project', 'l1l2l3')}"}
    last_err = None
    for model in models:
        body = {"model": model, "messages": messages, **cfg.get("params", {}), **extra}
        for attempt in range(cfg.get("max_retries", 4)):
            try:
                # Without a timeout an overloaded model can hang a request indefinitely and stall the cron run.
                r = httpx.post(f"{base_url}/chat/completions", json=body, headers=headers, timeout=180)
                r.raise_for_status()
                data = r.json()
                choice = data["choices"][0]
                if not choice["message"].get("content"):
                    raise ValueError(f"empty response (finish reason: {choice.get('finish_reason')})")
                log.info("%s usage: %s", model, data.get("usage"))
                return choice["message"]["content"]
            except Exception as e:  # 429/5xx from the API, empty or truncated output
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


def generate_json(prompt, schema, **params):
    """Return a dict that matches `schema` (a JSON Schema dict). `params` override config, e.g. reasoning_effort."""
    fmt = {"type": "json_schema", "json_schema": {"name": "result", "schema": _strict(schema), "strict": True}}
    return json.loads(_call([{"role": "user", "content": prompt}], response_format=fmt, **params))


def generate_text(prompt, **params):
    return _call([{"role": "user", "content": prompt}], **params)
