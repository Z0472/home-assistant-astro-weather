#!/usr/bin/env python3
"""Standalone Azure adapter around the unchanged Home Assistant backend."""
import argparse
import json
import math
import os
from pathlib import Path
import random
import signal
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'astro_weather_backend'))
import app  # Installs the same model/decision patches as the HA entrypoint.
from history import History, location_key
import met_cache

core = app.core
STOP = threading.Event()


def configure():
    core.OPTIONS_FILE = Path(os.environ.get('ASTRO_OPTIONS_FILE', '/config/options.json'))
    core.CACHE_DIR = Path(os.environ.get('ASTRO_DATA_DIR', '/data')) / 'cache'
    # Fail fast on a typo/invalid JSON instead of silently forecasting Prague.
    supplied = json.loads(core.OPTIONS_FILE.read_text())
    if not isinstance(supplied, dict):
        raise ValueError('Options must be a JSON object')
    for key, minimum, maximum in [('latitude', -90, 90), ('longitude', -180, 180)]:
        value = float(supplied[key])
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError('Invalid ' + key)
    options = core.load_options()
    ZoneInfo(options['timezone'])
    options.update(publish_homeassistant_entities=False, install_dashboard_cards=False,
                   install_lovelace_resources=False)
    options['use_satellite'] = bool(supplied.get('use_satellite', False))
    options['eumetsat_consumer_key'] = os.environ.get('EUMETSAT_CONSUMER_KEY', '')
    options['eumetsat_consumer_secret'] = os.environ.get('EUMETSAT_CONSUMER_SECRET', '')
    options['met_user_agent'] = os.environ.get('MET_USER_AGENT', options['met_user_agent'])
    core.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return options


def snapshot():
    with core.STATE_LOCK:
        return json.loads(json.dumps({'weather': core.STATE, 'decision': core.DECISION_STATE,
                                    'moon': core.MOON_STATE}))


def restore(payload):
    if payload:
        with core.STATE_LOCK:
            for target, name in [(core.STATE, 'weather'), (core.DECISION_STATE, 'decision'),
                                 (core.MOON_STATE, 'moon')]:
                target.clear()
                target.update(payload[name])


class Collector:
    def __init__(self, history, options):
        self.history, self.options = history, options
        self.pending = core.CACHE_DIR / ('pending_' + history.key + '.json')
        self.last_error = None
        self.next_refresh = 0.0

    def flush(self, connection):
        if self.pending.exists():
            pending = json.loads(self.pending.read_text())
            self.history.save(pending, connection)
            self.pending.unlink()  # Delete only after the database acknowledged INSERT.

    def cycle(self):
        with self.history.connect() as connection:
            if not self.history.lock(connection):
                return
            self.flush(connection)
            if time.monotonic() < self.next_refresh:
                return
            latest = self.history.latest()
            if latest:
                restore(latest)
                stamp = core.parse_iso_utc(latest['weather'].get('generated_at', ''))
                if stamp and datetime.now(timezone.utc) - stamp < timedelta(minutes=self.options['refresh_minutes']):
                    return
            # MET requests must not be scheduled exactly at XX:00.
            now = datetime.now(timezone.utc)
            if now.minute == 0 and STOP.wait(61 - now.second):
                return
            core.refresh_once(self.options)
            self.next_refresh = time.monotonic() + self.options['refresh_minutes'] * 60
            if self.options['use_satellite']:
                # Serialize with weather collection so archived documents are coherent.
                import satellite_nowcast_patch as satellite
                satellite._update_satellite(core, self.options)
            current = snapshot()
            if not current['weather'].get('generated_at'):
                raise RuntimeError('No generated_at in forecast')
            temporary = self.pending.with_suffix('.tmp')
            temporary.write_text(json.dumps(current, ensure_ascii=False))
            temporary.replace(self.pending)
            self.flush(connection)

    def run(self):
        while not STOP.is_set():
            try:
                self.cycle()
                self.last_error = None
            except Exception as exc:
                # Connection strings and provider credentials never enter our logs.
                self.last_error = type(exc).__name__
                core.log('CLOUD collection/history error: ' + self.last_error)
            STOP.wait(30 + random.uniform(0, 10))


def handler_class(history, collector, worker):
    class Handler(core.Handler):
        def do_GET(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path == '/livez':
                    return self.send_json({'alive': True})
                if parsed.path == '/readyz':
                    history.ready()
                    ready = worker.is_alive() and not STOP.is_set() and collector.last_error is None
                    return self.send_json({'ready': ready}, 200 if ready else 503)
                if parsed.path == '/history':
                    limit = int(query.get('limit', ['50'])[0])
                    before = int(query['before'][0]) if 'before' in query else None
                    items = history.list(limit, before)
                    return self.send_json({'items': items, 'next_before': items[-1]['id'] if len(items) == limit else None})
                if parsed.path.startswith('/history/'):
                    identifier = int(parsed.path.removeprefix('/history/'))
                    if identifier < 1:
                        raise ValueError('Invalid id')
                    row = history.get(identifier)
                    return self.send_json(row or {'error': 'not_found'}, 200 if row else 404)
                if parsed.path == '/moon':
                    return self.send_json(snapshot()['moon'])
                if parsed.path in ('/', '/dashboard.js', '/style.css'):
                    name = {'/': 'index.html', '/dashboard.js': 'dashboard.js', '/style.css': 'style.css'}[parsed.path]
                    body = (Path(__file__).parent / 'web' / name).read_bytes()
                    mime = {'/': 'text/html', '/dashboard.js': 'text/javascript', '/style.css': 'text/css'}[parsed.path]
                    self.send_response(200)
                    self.send_header('Content-Type', mime + '; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return super().do_GET()
            except (ValueError, OverflowError):
                return self.send_json({'error': 'invalid_parameter'}, 400)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                core.log('CLOUD API error: ' + type(exc).__name__)
                return self.send_json({'error': 'temporarily_unavailable'}, 503)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['serve', 'migrate'], default='serve', nargs='?')
    args = parser.parse_args()
    options = configure()
    history = History(location_key(options))
    if args.command == 'migrate':
        history.migrate()
        core.log('PostgreSQL schema ready')
        return
    history.ready()  # Migration runs in an init container, never hidden in an API request.
    met_cache.install(core)
    collector = Collector(history, options)
    worker = threading.Thread(target=collector.run, daemon=True, name='collector')
    server = ThreadingHTTPServer(('0.0.0.0', 8099), handler_class(history, collector, worker))
    server.timeout = 0.5
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    worker.start()
    core.log('Astro Weather Azure on port 8099; HA publication disabled')
    try:
        while not STOP.is_set():
            server.handle_request()
    finally:
        server.server_close()
        worker.join(timeout=20)


if __name__ == '__main__':
    main()
