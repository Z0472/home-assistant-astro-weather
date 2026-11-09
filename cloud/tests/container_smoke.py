"""CI-only real image smoke test; seed a current fixture to avoid provider traffic."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from history import History, location_key

root = Path(__file__).resolve().parents[2]
options_path = root / 'cloud/options.example.json'
options = json.loads(options_path.read_text())
db = History(location_key(options))
db.migrate()
db.save({'weather': {'generated_at': datetime.now(timezone.utc).isoformat(),
                     'backend_version': 'ci-fixture', 'state': 'ok', 'location': options,
                     'forecast': []},
         'decision': {'state': 'CI fixture', 'daily': []}, 'moon': {}})
base = ['docker', 'run', '--network', 'host']
for key in ['PGHOST', 'PGPORT', 'PGUSER', 'PGPASSWORD', 'PGDATABASE', 'PGSSLMODE']:
    base += ['-e', key]
base += ['-v', f'{options_path}:/config/options.json:ro']
subprocess.run(base + ['--rm', 'astro-weather:ci', 'python', '/app/cloud/server.py', 'migrate'], check=True)
identifier = subprocess.check_output(base + ['-d', '--read-only', '--tmpfs', '/tmp',
    '--tmpfs', '/data:uid=10001,gid=10001', '--shm-size', '1g', 'astro-weather:ci'], text=True).strip()
try:
    for attempt in range(30):
        try:
            with urlopen('http://127.0.0.1:8099/readyz', timeout=2) as response:
                assert json.load(response)['ready']
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError('Container did not become ready')
    with urlopen('http://127.0.0.1:8099/') as response:
        assert b'Astro Weather' in response.read()
    with urlopen('http://127.0.0.1:8099/history') as response:
        assert json.load(response)['items']
    with urlopen('http://127.0.0.1:8099/decision') as response:
        assert json.load(response)['state'] == 'CI fixture'
    print('Container migration, non-root read-only startup, UI and history passed')
finally:
    subprocess.run(['docker', 'logs', identifier], check=False)
    subprocess.run(['docker', 'stop', '-t', '25', identifier], check=False)
    subprocess.run(['docker', 'rm', identifier], check=False)
