# -*- coding: utf-8 -*-
"""fixJ (локально): владелец 13.10 «нынешние усиль, потом пересчитай, чтобы равное было».

1. УСИЛИТЬ: для компаний панели, которые есть в базе соседней сессии MEYER-7, добавить контакты MEYER-7, которых в
   панели нет (ключ – 10 цифр номера + добавочный). Уже имеющийся номер не дублируется; если у нашего номера нет ни ФИО,
   ни должности (и нет ручного решения), а в MEYER-7 у того же номера с той же страницы (тот же домен) они есть и
   стоят во фрагменте страницы рядом с номером – дописываются. Источник – «MEYER-7 13.10: <Источник> · <Проверка>»,
   ссылка и фрагмент – из MEYER-7. Роль и вид – нашей логикой (centro_catalog.rol_kontakta по должности со страницы;
   «Роль» и «ЛПР по оборудованию» MEYER-7 – только подсказка в источнике).
   Правило «чей сайт»: домен страницы, который наша проверка D у этой компании признала чужим (или чей номер уже стоит
   у нас с меткой чужого источника), – контакт с меткой chuzhoy_istochnik; «сайт холдинга/группы» (MEYER-7 или наша D)
   – ЛПР не этой компании, если человек не назван её сотрудником (метка «с сайта группы»).
   Почты: e-mail человека с ФИО – в person.email (раздел «Люди предприятия»; ЛПР без номера – «спросить у
   приёмной»), все почты – в company.pochta с пометкой должности/роли (так хранятся почты сейчас; contact.kind
   в базе только phone). Ничего не удаляется; лист «Снято» MEYER-7 не берётся (его нет в выгрузке).
2. ФЛАГИ ЛПР, lpr_kratko, ступени и балл – той же логикой, что загрузчики fixG/fixH и fixF2_ball.
3. ВЫРОВНЯТЬ: MILP fixI (домашние регионы: Алтайский край – Пяткова/Волков, Краснодарский – Ерохин/Беляев поровну,
   Воронежская – никому из четырёх; холдинги и пары с общими номерами целиком, в т. ч. НОВЫЕ общие номера из MEYER-7;
   по 150; минимум перемещений; компании с действиями продавцов не двигаются).

    python3 fixJ_plan.py <папка fixJ> <выход plan.json>
    в папке: db0/ (снимок баз), kodroot/app, m7_panel.json (выгрузка MEYER-7 по ИНН панели), fixD-holdingi.json,
             chey/*.json (проверка D: fixD, fixG, fixG3, fixH – по порядку, поздний главнее)
"""
import collections
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time

W, OUT = sys.argv[1:3]
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
SIM = os.path.join(W, 'sim')
os.makedirs(SIM, exist_ok=True)
for f in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
    shutil.copy(os.path.join(W, 'db0', f), os.path.join(SIM, f))
os.environ['CENTRIFUGAL_DB'] = os.environ['CENTRO_DB'] = os.path.join(SIM, 'meyer_baza1.db')
os.environ['CENTRO_SALES_DB'] = os.path.join(SIM, 'centro_sales_meyer1.db')
sys.path.insert(0, os.path.join(W, 'kodroot'))
from app.services import centro_catalog as cat  # noqa: E402
from app.services import centro_sales as sales  # noqa: E402
import fixC_razbor as R  # noqa: E402
import fixF2_ball as E2  # noqa: E402

DATA = '13.10'
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
FIO = {'meyer1': 'Пяткова', 'meyer2': 'Ерохин', 'meyer3': 'Беляев', 'meyer4': 'Волков'}
DOM = {'Алтайский край': ['meyer1', 'meyer4'], 'Краснодарский край': ['meyer2', 'meyer3'], 'Воронежская область': []}
KRD = 'Краснодарский край'


def domen(u):
    u = (u or '').strip().lower()
    if '//' in u:
        u = u.split('//', 1)[1]
    d = u.split('/', 1)[0].split('?', 1)[0].split(':', 1)[0].strip('.')
    return d[4:] if d.startswith('www.') else d


def kl(v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    return R.klyuch10(R.cifry(osn)), (dob or '')


def yadro(naim):
    n = (naim or '').replace('«', '"').replace('»', '"').replace('“', '"').replace('”', '"')
    m = [x.strip() for x in n.split('"')[1:] if x.strip()]
    core = ' '.join(m) if m else re.sub(r'^\s*(?:ООО|ОАО|ЗАО|ПАО|АО|СПК|СХПК)\s+', '', n.strip())
    return re.sub(r'[^0-9a-zа-яё]+', ' ', core.lower().replace('ё', 'е')).strip()


def nazvan_svoim(c, tekst):
    """Человек назван сотрудником этой компании: в должности/фрагменте – отличительная часть её названия."""
    y = yadro(c['predpriyatie'])
    t = re.sub(r'[^0-9a-zа-яё]+', ' ', (tekst or '').lower().replace('ё', 'е'))
    return len(y) >= 4 and (' ' + y + ' ') in (' ' + t + ' ')


# ====================================================================== исходные данные
m7 = json.load(open(os.path.join(W, 'm7_panel.json'), encoding='utf-8'))
k = sqlite3.connect(os.path.join(SIM, 'meyer_baza1.db'))
k.row_factory = sqlite3.Row
kat = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
kont = collections.defaultdict(list)
for r in k.execute("SELECT * FROM contact"):
    kont[r['inn']].append(dict(r))
lyudi_est = collections.defaultdict(list)
for r in k.execute("SELECT * FROM person"):
    lyudi_est[r['inn']].append(dict(r))
chey = {}
for f in sorted(os.listdir(os.path.join(W, 'chey'))):
    chey.update(json.load(open(os.path.join(W, 'chey', f), encoding='utf-8')))
obshchie_m7 = set(m7['K'])
print('компаний панели %d; есть в MEYER-7: %d; строк контактов MEYER-7 у них: %d' % (len(kat), len(obshchie_m7), len(m7['C'])))


def verdikt_domena(inn, d):
    """-> (вид: 'свой'|'чужой'|'группа'|'', текст метки/доказательства)."""
    c = kat[inn]
    for x in kont[inn]:                                    # уже стоит у нас с этого домена с меткой чужого
        if x.get('chuzhoy_istochnik') and domen(x.get('source_url')) == d:
            return 'чужой', x['chuzhoy_istochnik'], x.get('chuzhoy_dokaz') or ''
    glavnyy = domen(c.get('sayt'))
    ps = (c.get('proverka_sayta') or '').strip()
    if d and d == glavnyy and ps == 'чужой':
        return 'чужой', 'с сайта другого юрлица: %s (проверка сайта D)' % d, (c.get('sayt_chey') or '')[:500]
    if d and d == glavnyy and ps == 'группа':
        return 'группа', d, (c.get('sayt_chey') or '')[:500]
    v = ((chey.get(inn) or {}).get('domeny') or {}).get(d) or {}
    if v.get('verdikt') == 'чужой':
        return 'чужой', 'с сайта другого юрлица: %s (проверка D: %s)' % (d, '; '.join(v.get('chuzhoy') or [])[:160]), \
            'проверка D: ' + '; '.join(v.get('chuzhoy') or [])[:400]
    if v.get('verdikt') == 'группа':
        return 'группа', d, 'проверка D: ' + '; '.join(v.get('gruppa') or [])[:400]
    return '', '', ''


# ====================================================================== 1. УСИЛЕНИЕ
novye_k, novye_p, dopisano, pochty, propushcheno = [], [], [], collections.defaultdict(list), collections.Counter()
klyuchi = {inn: {kl(x['value']) for x in kont[inn] if x['kind'] == 'phone'} for inn in kat}
uzhe_novye = set()
for x in m7['C']:
    inn = x['_inn']
    if inn not in kat:
        continue
    c = kat[inn]
    url = x['Ссылка на источник'] or x['Сайт']
    d = domen(url)
    vid_d, metka, dokaz = verdikt_domena(inn, d)
    istochnik = x['Источник']
    gruppa = vid_d == 'группа' or 'холдинг' in istochnik.lower()
    fio = re.sub(r'\s+', ' ', x['ФИО']).strip()
    dolzh = re.sub(r'\s+', ' ', x['Должность (как на сайте)']).strip()
    frag = (x['Фрагмент страницы'] or '')[:1500]
    podskazka = 'подсказка MEYER-7: роль «%s», ЛПР по оборудованию «%s»%s' % (
        x['Роль'], x['ЛПР по оборудованию'], ('; ' + x['Почему ЛПР'][:150]) if x['Почему ЛПР'] else '')
    source = ('MEYER-7 %s: %s · %s · %s' % (DATA, istochnik, x['Проверка'], podskazka))[:900]
    chuzhoy = ''
    chuzhoy_dokaz = ''
    if vid_d == 'чужой':
        chuzhoy, chuzhoy_dokaz = metka, dokaz
    rk0 = cat.rol_kontakta({'position': dolzh, 'source': source})
    if gruppa and not chuzhoy and rk0['lpr'] and not nazvan_svoim(c, dolzh + ' ' + fio):
        chuzhoy = 'с сайта группы: %s – человек не назван сотрудником этой компании' % (d or istochnik)
        chuzhoy_dokaz = ('MEYER-7: %s; %s' % (istochnik, dokaz))[:500]
    # --- почта
    em = x['E-mail'].strip().lower()
    if em and '@' in em:
        pom = ', '.join(v for v in (dolzh or x['Роль'], fio) if v)
        if chuzhoy:
            pom += '; ' + chuzhoy[:80]
        pochty[inn].append((em, pom, rk0['lpr'] and not chuzhoy))
    # --- номер
    nomer = x['Мобильный'] or x['Рабочий']
    if not nomer:
        if fio and em and rk0['lpr']:              # ЛПР только с почтой – человек предприятия
            novye_p.append({'inn': inn, 'person': fio, 'position': dolzh, 'role': rk0['vid'], 'phone': '', 'phone_type': '',
                            'email': em, 'source_url': url, 'source': source, 'is_tech': rk0['teh'],
                            'chuzhoy_istochnik': chuzhoy or None,
                            'sprosit_u_priemnoy': 'MEYER-7: на странице «%s» – %s; номера нет, есть почта %s' % (d, ', '.join(
                                v for v in (fio, dolzh) if v), em)})
        continue
    key = kl(nomer)
    if not key[0] or len(key[0]) != 10:
        propushcheno['номер не разобран'] += 1
        continue
    if key in klyuchi[inn]:
        # уже есть у нас: дописать ФИО/должность, если у нашего их нет, а MEYER-7 с той же страницы их даёт
        if not (fio or dolzh) or chuzhoy:
            continue
        nash = next(y for y in kont[inn] if y['kind'] == 'phone' and kl(y['value']) == key)
        if (nash.get('rol_vruchnuyu') or '').strip() or (nash.get('chuzhoy_istochnik') or '').strip():
            continue
        n_person = (nash.get('person') or '').strip()
        n_pos = (nash.get('position') or '').strip()
        if n_pos == 'мобильный с сайта, без подписи':
            n_pos = ''
        stalo_p, stalo_d = n_person, n_pos
        if not n_person and fio:
            stalo_p = fio
            if dolzh and n_pos and n_pos != dolzh and n_pos.replace(fio, '').strip(' ,') == dolzh:
                stalo_d = dolzh                      # имя было склеено с должностью: «Руководитель ОМТО Мария»
        if not n_pos and dolzh:
            stalo_d = dolzh
        if (stalo_p, stalo_d) == (n_person, n_pos):
            continue
        tsifry = re.sub(r'\D', '', frag)
        fam = (fio.split() or [''])[0].lower()
        if domen(nash.get('source_url')) != d or key[0][-7:] not in tsifry or not (
                (fam and fam in frag.lower()) or (dolzh and dolzh.lower()[:25] in frag.lower())):
            propushcheno['номер есть, подпись MEYER-7 не подтверждена фрагментом/страницей'] += 1
            continue
        dopisano.append({'id': nash['id'], 'inn': inn, 'value': nash['value'],
                         'bylo': {'person': nash.get('person'), 'position': nash.get('position'), 'source': nash.get('source')},
                         'stalo': {'person': stalo_p or None, 'position': stalo_d,
                                   'source': ((nash.get('source') or '') + ' · %s дописаны из MEYER-7 %s (тот же номер на %s)'
                                              % ('/'.join(x_ for x_, f_ in (('ФИО', stalo_p != n_person), ('должность', stalo_d != n_pos)) if f_),
                                                 DATA, d))[:900]}})
        continue
    if (inn, key) in uzhe_novye:
        propushcheno['повтор номера внутри MEYER-7'] += 1
        continue
    uzhe_novye.add((inn, key))
    vid = cat.vid_nomera_po_cifram(nomer)
    s = {'inn': inn, 'value': nomer, 'kind': 'phone', 'person': fio or None, 'role': '', 'position': dolzh,
         'phone_type': vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий',
         'source': source, 'source_url': url, 'fragment': frag, 'is_unknown_owner': 0, 'vid_nomera': vid,
         'vid_pochemu': '', 'rol_vruchnuyu': '', 'chuzhoy_istochnik': chuzhoy or None, 'chuzhoy_dokaz': chuzhoy_dokaz or None,
         'podpis_stranicy': '', '_email': em, '_m7_lpr': x['ЛПР по оборудованию']}
    rk = cat.rol_kontakta(s)
    s['is_purchaser'], s['is_tech'] = rk['zakup'], rk['teh']
    s['has_role'] = int(bool(rk['lpr']) or rk['vid'] in ('приёмная', 'общий номер', 'техслужба (не ЛПР)', 'без подписи'))
    s['nomer_ne_lichnyy'] = None if rk['lpr'] else rk['vid']
    if rk['lpr']:
        s['role'] = rk['vid']
    s['_rol'] = rk['vid']
    s['_lpr'] = rk['lpr']
    novye_k.append(s)
    if fio:
        novye_p.append({'inn': inn, 'person': fio, 'position': dolzh, 'role': s['role'] or rk['vid'], 'phone': nomer,
                        'phone_type': s['phone_type'], 'email': em, 'source_url': url, 'source': source, 'is_tech': rk['teh'],
                        'chuzhoy_istochnik': chuzhoy or None, 'sprosit_u_priemnoy': None})
# люди: не дублировать тех, кто уже есть у компании (тот же человек – тот же номер или без номера)
est_lyudi = {(p['inn'], cat._kl_fio(p['person']), kl(p['phone'] or '')[0]) for ps in lyudi_est.values() for p in ps if p.get('person')}
est_fio = {(p['inn'], cat._kl_fio(p['person'])) for ps in lyudi_est.values() for p in ps if p.get('person')}
novye_p2, vidali = [], set()
for p in novye_p:
    kk = (p['inn'], cat._kl_fio(p['person']), kl(p['phone'] or '')[0])
    if kk in est_lyudi or kk in vidali or (not p['phone'] and (p['inn'], cat._kl_fio(p['person'])) in est_fio):
        continue
    vidali.add(kk)
    novye_p2.append(p)
novye_p = novye_p2
# почты в карточку компании: к уже записанным (company.pochta) – новые адреса с пометкой
pochta_izm = {}
for inn, spis in pochty.items():
    bylo = kat[inn].get('pochta') or ''
    est = {e.lower() for e in re.findall(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', bylo)}
    dob = []
    for em, pom, lpr in spis:
        if em in est:
            continue
        est.add(em)
        dob.append('%s (%sMEYER-7%s)' % (em, 'ЛПР: ' if lpr else '', (': ' + pom) if pom else ''))
    if dob:
        pochta_izm[inn] = {'bylo': bylo or None, 'stalo': ', '.join(v for v in [bylo] + dob if v)[:4000], 'dobavleno': len(dob),
                           'lpr': sum(1 for d_ in dob if d_.split(' (', 1)[1].startswith('ЛПР'))}
n_lpr = sum(1 for s in novye_k if s['_lpr'] and not s['chuzhoy_istochnik'])
n_lpr_mob = sum(1 for s in novye_k if s['_lpr'] and not s['chuzhoy_istochnik'] and s['vid_nomera'] == 'мобильный')
n_chuzh = sum(1 for s in novye_k if s['chuzhoy_istochnik'])
print('новых номеров %d (ЛПР %d, ЛПР с мобильным %d; с меткой чужого/группы %d) у %d компаний; дописано ФИО/должность у %d наших; '
      'людей %d; почт новых %d (из них ЛПР %d) у %d компаний; пропущено %s' % (
          len(novye_k), n_lpr, n_lpr_mob, n_chuzh, len({s['inn'] for s in novye_k}), len(dopisano), len(novye_p),
          sum(v['dobavleno'] for v in pochta_izm.values()), sum(v['lpr'] for v in pochta_izm.values()), len(pochta_izm), dict(propushcheno)))

# ====================================================================== 2. ЗАПИСЬ В КОПИЮ И ПЕРЕСЧЁТ
# флаги ЛПР – копия функции загрузчиков fixG/fixH (fixH_zamena.flagi)
def pokaz(cat, v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    d = re.sub(r'\D', '', osn)
    if len(d) == 11 and d[0] == '7':
        osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
    return osn + (' доб. ' + dob if dob else '')


def flagi(cat, items):
    tel = [x for x in items if x['kind'] == 'phone']
    lpr = [x for x in tel if x['lpr']]
    sprosit = [x for x in items if x['kind'] == 'sprosit']
    roli = list(dict.fromkeys(x['rol_vid'] for x in lpr))
    fio_lpr = {cat._kl_fio(x['person']) for x in lpr if x['person']}
    mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
    fio_mob = [x for x in mob if x['person']]
    if lpr:
        l0 = (fio_mob or mob or lpr)[0]
        kr = ' · '.join(v for v in (l0['person'], l0['position'] or l0['rol_vid'], pokaz(cat, l0['value'])) if v)
        if len(lpr) > 1:
            kr += ' (+ ещё %d)' % (len(lpr) - 1)
    elif sprosit:
        s0 = sprosit[0]
        kr = '%s · %s (без номера – спросить у приёмной)' % (s0['person'], s0['position'] or s0['rol_vid'])
    else:
        put_ = [x for x in tel if x['has_role']]
        if put_:
            p0 = put_[0]
            kr = ('ЛПР не найден, через приёмную: %s' if p0['rol_vid'] in ('приёмная', 'общий номер')
                  else 'ЛПР не найден, номер с сайта: %s') % pokaz(cat, p0['value'])
            n_mob = sum(1 for x in tel if x['vid_nomera'] == 'мобильный')
            if n_mob:
                kr += ' (мобильных без ЛПР: %d)' % n_mob
        else:
            kr = 'ЛПР не найден' + (', номера только неличные: %d' % len(tel) if tel else ', номеров нет')
    return {'has_tech': int(any(x['is_tech'] for x in lpr)), 'n_tech': sum(1 for x in lpr if x['is_tech']),
            'has_purchaser': int(any(x['is_purchaser'] for x in lpr)), 'n_purchaser': sum(1 for x in lpr if x['is_purchaser']),
            'lpr_mobilnyy': int(bool(mob)), 'lpr_s_fio': len(fio_lpr), 'lpr_roli': ', '.join(roli), 'lpr_kratko': kr,
            'n_phones': len(tel), 'has_phone': int(bool(tel))}



dannye_do = E2.poschitat_vse(os.path.join(SIM, 'meyer_baza1.db'), cat, sales)
kol_k = {r[1] for r in k.execute('pragma table_info(contact)')}
kol_p = {r[1] for r in k.execute('pragma table_info(person)')}
for s in novye_k:
    rr = {kk: v for kk, v in s.items() if kk in kol_k and not kk.startswith('_')}
    k.execute('INSERT INTO contact (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
for p in novye_p:
    rr = {kk: v for kk, v in p.items() if kk in kol_p}
    k.execute('INSERT INTO person (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
for x in dopisano:
    k.execute('UPDATE contact SET person=?, position=?, source=? WHERE id=?', (x['stalo']['person'], x['stalo']['position'],
                                                                             x['stalo']['source'], x['id']))
for inn, v in pochta_izm.items():
    k.execute('UPDATE company SET pochta=? WHERE inn=?', (v['stalo'], inn))
k.commit()
zatronuty = sorted({s['inn'] for s in novye_k} | {p['inn'] for p in novye_p} | {x['inn'] for x in dopisano})
flagi_izm = {}
for inn in zatronuty:
    c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
    nov = flagi(cat, cat.contacts(inn))
    izm = {p_: v for p_, v in nov.items() if c.get(p_) != v}
    if izm:
        flagi_izm[inn] = {'bylo': {p_: c.get(p_) for p_ in izm}, 'stalo': izm}
        k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % p_ for p_ in izm), list(izm.values()) + [inn])
k.commit()
dannye = E2.poschitat_vse(os.path.join(SIM, 'meyer_baza1.db'), cat, sales)
podnyalis = sorted((i for i in dannye if dannye[i]['tier'] > dannye_do[i]['tier']),
                   key=lambda i: (-(dannye[i]['tier'] - dannye_do[i]['tier']), -dannye[i]['score']))
upali = [i for i in dannye if dannye[i]['tier'] < dannye_do[i]['tier']]
print('ступень поднялась у %d компаний (%s), опустилась у %d %s' % (
    len(podnyalis), dict(collections.Counter('%d→%d' % (E2.STUPEN[dannye_do[i]['tier']], E2.STUPEN[dannye[i]['tier']]) for i in podnyalis)),
    len(upali), [(i, E2.STUPEN[dannye_do[i]['tier']], E2.STUPEN[dannye[i]['tier']]) for i in upali][:10]))

# ====================================================================== 3. ВЫРАВНИВАНИЕ
import numpy as np  # noqa: E402
from scipy.optimize import Bounds, LinearConstraint, milp  # noqa: E402

s_ = sqlite3.connect(os.path.join(SIM, 'centro_sales_meyer1.db'))
vlad = dict(s_.execute('SELECT inn, username FROM company_assignment').fetchall())
zakrep = set()
for t in ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item'):
    try:
        zakrep |= {str(r[0]) for r in s_.execute('SELECT DISTINCT inn FROM %s WHERE inn IS NOT NULL' % t)}
    except sqlite3.OperationalError:
        pass
region = {i: c['region'] for i, c in kat.items()}
naim = {i: c['predpriyatie'] for i, c in kat.items()}
for i in dannye:
    dannye[i]['klient_meyer'] = int(float(kat[i].get('bitrix_klient_meyer') or 0) > 0)
    dannye[i]['v_rabote'] = int(float(kat[i].get('bitrix_v_rabote') or 0) > 0)
assert not [i for i in kat if region[i] == 'Воронежская область'], 'в каталоге есть воронежские'
# новые общие номера: номер MEYER-7 у компании совпал с номером другой компании панели
po_kl = collections.defaultdict(set)
for r in k.execute("SELECT inn, value FROM contact WHERE kind='phone'"):
    kk = kl(r['value'])
    if kk[0]:
        po_kl[kk].add(r['inn'])
obshchie_novye = []
for s in novye_k:
    inns = po_kl.get(kl(s['value']), set())
    if len(inns) > 1:
        obshchie_novye.append({'inns': sorted(inns), 'nazvaniya': [naim[i] for i in sorted(inns)], 'hvost': kl(s['value'])[0][-4:]})
obshchie_novye = list({tuple(o['inns']): o for o in obshchie_novye}.values())
print('новых пар с общими номерами (из MEYER-7): %d %s' % (len(obshchie_novye), [(o['inns'], o['hvost']) for o in obshchie_novye]))
hold = json.load(open(os.path.join(W, 'fixD-holdingi.json'), encoding='utf-8'))
for g in {r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa LIKE 'gG-%'")}:
    hold['gruppy'][g] = {'nazvanie': g}
    for r in k.execute('SELECT inn FROM holding_chlen WHERE gruppa=?', (g,)):
        hold['inn_gruppa'][r[0]] = g
for o in obshchie_novye:
    hold['obshchie_nomera_bez_svyazi'].append({'inns': o['inns'], 'nazvaniya': o['nazvaniya']})
vse = sorted(dannye)
edin, pochemu_ed = E2.edinicy_razdachi(hold, set(vse))
U = sorted(edin)
N = len(vse)
CEL = {p: N // 4 + (1 if n < N % 4 else 0) for n, p in enumerate(PRODAVCY)}
krd = {i for i in vse if region[i] == KRD}
K = len(krd)
dop, konflikty = {}, []
for u in U:
    chl = edin[u]
    mozhno = set(PRODAVCY)
    for i in chl:
        if region[i] in DOM:
            mozhno &= set(DOM[region[i]])
    zak = {vlad[i] for i in chl if i in zakrep}
    if zak:
        dop[u] = sorted(zak)[:1]
        if not set(dop[u]) <= mozhno or len(zak) > 1:
            konflikty.append('группа %s с действиями у %s – остаётся' % (chl, sorted(zak)))
    elif not mozhno:
        raise SystemExit('группе %s по правилу городов некому достаться' % chl)
    else:
        dop[u] = sorted(mozhno)
idx = {}
for u in U:
    for p in dop[u]:
        idx[(u, p)] = len(idx)
nx = len(idx)
cost = np.zeros(nx)
for (u, p), j in idx.items():
    cost[j] = sum(1 for i in edin[u] if vlad[i] != p)
# обязательные: ступени, «ЛПР с мобильным всего», пороги выручки (медиана), средний балл; Битрикс и клиенты СЦ –
# в более широком коридоре («сколько получится»)
OSN = {'t4', 't3', 't2', 't1', 'lpr_mob_vse'}
metriki = [(kl_, f) for kl_, _, f in E2.POKAZATELI if kl_ not in ('lpr_mob_vse', 't0')]
metriki.append(('lpr_mob_vse', lambda r: int(r['tier'] in (3, 4))))
metriki.append(('klient_meyer', lambda r: r['klient_meyer']))
metriki.append(('v_rabote', lambda r: r['v_rabote']))
vy = sorted(dannye[i]['vyr'] for i in vse if dannye[i]['vyr'])
porogi = [vy[int(len(vy) * q)] for q in (0.25, 0.4, 0.46, 0.48, 0.5, 0.52, 0.54, 0.6, 0.75)]
metriki.append(('vyr_net', lambda r: int(not r['vyr'])))
for n_t, t in enumerate(porogi):
    metriki.append(('vyr_nizhe%d' % n_t, (lambda tt: (lambda r: int(bool(r['vyr']) and r['vyr'] < tt)))(t)))


def polosa(tot, w):
    if w <= 1:
        return tot // 4, -(-tot // 4)
    lo = -(-tot // 4) - (w // 2)
    return lo, lo + w


def reshit(zapas_stup, zapas_proch, koridor):
    A, lo, hi = [], [], []
    for u in U:
        row = np.zeros(nx)
        for p in dop[u]:
            row[idx[(u, p)]] = 1
        A.append(row); lo.append(1); hi.append(1)
    for p in PRODAVCY:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = len(edin[u])
        A.append(row); lo.append(CEL[p]); hi.append(CEL[p])
    for p in DOM[KRD]:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = sum(1 for i in edin[u] if i in krd)
        A.append(row); lo.append(K // 2); hi.append(-(-K // 2))
    for kl_, f in metriki:
        tot = sum(f(dannye[i]) for i in vse)
        a, b = polosa(tot, zapas_stup if kl_ in OSN else zapas_proch)
        for p in PRODAVCY:
            row = np.zeros(nx)
            for u in U:
                if (u, p) in idx:
                    row[idx[(u, p)]] = sum(f(dannye[i]) for i in edin[u])
            A.append(row); lo.append(a); hi.append(b)
    sr = sum(dannye[i]['score'] for i in vse) / N
    for p in PRODAVCY:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = sum(dannye[i]['score'] for i in edin[u])
        A.append(row); lo.append((sr - koridor) * CEL[p]); hi.append((sr + koridor) * CEL[p])
    return milp(cost, constraints=LinearConstraint(np.array(A), lo, hi), integrality=np.ones(nx),
                bounds=Bounds(0, 1), options={'time_limit': 240})


VARIANTY = [(1, 1, 2), (1, 2, 3), (1, 3, 3), (2, 2, 3), (2, 3, 5)]
reshennye = []
for zs, zp, kor in VARIANTY:
    res = reshit(zs, zp, kor)
    ok_ = res.x is not None and res.status in (0, 1)
    print('MILP: разница ступеней <=%d, прочих <=%d, средний балл ±%d: %s, перемещений %s' % (
        zs, zp, kor, res.message[:40], round(res.fun) if ok_ else '–'))
    if ok_:
        reshennye.append((round(res.fun), VARIANTY.index((zs, zp, kor)), res, zs, zp, kor))
if not reshennye:
    raise SystemExit('раскладка не найдена')
mn = min(x[0] for x in reshennye)
_, _, res, zs, zp, kor = min((x for x in reshennye if x[0] <= mn + 3), key=lambda x: x[1])
print('выбран вариант: ступени <=%d, прочие <=%d, балл ±%d (минимум перемещений среди вариантов – %d)' % (zs, zp, kor, mn))
novoe = {}
for (u, p), j in idx.items():
    if res.x[j] > 0.5:
        for i in edin[u]:
            novoe[i] = p
for u in U:
    assert len({novoe[i] for i in edin[u]}) == 1, edin[u]
peremeshcheniya = []
for i in vse:
    if novoe[i] != vlad[i]:
        u = next(uu for uu in U if i in edin[uu])
        prich = 'выравнивание качества очередей после усиления контактами MEYER-7 (13.10)'
        if len(edin[u]) > 1:
            prich += '; группа целиком: ' + '; '.join(sorted(pochemu_ed.get(i, [])))[:200]
        peremeshcheniya.append({'inn': i, 'nazvanie': naim[i], 'region': region[i], 'ot': vlad[i], 'komu': novoe[i],
                                'prichina': prich, 'stupen': E2.STUPEN[dannye[i]['tier']], 'ball': dannye[i]['score'],
                                'vyruchka_mln': round((dannye[i]['vyr'] or 0) / 1e6)})
t_do, _ = E2.tablica(vlad, dannye_do, 'ДО (сейчас)')
t_us, _ = E2.tablica(vlad, dannye, 'ПОСЛЕ УСИЛЕНИЯ, до выравнивания')
t_po, _ = E2.tablica(novoe, dannye, 'ПОСЛЕ ВЫРАВНИВАНИЯ')
print(t_do)
print(t_us)
print(t_po)
for kl_ in ('klient_meyer', 'v_rabote'):
    print('%s: после выравнивания %s' % (kl_, [sum(dannye[i][kl_] for i in vse if novoe[i] == p) for p in PRODAVCY]))
pot = collections.Counter((m['ot'], m['komu']) for m in peremeshcheniya)
print('перемещений %d: %s' % (len(peremeshcheniya), {'%s→%s' % (FIO[a], FIO[b]): n for (a, b), n in sorted(pot.items())}))
reg_po = {r: dict(collections.Counter(FIO[novoe[i]] for i in vse if region[i] == r)) for r in DOM}
print('домашние регионы после: %s' % reg_po)
if konflikty:
    print('КОНФЛИКТЫ: %s' % konflikty)
primery = [{'inn': i, 'nazvanie': naim[i], 'bylo': E2.STUPEN[dannye_do[i]['tier']], 'stalo': E2.STUPEN[dannye[i]['tier']],
            'lpr_kratko': (flagi_izm.get(i) or {}).get('stalo', {}).get('lpr_kratko') or kat[i].get('lpr_kratko')} for i in podnyalis]
plan = {'vremya': time.strftime('%Y%m%d-%H%M%S'), 'cel': CEL, 'dom': DOM,
        'kontakty': [{kk: v for kk, v in s.items() if not kk.startswith('_')} for s in novye_k],
        'lyudi': novye_p, 'dopisano': dopisano, 'pochta': pochta_izm, 'flagi': flagi_izm,
        'itogi_usileniya': {'kompaniy_v_m7': len(obshchie_m7), 'strok_m7': len(m7['C']), 'novyh_nomerov': len(novye_k),
                            'lpr': n_lpr, 'lpr_mob': n_lpr_mob, 'chuzhoy_ili_gruppa': n_chuzh,
                            'chuzhoy': sum(1 for s in novye_k if (s['chuzhoy_istochnik'] or '').startswith('с сайта другого')),
                            'gruppa': sum(1 for s in novye_k if (s['chuzhoy_istochnik'] or '').startswith('с сайта группы')),
                            'kompaniy_s_novymi': len({s['inn'] for s in novye_k}), 'dopisano': len(dopisano), 'lyudey': len(novye_p),
                            'pochty': sum(v['dobavleno'] for v in pochta_izm.values()),
                            'pochty_lpr': sum(v['lpr'] for v in pochta_izm.values()), 'propushcheno': dict(propushcheno)},
        'stupeni': {i: {'tier': dannye[i]['tier'], 'score': dannye[i]['score'], 'tier_do': dannye_do[i]['tier']} for i in vse},
        'podnyalis': primery, 'upali': upali,
        'peremeshcheniya': peremeshcheniya, 'obshchie_novye': obshchie_novye, 'konflikty': konflikty,
        'krasnodar_inn': sorted(krd), 'regiony_posle': reg_po,
        'milp': {'zapas_stupeney': zs, 'zapas_prochih': zp, 'koridor_balla': kor, 'peremeshcheniy': len(peremeshcheniya), 'minimum': mn},
        'tablica_do': t_do, 'tablica_usilenie': t_us, 'tablica_posle': t_po}
io.open(OUT, 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=1))
print('план: %s' % OUT)
