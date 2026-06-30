"""Send a grammar-constrained request to the model and return the parsed choices JSON.

This is the layer's only impure piece (network I/O); everything else is pure. Uses raw
/api/generate with manual ChatML (the chat endpoint chokes on grammar-fenced JSON). Endpoint and
model come from the environment."""
import json
import os
import urllib.error
import urllib.request


class ModelError(RuntimeError):
    """The model backend was unreachable, errored, or returned output we couldn't parse. Distinct
    from programming errors so the controller can map it to a 502 rather than a 500."""


def generate(prompt: str, schema: dict, *, num_ctx=2048, num_predict=1024,
             temperature=0.7, top_p=0.95, num_gpu=99, timeout=300) -> dict:
    base, model = os.environ["OLLAMA_URL"], os.environ["MODEL"]
    body = {
        "model": model, "prompt": prompt, "raw": True, "stream": False, "format": schema,
        "options": {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": temperature,
                    "top_p": top_p, "num_gpu": num_gpu, "stop": ["<|im_end|>"]},
    }
    req = urllib.request.Request(base + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ModelError(f"model backend unreachable at {base}: {e}") from e
    except json.JSONDecodeError as e:
        raise ModelError(f"model backend returned non-JSON envelope: {e}") from e
    try:
        return json.loads(resp.get("response", "").strip())
    except (json.JSONDecodeError, AttributeError) as e:
        raise ModelError(f"model returned no/invalid JSON in 'response': {e}") from e
