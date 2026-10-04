import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from engine.parcel_lookup import lookup


class handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        payload = json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        if status == 405:
            self.send_header('Allow', 'GET')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def do_GET(self):
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if any(len(values) != 1 for values in query.values()):
            return self.reply(400, {'error': 'Duplicate query parameter'})
        param = lambda name: query.get(name, [None])[0]
        try:
            result = lookup(param('address'), param('as_of'), param('year_built'), param('units'))
        except ValueError as error:
            return self.reply(400, {'error': str(error)})
        except Exception:
            return self.reply(503, {'error': 'Date lookup unavailable'})
        self.reply(200, result)

    def do_POST(self):
        self.reply(405, {'error': 'Method not allowed'})

    do_HEAD = do_POST
    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST
