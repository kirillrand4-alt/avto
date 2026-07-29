# -*- coding: utf-8 -*-
"""Три добивки по утверждению №2.

A) Два файла кэша, записанных под ЧУЖОЙ ИНН: что именно туда уехало.
Б) Почты: таблица emails, сколько добавила переразметка.
В) Пять-семь телефонов из партии 2026-07-29 — есть ли номер в кэше этой
   компании и стоит ли рядом заявленная роль.
"""
import gzip
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx
КЭШ = r'C:\seostat\drop\pagecache'
ПАРЫ = [('2462004363', '7731367261'), ('5003003915', '7703370008')]


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
    d = re.sub(r'\D', '', str(s or ''))
    if len(d) == 11 and d[0] in '78':
        d = d[1:]
    return d


def найти(t, tel):
    """Ищем номер в тексте, разрешая любые разделители между цифрами."""
    d = цифры(tel)
    if len(d) < 10:
        return -1
    rx = r'\D{0,3}'.join(d[i] for i in range(len(d)))
    m = re.search(rx, t)
    return m.start() if m else -1


def часть_а():
    for файл, чужой in ПАРЫ:
        cf = кэш(файл)
        ct = кэш(чужой)
        a = (e.execute('SELECT name, site FROM companies WHERE inn=?',
                       (файл,)).fetchone() or ['', ''])
        b = (e.execute('SELECT name, site FROM companies WHERE inn=?',
                       (чужой,)).fetchone() or ['', ''])
        n = e.execute("SELECT COUNT(*) FROM phone_contacts WHERE inn=? AND "
                      "source='сайт компании' AND updated_at LIKE "
                      "'2026-07-29%'", (чужой,)).fetchone()[0]
        print(' ФАЙЛ %s (%s / %s)' % (файл, a[0][:38], a[1]))
        print('   ЗАПИСАНО ПОД %s (%s / %s) свежих_телефонов=%d'
              % (чужой, b[0][:38], b[1], n))
        print('   есть_свой_кэш_у_чужого_инн=%s' % bool(ct))
        if cf:
            u = [p.get('url') for p in (cf.get('pages') or [])][:3]
            print('   url-ы файла:', json.dumps(u, ensure_ascii=False)[:200])
        tel = e.execute("SELECT phone, person, role FROM phone_contacts WHERE "
                        "inn=? AND source='сайт компании' LIMIT 5",
                        (чужой,)).fetchall()
        print('   телефоны у чужого инн:', json.dumps(
            tel, ensure_ascii=False)[:300])
        # где реально живут эти номера: в своём кэше или в кэше файла
        for ph, per, role in tel[:3]:
            гдеф = гдеч = False
            if cf:
                гдеф = any(найти(текст(p.get('html')), ph) >= 0
                           for p in (cf.get('pages') or []))
            if ct:
                гдеч = any(найти(текст(p.get('html')), ph) >= 0
                           for p in (ct.get('pages') or []))
            print('     %s -> в_кэше_файла_%s=%s в_своём_кэше=%s'
                  % (ph, файл, гдеф, гдеч))


def часть_б():
    print(' cols emails:', ','.join(
        r[1] for r in e.execute('PRAGMA table_info(emails)').fetchall()))
    for r in e.execute('SELECT source, COUNT(*), COUNT(DISTINCT inn) FROM '
                       'emails GROUP BY source ORDER BY 2 DESC').fetchall()[:14]:
        print('  %-22s n=%-5s инн=%s' % r)
    try:
        for r in e.execute(
                "SELECT substr(updated_at,1,10) d, COUNT(*) FROM emails "
                "WHERE source LIKE '%сайт%' GROUP BY d ORDER BY d"
        ).fetchall()[-8:]:
            print('  почты «сайт» %s n=%s' % r)
    except Exception as ex:  # noqa: BLE001
        print('  нет updated_at:', ex)


def часть_в():
    роли = ['гл.инженер', 'директор', 'снабжение/закупки', 'продажи',
            'приёмная', 'кадры', 'гл.энергетик']
    ок = плохо = 0
    for role in роли:
        r = e.execute(
            "SELECT inn, phone, person, role, source_url FROM phone_contacts "
            "WHERE source='сайт компании' AND updated_at LIKE '2026-07-29%' "
            "AND role=? LIMIT 1", (role,)).fetchone()
        if not r:
            print('  роль %s — записей нет' % role)
            continue
        inn, ph, per, rl, url = r
        d = кэш(inn)
        nm = (e.execute('SELECT name FROM companies WHERE inn=?',
                        (inn,)).fetchone() or [''])[0]
        if not d:
            print('  %s %s — КЭША НЕТ' % (inn, ph))
            continue
        нашли = None
        for p in (d.get('pages') or []):
            t = текст(p.get('html'))
            i = найти(t, ph)
            if i >= 0:
                нашли = (p.get('url'), t[max(0, i - 170):i + 110])
                break
        if нашли:
            ок += 1
            print('  OK инн=%s тел=%s роль=%r фио=%r | %s' %
                  (inn, ph, rl, per, nm[:32]))
            print('     стр=%s' % str(нашли[0])[:90])
            print('     КОНТЕКСТ: %s' % нашли[1][:300])
        else:
            плохо += 1
            print('  НЕТ В КЭШЕ инн=%s тел=%s роль=%r url=%s'
                  % (inn, ph, rl, str(url)[:70]))
    print('ЧАСТЬ_В найдено_в_кэше=%d не_найдено=%d' % (ок, плохо))


if __name__ == '__main__':
    print('=== А. ЧУЖОЙ ИНН ===')
    часть_а()
    print('=== Б. ПОЧТЫ ===')
    часть_б()
    print('=== В. ТЕЛЕФОНЫ В КЭШЕ ===')
    часть_в()
