"""Persistent MET HTTP cache for the standalone deployment only."""
import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime


def install(core):
    original = core.http_get

    def get(url, *, user_agent, timeout=60):
        if not url.startswith(core.MET_URL + '?'):
            return original(url, user_agent=user_agent, timeout=timeout)
        path = core.CACHE_DIR / ('met_http_' + hashlib.sha256(url.encode()).hexdigest() + '.json')
        now = time.time()
        try:
            cached = json.loads(path.read_text())
        except (OSError, ValueError):
            cached = {}
        if cached.get('next_request_at', 0) > now:
            if 'body' not in cached:
                raise RuntimeError('MET retry delayed after an upstream error')
            return base64.b64decode(cached['body'])
        headers = {'User-Agent': user_agent, 'Accept': 'application/json'}
        if cached.get('last_modified'):
            headers['If-Modified-Since'] = cached['last_modified']
        # Conservative global minimum: three hours, also across process restarts.
        next_at = now + 10800
        try:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                    raw = response.read()
                    json.loads(raw)  # Never cache an HTML error page as a forecast.
                    cached = {'body': base64.b64encode(raw).decode(),
                              'last_modified': response.headers.get('Last-Modified')}
                    expires = response.headers.get('Expires')
                    if expires:
                        next_at = max(next_at, parsedate_to_datetime(expires).timestamp())
            except urllib.error.HTTPError as exc:
                if exc.code != 304 or 'body' not in cached:
                    # Do not present failed retrieval as fresh model data.
                    cached = {}
                    raise
            cached['next_request_at'] = next_at
        except Exception:
            # Backoff is persisted; subsequent refreshes report missing MET.
            cached = {'next_request_at': next_at}
            raise
        finally:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(cached))
            temp.replace(path)
        return base64.b64decode(cached['body'])

    core.http_get = get
