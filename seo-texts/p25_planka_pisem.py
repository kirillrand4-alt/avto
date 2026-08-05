# -*- coding: utf-8 -*-
"""Планка: КАК выглядят письма, которые УЖЕ отправлены. Читаю их глазами, а не считаю.

Владелец задал приёмку словами «письма в очереди отправки… они должны быть не хуже тех,
что уже отправлены из панели». Значит планка существует и лежит в базе, а не у меня в
голове. Прежде чем класть в очередь своё, надо посмотреть на её.

ЗАЧЕМ ЭТО СТАДИИ A, А НЕ ТОЛЬКО ПРИЁМКЕ. Мера «подходящая новость» должна отвечать на
вопрос «хватит ли этого повода, чтобы письмо получилось персонифицированным». Ответ виден
только в готовом письме: если в отправленных повод в тексте НЕ упомянут — значит новость
конвейеру и не нужна была, и все мои уровни повода меряют не то. Если упомянут — видно,
чем именно: суммой, машиной, площадкой, датой. Это и есть требования к сигналу.

ЧТО ПЕЧАТАЮ. Схемы таблиц, счётчики и ПЯТЬ ПИСЕМ ЦЕЛИКОМ. Целиком — потому что выжимка
покажет то, что я и так ожидаю увидеть.

Только чтение. Ни провайдера, ни записи.
"""
import collections
import json
import os
import re
import sqlite3

BAZY = [r'C:\sender\sender.db', r'C:\sender\enrich.db',
        r'C:\seostat\data\centro_sales.db']
INTERES = ('ai_letter_log', 'recipients', 'letters', 'queue', 'outbox', 'sent',
           'confirm_reviews', 'campaign', 'messages')


def kolonki(cx, t):
    return [r[1] for r in cx.execute('pragma table_info("%s")' % t)]


nayden = []
for b in BAZY:
    if not os.path.exists(b):
        print('нет базы: %s' % b)
        continue
    cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
    tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    print('\n=== %s' % b)
    for t in sorted(tabl):
        try:
            n = cx.execute('select count(*) from "%s"' % t).fetchone()[0]
        except Exception:  # noqa: BLE001
            continue
        pometka = '  <-- смотрю' if any(x in t.lower() for x in INTERES) else ''
        print('  %-26s %7d%s' % (t, n, pometka))
        if pometka and n:
            print('      колонки: %s' % kolonki(cx, t))
            nayden.append((b, t, n))
    cx.close()

# --- где лежит ТЕЛО письма ------------------------------------------------------------
TELO = ('body', 'text', 'letter', 'html', 'message', 'content', 'subject', 'title')
print('\n\n########## ПИСЬМА ЦЕЛИКОМ')
pokazano = 0
svod = collections.Counter()
povod_v_tekste = collections.Counter()
for b, t, n in nayden:
    cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
    kol = kolonki(cx, t)
    telo = [k for k in kol if any(x in k.lower() for x in TELO)]
    if not telo:
        cx.close()
        continue
    print('\n\n===== %s.%s   строк %d   тело в колонках %s' % (os.path.basename(b), t, n, telo))
    # самые свежие: по rowid, чтобы не гадать имя колонки времени
    stroki = list(cx.execute('select rowid,%s from "%s" order by rowid desc limit 400'
                             % (','.join('"%s"' % k for k in kol), t)))
    for r in stroki:
        d = dict(zip(['rowid'] + kol, r))
        tekst = ' '.join(str(d.get(k) or '') for k in telo)
        if len(tekst.strip()) < 40:
            svod['%s: тело пустое/короткое' % t] += 1
            continue
        svod['%s: с телом' % t] += 1
        # упомянут ли повод: ищу признаки новости в самом письме
        if re.search(r'\d{1,3}(?:[\s ]\d{3})+|\bмлн\b|\bмлрд\b', tekst):
            povod_v_tekste['есть сумма'] += 1
        if re.search(r'компрессор|воздухоразделен|азот|кислород|сжат\w+ воздух|газодув',
                     tekst, re.I):
            povod_v_tekste['названа машина/среда'] += 1
        if re.search(r'прочит\w+|узнал\w*|новост\w+|сообщал\w*|объявил\w*|планиру\w+|'
                     r'строит\w+|модерниз\w+|реконструкц\w+', tekst, re.I):
            povod_v_tekste['есть отсылка к событию'] += 1
        if pokazano < 5:
            pokazano += 1
            print('\n\n-------- ПИСЬМО %d (rowid %s) --------' % (pokazano, d.get('rowid')))
            for k in kol:
                v = d.get(k)
                if v in (None, ''):
                    continue
                s = str(v)
                if k in telo and len(s) > 120:
                    print('  %s:\n%s' % (k, s[:2600]))
                else:
                    print('  %-16s %s' % (k, s[:200]))
    cx.close()

print('\n\n=== СЧЁТЧИКИ')
for k, v in svod.most_common():
    print('REC %-40s %d' % (k, v))
print('--- что письма используют из новости (по тем, у кого есть тело)')
for k, v in povod_v_tekste.most_common():
    print('REC %-40s %d' % (k, v))
print('ИТОГ ' + json.dumps({'таблиц с письмами': len(nayden),
                            'показано писем': pokazano,
                            'повод в тексте': dict(povod_v_tekste)}, ensure_ascii=False))
