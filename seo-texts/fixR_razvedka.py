# -*- coding: utf-8 -*-
"""fixR: только чтение. Белорусские номера (+375, «8 0XX …», 8-801) в каталоге панели Meyer:
сколько их, в каком формате, какой вид номера записан в contact.vid_nomera, у каких компаний,
на каких ступенях очереди. Номера в вывод НЕ печатаются (только маска), подробности – на дроп.
    python3 zapusk_na_servere.py fixR_razvedka.py
"""
import collections
import io
import json
import os
import re
import sqlite3
import time

KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
DOB = re.compile(r"\s*(?:доб\.?|доп\.?|вн\.?|ext\.?|#)\s*(\d{1,6})\s*$", re.I)


def maska(d):
    return d[:5] + 'X' * max(0, len(d) - 5)


def klass(v):
    t = str(v or '').strip()
    m = DOB.search(t)
    if m:
        t = t[:m.start()].strip()
    d = re.sub(r'\D', '', t)
    if t.startswith('+375'):
        return 'A_+375', d
    if t.startswith('+') and not t.startswith('+7'):
        return 'F_+прочие', d
    if d.startswith('375') and not t.startswith('+'):
        return 'B_375_без_плюса', d
    if d.startswith('810375'):
        return 'E_810375', d
    if len(d) == 11 and d.startswith('8801'):
        return 'D_8801', d
    if len(d) == 11 and d.startswith('80'):
        return 'C_80', d
    if len(d) == 11 and d.startswith('70'):
        return 'C2_70', d
    return '', d


k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
kol_c = [r[1] for r in k.execute('PRAGMA table_info(contact)')]
kol_co = [r[1] for r in k.execute('PRAGMA table_info(company)')]
print('contact: колонки', ', '.join(kol_c))
print('company: strana' if 'strana' in kol_co else 'company: колонки strana НЕТ')
komp = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
s.row_factory = sqlite3.Row
nazn = {r['inn']: dict(r) for r in s.execute('SELECT * FROM company_assignment')}
print('компаний в каталоге %d, назначений %d' % (len(komp), len(nazn)))
strana = collections.Counter(str(c.get('strana') or '') for c in komp.values())
print('страна:', dict(strana))
dl_inn = collections.Counter(len(str(i)) for i in komp)
print('длина ИНН/УНП:', dict(dl_inn))
by = {i for i, c in komp.items() if str(c.get('strana') or '').casefold().startswith(('бел', 'рб')) or len(str(i)) == 9}
print('белорусских (страна или 9 цифр): %d; из них в назначениях %d' % (len(by), len(by & set(nazn))))

stat = collections.defaultdict(lambda: collections.Counter())
podrob = collections.defaultdict(list)
inn_po_kl = collections.defaultdict(set)
for r in k.execute("SELECT * FROM contact WHERE kind='phone'"):
    r = dict(r)
    kl, d = klass(r.get('value'))
    if not kl:
        continue
    by_k = r['inn'] in by
    stat[kl]['всего'] += 1
    stat[kl]['у РБ-компаний' if by_k else 'у НЕ РБ-компаний'] += 1
    stat[kl]['цифр=%d' % len(d)] += 1
    stat[kl]['вид=' + str(r.get('vid_nomera') or '')] += 1
    stat[kl]['phone_type=' + str(r.get('phone_type') or '')] += 1
    if kl in ('A_+375', 'B_375_без_плюса'):
        stat[kl]['код=' + d[3:5]] += 1
    elif kl == 'C_80':
        stat[kl]['код=' + d[2:4]] += 1
    elif kl == 'F_+прочие':
        stat[kl]['пре=' + d[:3]] += 1
    inn_po_kl[kl].add(r['inn'])
    podrob[kl].append({'id': r['id'], 'inn': r['inn'], 'value': r.get('value'), 'vid_nomera': r.get('vid_nomera'),
                       'vid_pochemu': r.get('vid_pochemu'), 'phone_type': r.get('phone_type'),
                       'person': r.get('person'), 'position': r.get('position'), 'role': r.get('role'),
                       'by': by_k, 'source': str(r.get('source') or '')[:80]})
for kl in sorted(stat):
    print('== %s: компаний %d' % (kl, len(inn_po_kl[kl])))
    for kk, v in sorted(stat[kl].items()):
        print('     %s: %d' % (kk, v))
    for x in podrob[kl][:4]:
        d = re.sub(r'\D', '', str(x['value'] or ''))
        print('     пример: инн %s, %s, вид «%s», почему «%s»' % (x['inn'], maska(d), x['vid_nomera'] or '',
                                                                str(x['vid_pochemu'] or '')[:60]))
# НЕ РБ-компании с номерами «80…» – маски
for x in podrob.get('C_80', []):
    if not x['by']:
        print('   НЕ РБ, «80…»: инн %s, %s' % (x['inn'], maska(re.sub(r'\D', '', str(x['value'] or '')))))
# person: телефоны
kol_p = [r[1] for r in k.execute('PRAGMA table_info(person)')]
pk = [c for c in ('phone', 'nomer_10cifr') if c in kol_p]
np_ = collections.Counter()
for c in pk:
    for (v,) in k.execute('SELECT %s FROM person WHERE COALESCE(%s,"")<>""' % (c, c)):
        kl, d = klass(v)
        if kl:
            np_[c + ':' + kl] += 1
print('person, номера РБ-вида:', dict(np_))
# ступени у РБ-компаний
st = collections.Counter()
for i in by & set(nazn):
    st[(nazn[i]['username'], nazn[i].get('stupen_ocheredi'))] += 1
print('РБ: (менеджер, ступень) ->', sorted(st.items()))
# флаги РБ-компаний
fl = collections.Counter((int(bool(komp[i].get('lpr_mobilnyy'))), str(komp[i].get('pometka_ocheredi') or '')[:20]) for i in by)
print('РБ: (lpr_mobilnyy, pometka) ->', dict(fl))
VR = time.strftime('%Y%m%d-%H%M%S')
put = os.path.join(DROP, 'fixR-razvedka-%s.json' % VR)
io.open(put, 'w', encoding='utf-8').write(json.dumps({'podrob': podrob, 'by': sorted(by)}, ensure_ascii=False, indent=0))
print('подробно: %s' % os.path.basename(put))
