# -*- coding: utf-8 -*-
"""Три вопроса по лечению шлюза, один заход на сервере.

1. ПРОКСИ. Владелец разрешил жечь мобильные прокси. Проверяем: проходит ли через них
   то, что напрямую рвётся. Значения прокси НЕ печатаются - только хост и итог.
2. ЛЕКАРСТВО. Предлагаемая правка: перебирать ВСЕ адреса имени и проверять каждый
   рукопожатием, а не только TCP-connect. Проверяем на живом вызове модели.
3. ЗАМЕР «ДО» для правки `extract_event`: как сейчас ведёт себя классификатор и где
   именно он зовётся (места вызова нужны, чтобы правка не сломала конвейер).

Прибор ничего не правит: только читает и звонит.
"""
import json
import os
import re
import socket
import ssl
import sys
import time

sys.path.insert(0, r'C:\sender\server')

HOST = 'router.cheap'
TELO = json.dumps({'model': 'claude-fable-5', 'max_tokens': 16,
                   'messages': [{'role': 'user', 'content': 'Ответь одним словом: работает'}]})


def sekret(imya):
    v = os.environ.get(imya)
    if v:
        return v
    for p in (r'C:\sender\server\runner-secrets.env', r'C:\sender\runner-secrets.env',
              r'C:\sender\rs.env'):
        try:
            for line in open(p, encoding='utf-8', errors='replace'):
                if line.strip().startswith(imya + '='):
                    return line.split('=', 1)[1].strip()
        except Exception:  # noqa: BLE001
            continue
    return None


def zapros(sock, path='/v1/messages', telo=TELO, kluch=None):
    h = ['POST %s HTTP/1.1' % path, 'Host: ' + HOST, 'User-Agent: curl/8.5.0',
         'Accept: */*', 'Connection: close', 'Content-Type: application/json',
         'anthropic-version: 2023-06-01', 'Content-Length: %d' % len(telo.encode())]
    if kluch:
        h.append('x-api-key: ' + kluch)
    sock.sendall(('\r\n'.join(h) + '\r\n\r\n' + telo).encode('utf-8'))
    buf = b''
    while b'\r\n\r\n' not in buf and len(buf) < 32768:
        ch = sock.recv(8192)
        if not ch:
            break
        buf += ch
    if not buf:
        return 'пусто (соединение закрыто без байтов)'
    return buf.decode('latin1').split('\r\n')[0][:40]


# ---------------------------------------------------------------- 1. прокси
def cherez_proksi():
    print('\n### 1. ЧЕРЕЗ МОБИЛЬНЫЕ ПРОКСИ')
    kluch = sekret('PROVIDER_API_KEY')
    nashli = 0
    for imya in ('PROXY_URL', 'PROXY_URLV2', 'PROXY_URLV3'):
        u = sekret(imya)
        if not u:
            print('  %-12s в ключнице нет' % imya)
            continue
        nashli += 1
        u = u.strip()
        # форма записи (без значений): чтобы разобрать любой из принятых у нас форматов
        print('  %-12s форма: %s' % (imya, re.sub(r'[^:/@.]', 'x', u)[:70]))
        log = par = ph = pp = None
        m = re.match(r'^(?:https?://)?(?:([^:@/]+):([^@/]*)@)?([^:/@]+):(\d+)', u)
        if m:
            log, par, ph, pp = m.groups()
        if not ph:
            # формат хост:порт:логин:пароль
            ch = u.split('://')[-1].split(':')
            if len(ch) >= 4 and ch[1].isdigit():
                ph, pp, log, par = ch[0], ch[1], ch[2], ':'.join(ch[3:])
            elif len(ch) == 2 and ch[1].split('/')[0].isdigit():
                ph, pp = ch[0], ch[1].split('/')[0]
        if not ph:
            print('  %-12s адрес прокси не разобрался ни одним из двух форматов' % imya)
            continue
        t0 = time.time()
        s = None
        try:
            s = socket.create_connection((ph, int(pp)), timeout=30)
            s.settimeout(90)
            cn = 'CONNECT %s:443 HTTP/1.1\r\nHost: %s:443\r\n' % (HOST, HOST)
            if log:
                import base64
                cn += ('Proxy-Authorization: Basic %s\r\n'
                       % base64.b64encode(('%s:%s' % (log, par)).encode()).decode())
            s.sendall((cn + '\r\n').encode())
            buf = b''
            while b'\r\n\r\n' not in buf:
                ch = s.recv(4096)
                if not ch:
                    break
                buf += ch
            pervaya = buf.split(b'\r\n')[0].decode('latin1')
            if b' 200' not in buf.split(b'\r\n')[0]:
                print('  %-12s %-22s CONNECT отказ: %s' % (imya, ph[:22], pervaya[:40]))
                continue
            s = ssl.create_default_context().wrap_socket(s, server_hostname=HOST)
            kod = zapros(s, kluch=kluch)
            print('  %-12s %-22s -> %s за %.1f с' % (imya, ph[:22], kod, time.time() - t0))
        except Exception as ex:  # noqa: BLE001
            print('  %-12s %-22s СБОЙ за %.1f с: %s: %s'
                  % (imya, ph[:22], time.time() - t0, type(ex).__name__, str(ex)[:70]))
        finally:
            try:
                if s:
                    s.close()
            except Exception:  # noqa: BLE001
                pass
    if not nashli:
        print('  прокси в ключнице раннера не нашлось')


# ---------------------------------------------------------------- 2. лекарство
def soedinit_umno(host=HOST, port=443, timeout=20, ctx=None):
    """Перебор ВСЕХ адресов имени с проверкой РУКОПОЖАТИЕМ, а не только TCP-connect.

    Штатный `socket.create_connection` переходит к следующему адресу только если не удался
    TCP-connect. У нас TCP-connect к мёртвому адресу УДАЁТСЯ (фильтр отвечает SYN-ACK за
    0,02 с), а рвётся рукопожатие - и перебора уже нет. Отсюда «шлюз лежит» при живом
    втором адресе того же имени.
    """
    ctx = ctx or ssl.create_default_context()
    besy = []
    for sem in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        af, tp, pr, _c, sa = sem
        s = None
        try:
            s = socket.socket(af, tp, pr)
            s.settimeout(timeout)
            s.connect(sa)
            s = ctx.wrap_socket(s, server_hostname=host)
            return s, sa[0], besy
        except Exception as ex:  # noqa: BLE001
            besy.append('%s: %s' % (sa[0], type(ex).__name__))
            try:
                if s:
                    s.close()
            except Exception:  # noqa: BLE001
                pass
    raise OSError('ни один адрес %s не дал рукопожатия: %s' % (host, '; '.join(besy)))


def lekarstvo():
    print('\n### 2. ЛЕКАРСТВО: перебор адресов с проверкой рукопожатием')
    kluch = sekret('PROVIDER_API_KEY')
    ai = socket.getaddrinfo(HOST, 443, socket.AF_INET, socket.SOCK_STREAM)
    print('  DNS сейчас отдаёт первым: %s' % ai[0][4][0])
    ok = sboy = 0
    for i in range(5):
        t0 = time.time()
        try:
            s, ip, besy = soedinit_umno()
            kod = zapros(s, kluch=kluch)
            s.close()
            ok += 1
            print('  попытка %d: %s через %s за %.1f с%s'
                  % (i + 1, kod, ip, time.time() - t0,
                     ('   (мимо мёртвых: %s)' % '; '.join(besy)) if besy else ''))
        except Exception as ex:  # noqa: BLE001
            sboy += 1
            print('  попытка %d: СБОЙ за %.1f с: %s' % (i + 1, time.time() - t0,
                                                        str(ex)[:120]))
        time.sleep(1)
    print('  ИТОГ лекарства: ответ %d, сбой %d из 5' % (ok, sboy))


# ---------------------------------------------------------------- 3. места вызова
def mesta_vyzova():
    print('\n### 3. ГДЕ ЗОВЁТСЯ extract_event (правка не должна сломать конвейер)')
    put = r'C:\sender\server\news_scan.py'
    try:
        stroki = open(put, encoding='utf-8', errors='replace').read().split('\n')
    except Exception as ex:  # noqa: BLE001
        print('  %s не прочитан: %r' % (put, ex))
        return
    print('  %s: %d строк' % (put, len(stroki)))
    for i, l in enumerate(stroki, 1):
        if 'extract_event' in l:
            print('  --- строка %d ---' % i)
            for j in range(max(0, i - 6), min(len(stroki), i + 10)):
                mark = '>>' if j == i - 1 else '  '
                print('  %s %4d| %s' % (mark, j + 1, stroki[j][:112]))
    schet()


def schet():
    """Куда встроить ВИДИМЫЙ счётчик отказа: ищем, чем модуль отчитывается о прогоне."""
    put = r'C:\sender\server\news_scan.py'
    stroki = open(put, encoding='utf-8', errors='replace').read().split('\n')
    print('\n  чем модуль отчитывается о прогоне (raw_items/capex_events/with_inn/return):')
    for i, l in enumerate(stroki, 1):
        if re.search(r"raw_items|capex_events|with_inn|saved_to_db", l):
            print('  %4d| %s' % (i, l[:112]))
    print('\n  сигнатура enrich_ev и её окрестности:')
    for i, l in enumerate(stroki, 1):
        if re.search(r"def enrich_ev|def run\(|def main\(|ThreadPoolExecutor", l):
            print('  %4d| %s' % (i, l[:112]))


# ---------------------------------------------------------------- 4. замер «до»
def zamer_do():
    print('\n### 4. ЗАМЕР «ДО»: что отвечает extract_event сейчас')
    try:
        import news_scan as NS
    except Exception as ex:  # noqa: BLE001
        print('  news_scan не импортируется: %r' % (ex,))
        return
    KONTROL = [
        ('ОАО «Щекиноазот» ввело в эксплуатацию установку по производству метанола, '
         'инвестиции 20 млрд рублей', 'капекс'),
        ('«Норникель» объявил тендер на поставку центробежных компрессоров', 'капекс'),
        ('СИБУР начал строительство газоперерабатывающего комплекса', 'капекс'),
        ('Погода в Москве на выходные: ожидается дождь', 'ПУСТОЙ КОНТРОЛЬ'),
        ('Курс доллара вырос на 2 рубля', 'ПУСТОЙ КОНТРОЛЬ'),
        ('В Москве прошёл концерт классической музыки', 'ПУСТОЙ КОНТРОЛЬ'),
    ]
    nul = 0
    for t, chto in KONTROL:
        t0 = time.time()
        r = NS.extract_event(t, 'проба')
        if r is None:
            nul += 1
        print('  %-16s -> %s (%.1f с)' % (chto, json.dumps(r, ensure_ascii=False)[:70],
                                          time.time() - t0))
    print('  NULL: %d из %d  <- капекс и пустой контроль НЕОТЛИЧИМЫ' % (nul, len(KONTROL)))


def dokazat():
    """Доказать, что лекарство ОБХОДИТ мёртвый адрес, а не просто везёт с порядком DNS.

    В прошлом прогоне лекарство дало 5 ответов из 5, но DNS в ту минуту сам отдавал живой
    адрес первым - то есть перебор ни разу не понадобился, и «обходит» было бы словом на
    веру. Здесь порядок адресов принудительно ставится мёртвым вперёд.
    """
    print('\n### ДОКАЗАТЕЛЬСТВО: мёртвый адрес ставим ПЕРВЫМ принудительно')
    kluch = sekret('PROVIDER_API_KEY')
    nastoyashchiy = socket.getaddrinfo
    ai = [x for x in nastoyashchiy(HOST, 443, socket.AF_INET, socket.SOCK_STREAM)]
    ips = sorted({x[4][0] for x in ai})
    mertvyy = [ip for ip in ips if ip.startswith('104.')]
    if not mertvyy:
        print('  адреса 104.* сейчас нет в выдаче DNS, доказывать не на чем: %s' % ips)
        return
    poryadok = sorted(ai, key=lambda x: 0 if x[4][0].startswith('104.') else 1)
    print('  порядок для пробы: %s' % [x[4][0] for x in poryadok])

    def podmena(*a, **k):
        return poryadok

    print('  -- как ходит ШТАТНЫЙ create_connection (то, что внутри urllib) --')
    for i in range(2):
        t0 = time.time()
        try:
            socket.getaddrinfo = podmena
            s = socket.create_connection((HOST, 443), timeout=20)
            ip = s.getpeername()[0]
            s = ssl.create_default_context().wrap_socket(s, server_hostname=HOST)
            kod = zapros(s, kluch=kluch)
            s.close()
            print('     попытка %d: %s через %s за %.1f с' % (i + 1, kod, ip,
                                                              time.time() - t0))
        except Exception as ex:  # noqa: BLE001
            print('     попытка %d: СБОЙ за %.1f с: %s: %s'
                  % (i + 1, time.time() - t0, type(ex).__name__, str(ex)[:90]))
        finally:
            socket.getaddrinfo = nastoyashchiy

    print('  -- как ходит ЛЕКАРСТВО (перебор с проверкой рукопожатием) --')
    for i in range(2):
        t0 = time.time()
        try:
            socket.getaddrinfo = podmena
            s, ip, besy = soedinit_umno(timeout=12)
            socket.getaddrinfo = nastoyashchiy
            kod = zapros(s, kluch=kluch)
            s.close()
            print('     попытка %d: %s через %s за %.1f с | пропущено мёртвых: %s'
                  % (i + 1, kod, ip, time.time() - t0, besy or 'ни одного'))
        except Exception as ex:  # noqa: BLE001
            print('     попытка %d: СБОЙ за %.1f с: %s' % (i + 1, time.time() - t0,
                                                           str(ex)[:110]))
        finally:
            socket.getaddrinfo = nastoyashchiy


if __name__ == '__main__':
    bloki = sys.argv[1:] or ['proksi', 'lekarstvo', 'mesta', 'do']
    if 'dokazat' in bloki:
        dokazat()
    if 'proksi' in bloki:
        cherez_proksi()
    if 'lekarstvo' in bloki:
        lekarstvo()
    if 'mesta' in bloki:
        mesta_vyzova()
    if 'schet' in bloki:
        schet()
    if 'do' in bloki:
        zamer_do()
    print('\n=== проба лечения закончена ===')
