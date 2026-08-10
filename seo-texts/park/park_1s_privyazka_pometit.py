# -*- coding: utf-8 -*-
"""Помечает факты, у которых доказательство висит на ЧУЖОМ ИНН.

Как нашлось: жребий вытащил карточку 223-ФЗ «Запасные части к компрессорам для нужд филиала
ПАО "ОГК-2" — Адлерская ТЭС», стоявшую на факте ПАО «ТГК-1». Дальше — не догадка, а замер: на
карточках 223-ФЗ ИНН заказчика печатается почти всегда, поэтому по снимкам видно несовпадение.
35 таких карточек из 2 569 разобраны поимённо на сервере, и вот что оказалось:

    ИНН факта нашёлся на странице ....  0
    на странице ВООБЩЕ нет ИНН ...... 18   (страница не отдала реквизиты — не улика)
    на странице ЧУЖОЙ ИНН ........... 17   <- вот это и есть ошибка привязки

Корень виден в самих парах: сливались ОДНОИМЁННЫЕ юрлица из разных городов —
«АО ВОДОКАНАЛ» (Чебоксары, 2130017760) с «АО ВОДОКАНАЛ» (Якутск, 1435219600), МУП
«Тепловодоканал» (6633019419) с МУП «Тепловодоканал» (8605013419), ООО «ТВК» (5250067913) с
ООО «ТВК» (4202026697). Плюс пары «управляющая компания — актив»: УК «Аэропорты Регионов» и
аэропорт Ростова, РКС-Менеджмент и «Новая городская инфраструктура Прикамья».

То есть привязка делалась по НАЗВАНИЮ заказчика, а название юрлица в России не уникально.

Не удаляю: ставлю `privyazka_chuzhaya=1`. Факт остаётся с его ссылками, но доказанным не
считается и в выдачу как доказательство не идёт. Правкой ИНН не занимаюсь — это была бы
вторая догадка поверх первой; правильный путь — пересобрать такие факты с ИНН, снятым с той же
страницы, и это отдельная работа.
"""
import json, os, sqlite3, time

D = os.path.dirname(os.path.abspath(__file__))
razbor = json.load(open(os.path.join(D, 'PARK-1S-PRIVYAZKA-RAZBOR.json'), encoding='utf-8'))
chuzhie = [r for r in razbor if r.get('inn_na_stranice') and not r.get('sovpal')]
p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=120)
c = p.cursor()
if 'privyazka_chuzhaya' not in [r[1] for r in c.execute('pragma table_info(fakt)')]:
    c.execute('alter table fakt add column privyazka_chuzhaya integer default 0')

tronuto = 0
pary = []
for r in chuzhie:
    for (fid, inn, imya) in c.execute(
            """select f.id, f.inn, coalesce(f.nazvanie,'') from fakt f
               join fakt_ssylka s on s.fakt_id=f.id where s.url=? and f.inn=?""",
            (r['url'], r['inn_fakta'])).fetchall():
        c.execute('update fakt set privyazka_chuzhaya=1 where id=?', (fid,))
        tronuto += c.rowcount
        pary.append((inn, imya[:40], ','.join(r['inn_na_stranice']),
                     (r.get('zakazchik') or '')[:40]))
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ПРИВЯЗКА: доказательство на чужом ИНН',
           len(razbor), tronuto, len(razbor) - len(chuzhie),
           'на странице закупки напечатан ИНН другого юрлица; сливались одноимённые названия'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
print('разобрано карточек ................ %d' % len(razbor))
print('  с чужим ИНН на странице ......... %d' % len(chuzhie))
print('  помечено фактов ................. %d' % tronuto)
print('  предприятий затронуто ........... %d' % len({x[0] for x in pary}))
print('выдача после пометки: %d предприятий'
      % q('''select count(distinct inn) from fakt where v_parke=1 and coalesce(v_obzvone,0)=0
             and coalesce(posrednik,0)=0'''))
for x in pary[:8]:
    print('    %s %-40s -> на странице %s (%s)' % x)
p.close()
