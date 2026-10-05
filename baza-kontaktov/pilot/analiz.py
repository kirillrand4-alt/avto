# -*- coding: utf-8 -*-
"""Пилот XMLRiver, этапы после сбора выдачи (ТЗ п. 3.2–5). Запускается НА СЕРВЕРЕ.
LLM не вызывается, рабочие базы открываются только на чтение (sqlite mode=ro).

    python analiz.py etalon      # известные домены и ИНН → etalon.json
    python analiz.py proverka    # главные страницы кандидатов → sayty.jsonl (продолжение по домену)
    python analiz.py otchet      # BAZA-PILOT-DOMENY.csv + svodka.json

Колонки таблиц определяются по именам (site/url/email/inn), в выводе печатаются только
имена колонок и счётчики.
"""
import csv
import gzip
import html as H
import json
import os
import re
import sqlite3
import ssl
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import obrabotka as O  # noqa: E402

OUT = os.environ.get('BP_OUT', r'C:\sender\_ops\baza_pilot')
SERP = os.path.join(OUT, 'BAZA-PILOT-SERP.jsonl')
ETALON = os.path.join(OUT, 'etalon.json')
SAYTY = os.path.join(OUT, 'sayty.jsonl')
DROP = os.environ.get('BP_DROP', r'C:\seostat\drop\drop-storage')
DBS = [r'C:\sender\enrich.db', r'C:\sender\obzvon-index.db']
CSVS = [os.path.join(DROP, 'meyer-kompanii-0510.csv'), os.path.join(DROP, 'MEYER-BAZA-KOMPANII.csv')]
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36'
_EMAIL = re.compile(r'[\w.+-]+@([\w-]+\.)+[a-zа-я]{2,}', re.I)
_URLISH = re.compile(r'(https?://)?([\w-]+\.)+(ru|рф|xn--p1ai|by|com|net|org|su|info|biz|pro|kz)\b', re.I)


# --- эталон ---------------------------------------------------------------------------

def _ingest(val, kind, doms, inns):
    s = str(val or '')
    if not s:
        return
    if kind == 'inn':
        for x in re.findall(r'\d{10}|\d{12}|\d{9}', s):
            inns.add(x)
        return
    for m in _EMAIL.finditer(s):
        d = O.email_domain(m.group(0))
        if d:
            doms.add(d)
    if kind in ('site', 'url'):
        for m in _URLISH.finditer(s):
            if '@' in s[max(0, m.start() - 1):m.start()]:
                continue
            d = O.norm_domain(m.group(0))
            if d and d not in O._FREE_MAIL:
                doms.add(d)


_SKIP = {'site_description', 'site_title', 'site_source', 'phones_site', 'dir_inn'}


def _kind(col):
    c = col.lower()
    if c in _SKIP:
        return None
    if 'inn' in c or 'инн' in c or 'unp' in c:
        return 'inn'
    if 'mail' in c:
        return 'email'
    if any(k in c for k in ('site', 'сайт', 'domain', 'домен', 'url', 'web')):
        return 'site'
    return None


def etalon():
    doms, inns, cand, log = set(), set(), set(), []
    for db in DBS:
        if not os.path.exists(db):
            log.append(f'нет {db}')
            continue
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        want = {'companies', 'phone_contacts', 'obzvon'}
        for (t,) in con.execute("select name from sqlite_master where type='table'"):
            if t not in want:
                continue
            cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
            use = {c: _kind(c) for c in cols if _kind(c)}
            if t == 'phone_contacts':
                use = {c: k for c, k in use.items() if c == 'source_url' or k == 'email'}
            log.append(f'{os.path.basename(db)}:{t} колонки {sorted(use)}')
            if not use:
                continue
            q = 'select ' + ','.join(f'"{c}"' for c in use) + f' from "{t}"'
            n = 0
            for row in con.execute(q):
                n += 1
                for (c, k), v in zip(use.items(), row):
                    # cand_site — непроверенные кандидаты старого поиска: отдельно, не «известное»
                    _ingest(v, k, cand if c == 'cand_site' else doms, inns)
            log.append(f'  строк {n}')
        con.close()
    for p in CSVS:
        if not os.path.exists(p):
            log.append(f'нет {p}')
            continue
        with open(p, encoding='utf-8-sig', errors='replace') as f:
            r = csv.DictReader(f, delimiter=';' if f.readline().count(';') > 2 else ',')
            f.seek(0)
            r = csv.DictReader(f, delimiter=r.reader.dialect.delimiter)
            use = {c: _kind(c) for c in (r.fieldnames or []) if c and _kind(c)}
            log.append(f'{os.path.basename(p)} колонки {sorted(use)}')
            for row in r:
                for c, k in use.items():
                    _ingest(row.get(c), k, doms, inns)
    os.makedirs(OUT, exist_ok=True)
    json.dump({'domains': sorted(doms), 'inns': sorted(inns), 'cand_domains': sorted(cand - doms)},
              open(ETALON, 'w', encoding='utf-8'))
    print('===ИТОГ===')
    print('\n'.join(log))
    print(f'доменов {len(doms)}, ИНН/УНП {len(inns)}, кандидатов cand_site вне эталона {len(cand - doms)}')


# --- выдача → кандидаты -------------------------------------------------------------

def serp_rows():
    for line in open(SERP, encoding='utf-8'):
        j = json.loads(line)
        for d in j.get('docs') or []:
            yield {'engine': j['engine'], 'query': j['query'], 'segment': j['segment'],
                   'subsegment': j['subsegment'], 'region': j['region'], 'qid': j['qid'], **d}


def kandidaty():
    return O.aggregate(serp_rows(), O.load_stop(os.path.join(DIR, '..', 'stop_domeny.txt')),
                       O.load_post(os.path.join(DIR, '..', 'minus_slova.txt')))


# --- проверка главной ------------------------------------------------------------------

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE   # у мелких хозяйств просроченные сертификаты — сайт всё равно живой


def get(url, limit=100_000, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'ru,en;q=0.5'})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            raw = r.read(limit)
            cs = r.headers.get_content_charset() or ''
            final, st = r.geturl(), r.status
    except urllib.error.HTTPError as e:
        return e.code, url, ''
    except Exception as e:  # noqa: BLE001
        return None, url, type(e).__name__
    if not cs:
        m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000], re.I)
        cs = m.group(1).decode() if m else 'utf-8'
    try:
        return st, final, raw.decode(cs, 'replace')
    except LookupError:
        return st, final, raw.decode('utf-8', 'replace')


def razbor(doc):
    t = re.search(r'<title[^>]*>(.*?)</title>', doc, re.I | re.S)
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', doc, re.I | re.S)
    body = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', doc, flags=re.I | re.S)
    vis = H.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body)))
    clean = lambda x: H.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', x.group(1)))).strip() if x else ''
    return clean(t)[:200], clean(h1)[:200], vis


_KONT = re.compile(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.I | re.S)


def kontakty_link(doc, base):
    best = None
    for href, txt in _KONT.findall(doc):
        t = re.sub(r'<[^>]+>', ' ', txt).lower()
        h = href.lower()
        if re.search(r'реквизит|rekvizit|requisit', t + h):
            return urllib.parse.urljoin(base, href)
        if best is None and re.search(r'контакт|kontakt|contact', t + h):
            best = urllib.parse.urljoin(base, href)
    return best


def proverit(cand):
    d = cand['domain']
    st, final, doc = get('https://' + d + '/')
    if st is None or st >= 400:
        st2, final2, doc2 = get('http://' + d + '/')
        if st2 and st2 < 400:
            st, final, doc = st2, final2, doc2
    rec = {'domain': d, 'http_status': st, 'final_url': final, 'err': doc if st is None else ''}
    if not st or st >= 400:
        return rec
    title, h1, vis = razbor(doc)
    rec.update(title=title, h1=h1, is_parked=O.is_parked(st, doc, vis),
               final_domain=O.norm_domain(final),
               scores={s: O.profile_score(s, title, h1, vis) for s in O.SLOVAR})
    inn, unp = O.find_inn(vis), O.find_unp(vis)
    if not inn and not unp:
        k = kontakty_link(doc, final)
        if k and O.norm_domain(k) == O.norm_domain(final):
            s2, _, d2 = get(k)
            if s2 and s2 < 400:
                v2 = razbor(d2)[2]
                inn, unp = O.find_inn(v2), O.find_unp(v2)
                rec['kontakty_url'] = k
    rec['inn'], rec['unp'] = inn[:3], unp[:3]
    return rec


def proverka(budget=6000):
    cands, _, _ = kandidaty()
    done = set()
    if os.path.exists(SAYTY):
        done = {json.loads(l)['domain'] for l in open(SAYTY, encoding='utf-8')}
    todo = [c for d, c in sorted(cands.items()) if d not in done]
    t0, n = time.time(), 0
    with open(SAYTY, 'a', encoding='utf-8') as f, ThreadPoolExecutor(16) as ex:
        for rec in ex.map(proverit, todo):
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            n += 1
            if time.time() - t0 > budget:
                break
    print('===ИТОГ===')
    print(json.dumps({'kandidatov': len(cands), 'bylo': len(done), 'provereno': n,
                      'ostalos': len(todo) - n}, ensure_ascii=False))


# --- отчёт -------------------------------------------------------------------------

def otchet():
    cands, funnel, dropped = kandidaty()
    et = json.load(open(ETALON, encoding='utf-8'))
    kd, ki, kc = set(et['domains']), set(et['inns']), set(et.get('cand_domains') or [])
    sayty = {}
    for l in open(SAYTY, encoding='utf-8'):
        j = json.loads(l)
        sayty[j['domain']] = j
    rows, svod = [], {'funnel': {}, 'status': defaultdict(Counter), 'zaprosy': defaultdict(Counter)}
    for d, c in cands.items():
        s = sayty.get(d, {})
        alive = bool(s.get('http_status')) and s['http_status'] < 400
        segs = sorted(c['segments'])
        best = max((s.get('scores') or {}).get(x, -99) for x in segs) if alive else None
        tip = O.tip_sayta(s.get('title') or (c['titles'][0] if c['titles'] else ''), d) if alive else ''
        prof = alive and not s.get('is_parked') and best is not None and best >= O.POROG and not tip
        ids = (s.get('inn') or []) + (s.get('unp') or [])
        # редирект на другой домен: сверяем и исходный, и конечный
        fd = s.get('final_domain') or d
        st = O.status(d if d in kd else fd, ids, kd, ki) if prof else ''
        rows.append({'domain': O.domain_unicode(d), 'final_url': s.get('final_url', ''),
                     'http_status': s.get('http_status'), 'is_parked': int(bool(s.get('is_parked'))),
                     'engines': '|'.join(sorted(c['engines'])), 'segments': '|'.join(segs),
                     'subsegments': '|'.join(sorted(c['subsegments_full'])), 'regions': '|'.join(sorted(c['regions'])),
                     'queries_count': len(c['queries']), 'best_pos': c['best_pos'], 'profile_score': best,
                     'inn': '|'.join(s.get('inn') or []), 'unp': '|'.join(s.get('unp') or []),
                     'tip': tip, 'status': st, 'in_cand_site': int(d in kc or fd in kc), 'title': s.get('title') or (c['titles'][0] if c['titles'] else ''),
                     'post_hits': '|'.join(sorted(c['post_hits']))})
        if prof:
            for seg in segs:
                for eng in c['engines']:
                    svod['status'][f'{seg}|{eng}'][st] += 1
                svod['status'][f'{seg}|both'][st] += 1
                if st.startswith('new') and (d in kc or fd in kc):
                    svod['status'][f'{seg}|both'][st + '_but_cand_site'] += 1
                if st == 'new':
                    for q in c['queries']:
                        svod['zaprosy'][q]['new'] += 1
            for q in c['queries']:
                svod['zaprosy'][q]['prof'] += 1
        for q in c['queries']:
            svod['zaprosy'][q]['domains'] += 1
    for (seg, eng), f in funnel.items():
        ds = f['after_stop']
        live = {d for d in ds if (sayty.get(d) or {}).get('http_status') and sayty[d]['http_status'] < 400}
        prof = {r['domain'] for r in rows if r['status']}
        prof_k = {d for d in live if O.domain_unicode(d) in prof}
        svod['funnel'][f'{seg}|{eng}'] = {'urls': len(f['urls']), 'domains': len(f['domains']),
                                         'after_stop': len(ds), 'live': len(live), 'profile': len(prof_k),
                                         'with_id': sum(1 for d in prof_k if sayty[d].get('inn') or sayty[d].get('unp'))}
    cols = list(rows[0].keys()) if rows else []
    p = os.path.join(DROP, 'BAZA-PILOT-DOMENY.csv')
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r['status'] == '', r['segments'], -(r['profile_score'] or 0))))
    with open(SERP, 'rb') as a, gzip.open(os.path.join(DROP, 'BAZA-PILOT-SERP.jsonl.gz'), 'wb') as b:
        b.write(a.read())
    svod['dropped'] = Counter(v.split(':')[0] for v in dropped.values())
    json.dump(svod, open(os.path.join(DROP, 'BAZA-PILOT-SVODKA.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, default=lambda x: dict(x))
    print('===ИТОГ===')
    print(json.dumps({'kandidatov': len(rows), 'profilnyh': sum(1 for r in rows if r['status']),
                      'status': Counter(r['status'] for r in rows if r['status'])}, ensure_ascii=False))


if __name__ == '__main__':
    {'etalon': etalon, 'proverka': proverka, 'otchet': otchet}[sys.argv[1]]()
