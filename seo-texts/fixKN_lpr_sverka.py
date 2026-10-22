# -*- coding: utf-8 -*-
r"""fixKN (22.10): какие прежние ЛПР / личные номера ушли из панели КЦ при замене контактов «КО» и есть ли они в новых данных.
Только чтение (sqlite mode=ro): архив contact_arhiv_fixKN / person_arhiv_fixKN против новых строк contact тех же ИНН.
Номера и почты не выводятся – только счётчики.

    python3 zapusk_na_servere.py fixKN_lpr_sverka.py
"""
import collections
import re
import sqlite3

KAT = r'C:\seostat\data\centrifugal.db'
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
zam = [r[0] for r in k.execute('SELECT inn FROM import_fixKN')]


def kl_tel(v):
    d = re.sub(r'\D', '', str(v or ''))
    return d[-10:] if len(d) >= 10 else ''


novye = collections.defaultdict(set)
for r in k.execute('SELECT inn, kind, value, person FROM contact WHERE inn IN (%s)' % ','.join('?' * len(zam)), zam):
    novye[r['inn']].add(('t', kl_tel(r['value'])) if r['kind'] == 'phone' else ('e', str(r['value']).strip().lower()))
    if r['person']:
        novye[r['inn']].add(('f', str(r['person']).split()[0].lower().strip('.,')))


def lpr_stroka(r, tab):
    """Прежний «ЛПР» – названный человек с номером/почтой, или контакт с ролью / техническим / закупочным признаком,
    или мобильный (личный) номер. Общие номера и номера без владельца – не ЛПР."""
    person = str(r['person'] or '').strip()
    if tab == 'contact':
        if r['is_unknown_owner']:
            return None
        lich = 'мобил' in str(r['phone_type'] or '').lower()
        rol = bool(r['is_tech'] or r['is_purchaser'] or r['has_role'])
        if not (person or rol or lich):
            return None
        kl = ('t', kl_tel(r['value'])) if r['kind'] == 'phone' else ('e', str(r['value']).strip().lower())
        return {'kl': [kl], 'person': person, 'tech': bool(r['is_tech']), 'mob': lich, 'vid': r['kind']}
    if not person or r['privyazka_snyata']:
        return None
    kl = []
    if r['phone']:
        kl.append(('t', kl_tel(r['phone'])))
    if r['email']:
        kl.append(('e', str(r['email']).strip().lower()))
    if not kl:
        return None
    return {'kl': kl, 'person': person, 'tech': bool(r['is_tech']), 'mob': 'мобил' in str(r['phone_type'] or '').lower(), 'vid': 'person'}


itog = collections.Counter()
kompanii_poteri = set()
istochniki_poter = collections.Counter()
lyudi_vse, lyudi_net = set(), set()
for tab in ('contact', 'person'):
    for r in k.execute('SELECT * FROM %s_arhiv_fixKN' % tab):
        x = lpr_stroka(r, tab)
        if not x:
            continue
        inn = r['inn']
        est = any(kl in novye[inn] for kl in x['kl'] if kl[1])
        fam = x['person'].split()[0].lower().strip('.,') if x['person'] else ''
        est_fam = bool(fam) and ('f', fam) in novye[inn]
        chel = (inn, fam or str(x['kl']))
        lyudi_vse.add(chel)
        itog['%s: всего' % tab] += 1
        itog['%s: номер/почта есть в новых' % tab] += est
        itog['%s: нет номера, но фамилия есть в новых' % tab] += (not est and est_fam)
        itog['%s: нет ни номера, ни фамилии' % tab] += (not est and not est_fam)
        if not est and not est_fam:
            lyudi_net.add(chel)
            kompanii_poteri.add(inn)
            istochniki_poter[str(r['source'] or '')[:45]] += 1
            itog['%s: потеряно, из них технических' % tab] += x['tech']
            itog['%s: потеряно, из них мобильных' % tab] += x['mob']
print('компаний с заменой:', len(zam))
for kk in sorted(itog):
    print('  %-50s %d' % (kk, itog[kk]))
print('людей (ИНН + фамилия) среди прежних ЛПР: %d, из них нет в новых ни номером, ни фамилией: %d, у компаний: %d' % (
    len(lyudi_vse), len(lyudi_net), len(kompanii_poteri)))
print('источники того, чего нет в новых:', istochniki_poter.most_common(12))
# по людям: категории и сосредоточенность
kat = collections.defaultdict(set)
po_komp = collections.Counter()
for tab in ('contact', 'person'):
    for r in k.execute('SELECT * FROM %s_arhiv_fixKN' % tab):
        x = lpr_stroka(r, tab)
        if not x:
            continue
        fam = x['person'].split()[0].lower().strip('.,') if x['person'] else ''
        chel = (r['inn'], fam or str(x['kl']))
        if chel not in lyudi_net:
            continue
        ist = str(r['source'] or '')
        massa = 'P25-LYUDI' in ist
        kat['все'].add(chel)
        kat['из списков P25-LYUDI (закупочная документация)' if massa else 'из прочих источников'].add(chel)
        if x['tech']:
            kat['технические'].add(chel)
        if x['mob']:
            kat['с мобильным'].add(chel)
        if (x['tech'] or x['mob']) and not massa:
            kat['технические или с мобильным, не из P25-LYUDI'].add(chel)
for kk, v in kat.items():
    print('   людей %-55s %d (компаний %d)' % (kk, len(v), len({c[0] for c in v})))
for c in lyudi_net:
    po_komp[c[0]] += 1
print('   по компаниям (топ):', [n for _i, n in po_komp.most_common(12)])
