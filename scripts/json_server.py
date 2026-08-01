#!/usr/bin/env python3
"""Local static file + JSON REST API server for time_tracker_json.html.

Backs the app with a single JSON file (data/time-tracking.json) instead of
Firestore. See README.md's "Local JSON file" section for the data model
this implements.
"""

import argparse
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "data" / "time-tracking.json"

EMPTY_DB = {"timeEntries": [], "activeTimer": None, "clients": []}

_lock = threading.Lock()


def load_db():
    if not DATA_FILE.exists():
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        save_db(EMPTY_DB)
        return dict(EMPTY_DB)
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_db(db):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(db, f, indent=2)
    tmp.replace(DATA_FILE)


def seed_clients_if_empty(db):
    if db["clients"] or not db["timeEntries"]:
        return
    by_client = {}
    for e in db["timeEntries"]:
        client = e.get("client")
        if not client:
            continue
        projects = by_client.setdefault(client, [])
        project = e.get("project")
        if project and project not in projects:
            projects.append(project)
    for name, projects in by_client.items():
        db["clients"].append({"id": uuid.uuid4().hex, "name": name, "projects": projects})


ENTRY_ID_RE = re.compile(r"^/api/entries/([^/]+)$")
CLIENT_ID_RE = re.compile(r"^/api/clients/([^/]+)$")


class Handler(BaseHTTPRequestHandler):
    server_version = "TimeTrackingJSON/1.0"

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def log_message(self, fmt, *args):
        pass

    # ---- routing ----

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/entries":
            with _lock:
                db = load_db()
            return self._send_json(200, {"timeEntries": db["timeEntries"]})

        if path == "/api/timer":
            with _lock:
                db = load_db()
            return self._send_json(200, {"activeTimer": db["activeTimer"]})

        if path == "/api/clients":
            with _lock:
                db = load_db()
            return self._send_json(200, {"clients": db["clients"]})

        self._serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/entries":
            body = self._read_json_body()
            with _lock:
                db = load_db()
                record = {**body, "id": uuid.uuid4().hex}
                db["timeEntries"].append(record)
                save_db(db)
            return self._send_json(201, record)

        if path == "/api/entries/bulk-delete":
            body = self._read_json_body()
            ids = set(body.get("ids", []))
            with _lock:
                db = load_db()
                db["timeEntries"] = [e for e in db["timeEntries"] if e["id"] not in ids]
                save_db(db)
            return self._send_json(200, {"ok": True})

        if path == "/api/clients":
            body = self._read_json_body()
            with _lock:
                db = load_db()
                record = {"id": uuid.uuid4().hex, "name": body["name"], "projects": body.get("projects", [])}
                db["clients"].append(record)
                save_db(db)
            return self._send_json(201, record)

        self._send_json(404, {"error": "not found"})

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path

        m = ENTRY_ID_RE.match(path)
        if m:
            entry_id = m.group(1)
            body = self._read_json_body()
            with _lock:
                db = load_db()
                idx = next((i for i, e in enumerate(db["timeEntries"]) if e["id"] == entry_id), None)
                record = {**body, "id": entry_id}
                if idx is None:
                    db["timeEntries"].append(record)
                else:
                    db["timeEntries"][idx] = record
                save_db(db)
            return self._send_json(200, record)

        if path == "/api/timer":
            body = self._read_json_body()
            with _lock:
                db = load_db()
                db["activeTimer"] = body
                save_db(db)
            return self._send_json(200, db["activeTimer"])

        m = CLIENT_ID_RE.match(path)
        if m:
            client_id = m.group(1)
            body = self._read_json_body()
            with _lock:
                db = load_db()
                client = next((c for c in db["clients"] if c["id"] == client_id), None)
                if client is None:
                    return self._send_json(404, {"error": "client not found"})
                client.update(body)
                save_db(db)
            return self._send_json(200, client)

        self._send_json(404, {"error": "not found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        m = ENTRY_ID_RE.match(path)
        if m:
            entry_id = m.group(1)
            with _lock:
                db = load_db()
                db["timeEntries"] = [e for e in db["timeEntries"] if e["id"] != entry_id]
                save_db(db)
            return self._send_json(200, {"ok": True})

        if path == "/api/timer":
            with _lock:
                db = load_db()
                db["activeTimer"] = None
                save_db(db)
            return self._send_json(200, {"ok": True})

        m = CLIENT_ID_RE.match(path)
        if m:
            client_id = m.group(1)
            query = parse_qs(parsed.query)
            project = query.get("project", [None])[0]
            with _lock:
                db = load_db()
                client = next((c for c in db["clients"] if c["id"] == client_id), None)
                if client is None:
                    return self._send_json(404, {"error": "client not found"})
                if project:
                    db["timeEntries"] = [
                        e for e in db["timeEntries"]
                        if not (e.get("client") == client["name"] and e.get("project") == project)
                    ]
                    client["projects"] = [p for p in client["projects"] if p != project]
                else:
                    db["timeEntries"] = [e for e in db["timeEntries"] if e.get("client") != client["name"]]
                    db["clients"] = [c for c in db["clients"] if c["id"] != client_id]
                save_db(db)
            return self._send_json(200, {"ok": True})

        self._send_json(404, {"error": "not found"})

    # ---- static file serving ----

    def _serve_static(self, path):
        if path == "/":
            path = "/time_tracker_json.html"
        rel = path.lstrip("/")
        file_path = (REPO_ROOT / rel).resolve()
        if REPO_ROOT not in file_path.parents and file_path != REPO_ROOT:
            return self._send_json(403, {"error": "forbidden"})
        if not file_path.is_file():
            return self._send_json(404, {"error": "not found"})

        content_type = "text/html"
        if file_path.suffix == ".js":
            content_type = "text/javascript"
        elif file_path.suffix == ".json":
            content_type = "application/json"
        elif file_path.suffix == ".css":
            content_type = "text/css"

        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8934)
    args = parser.parse_args()

    with _lock:
        db = load_db()
        seed_clients_if_empty(db)
        save_db(db)

    server = ThreadingHTTPServer(("localhost", args.port), Handler)
    print(f"Serving time_tracker_json.html + API at http://localhost:{args.port}/time_tracker_json.html")
    print(f"Data file: {DATA_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
