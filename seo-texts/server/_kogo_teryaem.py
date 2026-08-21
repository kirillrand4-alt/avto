# -*- coding: utf-8 -*-
r"""Кого теряем на адресе: разбор по видам + выгрузка сайтов для ручного поиска.

Правило «берём только адрес, снятый с САЙТА компании» защищает от справочников
с общими и чужими ящиками. Но адрес info@zavod.ru, прочитанный в Checko, — тот
же самый ящик, что лежит на контактах zavod.ru, и выбрасывать его жалко.
Поэтому делим на три вида:
  СВОЙ ДОМЕН   домен адреса совпадает с доменом сайта — потеря чистая;
  ФРИМЕЙЛ      mail.ru/яндекс — адрес рабочий, но подтвердить некому;
  ЧУЖОЙ ДОМЕН  почта на постороннем домене — осторожность правила оправдана.
Отдельно — те, у кого адреса нет вовсе: у них есть сайт, и контакты на нём
владелец собирается искать руками.
"""
import csv
import io
import json
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import dogruz_935 as D  # noqa: E402

ВЫГРУЗКА = r'C:\sender\_tmp\bez-adresa-s-sayta.csv'
ФРИ = ('mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'inbox.ru',
       'list.ru', 'rambler.ru', 'internet.ru', 'icloud.com', 'mail.com')


def домен(u):
    u = re.sub(r'^https?://', '', str(u or '').strip().lower()).strip('/')
    u = u.split('/')[0].split('?')[0]
    return u[4:] if u.startswith('www.') else u


def ядро(d):
    ч = [x for x in d.split('.') if x]
    if len(ч) > 2 and ч[-2] in ('com', 'org', 'net', 'co'):
        return '.'.join(ч[-3:])
    return '.'.join(ч[-2:]) if len(ч) >= 2 else d


c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
продукция = {}
for r in c.execute("select inn, facts_json from site_facts where "
                   "coalesce(format,0)>=2 and facts_json like '%\"продукция\": [\"%'"):
    try:
        продукция[str(r['inn'])] = (json.loads(r['facts_json']).get('продукция') or [])
    except Exception:  # noqa: BLE001
        продукция[str(r['inn'])] = []
чистые = {str(r[0]) for r in c.execute(
    'select distinct e.inn from emails e where %s and %s' % (D.САЙТ, D.ЧИСТ))}
цель = set(продукция) - чистые

компании = {}
for r in c.execute("select inn, coalesce(nullif(short_name,''),name,'') nm, "
                   "coalesce(site,'') s, coalesce(cand_site,'') cs, "
                   "coalesce(region,'') reg, coalesce(division,'') div, "
                   "coalesce(okved,'') ok from companies"):
    if str(r['inn']) in цель:
        компании[str(r['inn'])] = dict(r)
почты = {}
for r in c.execute("select inn, lower(email) em, coalesce(source,'') src, "
                   "coalesce(pometka,'') pm from emails"):
    if str(r['inn']) in цель:
        почты.setdefault(str(r['inn']), []).append(dict(r))
c.close()

ст = {'всего': len(цель), 'свой_домен': 0, 'фримейл': 0, 'чужой_домен': 0,
      'адреса_нет': 0}
примеры = {'свой_домен': [], 'фримейл': [], 'чужой_домен': [], 'адреса_нет': []}
пометки, ряды = {}, []
for инн in sorted(цель):
    к = компании.get(инн) or {}
    сайт_txt = к.get('s') or к.get('cs') or ''
    сайт = ядро(домен(сайт_txt))
    спис = почты.get(инн) or []
    лучший = спис[0] if спис else {}
    вид = 'адреса_нет'
    if спис:
        вид = 'чужой_домен'
        for e in спис:
            d = ядро(домен(e['em'].split('@')[-1]))
            if сайт and d == сайт:
                вид, лучший = 'свой_домен', e
                break
            if d in ФРИ and вид == 'чужой_домен':
                вид, лучший = 'фримейл', e
    ст[вид] += 1
    for e in спис:
        к_ = (e['pm'] or '')[:40] or '(без пометки)'
        пометки[к_] = пометки.get(к_, 0) + 1
    строка = {
        'inn': инн, 'company': (к.get('nm') or '')[:70], 'site': сайт_txt[:60],
        'produkciya': '; '.join(продукция.get(инн) or [])[:120],
        'region': (к.get('reg') or '')[:34], 'napravlenie': к.get('div') or '',
        'okved': (к.get('ok') or '')[:40], 'vid': вид,
        'adres': (лучший.get('em') or '')[:50],
        'istochnik': (лучший.get('src') or '')[:24],
        'pometka': (лучший.get('pm') or '')[:60],
        'vsego_adresov': len(спис)}
    ряды.append(строка)
    if len(примеры[вид]) < 5:
        примеры[вид].append({k: v for k, v in строка.items()
                             if k in ('inn', 'company', 'site', 'produkciya',
                                      'adres', 'istochnik', 'pometka')})

ряды.sort(key=lambda r: (r['vid'] != 'свой_домен', r['vid'] != 'адреса_нет',
                         not r['site'], r['company']))
with io.open(ВЫГРУЗКА, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(ряды[0].keys()), delimiter=';')
    w.writeheader()
    w.writerows(ряды)

print(json.dumps({'примеры': примеры}, ensure_ascii=False, indent=1))
print(json.dumps({'счёт': ст, 'файл': ВЫГРУЗКА, 'строк': len(ряды),
                  'с_сайтом': sum(1 for r in ряды if r['site']),
                  'пометки': dict(sorted(пометки.items(),
                                         key=lambda x: -x[1])[:6])},
                 ensure_ascii=False, indent=1))
