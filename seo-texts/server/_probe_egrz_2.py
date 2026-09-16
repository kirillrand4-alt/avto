# -*- coding: utf-8 -*-
"""Проба 2: ПОЧЕМУ egrz.gov.ru не отдался — DNS, TCP, TLS, прокси, альтернативные хосты.

Только чтение сети и печать. Главное — последним.
"""
import socket
import ssl
import time
import urllib.request
import urllib.error

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                      urllib.request.HTTPSHandler(context=_CTX))
_SYS = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_CTX))

HOSTS = ['egrz.gov.ru', 'egrz.ru', 'gge.ru', 'zakupki.gov.ru', 'frprf.ru']
RES = []

# --- DNS ---
for h in HOSTS:
    try:
        ips = sorted({r[4][0] for r in socket.getaddrinfo(h, 443, proto=socket.IPPROTO_TCP)})
        RES.append(('dns', h, 'ok ' + ','.join(ips)))
    except Exception as e:  # noqa: BLE001
        RES.append(('dns', h, 'FAIL %s: %s' % (type(e).__name__, e)))

# --- TCP 443 ---
for h in HOSTS:
    t = time.time()
    try:
        s = socket.create_connection((h, 443), timeout=12)
        s.close()
        RES.append(('tcp', h, 'ok %.1fs' % (time.time() - t)))
    except Exception as e:  # noqa: BLE001
        RES.append(('tcp', h, 'FAIL %.1fs %s: %s' % (time.time() - t, type(e).__name__, e)))

# --- TLS handshake ---
for h in HOSTS:
    try:
        s = socket.create_connection((h, 443), timeout=12)
        ss = _CTX.wrap_socket(s, server_hostname=h)
        cert = ss.getpeercert(True)
        RES.append(('tls', h, 'ok proto=%s cert_bytes=%d' % (ss.version(), len(cert or b''))))
        ss.close()
    except Exception as e:  # noqa: BLE001
        RES.append(('tls', h, 'FAIL %s: %s' % (type(e).__name__, e)))


def http(tag, opener, url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    try:
        r = opener.open(req, timeout=timeout)
        b = r.read(400)
        RES.append((tag, url, 'code=%s len_head=%d head=%r' % (r.getcode(), len(b), b[:160])))
    except urllib.error.HTTPError as e:
        RES.append((tag, url, 'HTTP %s %r' % (e.code, (e.read()[:160] if e.fp else b''))))
    except Exception as e:  # noqa: BLE001
        RES.append((tag, url, 'FAIL %s: %s' % (type(e).__name__, e)))


http('direct', _DIRECT, 'https://egrz.gov.ru/')
http('sysprx', _SYS, 'https://egrz.gov.ru/')
http('direct', _DIRECT, 'http://egrz.gov.ru/')
http('direct', _DIRECT, 'https://egrz.ru/')
http('sysprx', _SYS, 'https://egrz.ru/')
http('direct', _DIRECT, 'https://gge.ru/')
http('direct', _DIRECT, 'https://zakupki.gov.ru/epz/main/public/home.html')

# --- через VC._fetch (там свои прокси/обход Turnstile) ---
try:
    import verify_company as VC
    if hasattr(VC, '_fetch'):
        for u in ('https://egrz.gov.ru/', 'https://egrz.ru/'):
            try:
                htm, method, meta = VC._fetch(u)
                RES.append(('vcfetch', u, 'method=%s len=%d meta=%r head=%r'
                            % (method, len(htm or ''), meta, (htm or '')[:160])))
            except Exception as e:  # noqa: BLE001
                RES.append(('vcfetch', u, 'FAIL %s: %s' % (type(e).__name__, e)))
    else:
        RES.append(('vcfetch', '-', 'нет VC._fetch'))
except Exception as e:  # noqa: BLE001
    RES.append(('vcfetch', '-', 'import FAIL %s: %s' % (type(e).__name__, e)))

print()
print('==================== ИТОГ ====================')
for tag, what, res in RES:
    print('%-8s %-50s %s' % (tag, what[:50], res[:400]))
