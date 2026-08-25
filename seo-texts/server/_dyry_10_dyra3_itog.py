# -*- coding: utf-8 -*-
"""ДЫРА 3: свод по уже посчитанной выборке из dyra3.json."""
import json
import statistics

d = json.load(open(r'C:\sender\_tmp\dyra3.json', encoding='utf-8'))
n = d['vsego_celey']
print('кэш есть, контактов нет вовсе:', n, '| из них с сайтом:', d['s_sajtom'])
print('по стадиям:', json.dumps(d['stadii'], ensure_ascii=False))
ok = [r for r in d['vyborka'] if 'err' not in r]
sp = [r for r in ok if r['pocht']]
st = [r for r in ok if r['tel']]
vp = sum(r['pocht'] for r in ok)
vt = sum(r['tel'] for r in ok)
print('ВЫБОРКА:', len(ok), 'компаний')
print('  с почтой: %d (%.1f%%) | с телефоном: %d (%.1f%%) | хоть с чем-то: %d (%.1f%%)' % (
    len(sp), 100.0 * len(sp) / len(ok), len(st), 100.0 * len(st) / len(ok),
    len({r['inn'] for r in sp} | {r['inn'] for r in st}),
    100.0 * len({r['inn'] for r in sp} | {r['inn'] for r in st}) / len(ok)))
print('  всего почт %d (медиана у нашедших %s), телефонов %d (медиана %s)' % (
    vp, int(statistics.median([r['pocht'] for r in sp])) if sp else 0,
    vt, int(statistics.median([r['tel'] for r in st])) if st else 0))
print('  почт отсеяно как платформенные/noreply: %d' % sum(r['pocht_musor'] for r in ok))
print('  чистых почт «общий/роль не опознана»: %d; с ролью в имени ящика: %d' % (
    sum(r['pocht_obshchie'] for r in ok), sum(r['pocht_s_rolyu'] for r in ok)))
print('  телефонов-реквизитов отброшено: %d' % sum(r['tel_rekvizit'] for r in ok))
print('  телефонов, уже стоящих за ДРУГИМ ИНН (коммутатор/справочник): %d' % sum(
    r['tel_chuzhie'] for r in ok))
print('  номеров у >=3 компаний выборки:', len(d['spravochnye_nomera']))
print('  страниц у целей: медиана %s' % int(statistics.median(
    [r.get('stranic', 0) for r in ok])))
ist = {}
for r in ok:
    ist[r.get('istochnik', '?')] = ist.get(r.get('istochnik', '?'), 0) + 1
print('  источник кэша:', json.dumps(ist, ensure_ascii=False))
k = len(ok)
print('ЭКСТРАПОЛЯЦИЯ на %d: почт ~%d, телефонов ~%d, компаний с контактом ~%d' % (
    n, round(vp * n / k), round(vt * n / k),
    round(len({r['inn'] for r in sp} | {r['inn'] for r in st}) * n / k)))
print('30 ПРИМЕРОВ (самые богатые):')
for r in sorted(ok, key=lambda x: -(x['pocht'] + x['tel']))[:30]:
    print(' ', r['inn'], '|стр', r.get('stranic'), '|почт', r['pocht'], '|тел', r['tel'],
          '|', (r.get('kesh_site') or '')[:26], '|', r['name'][:22], '|',
          ','.join(r['primery_pocht'][:2])[:38], '|', ','.join(r['primery_tel'][:2]))
print('10 ПУСТЫХ (ничего не нашлось):')
for r in [x for x in ok if not x['pocht'] and not x['tel']][:10]:
    print(' ', r['inn'], '|стр', r.get('stranic'), '|', (r.get('kesh_site') or '')[:30],
          '|', r['name'][:26], '|стадии', r.get('stadii', '')[:30])
