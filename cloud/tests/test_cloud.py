import contextlib
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import history
import met_cache
import server


def document(stamp='2026-11-09T18:00:00Z'):
    return {'weather': {'generated_at': stamp, 'state': 'ok', 'backend_version': '12.4.18',
                        'location': {'latitude': 50.0755, 'longitude': 14.4378, 'altitude': 250,
                                     'timezone': 'Europe/Prague'}, 'forecast': []},
            'decision': {'state': 'SPUSTIT', 'daily': []}, 'moon': {'state': 'ok'}}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(server.core, 'CACHE_DIR', Path(self.temp.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        server.STOP.clear()

    def test_configuration_disables_home_assistant_even_if_user_enables_it(self):
        options_file = Path(self.temp.name) / 'options.json'
        options_file.write_text(json.dumps({'latitude': 49, 'longitude': 14,
                                           'publish_homeassistant_entities': True}))
        with patch.dict(os.environ, {'ASTRO_OPTIONS_FILE': str(options_file), 'ASTRO_DATA_DIR': self.temp.name}):
            options = server.configure()
        self.assertFalse(options['publish_homeassistant_entities'])
        self.assertFalse(options['install_dashboard_cards'])
        self.assertFalse(options['use_satellite'])
        options_file.write_text('{broken')
        with patch.dict(os.environ, {'ASTRO_OPTIONS_FILE': str(options_file)}):
            with self.assertRaises(ValueError):
                server.configure()

    def test_pending_survives_failed_database_write(self):
        db = Mock(key='test-location')
        collector = server.Collector(db, {'refresh_minutes': 30})
        collector.pending.write_text(json.dumps(document()))
        db.save.side_effect = RuntimeError('database down')
        with self.assertRaises(RuntimeError):
            collector.flush(None)
        self.assertTrue(collector.pending.exists())
        db.save.side_effect = None
        collector.flush(None)
        self.assertFalse(collector.pending.exists())
        self.assertEqual(db.save.call_count, 2)

    def test_existing_snapshot_restored_without_requerying_providers(self):
        db = Mock(key='test-location')
        db.connect.side_effect = lambda: contextlib.nullcontext(Mock())
        db.lock.return_value = True
        db.latest.return_value = document(datetime.now(timezone.utc).isoformat())
        collector = server.Collector(db, {'refresh_minutes': 30})
        with patch.object(server.core, 'refresh_once') as refresh:
            collector.cycle()
            refresh.assert_not_called()
        self.assertEqual(server.snapshot()['weather'], db.latest.return_value['weather'])

    def test_standby_does_not_fetch_or_write(self):
        db = Mock(key='test-location')
        db.connect.side_effect = lambda: contextlib.nullcontext(Mock())
        db.lock.return_value = False
        with patch.object(server.core, 'refresh_once') as refresh:
            server.Collector(db, {}).cycle()
            refresh.assert_not_called()
        db.save.assert_not_called()

    def test_http_dashboard_history_validation_and_database_outage(self):
        db, collector, worker = Mock(), Mock(last_error=None), Mock()
        db.list.return_value = []
        db.get.return_value = None
        worker.is_alive.return_value = True
        http = ThreadingHTTPServer(('127.0.0.1', 0), server.handler_class(db, collector, worker))
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{http.server_port}'
        try:
            for path in ['/', '/dashboard.js', '/style.css', '/livez', '/readyz', '/forecast', '/decision', '/moon', '/history']:
                with urlopen(url + path) as response:
                    self.assertEqual(response.status, 200, path)
            for path, status in [('/history?limit=no', 400), ('/history/0', 400),
                                 ('/history/1', 404), ('/../schema.sql', 404)]:
                with self.assertRaises(HTTPError) as raised:
                    urlopen(url + path)
                self.assertEqual(raised.exception.code, status)
            db.ready.side_effect = RuntimeError('secret-value-must-not-leak')
            with self.assertRaises(HTTPError) as raised:
                urlopen(url + '/readyz')
            self.assertEqual(raised.exception.code, 503)
            self.assertNotIn(b'secret-value', raised.exception.read())
            with urlopen(url + '/livez') as response:
                self.assertEqual(response.status, 200)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

    def test_location_identity_includes_altitude(self):
        options = document()['weather']['location']
        self.assertNotEqual(history.location_key(options), history.location_key({**options, 'altitude': 999}))


class MetCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original = Mock()
        self.core = Mock(MET_URL='https://api.met.no/weatherapi/locationforecast/2.0/complete',
                         CACHE_DIR=Path(self.temp.name), http_get=self.original)
        met_cache.install(self.core)
        self.url = self.core.MET_URL + '?lat=49&lon=14'

    def test_cache_survives_restart_and_respects_minimum_and_expiry(self):
        response = Mock()
        response.read.return_value = b'{"properties":{}}'
        response.headers = {'Last-Modified': 'Mon, 09 Nov 2026 06:00:00 GMT',
                            'Expires': 'Mon, 09 Nov 2026 18:00:00 GMT'}
        with patch('met_cache.time.time', return_value=1794218400), patch('met_cache.urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value = response
            self.core.http_get(self.url, user_agent='test')
            self.core.http_get(self.url, user_agent='test')
            self.assertEqual(request.call_count, 1)
            met_cache.install(self.core)
            self.assertEqual(self.core.http_get(self.url, user_agent='test'), b'{"properties":{}}')
            self.assertEqual(request.call_count, 1)

    def test_failed_request_is_backed_off_without_silently_serving_stale(self):
        with patch('met_cache.urllib.request.urlopen', side_effect=HTTPError(self.url, 503, 'down', {}, None)) as request:
            with self.assertRaises(HTTPError):
                self.core.http_get(self.url, user_agent='test')
            with self.assertRaises(RuntimeError):
                self.core.http_get(self.url, user_agent='test')
            self.assertEqual(request.call_count, 1)

    def test_non_met_requests_are_unchanged(self):
        self.core.http_get('https://example.org/data', user_agent='test')
        self.original.assert_called_once()


@unittest.skipUnless(os.environ.get('ASTRO_TEST_POSTGRES') == '1', 'Requires isolated PostgreSQL test database')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = history.History('integration-test-location')
        self.db.migrate()
        with self.db.connect() as conn:
            conn.execute('DELETE FROM astro_forecast_snapshots')

    def test_migration_idempotency_deduplication_and_history(self):
        self.db.migrate()
        first = document()
        self.db.save(first)
        self.db.save({**first, 'decision': {'state': 'must-not-overwrite'}})
        self.db.save(document('2026-11-09T18:30:00Z'))
        rows = self.db.list(limit=1)
        self.assertEqual(len(rows), 1)
        older = self.db.list(before=rows[0]['id'])
        self.assertEqual(len(older), 1)
        self.assertEqual(self.db.get(older[0]['id'])['decision']['state'], 'SPUSTIT')
        self.assertEqual(self.db.latest()['weather']['generated_at'], '2026-11-09T18:30:00Z')
        self.assertEqual(history.History('other-location').list(), [])
        self.assertIsNone(history.History('other-location').get(rows[0]['id']))
        for limit in (0, 201):
            with self.assertRaises(ValueError):
                self.db.list(limit=limit)

    def test_collection_lock_released_on_connection_close(self):
        with self.db.connect() as first, self.db.connect() as second:
            self.assertTrue(self.db.lock(first))
            self.assertFalse(self.db.lock(second))
        with self.db.connect() as third:
            self.assertTrue(self.db.lock(third))


if __name__ == '__main__':
    unittest.main()
