#!/usr/bin/env python3
# ZENOS Sheets local server: serves the built app and relays AI calls to the
# user's own provider (OpenAI-compatible or Anthropic). Same-origin for the app,
# so no CORS issues; the API key stays on this machine and is never stored here.
import os, json
import urllib.request
import urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dist')
HOST = '127.0.0.1'
PORT = 5174


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIST, **k)

    def log_message(self, *a):
        pass

    def _host_ok(self):
        # Only accept requests addressed to this machine (blocks DNS-rebinding
        # and any access that is not same-origin localhost).
        h = (self.headers.get('Host') or '').rsplit(':', 1)[0]
        return h in ('127.0.0.1', 'localhost', '::1', '[::1]', '')

    def _json(self, code, obj):
        b = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {'error': 'forbidden'})
        return super().do_GET()

    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {'error': 'forbidden'})
        if self.path.rstrip('/') != '/ai/chat':
            return self._json(404, {'error': 'not found'})
        try:
            ln = int(self.headers.get('Content-Length', '0') or '0')
            body = json.loads(self.rfile.read(ln) or b'{}')
        except Exception as e:
            return self._json(400, {'error': 'bad request: %s' % e})

        provider = (body.get('provider') or 'openai').lower()
        base = (body.get('baseUrl') or '').rstrip('/')
        key = body.get('apiKey') or ''
        model = body.get('model') or ''
        messages = body.get('messages') or []
        if not key:
            return self._json(400, {'error': 'No AI is set up yet (register a key first).'})

        try:
            if provider == 'anthropic':
                text = self._anthropic(base, key, model, messages, body)
            else:
                text = self._openai(base, key, model, messages, body)
            return self._json(200, {'text': text})
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode('utf-8', 'replace')[:700]
            except Exception:
                detail = str(e)
            self._json(e.code, {'error': detail})
        except Exception as e:
            self._json(502, {'error': 'relay failed: %s' % e})

    def _openai(self, base, key, model, messages, body):
        if not base:
            raise ValueError('Enter an OpenAI-compatible endpoint (/v1).')
        payload = json.dumps({
            'model': model or 'gpt-4o-mini',
            'messages': messages,
            'temperature': body.get('temperature', 0.2),
        }).encode('utf-8')
        req = urllib.request.Request(
            base + '/chat/completions',
            data=payload,
            method='POST',
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return data['choices'][0]['message']['content']

    def _anthropic(self, base, key, model, messages, body):
        base = base or 'https://api.anthropic.com'
        system = '\n'.join(m.get('content', '') for m in messages if m.get('role') == 'system')
        conv = [
            {'role': m.get('role'), 'content': m.get('content', '')}
            for m in messages if m.get('role') in ('user', 'assistant')
        ]
        pl = {
            'model': model or 'claude-sonnet-4-5',
            'max_tokens': int(body.get('max_tokens', 2048)),
            'messages': conv,
        }
        if system:
            pl['system'] = system
        req = urllib.request.Request(
            base + '/v1/messages',
            data=json.dumps(pl).encode('utf-8'),
            method='POST',
            headers={
                'content-type': 'application/json',
                'x-api-key': key,
                'anthropic-version': '2023-06-01',
            },
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        parts = data.get('content') or []
        return ''.join(p.get('text', '') for p in parts if p.get('type') == 'text')


if __name__ == '__main__':
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
