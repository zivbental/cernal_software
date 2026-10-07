"""Stateless hosting adapter. Each optimization finishes in its HTTP request.

No job IDs, shared sequence storage, or background tasks are used. The optimizer
and frozen scientific references are the same as in the local application.
"""
import json
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, Response, request, send_file
from werkzeug.exceptions import HTTPException

from . import __version__
from .config import DEFAULT_BUDGET, STRATEGIES, validate_request
from .pipeline import optimize
from .references import ReferenceStore
from .report import export
from .rna import RNAEngine
from .sequence import InputError
from .web_assets import PUBLIC_ASSETS

ONLINE_WALL_SECONDS = 40
ONLINE_DEADLINE_SECONDS = 240
MAX_REQUEST_BYTES = 131072
MAX_RESPONSE_BYTES = 4400000


def create_app(root=None):
    refs = ReferenceStore() if root is None else ReferenceStore(root)
    engine = RNAEngine(refs.root)
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = MAX_REQUEST_BYTES
    # A single native RNA calculation runs at a time inside this instance.
    # A second request can retry; it must not wait behind an unbounded queue.
    compute_lock = threading.Lock()

    def reply(value, status=200, content_type='application/json; charset=utf-8', filename=None):
        if not isinstance(value, (str, bytes)):
            value = json.dumps(value, ensure_ascii=False, allow_nan=False)
        response = Response(value, status=status, content_type=content_type)
        if filename:
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @app.after_request
    def response_headers(response):
        response.headers.update({
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        })
        return response

    @app.before_request
    def same_origin_post():
        if request.method != 'POST':
            return None
        origin = request.headers.get('Origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in {'http', 'https'} or parsed.netloc != request.host or parsed.path or parsed.query or parsed.fragment:
                return reply({'error': 'Submit requests from this application page.'}, 403)
        if request.mimetype != 'application/json':
            return reply({'error': 'Content-Type must be application/json.'}, 415)
        if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
            return reply({'error': 'Request is too large.'}, 413)

    @app.errorhandler(InputError)
    def input_error(exc):
        return reply({'error': str(exc), 'field': exc.field, 'status': 'input_invalid'}, 400)

    @app.errorhandler(HTTPException)
    def http_error(exc):
        messages = {400: 'Invalid JSON request.', 404: 'Not found.', 405: 'Method not allowed.', 413: 'Request is too large.'}
        return reply({'error': messages.get(exc.code, exc.name)}, exc.code)

    @app.get('/api/meta')
    def metadata():
        return reply({'version': __version__, 'execution_mode': 'online',
                      'hosts': [h.metadata() for h in refs.hosts.values()],
                      'strategies': STRATEGIES, 'budget_defaults': DEFAULT_BUDGET,
                      'rna': {'available': engine.reason is None, 'reason': engine.reason, 'model': engine.config},
                      'limits': {'cds_nt': 9000, 'upstream_nt': 300, 'candidates_per_strategy': 1,
                                 'wall_seconds_per_strategy': ONLINE_WALL_SECONDS,
                                 'request_deadline_seconds': ONLINE_DEADLINE_SECONDS}})

    @app.get('/api/example')
    def example():
        return reply((refs.root / 'examples/request.json').read_bytes())

    @app.get('/api/references/<host_id>/codons.csv')
    def codon_table(host_id):
        if host_id not in refs.hosts:
            return reply({'error': 'Unknown host reference.'}, 404)
        path = refs.root / refs.hosts[host_id].config['reference_directory'] / 'codon_parameters.csv'
        return reply(path.read_bytes(), content_type='text/csv; charset=utf-8', filename=host_id + '-codon-parameters.csv')

    @app.post('/api/optimize')
    def run():
        raw = request.get_json()
        normalized, *_ = validate_request(raw, refs)
        if normalized['search_budget']['wall_seconds'] > ONLINE_WALL_SECONDS:
            raise InputError('Online runs support up to 40 seconds per preference. Use the local application for larger budgets.', 'search_budget')
        if not compute_lock.acquire(blocking=False):
            response = reply({'error': 'This worker is busy. Try again shortly.'}, 429)
            response.headers['Retry-After'] = '5'
            return response
        deadline = time.monotonic() + ONLINE_DEADLINE_SECONDS
        timed_out = False

        def deadline_reached():
            nonlocal timed_out
            timed_out = timed_out or time.monotonic() >= deadline
            return timed_out

        try:
            result = optimize(raw, refs, cancelled=deadline_reached)
            result['run']['execution'] = {'mode': 'online', 'deadline_seconds': ONLINE_DEADLINE_SECONDS,
                                           'deadline_reached': timed_out, 'persistent_result_storage': False}
            if timed_out:
                # The callback is a resource limit here, not a user cancellation.
                result['status'] = 'partial_results' if result['candidates'] else 'no_results'
                result['warnings'].append('online_time_limit_reached')
                for status in result['strategy_status']:
                    if status['status'] == 'cancelled':
                        status['status'] = 'budget_exhausted' if status.get('returned_count') else 'no_feasible_candidate_found'
                        status['reason'] = 'online_time_limit_reached'
                    if status.get('budget', {}).get('termination_reason') == 'cancelled':
                        status['budget']['termination_reason'] = 'online_time_limit_reached'
            # Exports travel with the response and are downloaded in the browser.
            # They do not need a second server request or survive in process memory.
            exports = {fmt: {'all': export(result, fmt)[0],
                             'by_id': {c['candidate_id']: export(result, fmt, [c['candidate_id']])[0]
                                       for c in result['candidates']}}
                       for fmt in ('fasta', 'csv')}
            body = json.dumps({'report': result, 'exports': exports}, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(body) > MAX_RESPONSE_BYTES:
                return reply({'error': 'This detailed report is too large for online delivery. Run the same settings locally to export the complete report.'}, 413)
            return reply(body)
        except InputError:
            raise
        except Exception:
            # Do not expose traceback paths, headers or user sequences.
            return reply({'error': 'Optimization could not finish. Try again or run the same settings locally.'}, 500)
        finally:
            compute_lock.release()

    @app.get('/')
    def page():
        html = (refs.root / 'web/index.html').read_text(encoding='utf-8')
        return reply(html.replace('Local computation', 'Online computation'), content_type='text/html; charset=utf-8')

    @app.get('/app.js')
    @app.get('/style.css')
    @app.get('/presentation.js')
    @app.get('/presentation.css')
    def asset():
        filename = request.path.lstrip('/')
        mime = 'text/javascript; charset=utf-8' if filename.endswith('.js') else 'text/css; charset=utf-8'
        return reply((refs.root / 'web' / filename).read_bytes(), content_type=mime)

    @app.get('/assets/<path:filename>')
    def presentation_asset(filename):
        # Vercel serves public/ directly; this route supports local WSGI use.
        if filename not in PUBLIC_ASSETS:
            return reply({'error': 'Not found'}, 404)
        return send_file(refs.root / 'public/assets' / filename,
                         mimetype=PUBLIC_ASSETS[filename], conditional=True)

    @app.get('/favicon.ico')
    def favicon():
        return reply(b'', 204)

    return app
