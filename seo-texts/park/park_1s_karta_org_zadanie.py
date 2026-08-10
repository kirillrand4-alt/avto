# -*- coding: utf-8 -*-
"""Задание: достроить вторую ссылку — карточку организации ЕИС, где напечатан ИНН.

Зачем. Мерка, поправленная 3-й сессией, показала: машина доказана у 95 % фактов выдачи, а
машина ВМЕСТЕ с ИНН — только у 63 %. Разрыв не от плохих данных: извещение 44-ФЗ печатает
только НАЗВАНИЕ заказчика, ИНН лежит на отдельной странице — карточке организации. У 3 369
фактов с карточкой 44-ФЗ этой второй ссылки нет.

Достроить её можно: первые 11 цифр реестрового номера 44-ФЗ — это код организации, и по нему
открывается `epz/organization/view/info.html?organizationCode=<код>`. Проверено на потоке
3-й сессии: номер 0101100007322000016 -> код 01011000073, и именно такую ссылку она кладёт
полем `zakazchik_kartochka`.

НО ВСЛЕПУЮ ЗАПИСЫВАТЬ НЕЛЬЗЯ. Код принадлежит тому, кто РАЗМЕЩАЕТ закупку, а это сплошь и
рядом уполномоченный орган: 75 администраций и центров закупок я уже вычистил из выдачи
именно по этой причине. Поэтому здесь только СОБИРАЕТСЯ задание; ссылка будет записана
после того, как страница открыта и ИНН на ней совпал с ИНН факта.

Запуск: python3 park_1s_karta_org_zadanie.py [сколько]
"""
import json, os, re, sqlite3, sys

D = os.path.dirname(os.path.abspath(__file__))
SKOLKO = int(sys.argv[1]) if len(sys.argv) > 1 else 400
c = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True)
rows = c.execute("""
    select f.id, f.inn, s.url
      from fakt f join fakt_ssylka s on s.fakt_id=f.id
     where f.v_parke=1 and coalesce(f.v_obzvone,0)=0 and coalesce(f.posrednik,0)=0
       and s.url like '%notice/ea44%regNumber=%'
       and not exists(select 1 from fakt_ssylka s2 where s2.fakt_id=f.id
                       and s2.url like '%epz/organization/%')
     group by f.id""").fetchall()

# по одному факту на предприятие сначала: карточка организации у всех фактов одного ИНН
# будет одна и та же, и покрытие предприятий важнее глубины
vidno, zad = set(), []
for fid, inn, url in rows:
    m = re.search(r'regNumber=(\d{19})', url)
    if not m:
        continue
    kod = m.group(1)[:11]
    if inn in vidno:
        continue
    vidno.add(inn)
    zad.append({'fakt_id': fid, 'inn': inn, 'kod': kod,
                'url': 'https://zakupki.gov.ru/epz/organization/view/info.html'
                       '?organizationCode=' + kod})
zad = zad[:SKOLKO]
with open(os.path.join(D, '_kartaorg.json'), 'w', encoding='utf-8') as f:
    json.dump(zad, f, ensure_ascii=False)
print('фактов 44-ФЗ без ссылки на организацию: %d' % len(rows))
print('  предприятий среди них ................ %d' % len({r[1] for r in rows}))
print('  в задание (по одному на предприятие) . %d' % len(zad))
c.close()
