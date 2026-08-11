# -*- coding: utf-8 -*-
"""Добирает ПОЛНЫЙ список кодов ОКВЭД из всех источников, что уже лежат у меня.

Владелец открыл карточку МЭС: на checko у неё «Виды деятельности 27», а в моей карточке —
«1 кодов». И спросил по делу: «почему не все ОКВЭД? сессия соседняя запускала же проверку по
чеко полную».

Замер до починки, по 5 629 предприятиям выдачи:

    с основным кодом ................ 2 139
    со СПИСКОМ кодов (больше одного) ...  642
    только один код ................. 1 497

Полная проверка соседней сессии была, но по ДРУГОМУ списку предприятий: её сбор — 876 карточек
«Виды деятельности» и 2 961 карточка компании, и на мою нынешнюю выдачу из них приходятся 548
и 222. Так вышло потому, что я недавно убрал из парка всех, кто уже в обзвоне (запись 141.3),
и выдача сменилась — та же причина, по которой мимо прошли 2 445 её контактных строк.

Здесь собирается всё, что есть у меня на руках, из четырёх источников сразу; недостающее
придётся просить прогоном — checko из песочницы отвечает 429.

Ничего не затирается: список кодов ставится там, где его нет или где он короче найденного.

Запуск: python3 park_1s_okved_spisok_dobrat.py [--pisat]
"""
import csv
import json
import os
import re
import sqlite3
import sys
import time

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
KOD = re.compile(r'\b\d{2}(?:\.\d{1,2}){0,3}\b')
csv.field_size_limit(10 ** 7)


def kody_iz(znachenie):
    """Список кодов из чего угодно: массива, строки через « | », строки с именами."""
    if isinstance(znachenie, (list, tuple)):
        tekst = ' '.join(str(x) for x in znachenie)
    else:
        tekst = str(znachenie or '')
    vidno, itog = set(), []
    for k in KOD.findall(tekst):
        if k not in vidno:
            vidno.add(k)
            itog.append(k)
    return itog


def iz_jsonl(imya, polya):
    out = {}
    put = os.path.join(D, imya)
    if not os.path.exists(put):
        return out
    for ln in open(put, encoding='utf-8', errors='replace'):
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        inn = str(r.get('inn') or '').strip()
        kody = []
        for pole in polya:
            kody = kody_iz(r.get(pole))
            if len(kody) > 1:
                break
        if inn and len(kody) > len(out.get(inn, [])):
            out[inn] = kody
    return out


def iz_csv(imya, pole):
    out = {}
    put = os.path.join(D, imya)
    if not os.path.exists(put):
        return out
    for r in csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'):
        inn = (r.get('inn') or '').strip()
        kody = kody_iz(r.get(pole))
        if inn and len(kody) > len(out.get(inn, [])):
            out[inn] = kody
    return out


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c, c2 = p.cursor(), p.cursor()
vydacha = {r[0] for r in c.execute("""select distinct inn from fakt where v_parke=1
             and coalesce(v_obzvone,0)=0 and coalesce(posrednik,0)=0""")}

istochniki = {
    'PARK-OKVED-2S.jsonl': iz_jsonl('PARK-OKVED-2S.jsonl', ('okved_kody', 'okved_s_imenami')),
    'PARK-CHECKO-2S.jsonl': iz_jsonl('PARK-CHECKO-2S.jsonl', ('okved_kody', 'okved_all')),
    'PARK-VYDACHA-PREDPRIYATIYA-2S.csv': iz_csv('PARK-VYDACHA-PREDPRIYATIYA-2S.csv', 'okved_kody'),
}
# справочник базы обзвона: там тоже лежит список кодов
spr = {}
try:
    for inn, vse in c.execute("select inn, okved_all from spravochnik where coalesce(okved_all,'')<>''"):
        k = kody_iz(vse)
        if len(k) > len(spr.get(inn, [])):
            spr[inn] = k
except sqlite3.OperationalError:
    pass
istochniki['справочник базы обзвона'] = spr

luchshee = {}
for imya, d in istochniki.items():
    v_vydache = sum(1 for i in d if i in vydacha and len(d[i]) > 1)
    print('  %-38s ИНН %-6d из них в выдаче со списком %d' % (imya, len(d), v_vydache))
    for inn, kody in d.items():
        if len(kody) > len(luchshee.get(inn, [])):
            luchshee[inn] = kody

itog = {'дописан список кодов': 0, 'список стал длиннее': 0, 'нечего добавить': 0}
for inn, kody in luchshee.items():
    if inn not in vydacha or len(kody) < 2:
        continue
    r = c2.execute("select coalesce(okved_vse,''), coalesce(okved,'') from finansy where inn=?",
                   (inn,)).fetchone()
    bylo = kody_iz(r[0]) if r else []
    if len(kody) <= len(bylo):
        itog['нечего добавить'] += 1
        continue
    itog['список стал длиннее' if bylo else 'дописан список кодов'] += 1
    if PISAT:
        if not r:
            c2.execute('insert into finansy(inn, ts) values (?,?)',
                       (inn, time.strftime('%Y-%m-%d %H:%M:%S')))
        c2.execute('update finansy set okved_vse=? where inn=?', (' | '.join(kody), inn))

print()
for k, v in itog.items():
    print('  %-24s %d' % (k, v))
if not PISAT:
    print()
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback()
    p.close()
    raise SystemExit
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ОКВЭД: добор полного списка кодов',
           len(luchshee), itog['дописан список кодов'] + itog['список стал длиннее'],
           itog['нечего добавить'], 'из четырёх источников, что уже лежали у меня'))
p.commit()
skolko = c.execute("""select count(*) from finansy where inn in (%s)
                        and coalesce(okved_vse,'') like '%%|%%'"""
                   % ','.join('?' * len(vydacha)), list(vydacha)).fetchone()[0]
print()
print('в выдаче со списком кодов: %d из %d' % (skolko, len(vydacha)))
p.close()
