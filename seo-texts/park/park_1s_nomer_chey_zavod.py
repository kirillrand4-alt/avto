# -*- coding: utf-8 -*-
"""Доказательство номера обязано связывать человека с ЭТИМ предприятием, а не просто с именем.

Владелец открыл снимок и спросил: «вот это как доказывает, что она инженер с номером?»
На снимке — карточка `prodoctorov.ru`: Казанцева Галина Валерьевна, **неонатолог-педиатр из
Челябинска**, стаж 29 лет, запись на приём. А в базе она значилась «начальник цеха»
Екатеринбургского водоканала с этим номером. Полная тёзка.

Мой признак спрашивал два вопроса — есть ли номер и стоит ли рядом фамилия — и оба получил
«да». Не спрашивал он третьего: **относится ли страница к нашему предприятию**. Это тот же
дефект, который я сам нашёл для машин в записи 124 («машина есть, но чья — не сказано») и не
применил к контактам.

Здесь вводится третье условие, и признак становится однородным с машинным:

    1. номер записан на странице СВЯЗНО (цифры подряд, разделители — пробел, дефис, скобка);
    2. фамилия человека стоит рядом с номером (окно ±260 знаков);
    3. страница связана с ПРЕДПРИЯТИЕМ — на ней есть ИНН, либо характерное слово из
       названия организации, либо это её собственный сайт (домен совпадает с сайтом ЕГРЮЛ),
       либо это площадка закупок, где карточка заведена от имени заказчика.

Площадки закупок (zakupki.gov.ru, ЭТП ГПБ, Тендер.Про, Росэлторг, Фабрикант, РТС, ТЭК-Торг)
принимаются как связанные: там контактное лицо публикует САМ заказчик, и связь с ИНН лежит в
самой карточке. Агрегаторы и соцсети (prodoctorov, vk, avito, 2gis, zoon, hh) — не
принимаются: там имя есть, а принадлежности к нашему предприятию нет.

Запуск: python3 park_1s_nomer_chey_zavod.py [--pisat]
"""
import os, re, sqlite3, sys, time
from urllib.parse import urlparse

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
PLOSHCHADKI = ('zakupki.gov.ru', 'etpgpb.ru', 'tender.pro', 'roseltorg.ru', 'fabrikant.ru',
               'rts-tender.ru', 'tektorg.ru', 'sberbank-ast.ru', 'zakupki.mos.ru',
               'gosnadzor.ru', 'monitor-pb.ru', 'docs.cntd.ru')
AGREGATORY = ('prodoctorov', 'vk.com', 'ok.ru', 'facebook', 'instagram', 'avito', 'youla',
              'hh.ru', 'superjob', 'zoon.', 'yell.', '2gis', 'flamp', 'orgpage', 'rusprofile',
              'list-org', 'checko', 'careerist', 'vseinstrumenti', 'yandex.', 'google.')
STOP_SLOVA = {'ООО', 'АО', 'ПАО', 'ЗАО', 'ОАО', 'ФГУП', 'ГУП', 'МУП', 'НАО', 'АК', 'ИМ',
              'ОБЩЕСТВО', 'АКЦИОНЕРНОЕ', 'ПУБЛИЧНОЕ', 'ОГРАНИЧЕННОЙ', 'ОТВЕТСТВЕННОСТЬЮ',
              'ПРЕДПРИЯТИЕ', 'УНИТАРНОЕ', 'МУНИЦИПАЛЬНОЕ', 'ГОСУДАРСТВЕННОЕ', 'ФЕДЕРАЛЬНОЕ',
              'ЗАВОД', 'КОМБИНАТ', 'ГОРОДА', 'ФИЛИАЛ'}


def slova_nazvaniya(nazvanie):
    """Характерные слова названия: без организационных форм и коротких кусков."""
    return [w for w in re.findall(r'[А-ЯЁA-Z][А-ЯЁA-Z\-]{3,}', (nazvanie or '').upper())
            if w not in STOP_SLOVA]


def svyaz_s_predpriyatiem(url, inn, nazvanie, sayt, tekst):
    """-> (связано ли, чем именно). Текст может быть пустым — тогда судим по адресу."""
    domen = (urlparse(url or '').netloc or '').replace('www.', '').lower()
    if any(a in domen for a in AGREGATORY):
        return False, 'агрегатор/соцсеть: имя есть, принадлежность не доказана'
    if any(pl in domen for pl in PLOSHCHADKI):
        return True, 'площадка закупок: карточку заводит сам заказчик'
    sayt_d = (urlparse(sayt or '').netloc or sayt or '').replace('www.', '').lower()
    if sayt_d and domen and (domen.endswith(sayt_d) or sayt_d.endswith(domen)):
        return True, 'собственный сайт предприятия'
    if tekst:
        if inn and inn in tekst:
            return True, 'ИНН предприятия на странице'
        est = [w for w in slova_nazvaniya(nazvanie) if w in tekst.upper()]
        if est:
            return True, 'название предприятия на странице: ' + est[0]
    return False, 'страница не связана с предприятием'


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
if PISAT and 'svyaz' not in [r[1] for r in c.execute('pragma table_info(nomer_dokaz)')]:
    c.execute('alter table nomer_dokaz add column svyaz text')

rows = c.execute("""select nd.inn, nd.nomer, nd.chelovek, nd.ssylka, nd.citata,
                           coalesce(f.imya,''), coalesce(s.name,'')
                      from nomer_dokaz nd
                      left join finansy f on f.inn = nd.inn
                      left join spravochnik s on s.inn = nd.inn
                     where nd.dokazano=1""").fetchall()
itog = {'связано': 0, 'НЕ связано': 0}
poteri = []
for inn, nomer, chel, url, citata, imya, sayt in rows:
    nazv = imya or ''
    if not nazv:
        r = c.execute("select nazvanie from fakt where inn=? and coalesce(nazvanie,'')<>'' limit 1",
                      (inn,)).fetchone()
        nazv = r[0] if r else ''
    # `sayt` в справочнике нет — вместо него второе название из базы обзвона: если оно
    # встретится на странице, связь с предприятием тоже доказана
    ok, chem = svyaz_s_predpriyatiem(url, inn, (nazv + ' ' + (sayt or '')).strip(), '', citata or '')
    itog['связано' if ok else 'НЕ связано'] += 1
    if not ok:
        poteri.append((inn, chel, (urlparse(url or '').netloc or '').replace('www.', ''), chem))
    if PISAT:
        c.execute('update nomer_dokaz set svyaz=?, dokazano=? where inn=? and nomer=?',
                  (chem, 1 if ok else 0, inn, nomer))

print('проверено доказанных номеров: %d' % len(rows))
for k, v in itog.items():
    print('  %-14s %d' % (k, v))
print()
print('снимается доказанность (страница не связана с предприятием):')
for inn, chel, domen, chem in poteri[:20]:
    print('  %-11s %-28s %-22s %s' % (inn, (chel or '')[:28], domen[:22], chem[:40]))
if not PISAT:
    print()
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback()
    p.close()
    raise SystemExit
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'НОМЕРА: третье условие — связь с предприятием',
           len(rows), itog['связано'], itog['НЕ связано'],
           'снимок с агрегатора (prodoctorov, vk) доказывает имя, но не принадлежность'))
p.commit()
print()
print('осталось доказанных: %d'
      % c.execute('select count(*) from nomer_dokaz where dokazano=1').fetchone()[0])
p.close()
