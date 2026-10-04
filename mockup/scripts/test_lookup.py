import hashlib
import json
from datetime import date
from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from unittest import TestCase
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.lookup import handler
from engine.parcel_lookup import lookup
from engine.run import evaluation_rules
from engine.verdict import verdicts_for_building

ROOT = Path(__file__).resolve().parents[2]


class LookupTests(TestCase):
    def test_matches_original_engine_path_and_does_not_mutate_overrides(self):
        buildings = json.loads((ROOT / 'out/buildings.json').read_text())
        expected = verdicts_for_building(buildings['A0001'], evaluation_rules(fetch=False), '2026-10-03')
        baseline = lookup('A0001', '2026-10-03')
        self.assertEqual(baseline['lookups'], expected)
        self.assertEqual(baseline['rules_sha256'], hashlib.sha256((ROOT / 'out/rules.json').read_bytes()).hexdigest())
        changed = lookup('A0001', '2026-10-03', '2020', '100000')
        self.assertEqual(changed['fact_overrides'], {'year_built': 2020, 'units': 100000})
        self.assertEqual(lookup('A0001', '2026-10-03'), baseline)

    def test_invalid_inputs(self):
        for args in [('A9999', '2026-10-03'), ('../../secret', '2026-10-03'), ('A0001', '2026-02-30'), ('A0001', '2026-1-01'), ('A0001', '2026-10-03', '1599'), ('A0001', '2026-10-03', str(date.today().year + 1)), ('A0001', '2026-10-03', None, '0'), ('A0001', '2026-10-03', None, '100001')]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                lookup(*args)

    def test_vercel_python_http_handler(self):
        server = HTTPServer(('127.0.0.1', 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}/api/lookup'
        try:
            with urlopen(base + '?address=A0001&as_of=2026-10-03&year_built=2020&units=5') as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(json.load(response)['fact_overrides'], {'year_built': 2020, 'units': 5})
            for request, status in [(base, 400), (base + '?address=A0001&address=A0002&as_of=2026-10-03', 400), (Request(base, data=b'{}', method='POST'), 405)]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code, status)
                self.assertIn('error', json.load(error.exception))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
