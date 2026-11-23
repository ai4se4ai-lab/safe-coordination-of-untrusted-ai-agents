"""Stdlib-only Ollama chat client shared by the LLM studies."""
import json
import time
import urllib.request


def chat(host, model, prompt, temperature=0.2, seed=0, num_predict=2500, num_ctx=8192, timeout=900):
    body = {"model": model, "stream": False, "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": temperature, "seed": seed, "num_predict": num_predict, "num_ctx": num_ctx}}
    if "gpt-oss" in model:
        body["think"] = "low"
    started, error, response = time.monotonic(), None, None
    for _ in range(3):
        try:
            request = urllib.request.Request(host.rstrip("/") + "/api/chat", json.dumps(body).encode(),
                                             {"Content-Type": "application/json"})
            response = json.load(urllib.request.urlopen(request, timeout=timeout))
            error = None
            break
        except Exception as e:  # noqa: BLE001 transport failure: retry the identical call
            error = repr(e)
            time.sleep(3)
    response = response or {}
    return response.get("message", {}).get("content", ""), {
        "prompt_tokens": response.get("prompt_eval_count"), "output_tokens": response.get("eval_count"),
        "seconds": time.monotonic() - started, "transport_error": error}
