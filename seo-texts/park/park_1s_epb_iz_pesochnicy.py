# -*- coding: utf-8 -*-
"""Проверка доказательств ЭПБ ИЗ ПЕСОЧНИЦЫ: сервер к monitor-pb не пускают, а мы пройдём.

Находка 3-й сессии, перепроверенная мной: `monitor-pb.ru` с сервера владельца отдаёт таймаут,
а из нашего контейнера отвечает за 1–2 секунды. Значит серверные нули по этому домену — это
«прибор не прочёл», а не «доказательство плохое», и весь замер надо гнать отсюда.

Тонкость, которой у соседа нет: БРАУЗЕР из песочницы тоже не идёт — Chromium даёт
ERR_CONNECTION_RESET и напрямую, и через прокси контейнера. Идёт только curl/urllib через
агент-прокси. Поэтому снимок-картинку отсюда не сделать, а проверить текст — можно, и для
доказанности этого хватает: нужно увидеть на странице ИНН эксплуатанта и наименование машины.

Что делает: берёт факты выдачи, у которых ЛУЧШАЯ ссылка — карточка ЭПБ, тянет страницы и
пишет в `park.db` (таблица `dokaz_tekst`), что реально на том конце. Результат durable: сразу
в базу, не в возвращаемый JSON.

Запуск: python3 park_1s_epb_iz_pesochnicy.py [сколько]
"""
import os, re, sqlite3, sys, time, urllib.error, urllib.request

D = os.path.dirname(os.path.abspath(__file__))
SKOLKO = int(sys.argv[1]) if len(sys.argv) > 1 else 300
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
SIN = {'турбокомпрессор': ['турбокомпрессор', 'центробежн', 'компрессор'],
       'компрессорная станция': ['компрессорн'], 'ПКС': ['компрессор'], 'МКС': ['компрессорн'],
       'ГПА': ['газоперекачив', 'нагнетател', 'гпа'], 'нагнетатель': ['нагнетател', 'компрессор'],
       'воздуходувка': ['воздуходувк', 'газодувк', 'компрессор'],
       'ресивер': ['ресивер', 'воздухосборник', 'буферн'],
       'осушитель': ['осушител', 'влагоотделител'],
       'ВРУ': ['воздухораздел', 'кислород', 'азот'],
       'генератор азота': ['азот'], 'генератор кислорода': ['кислород'],
       'компрессор': ['компрессор', 'компримир', 'сжатого воздуха']}
TEG = re.compile(r'<[^>]+>')

p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
c.execute("""create table if not exists dokaz_tekst(
    fakt_id integer primary key, inn text, url text, http integer, znakov integer,
    inn_na_stranice integer, tip_na_stranice integer, citata text, ts text)""")

rows = c.execute("""
    select f.id, f.inn, f.tip, s.url from fakt f join fakt_ssylka s on s.fakt_id=f.id
     where f.v_parke=1 and coalesce(f.v_obzvone,0)=0 and coalesce(f.posrednik,0)=0
       and s.url like '%monitor-pb.ru/conclusion/%'
       and f.id not in (select fakt_id from dokaz_tekst)
     group by f.id
     -- СНАЧАЛА ПО ОДНОМУ ФАКТУ НА ПРЕДПРИЯТИЕ. Первый прогон шёл по порядку id и дал
     -- 187 доказательств всего у 12 предприятий: у одного завода бывают десятки заключений.
     -- Владельцу нужно, чтобы доказано было КАК МОЖНО БОЛЬШЕ предприятий, а не как можно
     -- глубже одно, поэтому идём вширь: сперва первый факт каждого ИНН, потом второй и т. д.
     order by (select count(*) from fakt f2 join fakt_ssylka s2 on s2.fakt_id=f2.id
                where f2.inn=f.inn and f2.id<f.id and s2.url like '%monitor-pb.ru/conclusion/%'),
              f.inn
     limit ?""", (SKOLKO,)).fetchall()
print('фактов на проверку: %d' % len(rows))

itog = {'открылось': 0, 'ИНН виден': 0, 'машина названа': 0, 'доказывает': 0, 'ошибок': 0}
for fid, inn, tip, url in rows:
    kod, tekst = 0, ''
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=40) as r:
            kod = r.status
            tekst = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        kod = e.code
    except Exception:  # noqa: BLE001
        itog['ошибок'] += 1
    plain = re.sub(r'\s+', ' ', TEG.sub(' ', tekst))
    nizh = plain.lower()
    est_inn = inn in plain
    slova = SIN.get(tip) or [tip.split()[0].lower()[:9]]
    est_tip = any(s in nizh for s in slova)
    i = plain.find(inn)
    citata = plain[max(0, i - 120):i + 160] if i >= 0 else plain[:220]
    if kod:
        itog['открылось'] += 1
    itog['ИНН виден'] += 1 if est_inn else 0
    itog['машина названа'] += 1 if est_tip else 0
    itog['доказывает'] += 1 if (est_inn and est_tip) else 0
    c.execute("""insert or replace into dokaz_tekst values (?,?,?,?,?,?,?,?,?)""",
              (fid, inn, url, kod, len(plain), 1 if est_inn else 0, 1 if est_tip else 0,
               citata[:300], time.strftime('%Y-%m-%d %H:%M:%S')))
    p.commit()

print('открылось ........ %d' % itog['открылось'])
print('  ИНН виден ...... %d' % itog['ИНН виден'])
print('  машина названа . %d' % itog['машина названа'])
print('  ДОКАЗЫВАЕТ ..... %d' % itog['доказывает'])
print('  ошибок сети .... %d' % itog['ошибок'])
q = lambda s: c.execute(s).fetchone()[0]
print('всего проверено текстом за все прогоны: %d' % q('select count(*) from dokaz_tekst'))
print('  из них доказывают: %d' % q('select count(*) from dokaz_tekst where inn_na_stranice=1 and tip_na_stranice=1'))
p.close()
