# -*- coding: utf-8 -*-
"""Прибор: на каком шаге рвётся связь сервера с router.cheap.

10054 (WinError) = удалённая сторона закрыла соединение. Это НЕ «нет маршрута»: значит
кто-то на той стороне (или посередине) решил нас оборвать. Различаем три версии:
    1) блокировка по IP сервера      - рвётся ещё до TLS либо сразу после ClientHello;
    2) разрыв на TLS-рукопожатии     - падает handshake, до HTTP дело не доходит;
    3) обрыв после отправки тела     - рукопожатие прошло, заголовки ушли, ответ не пришёл.
Прибор проходит эти шаги по отдельности и печатает, докуда дошёл каждый вариант.

У каждой пробы свой контроль: тот же код бьётся в заведомо живые чужие хосты, чтобы
отличить «сеть сервера сломана вообще» от «шлюз режет именно нас».

Ключи НЕ печатаются: только «есть/нет» и длина.

Запуск: python3 seo-texts/zapusk_na_servere.py shlyuz_diagnoz_servera.py [blok ...]
Блоки: env dns tcp tls http api ua curl proxy  (без аргументов - все, кроме proxy)
"""
import json
import os
import platform
import socket
import ssl
import subprocess
import sys
import time

HOST = 'router.cheap'
PORT = 443

# контрольные хосты: дроп владельца (сервер ходит на него постоянно), фронт Anthropic
# (тоже за Cloudflare) и голый край Cloudflare.
KONTROL = [('parsercompressor.online', '/drop/list'),
           ('api.anthropic.com', '/v1/messages'),
           ('www.cloudflare.com', '/'),
           ('ya.ru', '/')]

ITOG = []
LOG = []


def skazat(s):
    LOG.append(s)
    print(s, flush=True)


def vylozhit_na_drop(imya='3s-shlyuz-log.txt'):
    """Полный лог на дроп: вывод задания приходит ХВОСТОМ ~6000 знаков, начало теряется.

    Секреты дропа ищем в окружении и в файлах раннера; значения не печатаем.
    """
    url = os.environ.get('DROP_URL') or 'https://parsercompressor.online/drop'
    tok = os.environ.get('DROP_TOKEN') or ''
    if not tok:
        for p in (r'C:\sender\server\runner-secrets.env', r'C:\sender\runner-secrets.env',
                  r'C:\sender\server\.env', r'C:\sender\.env'):
            try:
                for line in open(p, encoding='utf-8', errors='replace'):
                    if line.strip().startswith('DROP_TOKEN='):
                        tok = line.split('=', 1)[1].strip()
                    if line.strip().startswith('DROP_URL='):
                        url = line.split('=', 1)[1].strip()
            except Exception:  # noqa: BLE001
                continue
            if tok:
                skazat('  секрет дропа взят из %s' % p)
                break
    if not tok:
        skazat('  ДРОП: токена нет ни в окружении, ни в файлах раннера - лог не выложен')
        return
    try:
        import urllib.request as U
        telo = ('\n'.join(LOG)).encode('utf-8')
        req = U.Request('%s/%s' % (url.rstrip('/'), imya), data=telo, method='PUT',
                        headers={'X-Drop-Token': tok})
        with U.urlopen(req, timeout=90) as r:
            skazat('  ДРОП: лог выложен как %s (%d Б), ответ %s' % (imya, len(telo), r.status))
    except Exception as ex:  # noqa: BLE001
        skazat('  ДРОП: не выложился: %r' % (ex,))


def _ctx(tls_ver=None, ciphers=None, alpn=None):
    c = ssl.create_default_context()
    if tls_ver == '1.2':
        c.minimum_version = ssl.TLSVersion.TLSv1_2
        c.maximum_version = ssl.TLSVersion.TLSv1_2
    elif tls_ver == '1.3':
        c.minimum_version = ssl.TLSVersion.TLSv1_3
        c.maximum_version = ssl.TLSVersion.TLSv1_3
    if ciphers:
        try:
            c.set_ciphers(ciphers)
        except Exception as ex:  # noqa: BLE001
            return ('CIPHER-ERR', repr(ex)[:80])
    if alpn is not None:
        try:
            c.set_alpn_protocols(alpn)
        except Exception:  # noqa: BLE001
            pass
    return c


def proba(imya, **kw):
    """Обёртка: гарантирует, что КАЖДАЯ проба напечатается и попадёт в итог.

    Первая версия печатала в конце `_proba`, и пробы с ранним `return` (пустой ответ,
    отказ CONNECT) исчезали молча - ровно та болезнь, которую этот прибор и ищет.
    """
    r = _proba(imya, **kw)
    ITOG.append(r)
    kratko = ('OK ' + str(r.get('kod'))) if r.get('kod') else ('СБОЙ на «%s»: %s'
                                                              % (r['stadiya'], r['oshibka']))
    skazat('  %-34s %-46s %s' % (imya[:34], kratko[:46], json.dumps(r['t'])))
    if r.get('connect'):
        skazat('       CONNECT: %s' % r['connect'])
    if r.get('zag'):
        skazat('       заголовки: %s' % json.dumps(r['zag'], ensure_ascii=False)[:150])
    if r.get('otvet'):
        skazat('       тело: %s' % r['otvet'][:150])
    if r.get('tls'):
        skazat('       tls: %s   %s' % (r['tls'], r.get('sert', '')))
    return r


def _proba(imya, host=HOST, port=PORT, path='/', method='GET', body=None, ua='curl/8.5.0',
           extra_headers=None, tls_ver=None, ciphers=None, alpn=None, proxy=None,
           timeout=40, pauza_pered_telom=0.0, pokazat_otvet=220):
    """Ручной проход по шагам: dns -> tcp -> (CONNECT) -> tls -> заголовки -> тело -> ответ.

    `stadiya` - последний УСПЕШНО пройденный шаг, `oshibka` - на чём споткнулись дальше.
    """
    r = {'proba': imya, 'host': host, 'stadiya': 'start', 'oshibka': None, 'kod': None,
         't': {}}
    s = None
    t0 = time.time()
    try:
        # --- DNS ---
        cel_host, cel_port = (proxy[0], proxy[1]) if proxy else (host, port)
        ai = socket.getaddrinfo(cel_host, cel_port, 0, socket.SOCK_STREAM)
        r['ip'] = sorted({a[4][0] for a in ai})
        r['stadiya'] = 'dns'
        r['t']['dns'] = round(time.time() - t0, 2)

        # --- TCP ---
        t = time.time()
        s = socket.create_connection((cel_host, cel_port), timeout=timeout)
        s.settimeout(timeout)
        r['stadiya'] = 'tcp'
        r['t']['tcp'] = round(time.time() - t, 2)

        # --- CONNECT через прокси ---
        if proxy:
            t = time.time()
            cn = 'CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n' % (host, port, host, port)
            if len(proxy) > 2 and proxy[2]:
                import base64
                au = base64.b64encode(('%s:%s' % (proxy[2], proxy[3])).encode()).decode()
                cn += 'Proxy-Authorization: Basic %s\r\n' % au
            cn += '\r\n'
            s.sendall(cn.encode())
            buf = b''
            while b'\r\n\r\n' not in buf:
                ch = s.recv(4096)
                if not ch:
                    break
                buf += ch
            r['connect'] = buf.split(b'\r\n')[0].decode('latin1')[:60]
            if b' 200' not in buf.split(b'\r\n')[0]:
                r['oshibka'] = 'CONNECT отказ: ' + r['connect']
                return r
            r['stadiya'] = 'connect'
            r['t']['connect'] = round(time.time() - t, 2)

        # --- TLS ---
        t = time.time()
        ctx = _ctx(tls_ver, ciphers, alpn)
        if isinstance(ctx, tuple):
            r['oshibka'] = 'набор шифров не принят питоном: ' + ctx[1]
            return r
        s = ctx.wrap_socket(s, server_hostname=host)
        r['tls'] = '%s / %s' % (s.version(), (s.cipher() or ('?',))[0])
        try:
            cert = s.getpeercert() or {}
            iss = dict(x[0] for x in cert.get('issuer', ()))
            r['sert'] = '%s | до %s' % (iss.get('organizationName', '?')[:22],
                                        (cert.get('notAfter') or '?')[:20])
        except Exception:  # noqa: BLE001
            pass
        r['stadiya'] = 'tls'
        r['t']['tls'] = round(time.time() - t, 2)

        # --- заголовки ---
        t = time.time()
        telo = body if isinstance(body, bytes) else (body or '').encode('utf-8')
        h = ['%s %s HTTP/1.1' % (method, path), 'Host: ' + host, 'Accept: */*',
             'Connection: close']
        if ua:
            h.append('User-Agent: ' + ua)
        for k, v in (extra_headers or {}).items():
            h.append('%s: %s' % (k, v))
        if method != 'GET':
            h.append('Content-Type: application/json')
            h.append('Content-Length: %d' % len(telo))
        s.sendall(('\r\n'.join(h) + '\r\n\r\n').encode('utf-8'))
        r['stadiya'] = 'zagolovki'
        r['t']['zagolovki'] = round(time.time() - t, 2)

        # --- тело отдельно, чтобы отличить обрыв на заголовках от обрыва на теле ---
        if telo:
            if pauza_pered_telom:
                time.sleep(pauza_pered_telom)
            t = time.time()
            s.sendall(telo)
            r['stadiya'] = 'telo'
            r['t']['telo'] = round(time.time() - t, 2)
            r['telo_bayt'] = len(telo)

        # --- ответ ---
        t = time.time()
        buf = b''
        while b'\r\n\r\n' not in buf and len(buf) < 65536:
            ch = s.recv(8192)
            if not ch:
                break
            buf += ch
            if r['stadiya'] != 'pervyy_bayt':
                r['stadiya'] = 'pervyy_bayt'
                r['t']['pervyy_bayt'] = round(time.time() - t, 2)
        if not buf:
            r['oshibka'] = 'ответ пуст: соединение закрыто без единого байта'
            return r
        golova, _, hvost = buf.partition(b'\r\n\r\n')
        stroki = golova.decode('latin1').split('\r\n')
        r['kod'] = stroki[0][:40]
        r['stadiya'] = 'otvet'
        for st in stroki[1:]:
            nk = st.split(':', 1)[0].strip().lower()
            if nk in ('server', 'cf-ray', 'cf-mitigated', 'x-request-id', 'content-type'):
                r.setdefault('zag', {})[nk] = st.split(':', 1)[1].strip()[:48]
        # дочитать немного тела
        try:
            while len(hvost) < pokazat_otvet:
                ch = s.recv(4096)
                if not ch:
                    break
                hvost += ch
        except Exception:  # noqa: BLE001
            pass
        r['otvet'] = hvost.decode('utf-8', 'replace')[:pokazat_otvet].replace('\n', ' ')
        r['t']['vsego'] = round(time.time() - t0, 2)
    except Exception as ex:  # noqa: BLE001
        r['oshibka'] = '%s: %s' % (type(ex).__name__, str(ex)[:120])
        r['t']['vsego'] = round(time.time() - t0, 2)
    finally:
        try:
            if s:
                s.close()
        except Exception:  # noqa: BLE001
            pass
    return r


# ------------------------------------------------------------------ блоки
def blok_env():
    skazat('### ОКРУЖЕНИЕ СЕРВЕРА')
    skazat('  python %s | %s | ssl %s' % (sys.version.split()[0], platform.platform()[:40],
                                          ssl.OPENSSL_VERSION))
    for k in ('PROVIDER_API_KEY', 'PROVIDER_BASE_URL', 'HTTPS_PROXY', 'https_proxy',
              'HTTP_PROXY', 'NO_PROXY'):
        v = os.environ.get(k)
        if k.endswith('KEY') or 'TOKEN' in k:
            skazat('  %-18s %s (длина %s)' % (k, 'есть' if v else 'НЕТ', len(v) if v else '-'))
        else:
            skazat('  %-18s %s' % (k, (v or 'нет')[:60]))
    try:
        import urllib.request as U
        skazat('  системный прокси питона: %s' % json.dumps(U.getproxies())[:140])
    except Exception as ex:  # noqa: BLE001
        skazat('  прокси не прочитан: %r' % (ex,))
    # наш внешний IP - чтобы сравнить с песочницей (версия «блокировка по IP»)
    for h, p in (('api.ipify.org', '/'), ('ifconfig.me', '/ip')):
        r = proba('внешний IP через ' + h, host=h, path=p, timeout=20, pokazat_otvet=60)
        if r.get('otvet'):
            break


def blok_dns():
    skazat('\n### DNS')
    for h in [HOST] + [k[0] for k in KONTROL]:
        t = time.time()
        try:
            ai = socket.getaddrinfo(h, 443, 0, socket.SOCK_STREAM)
            skazat('  %-26s %s  (%.2f с)' % (h, sorted({a[4][0] for a in ai}),
                                             time.time() - t))
        except Exception as ex:  # noqa: BLE001
            skazat('  %-26s НЕ РЕЗОЛВИТСЯ: %r' % (h, ex))


def blok_tcp():
    skazat('\n### TCP до каждого адреса router.cheap (443) - живёт ли порт вообще')
    try:
        ips = sorted({a[4][0] for a in socket.getaddrinfo(HOST, 443, 0, socket.SOCK_STREAM)})
    except Exception as ex:  # noqa: BLE001
        skazat('  dns сдох: %r' % (ex,))
        return
    for ip in ips:
        t = time.time()
        try:
            s = socket.create_connection((ip, 443), timeout=15)
            s.close()
            skazat('  %-20s TCP открыт за %.2f с' % (ip, time.time() - t))
        except Exception as ex:  # noqa: BLE001
            skazat('  %-20s TCP НЕ ОТКРЫТ: %s' % (ip, repr(ex)[:80]))
        # держим соединение открытым 5 с без байтов: рвут ли молчащее соединение
        try:
            s = socket.create_connection((ip, 443), timeout=15)
            s.settimeout(6)
            time.sleep(5)
            try:
                s.setblocking(False)
                ost = s.recv(1)
                skazat('  %-20s молчащее соединение: сервер прислал %d байт (=рвёт)'
                       % (ip, len(ost)))
            except BlockingIOError:
                skazat('  %-20s молчащее соединение живо 5 с (не рвут до ClientHello)' % ip)
            except Exception as ex:  # noqa: BLE001
                skazat('  %-20s молчащее соединение ОБОРВАНО: %s' % (ip, repr(ex)[:60]))
            s.close()
        except Exception as ex:  # noqa: BLE001
            skazat('  %-20s вторая проба не поднялась: %s' % (ip, repr(ex)[:60]))


def blok_tls():
    skazat('\n### TLS: доходит ли до рукопожатия и от чего оно зависит')
    proba('TLS по умолчанию + GET /', path='/')
    proba('TLS 1.2 принудительно', path='/', tls_ver='1.2')
    proba('TLS 1.3 принудительно', path='/', tls_ver='1.3')
    proba('только ECDHE-RSA-AES128-GCM', path='/', tls_ver='1.2',
          ciphers='ECDHE-RSA-AES128-GCM-SHA256')
    proba('шифры DEFAULT (широкий набор)', path='/', ciphers='DEFAULT:@SECLEVEL=1')
    proba('ALPN h2,http/1.1', path='/', alpn=['h2', 'http/1.1'])
    proba('ALPN не заявлен', path='/', alpn=None)


def blok_http():
    skazat('\n### HTTPS GET на корень и на /v1/messages (ответ = ответ, пусть даже 4xx)')
    proba('GET / (UA curl)', path='/')
    proba('GET /v1/models (UA curl)', path='/v1/models')
    proba('POST /v1/messages БЕЗ ключа', path='/v1/messages', method='POST',
          body='{"model":"claude-fable-5","max_tokens":8,"messages":[{"role":"user","content":"hi"}]}',
          extra_headers={'anthropic-version': '2023-06-01'})


def _telo(n_znakov=1):
    txt = 'Ответь одним словом: работает' + (' .' * n_znakov)
    return json.dumps({'model': 'claude-fable-5', 'max_tokens': 16,
                       'messages': [{'role': 'user', 'content': txt}]}, ensure_ascii=False)


def blok_api():
    kl = os.environ.get('PROVIDER_API_KEY') or ''
    skazat('\n### POST /v1/messages С ключом (ключ %s, длина %d)'
           % ('есть' if kl else 'НЕТ', len(kl)))
    if not kl:
        return
    h = {'x-api-key': kl, 'anthropic-version': '2023-06-01'}
    proba('короткое тело (~120 Б)', path='/v1/messages', method='POST', body=_telo(1),
          extra_headers=h, timeout=90)
    proba('то же + stream:true', path='/v1/messages', method='POST',
          body=json.dumps({'model': 'claude-fable-5', 'max_tokens': 16, 'stream': True,
                           'messages': [{'role': 'user', 'content': 'Ответь одним словом: работает'}]}),
          extra_headers=h, timeout=90)
    proba('тело ~4 КБ', path='/v1/messages', method='POST', body=_telo(2000),
          extra_headers=h, timeout=90)
    proba('пауза 3 с между заголовками и телом', path='/v1/messages', method='POST',
          body=_telo(1), extra_headers=h, timeout=90, pauza_pered_telom=3.0)


def blok_ua():
    kl = os.environ.get('PROVIDER_API_KEY') or ''
    skazat('\n### Влияет ли User-Agent (у нас специально curl/8.5.0 из-за WAF шлюза)')
    h = {'x-api-key': kl, 'anthropic-version': '2023-06-01'} if kl else {}
    for imya, ua in (('curl/8.5.0', 'curl/8.5.0'),
                     ('python-urllib/3', 'Python-urllib/3.11'),
                     ('браузерный Chrome', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                                           'Chrome/128.0.0.0 Safari/537.36'),
                     ('без UA вообще', None)):
        proba('GET / UA=' + imya, path='/', ua=ua)
    if kl:
        proba('POST /v1/messages UA=Chrome', path='/v1/messages', method='POST',
              body=_telo(1), extra_headers=h, timeout=90,
              ua='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                 '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')


def blok_kontrol():
    skazat('\n### КОНТРОЛЬ: те же шаги на заведомо живые чужие хосты')
    for h, p in KONTROL:
        proba('контроль ' + h, host=h, path=p, timeout=30, pokazat_otvet=90)


def blok_curl():
    """Отдельный контроль на отпечаток TLS: настоящий curl.exe вместо питона.

    Если curl.exe проходит, а питон рвётся - дело не в IP и не в ключе, а в том, КАК
    питон здоровается (JA3-отпечаток): Cloudflare шлюза видит питоновское рукопожатие
    при заголовке curl и рвёт. Тогда лечится не сетью, а клиентом.
    """
    skazat('\n### curl.exe (другой TLS-стек с того же IP)')
    kl = os.environ.get('PROVIDER_API_KEY') or ''
    pr = [('GET / curl.exe', ['curl.exe', '-sS', '-o', 'NUL', '-w', '%{http_code} %{time_total}',
                              '--max-time', '40', 'https://router.cheap/'])]
    if kl:
        pr.append(('POST /v1/messages curl.exe',
                   ['curl.exe', '-sS', '-o', '-', '-w', '\\nКОД %{http_code} за %{time_total}',
                    '--max-time', '90', 'https://router.cheap/v1/messages',
                    '-H', 'content-type: application/json',
                    '-H', 'anthropic-version: 2023-06-01',
                    '-H', 'x-api-key: ' + kl,
                    '-d', _telo(1)]))
    for imya, cmd in pr:
        t = time.time()
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=120)
            out = (p.stdout or b'').decode('utf-8', 'replace')
            err = (p.stderr or b'').decode('utf-8', 'replace')
            if kl:
                out = out.replace(kl, '<КЛЮЧ>')
                err = err.replace(kl, '<КЛЮЧ>')
            skazat('  %-28s rc=%s за %.1f с | %s' % (imya, p.returncode, time.time() - t,
                                                     (out[-300:] or err[-200:]).replace('\n', ' ')))
        except Exception as ex:  # noqa: BLE001
            skazat('  %-28s не запустился: %r' % (imya, ex))


def blok_proxy():
    """Через мобильные прокси профилей Dolphin (владелец разрешил их жечь)."""
    skazat('\n### Через прокси профилей Dolphin')
    prox = []
    try:
        import urllib.request as U
        req = U.Request('http://localhost:3001/v1.0/browser_profiles?limit=50')
        d = json.loads(U.urlopen(req, timeout=15).read().decode('utf-8', 'replace'))
        for pr in (d.get('data') or d.get('items') or []):
            px = pr.get('proxy') or {}
            if px.get('host') and px.get('port'):
                prox.append((px['host'], int(px['port']), px.get('login'),
                             px.get('password'), px.get('type', '?'), pr.get('name', '')[:18]))
    except Exception as ex:  # noqa: BLE001
        skazat('  локальный API Dolphin не отдал профили: %s' % repr(ex)[:110])
    vidno = {}
    for p in prox:
        vidno.setdefault((p[0], p[1]), p)
    skazat('  прокси найдено: %d уникальных' % len(vidno))
    for (ph, pp), p in list(vidno.items())[:4]:
        if str(p[4]).lower() not in ('http', 'https', ''):
            skazat('  %s:%s тип %s - CONNECT не умеем, пропуск' % (ph, pp, p[4]))
            continue
        proba('через прокси %s (%s)' % (ph, p[5]), path='/', proxy=(ph, pp, p[2], p[3]),
              timeout=60)
        kl = os.environ.get('PROVIDER_API_KEY') or ''
        if kl:
            proba('через прокси %s POST' % ph, path='/v1/messages', method='POST',
                  body=_telo(1), extra_headers={'x-api-key': kl,
                                                'anthropic-version': '2023-06-01'},
                  proxy=(ph, pp, p[2], p[3]), timeout=120)


def _odna_svyaz(ip=None, host=HOST, timeout=20, delat_get=True, ua='curl/8.5.0'):
    """Одно соединение до конца: connect -> handshake -> GET -> код. Возвращает (metka, ip, t)."""
    t0 = time.time()
    s = None
    try:
        cel = ip or host
        s = socket.create_connection((cel, 443), timeout=timeout)
        real_ip = s.getpeername()[0]
        ctx = ssl.create_default_context()
        s = ctx.wrap_socket(s, server_hostname=host)
        if not delat_get:
            return 'tls-ok', real_ip, time.time() - t0
        s.sendall(('GET / HTTP/1.1\r\nHost: %s\r\nUser-Agent: %s\r\nAccept: */*\r\n'
                   'Connection: close\r\n\r\n' % (host, ua)).encode())
        buf = s.recv(64)
        if not buf:
            return 'пусто', real_ip, time.time() - t0
        return buf.decode('latin1').split('\r\n')[0][9:16].strip(), real_ip, time.time() - t0
    except Exception as ex:  # noqa: BLE001
        nm = type(ex).__name__
        if isinstance(ex, ConnectionResetError) or '10054' in str(ex):
            nm = 'RESET'
        elif isinstance(ex, ssl.SSLError):
            nm = 'SSL:' + (getattr(ex, 'reason', '') or '')[:18]
        return nm, (ip or '?'), time.time() - t0
    finally:
        try:
            if s:
                s.close()
        except Exception:  # noqa: BLE001
            pass


def blok_chastota():
    """ГЛАВНЫЙ замер: рвётся ли КАЖДОЕ соединение или доля. Молчаливый сбой почти всегда
    оказывается плавающим, а плавающее лечится ретраем, а не переездом."""
    skazat('\n### ЧАСТОТА СБОЯ: 30 подряд соединений до router.cheap')
    try:
        ai = socket.getaddrinfo(HOST, 443, 0, socket.SOCK_STREAM)
        v4 = sorted({a[4][0] for a in ai if a[0] == socket.AF_INET})
        v6 = sorted({a[4][0] for a in ai if a[0] == socket.AF_INET6})
        skazat('  адреса: IPv4 %s | IPv6 %s' % (v4, v6))
    except Exception as ex:  # noqa: BLE001
        skazat('  dns сдох: %r' % (ex,))
        v4, v6 = [], []
    for imya, celi, n in (('по имени (как клиент)', [None], 30),
                          ('IPv4 %s' % (v4[:1] or ['-']), v4[:1], 10),
                          ('IPv4 %s' % (v4[1:2] or ['-']), v4[1:2], 10),
                          ('IPv6 %s' % (v6[:1] or ['-']), v6[:1], 6)):
        if not celi or celi == ['-']:
            continue
        schet = {}
        stroka = []
        for i in range(n):
            m, ip, t = _odna_svyaz(celi[i % len(celi)])
            schet[m] = schet.get(m, 0) + 1
            stroka.append('.' if m.strip() in ('200', '301', '302', '400', '401', '403')
                          else ('R' if m == 'RESET' else '?'))
            time.sleep(0.4)
        skazat('  %-26s %s  %s' % (imya[:26], ''.join(stroka),
                                   json.dumps(schet, ensure_ascii=False)))
    skazat('  КОНТРОЛЬ теми же 10 соединениями на www.cloudflare.com:')
    schet = {}
    stroka = []
    for i in range(10):
        m, ip, t = _odna_svyaz(host='www.cloudflare.com')
        schet[m] = schet.get(m, 0) + 1
        stroka.append('.' if m.strip().isdigit() else ('R' if m == 'RESET' else '?'))
        time.sleep(0.3)
    skazat('  %-26s %s  %s' % ('www.cloudflare.com', ''.join(stroka),
                               json.dumps(schet, ensure_ascii=False)))
    skazat('  КОНТРОЛЬ: 6 соединений на дроп владельца (заведомо рабочий путь сервера):')
    schet = {}
    for i in range(6):
        m, ip, t = _odna_svyaz(host='parsercompressor.online')
        schet[m] = schet.get(m, 0) + 1
        time.sleep(0.3)
    skazat('  %-26s %s' % ('parsercompressor.online', json.dumps(schet, ensure_ascii=False)))

    skazat('\n  Рвётся ли ПАУЗА: 5 соединений с промежутком 20 с (не всплеск ли виноват)')
    stroka = []
    for i in range(5):
        m, ip, t = _odna_svyaz()
        stroka.append('%s' % m.strip())
        if i < 4:
            time.sleep(20)
    skazat('    ' + ' | '.join(stroka))

    skazat('\n  Молчащее соединение (держим 8 с без ClientHello) - рвут ли до рукопожатия:')
    for i in range(3):
        try:
            s = socket.create_connection((HOST, 443), timeout=15)
            s.settimeout(9)
            time.sleep(8)
            try:
                s.setblocking(False)
                d = s.recv(1)
                skazat('    проба %d: прислали %d Б (FIN/RST до рукопожатия)' % (i + 1, len(d)))
            except BlockingIOError:
                skazat('    проба %d: соединение живо, молчание не наказывается' % (i + 1))
            except Exception as ex:  # noqa: BLE001
                skazat('    проба %d: ОБРЫВ молчащего: %s' % (i + 1, repr(ex)[:60]))
            s.close()
        except Exception as ex:  # noqa: BLE001
            skazat('    проба %d: не поднялось: %s' % (i + 1, repr(ex)[:60]))


def blok_nagruzka():
    """Доля сбоя на РЕАЛЬНОМ вызове модели (то, чем живёт сбор новостей)."""
    kl = os.environ.get('PROVIDER_API_KEY') or ''
    skazat('\n### 8 реальных коротких вызовов /v1/messages подряд (ключ %s)'
           % ('есть' if kl else 'НЕТ'))
    if not kl:
        return
    h = {'x-api-key': kl, 'anthropic-version': '2023-06-01'}
    ok = sboy = 0
    for i in range(8):
        r = _proba('вызов %d' % (i + 1), path='/v1/messages', method='POST', body=_telo(1),
                   extra_headers=h, timeout=90)
        if r.get('kod'):
            ok += 1
        else:
            sboy += 1
        skazat('  вызов %-2d %-34s %s' % (i + 1, (r.get('kod') or
                                                  ('СБОЙ на «%s»: %s' % (r['stadiya'],
                                                                         r['oshibka'])))[:34],
                                          json.dumps(r['t'])))
        time.sleep(1.5)
    skazat('  ИТОГ вызовов: ответ %d, сбой %d из 8' % (ok, sboy))


def blok_klient():
    """Как падает НАШ рабочий путь - verify_company._provider_call_stdlib."""
    skazat('\n### Наш штатный путь: verify_company._provider_call_stdlib')
    sys.path.insert(0, r'C:\sender\server')
    try:
        import verify_company as VC
        t = time.time()
        try:
            out = VC._provider_call_stdlib('Ответь одним словом: работает')
            skazat('  ОТВЕТ %d знаков за %.1f с: %r' % (len(out or ''), time.time() - t,
                                                        (out or '')[:60]))
        except Exception as ex:  # noqa: BLE001
            skazat('  СБОЙ за %.1f с: %s: %s' % (time.time() - t, type(ex).__name__,
                                                 str(ex)[:160]))
        import inspect
        src = inspect.getsource(VC._provider_call_stdlib)
        nuzhno = [l for l in src.split('\n')
                  if any(z in l for z in ('_BEZ_PROXY', 'ProxyHandler', 'build_opener',
                                          'Request(', 'add_header', 'User-Agent', 'context',
                                          'ssl', 'timeout', 'stream'))]
        skazat('  ключевые строки клиента (%d):' % len(nuzhno))
        for l in nuzhno[:22]:
            skazat('    ' + l.strip()[:110])
    except Exception as ex:  # noqa: BLE001
        skazat('  verify_company не прочитан: %r' % (ex,))


BLOKI = {'env': blok_env, 'dns': blok_dns, 'tcp': blok_tcp, 'tls': blok_tls,
         'http': blok_http, 'api': blok_api, 'ua': blok_ua, 'kontrol': blok_kontrol,
         'curl': blok_curl, 'proxy': blok_proxy, 'klient': blok_klient,
         'chastota': blok_chastota, 'nagruzka': blok_nagruzka}

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a in BLOKI]
    if not args:
        args = ['env', 'dns', 'tcp', 'tls', 'http', 'api', 'ua', 'kontrol', 'curl', 'klient']
    for a in args:
        try:
            BLOKI[a]()
        except Exception as ex:  # noqa: BLE001
            skazat('### блок %s упал целиком: %r' % (a, ex))
    # итог дублируем в конце: вывод приходит хвостом
    skazat('\n=== ИТОГ: докуда дошла каждая проба ===')
    for r in ITOG:
        skazat('%-36s %-10s %s' % (r['proba'][:36], r['stadiya'],
                                   (r.get('kod') or r.get('oshibka') or '')[:60]))
    vylozhit_na_drop('3s-shlyuz-log-%s.txt' % '-'.join(args))
