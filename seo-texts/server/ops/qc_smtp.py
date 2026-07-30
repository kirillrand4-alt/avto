# -*- coding: utf-8 -*-
"""SMTP-проба ЯЩИКА через RCPT TO. ПИСЬМО НЕ ОТПРАВЛЯЕТСЯ.

ЧТО ИМЕННО МЕРЯЕТ. Не «жив ли адрес», а «принимает ли почтовый сервер домена
конверт на этот адрес в RCPT TO с нашего IP». Это две разные величины, и вся
конструкция ниже нужна ровно затем, чтобы их не перепутать:

  * сервер может отвечать 250 на ЛЮБОЙ адрес (catch-all) — тогда «принял» не
    значит «ящик есть». Ловится пробой заведомо несуществующего ящика на том же
    домене ДО настоящих адресов;
  * сервер может отвечать 550 на любой адрес с незнакомого IP (глухой отказ) —
    тогда «отверг» не значит «ящика нет». Отличается только тем, что на ТОМ ЖЕ
    домене хоть один настоящий адрес получил 250. Домен, где такое случилось,
    помечается «различает адреса», и лишь на нём приговор «ящика нет» имеет
    силу. Это и есть честная граница выборки.

ПРОТОКОЛ: connect -> EHLO -> MAIL FROM -> RCPT TO (фальшивый) -> RSET ->
RCPT TO (настоящие) -> QUIT. Команды DATA нет НИ В ОДНОЙ ветке — проверено
глазами и отсутствием вызова srv.data()/srv.send_message() в файле.

Вежливость: одно соединение на ДОМЕН (а не на адрес), не больше _RCPT_КАП
адресов за сессию, интервал между соединениями к одному MX-хосту, очередь
перемешана по MX-хостам (иначе 684 яндексовых домена бьют в один хост подряд).

Durable: таблицы smtp_domains и email_smtp в enrich.db + qc_smtp_stream.jsonl.
Резюм: домен с непустым checked_at не переспрашивается.

Запуск: python qc_smtp.py [бюджет_сек] [потоков] [--recheck] [--limit N]
"""
import io
import json
import os
import random
import re
import smtplib
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 330.0
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 14
ПЕРЕПРОВЕРКА = '--recheck' in sys.argv
ЛИМИТ = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 0
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\qc_smtp_stream.jsonl'
_RCPT_КАП = 12          # адресов за одну сессию: больше — сервер бросает 421
_ИНТЕРВАЛ_MX = 0.8      # сек между соединениями к одному и тому же MX-хосту
_ОТПРАВИТЕЛЬ = 'postmaster@parsercompressor.online'
_HELO = 'parsercompressor.online'

print(json.dumps({'ГОЛОВА': 'qc_smtp старт', 'бюджет': БЮДЖЕТ,
                  'потоков': ПОТОКОВ}, ensure_ascii=False))
sys.stdout.flush()

db = EDB.EnrichDB()
e = db.cx
e.execute("""CREATE TABLE IF NOT EXISTS smtp_domains(
    domain TEXT PRIMARY KEY, mx_host TEXT, banner TEXT,
    code_fake INTEGER, catchall INTEGER, state TEXT,
    n_probed INTEGER, n_ok INTEGER, n_reject INTEGER, n_temp INTEGER,
    err TEXT, checked_at TEXT)""")
e.execute("""CREATE TABLE IF NOT EXISTS email_smtp(
    email TEXT PRIMARY KEY, domain TEXT, mx_host TEXT,
    code INTEGER, verdict TEXT, msg TEXT, checked_at TEXT)""")
e.commit()

# ---- очередь: домен -> его адреса ----
по_домену = {}
for (em,) in e.execute("select distinct lower(trim(email)) from emails "
                       "where email like '%@%.%'"):
    if not em or em.count('@') != 1:
        continue
    d = em.split('@')[1]
    if not d or ' ' in d:
        continue
    по_домену.setdefault(d, []).append(em)

готово = set() if ПЕРЕПРОВЕРКА else {
    r[0] for r in e.execute("select domain from smtp_domains "
                            "where coalesce(checked_at,'')<>''")}
# MX из уже сделанного скана (mx_scan), чтобы не ходить в DNS второй раз
mx_кэш = {}
try:
    for d, h in e.execute("select domain, mx_host from mx_domains"):
        mx_кэш[d] = h or ''
except Exception:  # noqa: BLE001
    pass

todo = [d for d in по_домену if d not in готово]
# перемешать по MX-хосту: подряд идущие яндексовые домены иначе бьют в один хост
todo.sort(key=lambda d: (random.random()))
корзины = {}
for d in todo:
    корзины.setdefault(mx_кэш.get(d, '?'), []).append(d)
очередь = []
while корзины:
    for h in list(корзины):
        очередь.append(корзины[h].pop())
        if not корзины[h]:
            del корзины[h]
if ЛИМИТ:
    очередь = очередь[:ЛИМИТ]

o = {'доменов_всего': len(по_домену), 'адресов_всего': sum(len(v) for v in по_домену.values()),
     'уже_проверено_доменов': len(готово), 'в_очереди': len(очередь),
     'обработано': 0, 'catchall': 0, 'no_mx': 0, 'conn_fail': 0,
     'адресов_ok': 0, 'адресов_reject': 0, 'адресов_temp': 0, 'адресов_unknown': 0}

замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
_mx_замки = {}
_mx_последний = {}
_gl = threading.Lock()


def _мх_ждать(host):
    """Не чаще одного соединения в _ИНТЕРВАЛ_MX к одному MX-хосту."""
    with _gl:
        lk = _mx_замки.setdefault(host, threading.Lock())
    with lk:
        t = _mx_последний.get(host, 0.0)
        д = _ИНТЕРВАЛ_MX - (time.time() - t)
        if д > 0:
            time.sleep(д)
        _mx_последний[host] = time.time()


def mx_host(домен):
    h = mx_кэш.get(домен)
    if h:
        return h
    try:
        r = subprocess.run(['nslookup', '-type=MX', домен], capture_output=True,
                           text=True, timeout=12, encoding='utf-8', errors='replace')
        txt = r.stdout or ''
    except Exception:  # noqa: BLE001
        return ''
    хосты = re.findall(r'mail exchanger\s*=\s*(?:\d+\s+)?(\S+)', txt, re.I)
    return хосты[0].strip().rstrip('.') if хосты else ''


def работа(домен):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    адреса = sorted(set(по_домену.get(домен) or []))
    зап = {'domain': домен, 'mx_host': '', 'banner': '', 'code_fake': None,
           'catchall': None, 'state': '', 'n_probed': 0, 'n_ok': 0,
           'n_reject': 0, 'n_temp': 0, 'err': ''}
    строки = []
    host = mx_host(домен)
    зап['mx_host'] = host
    if not host:
        зап['state'] = 'no_mx'
        for a in адреса:
            строки.append((a, домен, '', None, 'no_mx', '', db.now))
        _сохранить(зап, строки)
        return
    _мх_ждать(host)
    srv = None
    try:
        srv = smtplib.SMTP(timeout=14)
        код, баннер = srv.connect(host, 25)
        зап['banner'] = (баннер or b'').decode('utf-8', 'replace')[:160] \
            if isinstance(баннер, bytes) else str(баннер)[:160]
        if код >= 400:
            зап['state'] = 'greet_reject'
            зап['err'] = str(код)
            for a in адреса:
                строки.append((a, домен, host, код, 'blocked_greet', зап['banner'][:120], db.now))
            _сохранить(зап, строки)
            try:
                srv.close()
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            srv.ehlo(_HELO)
        except Exception:  # noqa: BLE001
            srv.helo(_HELO)
        код_mf, отв_mf = srv.mail(_ОТПРАВИТЕЛЬ)
        if код_mf >= 400:
            зап['state'] = 'mailfrom_reject'
            зап['err'] = str(код_mf) + ' ' + (отв_mf or b'').decode('utf-8', 'replace')[:80]
            for a in адреса:
                строки.append((a, домен, host, код_mf, 'blocked_mailfrom',
                               зап['err'][:120], db.now))
            _сохранить(зап, строки)
            srv.quit()
            return
        # --- контроль catch-all: заведомо несуществующий ящик ЭТОГО домена ---
        фейк = 'nx%s@%s' % (''.join(random.choice('abcdefghijkmnpqrstuvwxyz0123456789')
                                    for _ in range(12)), домен)
        код_ф, отв_ф = srv.rcpt(фейк)
        зап['code_fake'] = код_ф
        зап['catchall'] = 1 if код_ф in (250, 251, 252) else 0
        try:
            srv.rset()
            srv.mail(_ОТПРАВИТЕЛЬ)
        except Exception:  # noqa: BLE001
            pass
        if зап['catchall']:
            зап['state'] = 'catchall'
            for a in адреса:
                строки.append((a, домен, host, код_ф, 'catchall',
                               'домен принимает любой адрес', db.now))
            _сохранить(зап, строки)
            try:
                srv.quit()
            except Exception:  # noqa: BLE001
                pass
            return
        зап['state'] = 'probed'
        for i, a in enumerate(адреса):
            if i >= _RCPT_КАП:
                строки.append((a, домен, host, None, 'unprobed',
                               'потолок адресов за сессию', db.now))
                continue
            try:
                к, отв = srv.rcpt(a)
            except Exception as ex:  # noqa: BLE001
                строки.append((a, домен, host, None, 'conn_lost',
                               type(ex).__name__, db.now))
                зап['err'] = 'обрыв на ' + str(i)
                break
            т = (отв or b'').decode('utf-8', 'replace')[:110] if isinstance(отв, bytes) \
                else str(отв)[:110]
            if к in (250, 251, 252):
                в = 'ok'
                зап['n_ok'] += 1
            elif к in (550, 551, 553, 554, 501, 502, 552, 555):
                в = 'reject'
                зап['n_reject'] += 1
            elif 400 <= к < 500:
                в = 'tempfail'
                зап['n_temp'] += 1
            else:
                в = 'unknown'
            зап['n_probed'] += 1
            строки.append((a, домен, host, к, в, т, db.now))
            if к == 421:                       # сервер попросил уйти
                зап['err'] = '421 на ' + str(i)
                break
            try:
                srv.rset()
                srv.mail(_ОТПРАВИТЕЛЬ)
            except Exception:  # noqa: BLE001
                break
        try:
            srv.quit()
        except Exception:  # noqa: BLE001
            pass
    except (socket.timeout, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected,
            OSError) as ex:
        зап['state'] = зап['state'] or 'conn_fail'
        зап['err'] = type(ex).__name__ + ': ' + str(ex)[:70]
        if not строки:
            for a in адреса:
                строки.append((a, домен, host, None, 'conn_fail',
                               зап['err'][:110], db.now))
    except Exception as ex:  # noqa: BLE001
        зап['state'] = зап['state'] or 'error'
        зап['err'] = type(ex).__name__ + ': ' + str(ex)[:70]
        if not строки:
            for a in адреса:
                строки.append((a, домен, host, None, 'unknown',
                               зап['err'][:110], db.now))
    finally:
        try:
            if srv:
                srv.close()
        except Exception:  # noqa: BLE001
            pass
    _сохранить(зап, строки)


def _сохранить(зап, строки):
    with замок:
        e.execute('INSERT OR REPLACE INTO smtp_domains(domain,mx_host,banner,'
                  'code_fake,catchall,state,n_probed,n_ok,n_reject,n_temp,err,'
                  'checked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (зап['domain'], зап['mx_host'], зап['banner'], зап['code_fake'],
                   зап['catchall'], зап['state'], зап['n_probed'], зап['n_ok'],
                   зап['n_reject'], зап['n_temp'], зап['err'], db.now))
        if строки:
            e.executemany('INSERT OR REPLACE INTO email_smtp'
                          '(email,domain,mx_host,code,verdict,msg,checked_at)'
                          ' VALUES(?,?,?,?,?,?,?)', строки)
        o['обработано'] += 1
        if зап['state'] == 'catchall':
            o['catchall'] += 1
        elif зап['state'] == 'no_mx':
            o['no_mx'] += 1
        elif зап['state'] in ('conn_fail', 'error', 'greet_reject', 'mailfrom_reject'):
            o['conn_fail'] += 1
        o['адресов_ok'] += зап['n_ok']
        o['адресов_reject'] += зап['n_reject']
        o['адресов_temp'] += зап['n_temp']
        if o['обработано'] % 20 == 0:
            e.commit()
        ф.write(json.dumps({'д': зап['domain'], 'mx': зап['mx_host'],
                            'сост': зап['state'], 'ф': зап['code_fake'],
                            'ok': зап['n_ok'], 'rej': зап['n_reject'],
                            'tmp': зап['n_temp'], 'err': зап['err'][:60]},
                           ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(работа, очередь))
e.commit()
ф.close()

o['сек'] = round(time.time() - НАЧАЛО)
o['осталось_доменов'] = e.execute(
    'select count(*) from (select distinct lower(substr(email,instr(email,%s)+1)) d '
    "from emails where email like '%%@%%.%%') x "
    'where d not in (select domain from smtp_domains)' % "'@'").fetchone()[0]
o['в_email_smtp'] = e.execute('select count(*) from email_smtp').fetchone()[0]
o['вердикты'] = {r[0]: r[1] for r in e.execute(
    'select verdict, count(*) from email_smtp group by 1 order by 2 desc')}
o['состояния_доменов'] = {r[0]: r[1] for r in e.execute(
    'select state, count(*) from smtp_domains group by 1 order by 2 desc')}
print(json.dumps(o, ensure_ascii=False, indent=1))
print(json.dumps({'ХВОСТ': 'qc_smtp круг готов', 'обработано': o['обработано'],
                  'осталось': o['осталось_доменов'], 'сек': o['сек']},
                 ensure_ascii=False))
sys.stdout.flush()
os._exit(0)
