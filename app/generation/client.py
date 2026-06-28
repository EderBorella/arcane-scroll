"""Send a grammar-constrained request to the model and return the parsed choices JSON.

This is the layer's only impure piece (network I/O); everything else is pure. Uses raw
/api/generate with manual ChatML (the chat endpoint chokes on grammar-fenced JSON). Endpoint and
model come from the environment."""
import json
import os
import urllib.request


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
    resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    return json.loads(resp.get("response", "").strip())
