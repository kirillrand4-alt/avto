# -*- coding: utf-8 -*-
# 20.10, владелец: «по 70к — чтобы в одном файле было всё, что собрали». Свод 785 тыс. деклараций ФСА (fsa-meyer-decl.jsonl)
# по изготовителю: число, первая/последняя дата, сколько действуют сейчас, за последние 6/12 мес., товарные знаки,
# происхождение, тип заявителя, адреса производства, вся продукция (уникальная, укорочено), основы поиска.
# Выход: C:\seostat\drop\drop-storage\fsa-meyer-decl-svod.jsonl (по строке на ИНН изготовителя).
import collections, datetime, io, json, re
ВХ = r'C:\sender\server\fsa-meyer-decl.jsonl'
ВЫХ = r'C:\seostat\drop\drop-storage\fsa-meyer-decl-svod.jsonl'
сегодня = datetime.date.today()
d6, d12 = (сегодня - datetime.timedelta(days=183)).isoformat(), (сегодня - datetime.timedelta(days=365)).isoformat()
св = {}
for s in io.open(ВХ, encoding='utf-8', errors='replace'):
    try:
        x = json.loads(s)
    except ValueError:
        continue
    инн = re.sub(r'\D', '', x.get('manufacterInn') or '')
    if not инн:
        continue
    z = св.get(инн)
    if z is None:
        z = св[инн] = {'инн': инн, 'n': 0, 'ид': set(), 'первая': '9999', 'последняя': '', 'действ': 0, 'за6': 0, 'за12': 0,
                       'знаки': collections.Counter(), 'происх': collections.Counter(), 'заявитель': collections.Counter(),
                       'адреса': collections.Counter(), 'продукция': collections.Counter(), 'основы': collections.Counter(),
                       'чужой_заявитель': 0, 'посл_ид': ('', '')}
    if x['id'] in z['ид']:
        continue
    z['ид'].add(x['id'])
    z['n'] += 1
    д = x.get('declDate') or ''
    z['первая'] = min(z['первая'], д or '9999')
    if д >= z['последняя']:
        z['последняя'] = д
        z['посл_ид'] = (д, x['id'])
    z['действ'] += str(x.get('idStatus')) == '6' or (x.get('declEndDate') or '') >= сегодня.isoformat()
    z['за6'] += д >= d6
    z['за12'] += д >= d12
    if x.get('productIdentificationTrademark'):
        z['знаки'][x['productIdentificationTrademark'].strip()[:60]] += 1
    z['происх'][(x.get('productOrig') or '').strip()[:40]] += 1
    z['заявитель'][(x.get('applicantType') or '').strip()[:40]] += 1
    if re.sub(r'\D', '', x.get('applicantInn') or '') != инн:
        z['чужой_заявитель'] += 1
    if x.get('manufacterAddress'):
        z['адреса'][re.sub(r'\s+', ' ', x['manufacterAddress']).strip()[:200]] += 1
    п = re.sub(r'\s+', ' ', x.get('productFullName') or '').strip()
    if п:
        z['продукция'][п[:160]] += 1
    if x.get('слово'):
        z['основы'][x['слово']] += 1
with io.open(ВЫХ, 'w', encoding='utf-8') as f:
    for z in св.values():
        прод = [p for p, _ in z['продукция'].most_common(40)]
        текст, всего = [], 0
        for p in прод:
            if всего + len(p) > 1500:
                break
            текст.append(p)
            всего += len(p) + 3
        f.write(json.dumps({'инн': z['инн'], 'деклараций': z['n'], 'первая': z['первая'] if z['первая'] != '9999' else '',
                            'последняя': z['последняя'], 'последняя_id': z['посл_ид'][1], 'действуют': z['действ'],
                            'за_6_мес': z['за6'], 'за_12_мес': z['за12'], 'позиций': len(z['продукция']),
                            'продукция': ' | '.join(текст), 'знаки': [k for k, _ in z['знаки'].most_common(8)],
                            'происхождение': dict(z['происх'].most_common(4)), 'тип_заявителя': dict(z['заявитель'].most_common(4)),
                            'заявитель_другой': z['чужой_заявитель'], 'адреса': [k for k, _ in z['адреса'].most_common(3)],
                            'основы': [k for k, _ in z['основы'].most_common(10)]}, ensure_ascii=False) + '\n')
print('===ИТОГ===', len(св))
