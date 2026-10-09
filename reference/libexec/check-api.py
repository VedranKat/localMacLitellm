#!/usr/bin/env python3
"""A temporary local provider verifies inference and spending without charges."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

def check_api(admin):
    calls = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(request.get("stream", False))
            common = {"id": "chatcmpl-local-check", "created": int(time.time()), "model": "gpt-4o-mini"}
            self.send_response(200)
            if request.get("stream"):
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for chunk in (
                    {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "OK"}, "finish_reason": None}]},
                    {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                    {**common, "object": "chat.completion.chunk", "choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4}},
                ):
                    self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            else:
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({**common, "object": "chat.completion", "choices": [{"index": 0,
                    "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4}}).encode())
    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    provider.daemon_threads = True
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    owner = "local-verification-" + uuid4().hex
    alias = "local-check-" + uuid4().hex
    model_id = None
    keys = []
    try:
        admin.call("/user/new", {"user_id": owner, "user_role": "internal_user_viewer", "auto_create_key": False})
        model = admin.call("/model/new", {"model_name": alias,
            "litellm_params": {"model": "openai/gpt-4o-mini", "api_base": f"http://127.0.0.1:{provider.server_port}/v1", "api_key": "local-fixture-only"},
            "model_info": {"input_cost_per_token": 0.0001, "output_cost_per_token": 0.0001}})
        model_id = model.get("model_info", {}).get("id") or model.get("id")
        if not model_id:
            raise RuntimeError("Could not identify disposable model")
        for label in ("normal", "stream", "budget"):
            result = admin.call("/key/generate", {"user_id": owner, "key_alias": owner + "-" + label,
                "models": [alias], "max_budget": 0.00000001 if label == "budget" else 1,
                "budget_duration": "1d", "rpm_limit": 60, "max_parallel_requests": 4,
                "allowed_routes": ["/v1/chat/completions", "/chat/completions", "/v1/models", "/models"]})
            keys.append(result["key"])
        for stream, key in zip((False, True), keys):
            body = {"model": alias, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 8, "stream": stream}
            if stream:
                body["stream_options"] = {"include_usage": True}
            request = urllib.request.Request("http://127.0.0.1:4000/v1/chat/completions", data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=30) as response:
                result = response.read()
                if b"OK" not in result:
                    raise RuntimeError("Inference result failed")
            # Wait for asynchronous DB cost updates without ever printing keys.
            for attempt in range(30):
                info = admin.call("/key/info?key=" + key).get("info", {})
                if float(info.get("spend", 0)) > 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Usage cost was not captured")
        before = len(calls)
        try:
            admin.call("/v1/chat/completions", {"model": alias, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 8}, keys[2])
            raise RuntimeError("Tiny budget did not block inference")
        except RuntimeError as error:
            if not any("HTTP " + code in str(error) for code in ("422", "429", "400")):
                raise
        if len(calls) != before:
            raise RuntimeError("Budget rejection still contacted the provider")
        try:
            admin.call("/v1/chat/completions", {"model": "unauthorized-model", "messages": [{"role": "user", "content": "Hi"}]}, keys[0])
            raise RuntimeError("Model restriction failed")
        except RuntimeError as error:
            if not any("HTTP " + code in str(error) for code in ("401", "403")):
                raise
        for path, body in (("/key/list", None), ("/user/list", None), ("/prompts/test", {})):
            try:
                admin.call(path, body, keys[0])
                raise RuntimeError("Inference key reached a management route")
            except RuntimeError as error:
                if not any("HTTP " + code in str(error) for code in ("401", "403")):
                    raise
        admin.call("/v1/models", key=keys[0])
        deleted = keys.pop(0)
        admin.call("/key/delete", {"keys": [deleted]})
        try:
            admin.call("/v1/models", key=deleted)
            raise RuntimeError("Revoked key remained usable")
        except RuntimeError as error:
            if not any("HTTP " + code in str(error) for code in ("401", "403")):
                raise
        print("Local inference, streaming cost accounting, dollar budget, model restrictions and revocation passed.")
    finally:
        if keys:
            admin.call("/key/delete", {"keys": keys})
        if model_id:
            admin.call("/model/delete", {"id": model_id})
        admin.call("/user/delete", {"user_ids": [owner]})
        provider.shutdown()
        provider.server_close()
