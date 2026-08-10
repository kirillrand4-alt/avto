# -*- coding: utf-8 -*-
"""Перепроверка карточек ЭПБ строгим признаком: ИНН должен стоять после слова «Эксплуатант».

Дефект нашёлся, когда я строил контроль подделки. На карточке ЭПБ **два** ИНН:

    Стороны  Экспертная организация ООО «ТЕХЭКСПЕРТ» (ИНН 5407066558)
             Эксплуатант АО «ПО ЭХЗ» ИНН 2453013555

Моя проверка искала ИНН факта где угодно в тексте — то есть засчитала бы карточку и тогда,
когда наш ИНН принадлежит ЭКСПЕРТНОЙ организации, а машина стоит у совсем другого завода.
Экспертные организации сами закупают компрессоры и попадают к нам в парк, так что случай не
выдуманный.

Разбор по сохранённым цитатам дал 1 565 карточек, где ИНН точно эксплуатанта, и 571, где
цитата обрезана и не даёт ответа. Значит нужно не гадать по цитате, а перечитать страницу и
записать отдельный признак.

Пишем `inn_ekspluatant` в `dokaz_tekst`: 1 — ИНН факта стоит после слова «Эксплуатант»;
0 — стоит на странице, но не там (доказательство машины ЭТОМУ предприятию не принадлежит).

Запуск: python3 park_1s_epb_ekspluatant.py [сколько]
"""
import importlib.util, os, re, sqlite3, sys, time, urllib.error, urllib.request

D = os.path.dirname(os.path.abspath(__file__))
SKOLKO = int(sys.argv[1]) if len(sys.argv) > 1 else 400
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
_spec = importlib.util.spec_from_file_location('park_sin', os.path.join(D, 'park_sin.py'))
park_sin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(park_sin)
TEG = re.compile(r'<[^>]+>')
# «Эксплуатант АО "ПО ЭХЗ" ИНН 2453013555» и «Эксплуатант ООО "РИТЭК" (ИНН 6317130144)»
EKSPL = re.compile(r'Эксплуатант\b[^И]{0,120}?ИНН\s*[:№]?\s*(\d{10,12})')

p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=120)
c = p.cursor()
if 'inn_ekspluatant' not in [r[1] for r in c.execute('pragma table_info(dokaz_tekst)')]:
    c.execute('alter table dokaz_tekst add column inn_ekspluatant integer')

rows = c.execute("""select d.fakt_id, d.inn, f.tip, d.url from dokaz_tekst d
                    join fakt f on f.id = d.fakt_id
                    where d.http=200 and d.inn_na_stranice=1 and d.inn_ekspluatant is null
                    limit ?""", (SKOLKO,)).fetchall()
print('карточек на перепроверку: %d' % len(rows))
itog = {'ИНН эксплуатанта': 0, 'ИНН НЕ эксплуатанта': 0, 'не открылась': 0}
for fid, inn, tip, url in rows:
    tekst = ''
    for popytka in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                tekst = r.read().decode('utf-8', 'replace')
            break
        except urllib.error.HTTPError:
            break
        except Exception:  # noqa: BLE001
            if popytka < 2:
                time.sleep(3 * (popytka + 1))
    time.sleep(0.4)
    if not tekst:
        itog['не открылась'] += 1
        continue
    plain = re.sub(r'\s+', ' ', TEG.sub(' ', tekst)).replace('&quot;', '"')
    nashi = EKSPL.findall(plain)
    est = 1 if inn in nashi else 0
    itog['ИНН эксплуатанта' if est else 'ИНН НЕ эксплуатанта'] += 1
    c.execute('update dokaz_tekst set inn_ekspluatant=? where fakt_id=?', (est, fid))
    p.commit()

q = lambda s: c.execute(s).fetchone()[0]
for k, v in itog.items():
    print('  %-24s %d' % (k, v))
print()
print('всего размечено: %d' % q('select count(*) from dokaz_tekst where inn_ekspluatant is not null'))
print('  ИНН эксплуатанта ....... %d' % q('select count(*) from dokaz_tekst where inn_ekspluatant=1'))
print('  ИНН НЕ эксплуатанта .... %d' % q('select count(*) from dokaz_tekst where inn_ekspluatant=0'))
print('  предприятий, где ВСЕ карточки чужие: %d'
      % q("""select count(*) from (select inn from dokaz_tekst where inn_ekspluatant is not null
              group by inn having sum(coalesce(inn_ekspluatant,0))=0)"""))
p.close()
