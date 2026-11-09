"""Append-only forecast snapshots. libpq PG* variables carry credentials."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def location_key(options):
    # Altitude and timezone affect the forecast and night calculation.
    return hashlib.sha256(json.dumps([
        round(float(options['latitude']), 4), round(float(options['longitude']), 4),
        int(options['altitude']), options['timezone'],
    ], separators=(',', ':')).encode()).hexdigest()


class History:
    def __init__(self, key):
        self.key = key

    def connect(self):
        return psycopg.connect('', connect_timeout=5, autocommit=True,
                               options='-c statement_timeout=10000', row_factory=dict_row)

    def migrate(self):
        with self.connect() as conn, conn.transaction():
            conn.execute('SELECT pg_advisory_xact_lock(74122001)')
            conn.execute(Path(__file__).with_name('schema.sql').read_text())

    def ready(self):
        with self.connect() as conn:
            conn.execute('SELECT id FROM astro_forecast_snapshots LIMIT 0')

    def lock(self, conn):
        # Stable signed bigint, independent of Python's randomized hash().
        key = int.from_bytes(hashlib.sha256(self.key.encode()).digest()[:8], 'big', signed=True)
        return conn.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (key,)).fetchone()['acquired']

    def save(self, snapshot, conn=None):
        weather = snapshot['weather']
        stamp = datetime.fromisoformat(weather['generated_at'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Snapshot timestamp must include a timezone')
        values = (self.key, stamp, weather.get('backend_version', 'unknown'),
                  Jsonb(weather), Jsonb(snapshot['decision']), Jsonb(snapshot['moon']))
        sql = '''INSERT INTO astro_forecast_snapshots
                 (location_key, generated_at, backend_version, weather, decision, moon)
                 VALUES (%s, %s, %s, %s, %s, %s)
                 ON CONFLICT (location_key, generated_at) DO NOTHING'''
        if conn is not None:
            conn.execute(sql, values)
        else:
            with self.connect() as connection:
                connection.execute(sql, values)

    def latest(self):
        with self.connect() as conn:
            return conn.execute('''SELECT weather, decision, moon FROM astro_forecast_snapshots
                WHERE location_key=%s ORDER BY generated_at DESC LIMIT 1''', (self.key,)).fetchone()

    def list(self, limit=50, before=None):
        if not 1 <= limit <= 200 or (before is not None and before < 1):
            raise ValueError('Invalid pagination')
        with self.connect() as conn:
            rows = conn.execute('''SELECT id, generated_at, recorded_at, backend_version,
                weather->>'state' AS state, decision->>'state' AS decision
                FROM astro_forecast_snapshots WHERE location_key=%s
                AND (%s::bigint IS NULL OR id < %s::bigint)
                ORDER BY id DESC LIMIT %s''', (self.key, before, before, limit)).fetchall()
        for row in rows:
            for field in ('generated_at', 'recorded_at'):
                row[field] = row[field].isoformat()
        return rows

    def get(self, identifier):
        with self.connect() as conn:
            return conn.execute('''SELECT id, weather, decision, moon FROM astro_forecast_snapshots
                WHERE location_key=%s AND id=%s''', (self.key, identifier)).fetchone()
