from __future__ import annotations

import json
import os
import time
from io import BytesIO
from typing import Generator

from flask import Flask, Response, jsonify, render_template, request, send_file

from crawler import CrawlConfig, CrawlerController, graph_payload, normalize_url
from state import AppState


app = Flask(__name__)
state = AppState()
controller = CrawlerController(state)


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    with state.lock:
        payload = {
            "meta": state.snapshot_meta(),
            "graph": graph_payload(state.graph),
            "has_circuit": state.latest_circuit_png is not None,
            "latest_circuit_meta": state.latest_circuit_meta,
        }
    return jsonify(payload)


@app.post("/api/crawl/start")
def api_crawl_start():
    body = request.get_json(silent=True) or {}
    seed_url = normalize_url(str(body.get("seed_url", "")).strip())
    if not seed_url:
        return jsonify({"ok": False, "error": "Please provide a valid http(s) seed URL."}), 400

    config = CrawlConfig(
        seed_url=seed_url,
        max_pages=max(1, min(int(body.get("max_pages", 50)), 300)),
        max_depth=max(0, min(int(body.get("max_depth", 2)), 6)),
        concurrency=max(1, min(int(body.get("concurrency", 5)), 20)),
        request_timeout=max(3, min(int(body.get("request_timeout", 15)), 60)),
        same_domain_only=bool(body.get("same_domain_only", True)),
    )
    try:
        controller.start(config)
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, "config": config.as_dict()})


@app.post("/api/crawl/stop")
def api_crawl_stop():
    controller.stop()
    return jsonify({"ok": True})


@app.get("/api/stream")
def api_stream() -> Response:
    def generate() -> Generator[str, None, None]:
        last_id = -1
        initial = {
            "type": "snapshot",
            "message": "Initial state",
            "graph": graph_payload(state.graph),
            "meta": state.snapshot_meta(),
            "circuit_updated": state.latest_circuit_png is not None,
            "latest_circuit_meta": state.latest_circuit_meta,
        }
        yield f"id: {last_id}\nevent: snapshot\ndata: {json.dumps(initial, ensure_ascii=False)}\n\n"
        while True:
            events = state.wait_for_events(last_id, timeout=10.0)
            if not events:
                heartbeat = {"type": "heartbeat", "ts": time.time()}
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat)}\n\n"
                continue

            for event in events:
                last_id = max(last_id, event["id"])
                payload = dict(event)
                if payload.get("type") == "snapshot":
                    payload["latest_circuit_meta"] = state.latest_circuit_meta
                    payload["circuit_updated"] = state.latest_circuit_png is not None
                event_name = payload.get("type", "message")
                yield f"id: {payload['id']}\nevent: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(generate(), mimetype="text/event-stream", headers=headers)


@app.get("/api/circuit/latest.png")
def api_circuit_png():
    with state.lock:
        if not state.latest_circuit_png:
            return jsonify({"ok": False, "error": "No quantum circuit available yet."}), 404
        png_bytes = state.latest_circuit_png
    return send_file(BytesIO(png_bytes), mimetype="image/png", max_age=0)


@app.get("/health")
def health():
    return jsonify({"ok": True, "running": state.running})


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=True, threaded=True)
