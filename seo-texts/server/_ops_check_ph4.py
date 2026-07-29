# -*- coding: utf-8 -*-
"""Утверждение №2, финальная сверка.

Правим свою же ошибку: раньше «доб. 0100» попадала в цифры номера и поиск
разваливался. Теперь добавочный отрезаем.

1) 14 телефонов партии 2026-07-29 сверяем с кэшем: есть ли номер на странице
   и стоит ли рядом слово заявленной роли.
2) Домен source_url vs companies.site — построчно по всей партии (324).
3) Точные объёмы почт партии.
"""
import gzip
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx
КЭШ = r'C:\seostat\drop\pagecache'
СЛОВА = {
    'гл.инженер': r'лавн\w+\s+инженер',
    'директор': r'директор',
    'снабжение/закупки': r'снабжен|закупк|МТО|МТС',
    'продажи': r'продаж|сбыт|коммерч|отдел\s+прода',
    'приёмная': r'приемн|приёмн|секрет|канцеляр',
    'кадры': r'кадр|персонал|HR|ваканс',
    'бухгалтерия': r'бухгалт',
    'гл.энергетик': r'энергетик',
    'гл.механик': r'механик',
    'нач.производства': r'производств',
    'техдиректор': r'техническ\w+\s+директор|техдиректор',
    'гл.технолог': r'технолог',
}


def текст(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h or '')
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


def кэш(inn):
    p = os.path.join(КЭШ, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return None
    try:
        return json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return None


def цифры(s):
    s = re.split(r'доб|ext|вн\.', str(s or ''), 1, re.I)[0]
    d = re.sub(r'\D', '', s)
    if len(d) == 11 and d[0] in '78':
        d = d[1:]
    return d


def найти(t, tel):
    d = цифры(tel)
    if len(d) < 10:
        return -1
    m = re.search(r'\D{0,3}'.join(d), t)
    return m.start() if m else -1


def dom(u):
    u = str(u or '').strip().lower()
    u = re.sub(r'^https?://', '', u).split('/')[0].split(':')[0]
    return u[4:] if u.startswith('www.') else u


def core(d):
    p = [x for x in d.split('.') if x]
    return '.'.join(p[-2:]) if len(p) >= 2 else d


def сверка():
    rows = []
    for role in СЛОВА:
        rows += e.execute(
            "SELECT inn, phone, person, role FROM phone_contacts WHERE "
            "source='сайт компании' AND updated_at LIKE '2026-07-29%' AND "
            "role=? LIMIT 2", (role,)).fetchall()
    есть = нет = роль_ок = роль_нет = 0
    провал = []
    for inn, ph, per, rl in rows:
        d = кэш(inn)
        if not d:
            нет += 1
            провал.append((inn, ph, rl, 'нет кэша'))
            continue
        поз = None
        for p in (d.get('pages') or []):
            t = текст(p.get('html'))
            i = найти(t, ph)
            if i >= 0:
                поз = (p.get('url'), t, i)
                break
        if not поз:
            нет += 1
            провал.append((inn, ph, rl, 'номера нет на страницах кэша'))
            continue
        есть += 1
        url, t, i = поз
        окно = t[max(0, i - 260):i + 160]
        рег = СЛОВА.get(rl)
        совп = bool(re.search(рег, окно, re.I)) if рег else False
        if совп:
            роль_ок += 1
        else:
            роль_нет += 1
            провал.append((inn, ph, rl, 'роль НЕ подтверждается: ' +
                           окно[-230:]))
        print('  %s %s роль=%-18s фио=%-28s роль_рядом=%s'
              % (inn, ph, rl, str(per)[:28], совп))
    print('  --- провалы ---')
    for x in провал[:14]:
        print('   ', json.dumps(x, ensure_ascii=False)[:330])
    print('СВЕРКА всего=%d номер_в_кэше=%d нет=%d роль_подтв=%d роль_нет=%d'
          % (len(rows), есть, нет, роль_ок, роль_нет))


def домены():
    rows = e.execute(
        "SELECT inn, phone, source_url FROM phone_contacts WHERE "
        "source='сайт компании' AND updated_at LIKE '2026-07-29%'").fetchall()
    ок = чуж = пусто = 0
    прим = []
    for inn, ph, url in rows:
        site = (e.execute('SELECT site FROM companies WHERE inn=?',
                          (inn,)).fetchone() or [''])[0]
        if not url or not site:
            пусто += 1
            continue
        if core(dom(url)) == core(dom(site)):
            ок += 1
        else:
            чуж += 1
            прим.append({'инн': inn, 'тел': ph, 'url': core(dom(url)),
                         'сайт': core(dom(site))})
    print('ДОМЕНЫ строк=%d свой=%d ЧУЖОЙ=%d без_url/сайта=%d'
          % (len(rows), ок, чуж, пусто))
    for x in прим[:10]:
        print('   ', json.dumps(x, ensure_ascii=False)[:200])


def почты():
    for r in e.execute(
            "SELECT source, substr(updated_at,1,10) d, COUNT(*), "
            "COUNT(DISTINCT inn) FROM emails WHERE updated_at LIKE "
            "'2026-07-29%' GROUP BY source, d ORDER BY 3 DESC").fetchall()[:12]:
        print('  %-20s %s n=%-5s инн=%s' % r)


if __name__ == '__main__':
    print('=== СВЕРКА ТЕЛЕФОНОВ С КЭШЕМ ===')
    сверка()
    print('=== ДОМЕНЫ ПОСТРОЧНО ===')
    домены()
    print('=== ПОЧТЫ 29.07 ===')
    почты()
