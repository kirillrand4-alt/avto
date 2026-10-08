# -*- coding: utf-8 -*-
"""fixC: скачать страницы-источники номеров каталога Meyer (только чтение сайтов).

Список адресов — fixC-urls.json на дропе. Сырые HTML (байты как есть + итоговый адрес и
кодировка из заголовка) складываются в fixC-stranicy.zip на дропе. В каталог не пишет."""
import concurrent.futures as cf
import gzip
import hashlib
import io
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
import zipfile
import zlib

D = r'C:\seostat\drop\drop-storage'
urls = json.load(io.open(os.path.join(D, 'fixC-urls.json'), encoding='utf-8'))
if len(sys.argv) > 1:
    urls = [u for u in urls if any(k in u for k in sys.argv[1:])]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/124.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def idn(u):
    p = urllib.parse.urlsplit(u)
    host = p.hostname or ''
    try:
        host.encode('ascii')
        h2 = host
    except UnicodeEncodeError:
        h2 = host.encode('idna').decode('ascii')
    netloc = h2 + (':%d' % p.port if p.port else '')
    path = urllib.parse.quote(p.path, safe='/%:@!$&\'()*+,;=-._~')
    q = urllib.parse.quote(p.query, safe='=&%+-._~/:,;')
    return urllib.parse.urlunsplit((p.scheme, netloc, path, q, ''))


def kachat(u):
    t0 = time.time()
    for popytka in range(2):
        try:
            rq = urllib.request.Request(idn(u), headers={'User-Agent': UA, 'Accept-Language': 'ru,en;q=0.8',
                                                         'Accept': 'text/html,*/*', 'Accept-Encoding': 'gzip, deflate'})
            r = urllib.request.urlopen(rq, timeout=25, context=ctx)
            b = r.read(6_000_000)
            enc = (r.headers.get('Content-Encoding') or '').lower()
            if enc == 'gzip':
                b = gzip.decompress(b)
            elif enc == 'deflate':
                try:
                    b = zlib.decompress(b)
                except zlib.error:
                    b = zlib.decompress(b, -zlib.MAX_WBITS)
            return u, {'ok': 1, 'kod': r.status, 'url': r.geturl(), 'ct': r.headers.get('Content-Type') or '',
                       'sek': round(time.time() - t0, 1)}, b
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:200]
            kod = getattr(e, 'code', None)
            if kod and kod in (404, 410):
                break
            time.sleep(1)
    return u, {'ok': 0, 'err': err, 'kod': kod}, b''


meta = {}
out = os.path.join(D, 'fixC-stranicy.zip')
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z, cf.ThreadPoolExecutor(16) as ex:
    for u, m, b in ex.map(kachat, urls):
        h = hashlib.md5(u.encode('utf-8')).hexdigest()[:16]
        m['fajl'] = h + '.html' if b else ''
        meta[u] = m
        if b:
            z.writestr(h + '.html', b)
    z.writestr('meta.json', json.dumps(meta, ensure_ascii=False, indent=1))
ok = sum(1 for m in meta.values() if m['ok'])
print('адресов %d, скачано %d, ошибок %d, архив %d байт' % (len(urls), ok, len(urls) - ok, os.path.getsize(out)))
