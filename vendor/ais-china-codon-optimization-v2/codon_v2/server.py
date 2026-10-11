"""Local trial server: bounded queue, one computation worker, in-memory jobs.

Sequence data never leaves this process except in explicit browser responses.
For internet deployment add authentication, TLS, isolation and persistent jobs.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from . import __version__
from .config import STRATEGIES, DEFAULT_BUDGET, validate_request
from .pipeline import optimize
from .references import ReferenceStore
from .report import export
from .rna import RNAEngine
from .sequence import InputError
from .web_assets import PUBLIC_ASSETS, WEB_ASSETS


class JobManager:
    def __init__(self, refs):
        self.refs, self.jobs, self.lock = refs, {}, threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="codon-compute")

    def submit(self, request):
        # Validate synchronously so input errors do not occupy queue slots.
        validate_request(request, self.refs)
        with self.lock:
            expired = [key for key, job in self.jobs.items() if job["state"] not in {"queued", "running"} and time.monotonic() - job["created"] > 7200]
            for key in expired:
                del self.jobs[key]
            if sum(job["state"] in {"queued", "running"} for job in self.jobs.values()) >= 4:
                raise OverflowError("The queue is full. Wait for an existing job to finish.")
            if len(self.jobs) >= 16:
                done = [key for key, job in self.jobs.items() if job["state"] not in {"queued", "running"}]
                if done:
                    del self.jobs[done[0]]
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {"state": "queued", "created": time.monotonic(), "cancel": threading.Event(), "report": None, "error": None}
            self.executor.submit(self._run, job_id, deepcopy(request))
        return job_id

    def _run(self, job_id, request):
        with self.lock:
            job = self.jobs[job_id]
            if job["cancel"].is_set():
                job["state"] = "cancelled"
                return
            job["state"] = "running"
        def progress(report):
            with self.lock:
                job["report"] = report
        try:
            result = optimize(request, self.refs, progress, job["cancel"].is_set)
            with self.lock:
                job["report"], job["state"] = result, "cancelled" if job["cancel"].is_set() else "finished"
        except Exception as exc:
            with self.lock:
                job["state"], job["error"] = "failed", f"{type(exc).__name__}: {exc}"

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = self.jobs[job_id]
            return deepcopy({"job_id": job_id, "state": job["state"], "report": job["report"], "error": job["error"]})

    def cancel(self, job_id):
        with self.lock:
            self.jobs[job_id]["cancel"].set()

    def close(self):
        with self.lock:
            for job in self.jobs.values():
                job["cancel"].set()
        self.executor.shutdown(wait=True, cancel_futures=True)


def create_server(host="127.0.0.1", port=8765, root=None):
    refs = ReferenceStore() if root is None else ReferenceStore(root)
    manager, token = JobManager(refs), secrets.token_urlsafe(32)
    engine = RNAEngine(refs.root)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # No sequences, query selections, or request bodies in logs.
            if args and "api/jobs" not in str(args[0]):
                super().log_message(format, *args)

        def send(self, value, status=200, content_type="application/json; charset=utf-8", filename=None, headers=None):
            body = value if isinstance(value, bytes) else (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def send_public_asset(self, filename):
            # Only names in the public manifest reach this method. Support byte
            # ranges so the reused hero video can seek without a full download.
            data = (refs.root / "public" / "assets" / filename).read_bytes()
            mime, total = PUBLIC_ASSETS[filename], len(data)
            headers = {"Accept-Ranges": "bytes"}
            requested = self.headers.get("Range")
            if not requested:
                return self.send(data, content_type=mime, headers=headers)
            try:
                unit, bounds = requested.split("=", 1)
                first, last = bounds.split("-", 1)
                if unit != "bytes" or (not first and not last):
                    raise ValueError
                if first:
                    start, end = int(first), min(int(last), total - 1) if last else total - 1
                else:
                    suffix = int(last)
                    if suffix <= 0:
                        raise ValueError
                    start, end = max(0, total - suffix), total - 1
                if start < 0 or start >= total or end < start:
                    raise ValueError
            except ValueError:
                return self.send(b"", 416, mime, headers={"Content-Range": f"bytes */{total}"})
            headers["Content-Range"] = f"bytes {start}-{end}/{total}"
            return self.send(data[start:end + 1], 206, mime, headers=headers)

        def check_host(self):
            authority = self.headers.get("Host", "")
            expected = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}", f"{host}:{self.server.server_port}"}
            return authority in expected

        def do_GET(self):
            if not self.check_host():
                return self.send({"error": "Invalid Host header"}, 403)
            url = urlsplit(self.path)
            try:
                if url.path == "/api/meta":
                    return self.send({"version": __version__, "token": token, "hosts": [h.metadata() for h in refs.hosts.values()],
                                      "strategies": STRATEGIES, "budget_defaults": DEFAULT_BUDGET,
                                      "rna": {"available": engine.reason is None, "reason": engine.reason, "model": engine.config},
                                      "limits": {"cds_nt": 9000, "upstream_nt": 300, "candidates_per_strategy": 1}})
                if url.path == "/api/example":
                    return self.send((refs.root / "examples/request.json").read_bytes())
                if url.path.startswith("/api/references/"):
                    parts = url.path.strip("/").split("/")
                    if len(parts) == 4 and parts[3] == "codons.csv" and parts[2] in refs.hosts:
                        reference = refs.hosts[parts[2]]
                        path = refs.root / reference.config["reference_directory"] / "codon_parameters.csv"
                        return self.send(path.read_bytes(), content_type="text/csv; charset=utf-8", filename=parts[2] + "-codon-parameters.csv")
                    raise KeyError("reference")
                if url.path.startswith("/api/jobs/"):
                    parts = url.path.strip("/").split("/")
                    if len(parts) not in (3, 4):
                        raise KeyError("route")
                    job = manager.get(parts[2])
                    if len(parts) == 3:
                        return self.send(job)
                    if parts[3] in {"json", "csv", "fasta"} and job["report"]:
                        query = parse_qs(url.query)
                        ids = query.get("ids", [None])[0]
                        body, mime = export(job["report"], parts[3], ids.split(",") if ids else None)
                        return self.send(body, content_type=mime, filename=f"codon-v2-{parts[2][:8]}.{parts[3]}")
                    raise KeyError("export")
                if url.path in WEB_ASSETS:
                    name, mime = WEB_ASSETS[url.path]
                    return self.send((refs.root / "web" / name).read_bytes(), content_type=mime)
                if url.path.startswith("/assets/") and url.path[8:] in PUBLIC_ASSETS:
                    return self.send_public_asset(url.path[8:])
                if url.path == "/favicon.ico":
                    return self.send(b"", 204)
                self.send({"error": "Not found"}, 404)
            except KeyError:
                self.send({"error": "This job does not exist or has expired. Run the optimization again."}, 404)
            except ValueError as exc:
                self.send({"error": str(exc)}, 400)
            except OSError:
                self.send({"error": "The requested local file is unavailable."}, 404)

        def do_POST(self):
            if not self.check_host() or self.headers.get("X-Codon-Token") != token:
                return self.send({"error": "Submit requests from the local application page."}, 403)
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return self.send({"error": "Origin rejected"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 131072:
                    return self.send({"error": "Request size must be between 1 and 131072 bytes."}, 413)
                raw = json.loads(self.rfile.read(length))
                if self.path == "/api/jobs":
                    return self.send({"job_id": manager.submit(raw), "state": "queued"}, 202)
                parts = self.path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "cancel":
                    manager.cancel(parts[2])
                    return self.send({"status": "cancellation_requested"})
                return self.send({"error": "Not found"}, 404)
            except InputError as exc:
                self.send({"error": str(exc), "field": exc.field, "status": "input_invalid"}, 400)
            except OverflowError as exc:
                self.send({"error": str(exc)}, 429)
            except KeyError:
                self.send({"error": "This job does not exist."}, 404)
            except (ValueError, UnicodeError, TypeError) as exc:
                self.send({"error": str(exc), "status": "input_invalid"}, 400)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.manager = manager
    return server


def serve(host="127.0.0.1", port=8765):
    server = create_server(host, port)
    print(f"Codon V2 {__version__}: http://{host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.manager.close()
        server.server_close()
