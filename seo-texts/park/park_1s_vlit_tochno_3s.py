# -*- coding: utf-8 -*-
"""Вливает «точную» базу 3-й сессии — но только те строки, что прошли МОЮ проверку.

Владелец: «если там реально теперь только доказанные телефоны — влей и убери не доказанные».
Ответ по замеру: реально — почти. Из 4 535 строк на мои предприятия приходятся 2 072, и из
них моих шести условий не выдерживают 179:

    общая почта организации (info@, zakupki@)  199 по всему файлу
    номер собран из соседних чисел              79
    доказательство только на агрегаторе         52

Условия и сами проверки взяты ДОСЛОВНО из `park_1s_proverit_tochno_3s.py` — тот же код, а не
переписанный заново: иначе проверка и влив разойдутся, и число «прошли» перестанет отвечать
за то, что легло в базу.

Строки, которые не прошли, не выбрасываются молча: они пишутся в `kontakt_otklonyon` с
причиной, чтобы их можно было добрать снимком, как 3-я сессия и предлагает в описи.

Запуск: python3 park_1s_vlit_tochno_3s.py [--pisat]
"""
import csv
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from urllib.parse import urlparse

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
FAYL = os.path.join(D, 'PARK-BAZA-TOCHNO-3S.csv')
AGREGATORY = ('prodoctorov', 'vk.com', 'ok.ru', 'facebook', 'instagram', 'avito', 'youla',
              'hh.ru', 'superjob', 'zoon.', 'yell.', '2gis', 'flamp', 'orgpage', 'rusprofile',
              'list-org', 'checko', 'careerist', 'vseinstrumenti')
OBSHCHIE = ('info@', 'office@', 'mail@', 'zakupki@', 'tender@', 'secretar', 'priemn', 'post@',
            'sekretar', 'general@', 'company@', 'contact@', 'reception')
csv.field_size_limit(10 ** 7)


def cifry(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    return c if len(c) == 10 else ''


def svyazno(nomer10, tekst):
    """Номер записан как ТЕЛЕФОН, а не собран из соседних чисел."""
    return bool(re.search(r'[\s\-()+]{0,3}'.join(nomer10), tekst or ''))


def familii(chelovek):
    return [w for w in re.findall(r'[А-ЯЁ][а-яё]{2,}', chelovek or '')]



p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
c.execute("""create table if not exists kontakt_otklonyon(
    inn text, chelovek text, znachenie text, vid text, prichina text, ssylka text, ts text)""")
vydacha = {r[0] for r in c.execute("""select distinct inn from fakt where v_parke=1
             and coalesce(v_obzvone,0)=0 and coalesce(posrednik,0)=0""")}
est = {(r[0], r[1], r[2]) for r in c.execute('select inn, vid, znachenie from contact_source')}
bylo = c.execute('select count(*) from contact_source').fetchone()[0]

itog = Counter()
for r in csv.DictReader(open(FAYL, encoding='utf-8-sig'), delimiter=';'):
    inn = (r.get('inn') or '').strip()
    if inn not in vydacha:
        itog['вне выдачи'] += 1
        continue
    chel = (r.get('chelovek') or '').strip()
    dolzh = (r.get('dolzhnost') or '').strip()
    citata = r.get('citata') or ''
    vid = (r.get('vid_nomera') or '').strip()
    nomer = cifry(r.get('nomer'))
    pochta = (r.get('pochta') or '').strip().lower()
    ssylki = [u.strip() for u in (r.get('istochniki') or '').split('|') if u.strip().startswith('http')]
    beda = ''
    if not ssylki:
        beda = 'ссылки нет'
    elif vid.upper().startswith('ЛИЧНЫЙ') and not (nomer and svyazno(nomer[-10:], citata)):
        beda = 'личный мобильный: номера в цитате нет'
    elif vid.upper().startswith('ЛИЧНЫЙ') and not any(f in citata for f in familii(chel)):
        beda = 'личный мобильный: фамилии в цитате нет'
    elif all(any(a in (urlparse(u).netloc or '').replace('www.', '') for a in AGREGATORY)
             for u in ssylki):
        beda = 'доказательство только на агрегаторе'
    elif nomer and not chel:
        beda = 'номер без человека'
    elif pochta and not nomer and any(o in pochta for o in OBSHCHIE):
        beda = 'общая почта организации'
    elif nomer and citata and not svyazno(nomer[-10:], citata):
        beda = 'номер собран из соседних чисел'
    if beda:
        itog['НЕ ВЛИТО: ' + beda] += 1
        c.execute('insert into kontakt_otklonyon values (?,?,?,?,?,?,?)',
                  (inn, chel, nomer or pochta, 'telefon' if nomer else 'email', beda,
                   ssylki[0] if ssylki else '', time.strftime('%Y-%m-%d %H:%M:%S')))
        continue
    for vid_k, znach in (('telefon', nomer), ('email', pochta)):
        if not znach or (inn, vid_k, znach) in est:
            continue
        for u in ssylki[:3]:
            c.execute("""insert into contact_source(inn, vid, znachenie, person, dolzhnost,
                             istochnik, source_url, domen, pervoistochnik, data_nablyudeniya,
                             quote, kto)
                         values (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (inn, vid_k, znach, chel, dolzh,
                       'точная база 3-й сессии: ' + (vid or r.get('vid_pochty') or ''), u,
                       re.sub(r'^https?://(www\.)?([^/]+).*', r'\2', u), 0,
                       time.strftime('%Y-%m-%d'), citata[:300], '3-я сессия, проверено 1-й'))
            itog['влито наблюдений'] += 1
        est.add((inn, vid_k, znach))
        itog['влито контактов'] += 1

for k, v in sorted(itog.items(), key=lambda x: -x[1]):
    print('  %-42s %d' % (k, v))
if not PISAT:
    print()
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback()
    p.close()
    raise SystemExit
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ТОЧНАЯ БАЗА 3-й СЕССИИ, проверенная мной',
           sum(v for k, v in itog.items() if k.startswith('НЕ ВЛИТО')) + itog['влито контактов'],
           itog['влито контактов'],
           sum(v for k, v in itog.items() if k.startswith('НЕ ВЛИТО')),
           'проверки взяты из park_1s_proverit_tochno_3s.py дословно'))
p.commit()
print()
print('contact_source: было %d, стало %d'
      % (bylo, c.execute('select count(*) from contact_source').fetchone()[0]))
print('отклонено с причиной: %d'
      % c.execute('select count(*) from kontakt_otklonyon').fetchone()[0])
p.close()
