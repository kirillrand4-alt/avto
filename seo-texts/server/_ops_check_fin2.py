# -*- coding: utf-8 -*-
"""6318101450: телефон гл.технолога, которого не нашлось в кэше. Плюс
проверяем, не склеен ли ещё где номер «база от одного, добавочный от
другого» — как у Перхина (3525392360).
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


def текст(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h or '')
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', h.replace('&nbsp;', ' '))


def кэш(inn):
    p = os.path.join(КЭШ, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return None
    return json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))


def А():
    inn = '6318101450'
    d = кэш(inn)
    print('  кэш есть=%s страниц=%s' % (bool(d), len((d or {}).get('pages') or [])))
    rows = e.execute("SELECT phone, person, role FROM phone_contacts WHERE "
                     "inn=? AND source='сайт компании'", (inn,)).fetchall()
    print('  телефонов в БД=%d: %s' % (len(rows), json.dumps(
        rows, ensure_ascii=False)[:400]))
    if not d:
        return
    сырой = ''.join((p.get('html') or '') for p in d.get('pages') or [])
    for проба in ('228-23-47', '2282347', '228 23 47'):
        print('  «%s» в сыром html: %s' % (проба, проба in сырой))
    t = текст(сырой)
    for m in list(re.finditer(r'технолог', t, re.I))[:3]:
        print('  ТЕХНОЛОГ:: %s' % t[max(0, m.start() - 180):m.start() + 120])


def склейки():
    """Ищем номера с добавочным, где база НЕ совпала с базой у того же ФИО."""
    rows = e.execute(
        "SELECT inn, phone, person, role FROM phone_contacts WHERE "
        "source='сайт компании' AND updated_at LIKE '2026-07-29%' AND "
        "(phone LIKE '%доб%' OR phone LIKE '%ext%')").fetchall()
    print('  строк с добавочным=%d' % len(rows))
    плохих = 0
    for inn, ph, per, rl in rows:
        d = кэш(inn)
        if not d:
            continue
        t = текст(''.join((p.get('html') or '') for p in d.get('pages') or []))
        баз = re.split(r'доб|ext', ph, 1, re.I)[0]
        цб = re.sub(r'\D', '', баз)
        if len(цб) == 11 and цб[0] in '78':
            цб = цб[1:]
        доб = re.sub(r'\D', '', re.split(r'доб|ext', ph, 1, re.I)[-1])
        # ищем «база ... доб» вместе в тексте
        rx = r'\D{0,3}'.join(цб) + r'[^0-9]{0,24}(?:доб|ext)[^0-9]{0,4}' + доб
        вместе = bool(re.search(rx, t, re.I))
        if not вместе:
            плохих += 1
            print('   СКЛЕЙКА? инн=%s тел=%r фио=%r роль=%r'
                  % (inn, ph, per, rl))
    print('СКЛЕЙКИ строк_с_доб=%d база+добавочный_НЕ_рядом=%d'
          % (len(rows), плохих))


if __name__ == '__main__':
    print('=== А ===')
    А()
    print('=== СКЛЕЙКИ ===')
    склейки()
