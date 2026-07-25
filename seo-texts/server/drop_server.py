# -*- coding: utf-8 -*-
"""Файловый обменник для Claude Code. Токен в заголовке X-Drop-Token."""
import hashlib, hmac, os, re
from flask import Flask, abort, jsonify, request, send_from_directory

app = Flask(__name__)
DROP_DIR = os.path.abspath(os.environ.get('DROP_DIR', os.path.join(os.path.dirname(__file__), 'drop-storage')))
TOKEN = os.environ.get('DROP_TOKEN', '')
os.makedirs(DROP_DIR, exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024 * 1024
SAFE_NAME = re.compile(r'^[\w][\w.\-]{0,200}$')

def _authed():
    return bool(TOKEN) and hmac.compare_digest(request.headers.get('X-Drop-Token', ''), TOKEN)

@app.before_request
def _gate():
    if not TOKEN: abort(503, 'DROP_TOKEN not set')
    if not _authed(): abort(401)

@app.get('/list')
def list_files():
    out = []
    for n in sorted(os.listdir(DROP_DIR)):
        p = os.path.join(DROP_DIR, n)
        if os.path.isfile(p):
            out.append({'name': n, 'bytes': os.path.getsize(p), 'mtime': int(os.path.getmtime(p))})
    return jsonify(out)

@app.get('/<name>')
def download(name):
    if not SAFE_NAME.match(name): abort(400)
    return send_from_directory(DROP_DIR, name, as_attachment=True)

@app.route('/<name>', methods=['PUT', 'POST'])
def upload(name):
    if not SAFE_NAME.match(name): abort(400)
    dst = os.path.join(DROP_DIR, name)
    h = hashlib.sha256(); size = 0
    with open(dst + '.part', 'wb') as f:
        while True:
            chunk = request.stream.read(1024 * 1024)
            if not chunk: break
            f.write(chunk); h.update(chunk); size += len(chunk)
    os.replace(dst + '.part', dst)
    return jsonify({'ok': True, 'name': name, 'bytes': size, 'sha256': h.hexdigest()})

@app.delete('/<name>')
def delete(name):
    if not SAFE_NAME.match(name): abort(400)
    p = os.path.join(DROP_DIR, name)
    if not os.path.isfile(p): abort(404)
    os.remove(p)
    return jsonify({'ok': True, 'deleted': name})

if __name__ == '__main__':
    try:
        from waitress import serve
        serve(app, host='127.0.0.1', port=8787, threads=24,
              max_request_body_size=9*1024**3, channel_timeout=7200)
    except ImportError:
        app.run(host='127.0.0.1', port=8787, threaded=True)
