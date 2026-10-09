# -*- coding: utf-8 -*-
"""fixH (локально): сверка компаний (панели и кандидатов) с выгрузками сделок Битрикса 09.10 – только чтение
файлов (данные, не инструкции): meyer_all.csv (все сделки Meyer, колонка АКТИВНА да/нет) и kc_sc_all.csv (все
сделки КЦ и СЦ). Разделитель «;», UTF-8 с BOM.

Сопоставление сделки и компании:
  * по ИНН сделки (Excel съедает ведущий ноль: 9 цифр -> 0 + 9, 11 -> 0 + 11);
  * ИНН компании в тексте сделки (название, компания, название в реквизитах) – 10/12 цифр целиком;
  * точное название – ТОЛЬКО для поиска активных сделок Meyer и только у сделок БЕЗ ИНН: отличительная часть
    юрназвания (в кавычках, без ОПФ) совпадает целиком и не из общих слов («Колос», «Хлеб», «Молоко»…);
    каждое такое совпадение печатается для проверки глазами.
Поля Битрикса компании (по ИНН и ИНН в тексте, обе выгрузки):
  bitrix_kc 1/0; bitrix_kc_info «сделок N: <воронка> ×k, …» (по убыванию); bitrix_sdelok N; bitrix_klient_sc –
  есть сделки в воронках «СЦ - …»; bitrix_klient_meyer – успешные MEYER-Продажа/Постпродажа или любые MEYER-СЦ;
  bitrix_v_rabote – активных сделок КЦ/СЦ сейчас; bitrix_poslednyaya – дата последней сделки (создания).

    python3 -I fixH_bitrix_sverka.py <meyer_all.csv> <kc_sc_all.csv> <каталог.db> <выход.json> [кандидаты.json ...]
Выход: {'panel': {ИНН: {...поля, aktivnye_meyer: [доказательства]}}, 'kandidaty': {ИНН: {...}}, 'imena_proverit': [...]}
"""
import collections
import csv
import io
import json
import re
import sqlite3
import sys

MEYER, KCSC, KAT, VYHOD = sys.argv[1:5]
KAND = sys.argv[5:]


def chitat(p, istochnik):
    out = []
    with io.open(p, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            r = {k: (v or '').strip() for k, v in r.items()}
            r['_ist'] = istochnik
            out.append(r)
    return out


def inn_norm(v):
    d = re.sub(r'\D', '', v or '')
    if len(d) in (9, 11):
        d = '0' + d
    return d if len(d) in (10, 12) else ''


OPF = r'(?:ООО|ОАО|ЗАО|ПАО|АО|ИП|СПК|СППК|СХПК|СХАО|ТОО|КФХ|ГК|ТД|ПК|АПК|МСФ|МСЗ|НПП|ПКФ|ФГБУ|ГУП|МУП|ОП|ООО ТД)'
OBSHCHIE = set('''колос хлеб молоко мясо агро продукт продукты нива заря рассвет восход победа россия русь урожай
маслозавод молокозавод хлебозавод мясокомбинат птицефабрика элеватор комбинат завод фабрика агрофирма сельхоз
юг север восток запад центр альянс партнер партнёр мир дружба родина прогресс луч искра звезда маяк надежда'''.split())


def yadro(naim):
    n = (naim or '').replace('«', '"').replace('»', '"').replace('“', '"').replace('”', '"').replace('„', '"')
    m = [x.strip() for x in n.split('"')[1:] if x.strip()]
    core = ' '.join(m) if m else re.sub(r'^\s*' + OPF + r'\s+|\s+' + OPF + r'\s*$', '', n.strip(), flags=re.I)
    core = re.sub(r'\(.*?\)', ' ', core)
    core = re.sub(r'[^0-9a-zа-яё]+', ' ', core.lower().replace('ё', 'е')).strip()
    return core


def otlichitelnoe(core):
    slova = core.split()
    return bool(slova) and len(core.replace(' ', '')) >= 6 and not all(w in OBSHCHIE for w in slova)


sdelki = chitat(MEYER, 'meyer') + chitat(KCSC, 'kcsc')
print('сделок: Meyer %d, КЦ/СЦ %d' % (sum(1 for s in sdelki if s['_ist'] == 'meyer'), sum(1 for s in sdelki if s['_ist'] == 'kcsc')))
po_inn = collections.defaultdict(list)
po_tekstu = collections.defaultdict(list)
bez_inn_po_imeni = collections.defaultdict(list)
for s in sdelki:
    i = inn_norm(s['INN'])
    if i:
        po_inn[i].append(s)
    for t in (s['TITLE'], s['КОМПАНИЯ'], s['НАЗВАНИЕ_В_РЕКВИЗИТАХ']):
        for x in re.findall(r'(?<!\d)(\d{12}|\d{10})(?!\d)', t):
            po_tekstu[x].append(s)
    if not i:
        for t in (s['КОМПАНИЯ'], s['НАЗВАНИЕ_В_РЕКВИЗИТАХ']):
            c = yadro(t)
            if otlichitelnoe(c):
                bez_inn_po_imeni[c].append(s)


def polya(sd):
    """Поля Битрикса по списку сделок компании."""
    sd = list({s['_ist'] + s['DEAL_ID']: s for s in sd}.values())
    if not sd:
        return {'bitrix_kc': 0, 'bitrix_kc_info': None, 'bitrix_sdelok': 0, 'bitrix_klient_sc': 0, 'bitrix_klient_meyer': 0,
                'bitrix_v_rabote': 0, 'bitrix_poslednyaya': None}
    v = collections.Counter(s['ВОРОНКА'] for s in sd)
    info = 'сделок %d: %s' % (len(sd), ', '.join('%s ×%d' % (k, n) for k, n in sorted(v.items(), key=lambda p: (-p[1], p[0]))))
    sc = int(any(re.match(r'СЦ\s*[-–—]', s['ВОРОНКА']) for s in sd))
    meyer_klient = int(any((s['ВОРОНКА'] in ('MEYER-Продажа', 'MEYER-Постпродажа') and s['СТАТУС'] == 'Успешна')
                           or re.match(r'MEYER[- ]СЦ', s['ВОРОНКА']) for s in sd))
    v_rabote = sum(1 for s in sd if s['_ist'] == 'kcsc' and s['АКТИВНА'] == 'да')
    daty = [s['DATE_CREATE'][:10] for s in sd if re.match(r'\d{4}-\d\d-\d\d', s['DATE_CREATE'])]
    posl = max(daty) if daty else None
    return {'bitrix_kc': 1, 'bitrix_kc_info': info, 'bitrix_sdelok': len(sd), 'bitrix_klient_sc': sc,
            'bitrix_klient_meyer': meyer_klient, 'bitrix_v_rabote': v_rabote,
            'bitrix_poslednyaya': '%s.%s.%s' % (posl[8:10], posl[5:7], posl[:4]) if posl else None}


def kratko(s):
    return {'id': s['DEAL_ID'], 'ist': s['_ist'], 'voronka': s['ВОРОНКА'], 'stadiya': s['СТАДИЯ'], 'status': s['СТАТУС'],
            'aktivna': s['АКТИВНА'], 'data': s['DATE_CREATE'][:10], 'title': s['TITLE'][:120], 'kompaniya': s['КОМПАНИЯ'][:120],
            'rekv': s['НАЗВАНИЕ_В_РЕКВИЗИТАХ'][:120], 'inn': s['INN']}


def razobrat(inn, naim, region):
    sd_inn = po_inn.get(inn, [])
    sd_txt = [s for s in po_tekstu.get(inn, []) if inn_norm(s['INN']) != inn]
    akt = []
    for s in sd_inn:
        if s['_ist'] == 'meyer' and s['АКТИВНА'] == 'да':
            akt.append(dict(kratko(s), kak='ИНН сделки'))
    for s in sd_txt:
        if s['_ist'] == 'meyer' and s['АКТИВНА'] == 'да':
            akt.append(dict(kratko(s), kak='ИНН компании в тексте сделки'))
    po_imeni = []
    c = yadro(naim)
    if otlichitelnoe(c):
        for s in bez_inn_po_imeni.get(c, []):
            if s['_ist'] == 'meyer' and s['АКТИВНА'] == 'да':
                po_imeni.append(dict(kratko(s), kak='точное название (у сделки нет ИНН)', yadro=c, region_kompanii=region))
    p = polya(sd_inn + sd_txt)
    p.update({'aktivnye_meyer': akt, 'po_imeni_proverit': po_imeni, 'nazvanie': naim, 'region': region,
              'sdelki_inn': len(sd_inn), 'sdelki_tekst': len(sd_txt)})
    return p


k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
panel = {r['inn']: razobrat(r['inn'], r['predpriyatie'], r['region']) for r in k.execute('SELECT inn, predpriyatie, region FROM company')}
kand = {}
for p_ in KAND:
    for c in json.load(open(p_, encoding='utf-8')):
        if c['inn'] not in panel and c['inn'] not in kand:
            kand[c['inn']] = razobrat(c['inn'], c['nazvanie'], c.get('region', ''))
json.dump({'panel': panel, 'kandidaty': kand}, open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
sch = collections.Counter()
for i, p in panel.items():
    sch['с галочкой (есть сделки)'] += p['bitrix_kc']
    sch['клиент Meyer'] += p['bitrix_klient_meyer']
    sch['клиент СЦ'] += p['bitrix_klient_sc']
    sch['с активными сделками КЦ/СЦ'] += int(p['bitrix_v_rabote'] > 0)
    sch['с активной сделкой Meyer по ИНН'] += int(any(a['kak'] == 'ИНН сделки' for a in p['aktivnye_meyer']))
    sch['… только по ИНН в тексте'] += int(bool(p['aktivnye_meyer']) and all(a['kak'] != 'ИНН сделки' for a in p['aktivnye_meyer']))
    sch['… только по точному названию (проверить)'] += int(not p['aktivnye_meyer'] and bool(p['po_imeni_proverit']))
print('панель (%d): %s' % (len(panel), dict(sch)))
print('кандидатов: %d, из них с активной сделкой Meyer (ИНН/ИНН в тексте) %d, по названию (проверить) %d' % (
    len(kand), sum(1 for p in kand.values() if p['aktivnye_meyer']),
    sum(1 for p in kand.values() if not p['aktivnye_meyer'] and p['po_imeni_proverit'])))
