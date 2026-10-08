# -*- coding: utf-8 -*-
"""fixD: план правок «чей сайт» по разбору (chey.json) + ручным решениям (fixD_ruchnye.py).

Выход – JSON-план (номера телефонов в нём не пишутся, только id контактов):
  kontakty: {id: {chuzhoy_istochnik, chuzhoy_dokaz}}
  kompanii: {ИНН: {verdikt, sayt_chey, sayt (новый, если меняется), sayt_domen}}
  svodka: числа по базам.
Правило пометки контакта: домен источника для этой компании «чужой» – помечается; «группа» –
помечается, если подпись номера на странице не называет саму компанию/её населённый пункт;
у контакта с несколькими ссылками хватает одной «своей», чтобы не помечать.

    python3 fixD_plan.py <папка-fixD> <выход.json>
"""
import json
import os
import re
import sqlite3
import sys

D, VYHOD = sys.argv[1], sys.argv[2]
sys.argv = [sys.argv[0], os.path.join(D, 'db/meyer_baza1.db'), os.path.join(D, 'pages'), os.path.join(D, 'svyazi.json'),
            os.path.join(D, 'dl/checko-meyer-razbor.json'), '/dev/null']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixD_chey_sayt as C  # noqa: E402
import fixD_ruchnye as R  # noqa: E402

chey = json.load(open(os.path.join(D, 'chey.json'), encoding='utf-8'))
k = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'db/meyer_baza1.db'), uri=True)
k.row_factory = sqlite3.Row
komp = {r['inn']: dict(r) for r in k.execute('select inn, predpriyatie, bazy, sayt, sayt_chey, adres, region from company')}
kont = {r['id']: dict(r) for r in k.execute('select id, inn, value, source, source_url, fragment from contact')}


def cifry(v):
    d = re.sub(r'\D', '', (v or '').split('доб')[0])
    return d[-10:]


def podpis_nomera(fragment, value):
    """Текст подписи перед номером внутри фрагмента: от предыдущего номера до этого."""
    f = fragment or ''
    c = cifry(value)
    if len(c) < 10:
        return ''
    # номер на странице может быть записан с любыми разделителями и с 8/+7
    pat = r'(?:\+?7|8)?[\s\-\(\)]*' + r'[\s\-\(\)]*'.join(list(c[:3])) + r'[\s\-\(\)]*' + r'[\s\-\(\)]*'.join(list(c[3:]))
    m = re.search(pat, f)
    if not m:
        return ''
    do = f[:m.start()]
    prev = list(re.finditer(r'(?:\+7|8)[\s\-\(\)]*\d[\d\s\-\(\)]{8,}\d|\[tel:[^\]]*\]', do))
    nach = prev[-1].end() if prev else max(0, len(do) - 120)
    return do[nach:]


def nazyvaet_kompaniyu(tekst, inn):
    c = komp[inn]
    t = C.norm(tekst)
    slova = [w for w in C.otlichitelnye(C.yadro_nazvaniya(c['predpriyatie'])) if len(w) >= 5]
    if any(w[:6] in t for w in slova):
        return True
    gor = C.gorod(c.get('adres') or '')
    return bool(gor) and C.norm(gor)[:6] in t


def verdikt_domena(inn, d):
    v = chey[inn]['domeny'].get(d)
    r = R.DOMENY.get((inn, d))
    if r:
        return {'verdikt': r[0], 'vladelec': r[1], 'dokaz': r[2], 'ruchnoy': True}
    if not v:
        return None
    if v['verdikt'] == 'свой':
        return {'verdikt': 'свой', 'vladelec': '', 'dokaz': '; '.join(v['svoj']), 'ruchnoy': False}
    if v['verdikt'] == 'группа':
        return {'verdikt': 'группа', 'vladelec': '', 'dokaz': '; '.join(v['gruppa'] + v['svoj']), 'ruchnoy': False}
    if v['verdikt'] == 'чужой':
        return {'verdikt': 'чужой', 'vladelec': '', 'dokaz': '; '.join(v['chuzhoy']), 'ruchnoy': False}
    return {'verdikt': 'не определено', 'vladelec': '', 'dokaz': '; '.join(v['kosv']), 'ruchnoy': False}


nerazobrannye = []
plan_k = {}
for inn, x in chey.items():
    for d, v in x['domeny'].items():
        vd = verdikt_domena(inn, d)
        if vd['verdikt'] in ('чужой', 'группа') and not vd['ruchnoy']:
            nerazobrannye.append((inn, d, vd['verdikt'], v['kontakty'][:3]))
        if vd['verdikt'] == 'свой' and v.get('proverit') and not vd['ruchnoy']:
            nerazobrannye.append((inn, d, 'свой?', v['kontakty'][:3]))

for kid, kt in kont.items():
    inn = kt['inn']
    if kid in R.KONTAKTY:
        flag, vl, dok = R.KONTAKTY[kid]
        if flag:
            plan_k[kid] = {'chuzhoy_istochnik': 'с сайта другого юрлица: ' + vl, 'chuzhoy_dokaz': dok + ' (проверено 08.10.2026)'}
        continue
    urls = [u for u in (kt['source_url'] or '').replace(';', ' ').split() if u.startswith('http')]
    doms = [C.domen(u) for u in urls if C.domen(u) and not C.ne_sayt(C.domen(u))]
    if not doms or inn not in chey:
        continue
    vds = [(d, verdikt_domena(inn, d)) for d in doms]
    vds = [(d, z) for d, z in vds if z]
    if not vds or any(z['verdikt'] in ('свой', 'не определено') for _, z in vds):
        continue
    d, z = vds[0]
    if z['verdikt'] == 'группа':
        pod = podpis_nomera(kt['fragment'], kt['value'])
        if pod and nazyvaet_kompaniyu(pod, inn):
            continue  # номер самой компании на сайте группы (подпись называет её)
    vl = z['vladelec'] or ('владелец %s' % d)
    plan_k[kid] = {'chuzhoy_istochnik': 'с сайта другого юрлица: ' + vl,
                   'chuzhoy_dokaz': '%s; страница %s (проверено 08.10.2026)' % (z['dokaz'], urls[0])}

# компании: итог «чей сайт», sayt и sayt_chey
plan_c = {}
for inn, c in komp.items():
    x = chey.get(inn) or {'domeny': {}, 'sayt_domen': ''}
    sd = x.get('sayt_domen') or ''
    novyj_sayt = None
    pochemu = ''
    if inn in R.SAYT:
        novyj_sayt, pochemu = R.SAYT[inn]
    vd = verdikt_domena(inn, sd) if sd else None
    if vd and vd['verdikt'] in ('чужой', 'группа') and novyj_sayt is None:
        novyj_sayt = ''
        pochemu = 'прежний сайт %s – %s' % (sd, vd['vladelec'] or 'страница другого юрлица')
    # итоговый вердикт компании: по (новому) сайту, иначе по домену с бóльшим числом номеров
    if novyj_sayt:
        glav = C.domen(novyj_sayt)
    elif novyj_sayt == '':
        glav = sd
    else:
        glav = sd
    if not glav and x['domeny']:
        glav = max(x['domeny'], key=lambda d: len(x['domeny'][d]['kontakty']))
    gv = verdikt_domena(inn, glav) if glav else None
    if gv is None:
        itog, tekst = 'нет сайта', 'сайта-источника нет (номера только с площадок закупок/реестров)'
    else:
        itog = gv['verdikt']
        if itog == 'свой':
            tekst = 'свой: %s' % gv['dokaz']
        elif itog == 'группа':
            tekst = 'сайт группы: %s; %s' % (gv['vladelec'] or glav, gv['dokaz'])
        elif itog == 'чужой':
            tekst = 'другое юрлицо: %s; %s' % (gv['vladelec'] or glav, gv['dokaz'])
        else:
            tekst = 'не определено (%s): на сайте нет ИНН/ОГРН, юрадреса и руководителя из checko%s' % (
                glav, ('; косвенно: ' + gv['dokaz']) if gv['dokaz'] else '')
    if pochemu:
        tekst += '. Сайт исправлен: ' + pochemu
    tekst = 'Проверка 08.10.2026 – ' + tekst
    plan_c[inn] = {'verdikt': itog, 'sayt_chey': tekst[:1500], 'glav_domen': glav}
    if novyj_sayt is not None and (novyj_sayt or '') != (c.get('sayt') or ''):
        plan_c[inn]['sayt'] = novyj_sayt

# сводка по базам
svodka = {}
for inn, p in plan_c.items():
    for b in (komp[inn]['bazy'] or 'без базы').split(' | '):
        s = svodka.setdefault(b, {'компаний': 0, 'свой': 0, 'группа': 0, 'чужой': 0, 'не определено': 0, 'нет сайта': 0,
                                  'помечено номеров': 0, 'компаний с помеченными': 0})
        s['компаний'] += 1
        s[p['verdikt']] += 1
for kid, p in plan_k.items():
    inn = kont[kid]['inn']
    for b in (komp[inn]['bazy'] or 'без базы').split(' | '):
        svodka[b]['помечено номеров'] += 1
for inn in {kont[kid]['inn'] for kid in plan_k}:
    for b in (komp[inn]['bazy'] or 'без базы').split(' | '):
        svodka[b]['компаний с помеченными'] += 1
vse = {'компаний': len(plan_c)}
for p in plan_c.values():
    vse[p['verdikt']] = vse.get(p['verdikt'], 0) + 1
vse['помечено номеров'] = len(plan_k)
vse['компаний с помеченными'] = len({kont[kid]['inn'] for kid in plan_k})
json.dump({'kontakty': plan_k, 'kompanii': plan_c, 'svodka': svodka, 'vse': vse},
          open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(json.dumps(vse, ensure_ascii=False))
print('сайт меняется у %d компаний' % sum(1 for p in plan_c.values() if 'sayt' in p))
print('НЕ РАЗОБРАНО ВРУЧНУЮ (чужой/группа/свой с чужим ИНН):')
for x in nerazobrannye:
    print('  ', x)
