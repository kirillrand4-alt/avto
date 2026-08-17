# -*- coding: utf-8 -*-
r"""Сколько компаний имеют максимально полную карточку.

Владелец 17.08: «посмотри сколько компаний имеют максимально возможно полную
карточку компании».

«Полная» — это не «много колонок заполнено», а закрытые блоки, каждый из которых
нужен для работы. Восемь блоков, и каждый проверяется по существу:

  реквизиты   имя, ОКВЭД, регион — по ним компания вообще опознаётся;
  огрн        отдельно: он нужен для проверок и выписок;
  сайт        адрес есть И привязка доказана уликой со страниц (ИНН, ОГРН, имя,
              домен). Недоказанный сайт — это не заполненный блок, а риск;
  паспорт     карточка текущего формата с продукцией: что предприятие делает;
  техника     оборудование, мощности, энергохозяйство, газы — то, из чего
              строится разговор по делу;
  почта       адрес для письма, не скрытый и не ловушка;
  человек     живой контакт: ФИО с должностью, а не общий ящик;
  телефон     для отдела продаж, когда письмо сработало;
  признак     наш или нет, с дословной уликой с сайта;
  новость     свежая, для «почему пишу сейчас»;
  выручка     для приоритета.

Считаем распределение: сколько блоков закрыто у скольких компаний, какие блоки
чаще всего пустые, и сколько компаний закрыли ВСЁ.

    python polnota.py            распределение и узкие места
    python polnota.py --polnye   показать самые полные карточки
"""
import json
import os
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import sverka_privyazki as SP     # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ТЕХНИКА = ('оборудование_линии', 'мощности', 'энергохозяйство', 'газы',
           'контроль_качества', 'расширение')
БЛОКИ = ('реквизиты', 'огрн', 'сайт доказан', 'паспорт', 'техника', 'почта',
         'человек', 'телефон', 'признак наш', 'свежая новость', 'выручка')


def строки():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    из = list(c.execute(
        "select k.inn, coalesce(k.name,'') name, coalesce(k.okved,'') okved, "
        "coalesce(k.region,'') region, coalesce(k.ogrn,'') ogrn, "
        "coalesce(nullif(k.site,''),nullif(k.cand_site,''),'') site, "
        "coalesce(k.best_email,'') pochta, coalesce(k.phones,'') tel, "
        "coalesce(k.nash_priznak,'') priznak, coalesce(k.revenue_rub,'') vyruchka, "
        "coalesce(f.facts_json,'') facts, coalesce(f.format,0) format, "
        "(select count(*) from people p where p.inn=k.inn "
        " and coalesce(p.person,'')<>'' and coalesce(p.post,'')<>'') lyudey "
        "from companies k left join site_facts f on f.inn=k.inn"))
    c.close()
    return из


def блоки(r):
    из = set()
    if r['name'] and r['okved'] and r['region']:
        из.add('реквизиты')
    if r['ogrn']:
        из.add('огрн')
    if r['site']:
        улики, _ = SP.улики(str(r['inn']), r['name'], r['site'], r['ogrn'])
        if улики:
            из.add('сайт доказан')
    d = {}
    if r['facts'] and r['format'] >= 2:
        try:
            d = json.loads(r['facts'])
        except Exception:  # noqa: BLE001
            d = {}
    if d.get('продукция'):
        из.add('паспорт')
    if any(d.get(п) for п in ТЕХНИКА):
        из.add('техника')
    if d.get('свежая_новость') or d.get('новости'):
        из.add('свежая новость')
    if r['pochta']:
        из.add('почта')
    if r['tel'] and r['tel'] not in ('[]', 'null'):
        из.add('телефон')
    if r['lyudey']:
        из.add('человек')
    if r['priznak'] and r['priznak'] not in ('нет', 'неизвестно'):
        из.add('признак наш')
    try:
        if float(r['vyruchka'] or 0) > 0:
            из.add('выручка')
    except Exception:  # noqa: BLE001
        pass
    return из


def свод():
    все = строки()
    распределение = {}
    пусто = {б: 0 for б in БЛОКИ}
    полные, почти = [], []
    for r in все:
        б = блоки(r)
        распределение[len(б)] = распределение.get(len(б), 0) + 1
        for имя in БЛОКИ:
            if имя not in б:
                пусто[имя] += 1
        if len(б) == len(БЛОКИ):
            полные.append(str(r['inn']))
        elif len(б) >= len(БЛОКИ) - 1:
            почти.append((str(r['inn']), sorted(set(БЛОКИ) - б)))
    return {'компаний': len(все), 'блоков_всего': len(БЛОКИ),
            'закрыто_блоков_у_скольких': dict(sorted(распределение.items(), reverse=True)),
            'закрыли_всё': len(полные),
            'закрыли_все_кроме_одного': len(почти),
            'чаще_всего_пусто': dict(sorted(пусто.items(), key=lambda x: -x[1])),
            'примеры_почти_полных': почти[:8]}


def полные(сколько=10):
    все = строки()
    из = []
    for r in все:
        б = блоки(r)
        if len(б) >= len(БЛОКИ) - 1:
            из.append({'инн': str(r['inn']), 'имя': r['name'][:40], 'сайт': r['site'],
                       'блоков': len(б), 'нет': sorted(set(БЛОКИ) - б),
                       'признак': r['priznak']})
        if len(из) >= сколько:
            break
    return из


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if '--polnye' in sys.argv:
        print(json.dumps(полные(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(свод(), ensure_ascii=False, indent=1))
