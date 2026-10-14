# -*- coding: utf-8 -*-
"""fixK (локально, только чтение): перепроверка пула MEYER-7 и предварительный рейтинг кандидатов.

    python3 -E -P fixK_otbor.py <папка fixK> [<папка с db0 и kodroot>]

Пул (pul_1310.pkl, 9 380 с ИНН) перепроверяется: не в панели (каталог сейчас), не в архиве arhiv_* (кроме
16 воронежских из fixG2 – Воронеж теперь домашний регион Козлова/Тюнина), выручка известна – от 30 млн
(владелец 13.10), нет активной сделки Meyer (meyer_all.csv: ИНН сделки, ИНН в тексте сделки, точное
название – логика fixH_bitrix_sverka), нет пометки сборки «сайт общий с компанией, где идёт сделка»,
основной ОКВЭД не «нецелевой» для пищевки с сегментом по доп. ОКВЭД (правило E1), без леса и химии.
Потом – контакты по правилам fixK_m7 и ступень ПАНЕЛИ (rol_kontakta + общий номер панели, формула fixF2_ball)
на копии каталога, куда вставлены все кандидаты. Выход: <fixK>/otbor.json и kandidaty-bitrix.json.
"""
import collections
import csv
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

W = sys.argv[1]
OSN = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(W.rstrip('/')), 'fixJ')
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
import fixK_m7 as M  # noqa: E402

SIM = os.path.join(W, 'sim_otbor')
os.makedirs(SIM, exist_ok=True)
shutil.copy(os.path.join(OSN, 'db0', 'meyer_baza1.db'), os.path.join(SIM, 'meyer_baza1.db'))
shutil.copy(os.path.join(OSN, 'db0', 'centro_sales_meyer1.db'), os.path.join(SIM, 'centro_sales_meyer1.db'))
os.environ['CENTRIFUGAL_DB'] = os.environ['CENTRO_DB'] = os.path.join(SIM, 'meyer_baza1.db')
os.environ['CENTRO_SALES_DB'] = os.path.join(SIM, 'centro_sales_meyer1.db')
sys.path.insert(0, os.path.join(OSN, 'kodroot'))
from app.services import centro_catalog as cat  # noqa: E402
from app.services import centro_sales as sales  # noqa: E402
import fixE1_regiony_segmenty as E1  # noqa: E402
import fixF2_ball as E2  # noqa: E402

TZ = json.load(open(os.path.join(ZDES, 'okved_segment_tz.json'), encoding='utf-8'))
E1.OKVED_TZ.update(TZ)
T0 = time.time()
pul, m, k3, dop = M.zagruzit()
sb = M.Sborka(pul, m, k3, dop)
print('сборка прочитана: пул %d, компаний %d, контактов %d (%.0f с)' % (len(pul), len(sb.komp), sum(len(v) for v in sb.kont.values()),
                                                                     time.time() - T0))
k = sqlite3.connect(os.path.join(SIM, 'meyer_baza1.db'))
panel = {r[0] for r in k.execute('SELECT inn FROM company')}
arhiv = {r[0]: r[1] for r in k.execute('SELECT inn, arhiv_prichina FROM arhiv_company')}
VOR16 = {i for i, p in arhiv.items() if 'воронежских' in (p or '')}
assert len(VOR16) == 16, len(VOR16)

# ---------------------------------------------------------------- Битрикс: сверка кандидатов (fixH_bitrix_sverka)
kand_b = [{'inn': M.kl_inn(r['inn']), 'nazvanie': M.s(r['Название']), 'region': M.s(r['Регион'])} for _, r in pul.iterrows()]
for i in sb.vozvrat:
    kand_b.append({'inn': i, 'nazvanie': M.s(sb.komp[i]['Название']), 'region': M.s(sb.komp[i]['Регион'])})
for i in VOR16:
    if i not in {x['inn'] for x in kand_b} and i in sb.komp:
        kand_b.append({'inn': i, 'nazvanie': M.s(sb.komp[i]['Название']), 'region': M.s(sb.komp[i]['Регион'])})
# «полимеры, гранула» – владелец 13.10 вернул в пул («пластик в гранулах мы сортируем»): из листа «Компании» с теми же
# фильтрами, что у пула (не в панели, без активной сделки по сборке, не «похоже, не покупатель», с ИНН, не «ИНН вероятный»)
POLIMERY, POLIMERY_STROKI = [], []
for _, r in k3.iterrows():
    if 'полимеры, гранула' not in M.s(r['Сегмент']):
        continue
    if r['v_paneli'] or r['akt'] or r['ne_pok'] or M.s(r['key']).startswith('САЙТ') or M.s(r['ИНН вероятный ⚠']):
        continue
    i = M.kl_inn(r['inn'])
    if not i or i in {M.kl_inn(x) for x in pul['inn']}:
        continue
    POLIMERY.append(i)
    POLIMERY_STROKI.append({'inn': i, 'vyr': r['vyr'], 'eda': False, 'dop': M.s(r['Как определён сегмент']) != 'по основному ОКВЭД',
                   'Сегмент': r['Сегмент'], 'Основной ОКВЭД': r['Основной ОКВЭД'], 'Ревизия: профиль': r['Ревизия: профиль'],
                   'dom': ''})
    kand_b.append({'inn': i, 'nazvanie': M.s(r['Название']), 'region': M.s(r['Регион'])})
print('«полимеры, гранула» возвращены в пул: %d' % len(POLIMERY))
json.dump(kand_b, open(os.path.join(W, 'kandidaty-bitrix.json'), 'w', encoding='utf-8'), ensure_ascii=False)
SV = os.path.join(W, 'sverka.json')
if not os.path.exists(SV):
    B = os.path.join(M.SCR, 'vhod-bitrix2')
    r = subprocess.run([sys.executable, '-I', os.path.join(ZDES, 'fixH_bitrix_sverka.py'), os.path.join(B, 'all', 'meyer_all.csv'),
                        os.path.join(B, 'zip', '2_kc_sc_all (1).csv'), os.path.join(SIM, 'meyer_baza1.db'), SV,
                        os.path.join(W, 'kandidaty-bitrix.json')], capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-1500:])
SVERKA = json.load(open(SV, encoding='utf-8'))
# Беларусь: УНП 9 цифр – сверка fixH дополняет 9 цифр нулём (как РФ-ИНН, съеденный Excel) и УНП не находит;
# поэтому отдельно: УНП в поле ИНН сделки как есть и 9 цифр УНП в тексте сделки (активные сделки Meyer)
AKT_UNP = collections.defaultdict(list)
for r in csv.DictReader(io.open(os.path.join(M.SCR, 'vhod-bitrix2', 'all', 'meyer_all.csv'), encoding='utf-8-sig', newline=''),
                        delimiter=';'):
    d_ = re.sub(r'\D', '', r.get('INN') or '')
    d_ = ('0' + d_) if len(d_) in (9, 11) else d_
    if r.get('АКТИВНА') == 'да' and d_:
        M.KLIENTY.setdefault(d_, (r.get('КОМПАНИЯ') or r.get('НАЗВАНИЕ_В_РЕКВИЗИТАХ') or '')[:80])
with io.open(os.path.join(M.SCR, 'vhod-bitrix2', 'all', 'meyer_all.csv'), encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f, delimiter=';'):
        if (r.get('АКТИВНА') or '').strip() != 'да':
            continue
        d = re.sub(r'\D', '', r.get('INN') or '')
        if len(d) == 9:
            AKT_UNP[d].append('сделка %s %s «%s»: УНП в поле ИНН' % (r['DEAL_ID'], r['ВОРОНКА'], (r['TITLE'] or '')[:60]))
        for t_ in (r.get('TITLE') or '', r.get('КОМПАНИЯ') or '', r.get('НАЗВАНИЕ_В_РЕКВИЗИТАХ') or ''):
            for x in re.findall(r'(?<!\d)(\d{9})(?!\d)', t_):
                AKT_UNP[x].append('сделка %s %s «%s»: УНП в тексте' % (r['DEAL_ID'], r['ВОРОНКА'], (r['TITLE'] or '')[:60]))
# fixT (14.10): и УСПЕШНЫЕ сделки Meyer («Meyer клиент», «Meyer привлечение успешно») – владелец: «таких не надо в панель»
USP_MEYER = M.uspeshnye_meyer(os.path.join(M.SCR, 'vhod-bitrix2', 'all', 'meyer_all.csv'))

# ---------------------------------------------------------------- проверки пула
otkaz = collections.defaultdict(list)
prichiny = collections.Counter()
kand = []
inn_pula = [M.kl_inn(x) for x in pul['inn']]
for i in sorted(VOR16):
    if i not in inn_pula and i in sb.komp:
        otkaz[i].append('воронежская из архива fixG2 не в пуле MEYER-7 (%s)' % (M.s(sb.komp[i]['Ревизия: профиль']) or 'отсеяна сборкой'))
stroki = [dict(r) for _, r in pul.iterrows()]
for r in POLIMERY_STROKI:
    stroki.append(r)
for i in sb.vozvrat:          # возвращённые из «Не вошли» (сайт клиента со сделкой): у самой компании сделки быть не должно
    z = sb.komp[i]
    stroki.append({'inn': i, 'vyr': float('nan'), 'eda': sb.vozvrat_eda[i], 'dop': False, 'Сегмент': z['Сегмент'],
                   'Основной ОКВЭД': z['Основной ОКВЭД'], 'Ревизия: профиль': z['Ревизия: профиль'], 'dom': ''})
for r in stroki:
    inn = M.kl_inn(r['inn'])
    pr = []
    if inn in panel:
        pr.append('уже в панели')
    if inn in arhiv and inn not in VOR16:
        pr.append('убрана из панели раньше (arhiv_*): %s' % (arhiv[inn] or '')[:120])
    vyr = r['vyr'] if r['vyr'] == r['vyr'] else None
    if vyr is not None and vyr < 3e7:
        pr.append('выручка %.1f млн – меньше 30 млн (владелец 13.10)' % (vyr / 1e6))
    sv = SVERKA['kandidaty'].get(inn) or SVERKA['panel'].get(inn) or {}
    if sv.get('aktivnye_meyer'):
        a = sv['aktivnye_meyer'][0]
        pr.append('активная сделка Meyer (%s): %s %s «%s»' % (a['kak'], a['id'], a['voronka'], a['title'][:60]))
    elif sv.get('po_imeni_proverit') and not (inn in M.IMENA and not M.IMENA[inn][0]):
        a = sv['po_imeni_proverit'][0]
        pr.append('возможна активная сделка Meyer по точному названию (у сделки нет ИНН): %s «%s» – не беру без проверки'
                  % (a['id'], a['title'][:60]))
    if len(inn) == 9 and AKT_UNP.get(inn):
        pr.append('активная сделка Meyer (Беларусь, по УНП): ' + AKT_UNP[inn][0])
    if USP_MEYER.get(inn):      # fixT 14.10: не только активные, но и успешные
        pr.append('успешная сделка Meyer: ' + USP_MEYER[inn][0])
    # «сайт общий с компанией, где идёт сделка» – НЕ причина (владелец 13.10: деление по компании)
    seg = M.s(r['Сегмент']).lower()
    if any(x in seg for x in M.LES_HIM):
        pr.append('лес/химия (владелец 13.10)')
    okv = M.s(r['Основной ОКВЭД'])
    if r['eda'] and r['dop'] and E1.necelevaya(okv):
        pr.append('сегмент только по доп. ОКВЭД, основной – %s (в панели была бы пометка «нецелевая», конец очереди)' % E1.necelevaya(okv))
    if pr:
        otkaz[inn] += pr
        prichiny[pr[0].split(' (')[0].split(':')[0][:60]] += 1
    else:
        kand.append(inn)
print('пул %d -> после проверок %d; отказы по первой причине: %s' % (len(pul), len(kand), dict(prichiny.most_common())))
print('воронежские из архива fixG2: в пуле %d, прошли %d: %s' % (sum(1 for i in VOR16 if i in inn_pula),
                                                                sum(1 for i in VOR16 if i in kand), sorted(i for i in VOR16 if i in kand)))

# ---------------------------------------------------------------- контакты и ступень панели на копии каталога
kol_c = {r[1] for r in k.execute('PRAGMA table_info(contact)')}
kol_p = {r[1] for r in k.execute('PRAGMA table_info(person)')}
statistika = collections.Counter()
for n, inn in enumerate(kand):
    c = sb.komp[inn]
    if inn in panel:
        continue
    k.execute('INSERT INTO company (inn, predpriyatie, region, okved, sayt, vyruchka_rub) VALUES (?,?,?,?,?,?)',
              (inn, M.s(c['Название']), M.s(c['Регион']), M.s(c['Основной ОКВЭД']), M.s(c['Сайт']), M.chislo(c['Выручка, руб'])))
    kont, lyudi, pochty, zh = M.kontakty_kompanii(sb, inn, cat)
    statistika['почт (в company.pochta)'] += len(pochty)
    statistika.update(zh)
    for x in kont:
        rr = {kk: v for kk, v in x.items() if kk in kol_c and not kk.startswith('_')}
        k.execute('INSERT INTO contact (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
    for x in lyudi:
        rr = {kk: v for kk, v in x.items() if kk in kol_p}
        k.execute('INSERT INTO person (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
k.commit()
print('контакты кандидатов вставлены (%.0f с): %s' % (time.time() - T0, dict(statistika)))
_kesh = {}
_orig = cat._shared_phone_keys


def _shared_kesh(conn):
    if 'k' not in _kesh:
        _kesh['k'] = _orig(conn)
    return _kesh['k']


cat._shared_phone_keys = _shared_kesh
rez = {}
for inn in kand:
    c = sb.komp[inn]
    items = cat.contacts(inn)
    tel = [x for x in items if x['kind'] == 'phone']
    lpr = [x for x in tel if x['lpr']]
    mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
    fio_mob = [x for x in mob if x['person']]
    tier = 4 if fio_mob else 3 if mob else 2 if lpr else 1
    vid_s, sila = M.sayt_prinyat(c['Сайт: чей'])
    rez[inn] = {'inn': inn, 'nazvanie': M.s(c['Название']), 'region': M.s(c['Регион']), 'strana': M.s(c['Страна']),
                'eda': None,
                'vyr': M.chislo(c['Выручка, руб']), 'tier': tier, 'st_sborki': int(c['st']), 'sila_sayta': sila,
                'proverka_sayta': vid_s, 'segment_sborki': M.s(c['Сегмент']), 'okved': M.s(c['Основной ОКВЭД']),
                'n_tel': len(tel), 'n_lpr': len(lpr), 'n_mob_lpr': len(mob),
                'roli_lpr': sorted({x['rol_vid'] for x in lpr}),
                'gruppa': M.s(c['Группа']), 'holding_agent': M.s(c['Холдинг (агент)']), 'vozvrat': int(inn in sb.vozvrat),
                'reviziya': M.s(c['Ревизия: профиль'])}
# eda: из пула (pul индекс совпадает с K3?)
eda = dict(zip([M.kl_inn(x) for x in pul['inn']], pul['eda']))
eda.update(sb.vozvrat_eda)
eda.update({i: False for i in POLIMERY})
dom = dict(zip([M.kl_inn(x) for x in pul['inn']], pul['dom']))
for i in list(sb.vozvrat) + POLIMERY:
    rg = E1.region_norm(M.s(sb.komp[i]['Регион']))
    dom[i] = {'Алтайский край': 'Алтай', 'Краснодарский край': 'Краснодар', 'Воронежская область': 'Воронеж'}.get(rg, '')
for inn, z in rez.items():
    z['eda'] = bool(eda.get(inn))
    z['dom'] = dom.get(inn, '')
tab = collections.Counter((z['eda'], z['tier']) for z in rez.values())
print('ступень панели (кандидаты %d): пищевка %s; прочие %s' % (len(rez), {t: tab[(True, t)] for t in (4, 3, 2, 1)},
                                                               {t: tab[(False, t)] for t in (4, 3, 2, 1)}))
per = collections.Counter((z['st_sborki'], z['tier']) for z in rez.values())
print('ступень сборки -> ступень панели: %s' % sorted(per.items()))
json.dump({'otkaz': otkaz, 'kandidaty': rez, 'vor16': sorted(VOR16), 'statistika_kontaktov': statistika},
          open(os.path.join(W, 'otbor.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print('готово за %.0f с -> %s' % (time.time() - T0, os.path.join(W, 'otbor.json')))
