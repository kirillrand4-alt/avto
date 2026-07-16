# -*- coding: utf-8 -*-
"""Файловый обменник для Claude Code (drop-эндпоинт) на parsercompressor.online.

Отдельное мини-приложение Flask: токен в заголовке, PUT/POST залив, GET скачивание,
листинг. Хранит файлы в подпапке ./drop-storage (или DROP_DIR из окружения).

Запуск (рядом с основным приложением, другой порт):
    set DROP_TOKEN=<длинный-случайный-токен>
    python drop_server.py            # слушает 127.0.0.1:8787

Маршрут в Caddyfile (добавить в блок parsercompressor.online):
    handle_path /drop/* {
        reverse_proxy 127.0.0.1:8787
    }

Проверка:
    curl -H "X-Drop-Token: $T" https://parsercompressor.online/drop/list
    curl -H "X-Drop-Token: $T" -T file.csv https://parsercompressor.online/drop/file.csv
    curl -H "X-Drop-Token: $T" -O https://parsercompressor.online/drop/file.csv
"""
import hashlib
import hmac
import os
import re

from flask import Flask, abort, jsonify, request, send_from_directory

app = Flask(__name__)
DROP_DIR = os.path.abspath(os.environ.get('DROP_DIR', os.path.join(os.path.dirname(__file__), 'drop-storage')))
TOKEN = os.environ.get('DROP_TOKEN', '')
os.makedirs(DROP_DIR, exist_ok=True)

MAX_BYTES = 8 * 1024 * 1024 * 1024          # 8 ГБ на файл
app.config['MAX_CONTENT_LENGTH'] = MAX_BYTES
SAFE_NAME = re.compile(r'^[\w][\w.\-]{0,200}$')  # без путей/слэшей - только имя файла


def _authed():
    got = request.headers.get('X-Drop-Token', '')
    return bool(TOKEN) and hmac.compare_digest(got, TOKEN)


@app.before_request
def _gate():
    if not TOKEN:
        abort(503, 'DROP_TOKEN не задан на сервере')
    if not _authed():
        abort(401)


@app.get('/list')
def list_files():
    out = []
    for n in sorted(os.listdir(DROP_DIR)):
        p = os.path.join(DROP_DIR, n)
        if os.path.isfile(p):
            out.append({'name': n, 'bytes': os.path.getsize(p),
                        'mtime': int(os.path.getmtime(p))})
    return jsonify(out)


@app.get('/<name>')
def download(name):
    if not SAFE_NAME.match(name):
        abort(400, 'недопустимое имя')
    return send_from_directory(DROP_DIR, name, as_attachment=True)


@app.route('/<name>', methods=['PUT', 'POST'])
def upload(name):
    if not SAFE_NAME.match(name):
        abort(400, 'недопустимое имя')
    dst = os.path.join(DROP_DIR, name)
    h = hashlib.sha256()
    size = 0
    with open(dst + '.part', 'wb') as f:
        while True:
            chunk = request.stream.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            size += len(chunk)
    os.replace(dst + '.part', dst)
    return jsonify({'ok': True, 'name': name, 'bytes': size, 'sha256': h.hexdigest()})


@app.delete('/<name>')
def delete(name):
    if not SAFE_NAME.match(name):
        abort(400, 'недопустимое имя')
    p = os.path.join(DROP_DIR, name)
    if not os.path.isfile(p):
        abort(404)
    os.remove(p)
    return jsonify({'ok': True, 'deleted': name})


if __name__ == '__main__':
    # только локально; наружу выставляет Caddy по /drop/*
    try:
        from waitress import serve
        serve(app, host='127.0.0.1', port=8787)
    except ImportError:
        app.run(host='127.0.0.1', port=8787)
