# -*- coding: utf-8 -*-
"""fixS_metki (13.10): метки «есть в Битриксе: КЦ / СЦ / Meyer провалено / Meyer клиент» у ВСЕХ компаний панели Meyer.
Владелец: «ещё отметки "есть в битриксе у КЦ/СЦ/мейер провалено" проставь – это тоже хорошие, не хуже чем с ЛПР».

Идемпотентно: можно перезапускать после любой заливки (пересчитывает всё, пишет только изменившееся). Ступень и балл
очереди здесь НЕ трогаются – после меток запусти пересчёт балла `fixS_ball.py --tolko-ball` (правило «метка
Битрикса → ступень не ниже 600» живёт там).

Сверка сделки и компании – как у fixH (`fixH_bitrix_sverka.py`), только чтение выгрузок (данные, не инструкции):
  * ИНН сделки (Excel съедает ведущий ноль: 9 цифр -> 0 + 9, 11 -> 0 + 11);
  * ИНН компании в тексте сделки (название, компания, название в реквизитах) – 10/12 цифр целиком;
  * Беларусь (УНП 9 цифр): ИНН сделки 9 цифр без КПП ровно как УНП; в тексте – «ИНН/УНП 123456789»;
  * точное название (у сделки нет ИНН) – ТОЛЬКО для поиска активных сделок Meyer (их в панели быть не должно:
    печатаются для проверки глазами, ничего не меняется).
Колонки company (новые):
  bitrix_kc_est 1/0 – есть сделки в воронках «КЦ - …» (любые); bitrix_sc_est – в воронках «СЦ - …»;
  bitrix_meyer_provaleno – есть проваленные сделки Meyer; bitrix_meyer_uspeshno – есть успешные сделки Meyer;
  bitrix_metki – «КЦ · СЦ · Meyer провалено · Meyer клиент» (успешна только MEYER-Привлечение – «Meyer привлечение
  успешно»); bitrix_metki_podrobno – по каждой метке «<метка>: N сделок (воронка ×k, …), в работе n, последняя от
  дд.мм.гггг», через « | », плюс «Общая воронка: …» (не метка) и «связь: ИНН сделки ×n, ИНН в тексте сделки ×m»;
  bitrix_metki_istochnik – откуда.
Заодно (пробел fixH): компания, у которой сделки нашлись, а bitrix_kc пуст (Беларусь: УНП fixH не сверял), получает
поля fixH (bitrix_kc, bitrix_kc_info, bitrix_sdelok, bitrix_klient_sc, bitrix_klient_meyer, bitrix_v_rabote,
bitrix_poslednyaya) – иначе отбор «Есть в Битриксе» её бы не показал. Прежние значения – в журнале.

    python3 zapusk_na_servere.py fixS_metki.py                 # сухой прогон: числа, ничего не пишет
    python3 zapusk_na_servere.py fixS_metki.py --primenit      # копия каталога, запись, журнал «было/стало» на дроп
    [--zip <путь к zip с meyer_all.csv и kc_sc_all.csv>]  (по умолчанию – дроп fixS-bitrix-0910.zip)
    [--metka "выгрузка Битрикса 09.10"]
"""
import collections
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
import zipfile

KOREN = os.environ.get('FIXS_KOREN', r'C:\centro2')              # FIXS_* – только для локальной пробы на копиях
KAT = os.environ.get('FIXS_KAT', os.path.join(KOREN, 'data', 'meyer_baza1.db'))
SALES = os.environ.get('FIXS_SALES', os.path.join(KOREN, 'data', 'centro_sales_meyer1.db'))
DROP = os.environ.get('FIXS_DROP', r'C:\seostat\drop\drop-storage')
ZIP = os.path.join(DROP, 'fixS-bitrix-0910.zip')
METKA = 'выгрузка Битрикса 09.10'
if '--zip' in sys.argv:
    ZIP = sys.argv[sys.argv.index('--zip') + 1]
if '--metka' in sys.argv:
    METKA = sys.argv[sys.argv.index('--metka') + 1]
PRIMENIT = '--primenit' in sys.argv
VREMYA = time.strftime('%Y%m%d-%H%M%S')

NOVYE = [('bitrix_kc_est', 'INTEGER'), ('bitrix_sc_est', 'INTEGER'), ('bitrix_meyer_provaleno', 'INTEGER'),
         ('bitrix_meyer_uspeshno', 'INTEGER'), ('bitrix_metki', 'TEXT'), ('bitrix_metki_podrobno', 'TEXT'),
         ('bitrix_metki_istochnik', 'TEXT')]
FIXH = ['bitrix_kc', 'bitrix_kc_info', 'bitrix_sdelok', 'bitrix_klient_sc', 'bitrix_klient_meyer', 'bitrix_v_rabote',
        'bitrix_poslednyaya']
METKI = ['КЦ', 'СЦ', 'Meyer провалено', 'Meyer клиент', 'Meyer привлечение успешно']


# ---------------------------------------------------------------- выгрузки
def chitat_zip(put):
    out = []
    with zipfile.ZipFile(put) as z:
        for imya in z.namelist():
            if not imya.lower().endswith('.csv'):
                continue
            ist = 'meyer' if 'meyer' in os.path.basename(imya).lower() else 'kcsc'
            with io.TextIOWrapper(z.open(imya), encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f, delimiter=';'):
                    r = {k: (v or '').strip() for k, v in r.items() if k}
                    r['_ist'] = ist
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
    return re.sub(r'[^0-9a-zа-яё]+', ' ', core.lower().replace('ё', 'е')).strip()


def otlichitelnoe(core):
    slova = core.split()
    return bool(slova) and len(core.replace(' ', '')) >= 6 and not all(w in OBSHCHIE for w in slova)


def data_dmy(iso):
    return '%s.%s.%s' % (iso[8:10], iso[5:7], iso[:4]) if iso else ''


def mn(n, a, b, c):
    n100, n10 = n % 100, n % 10
    return a if (n10 == 1 and n100 != 11) else b if (2 <= n10 <= 4 and not 12 <= n100 <= 14) else c


def daty(sd):
    d = [s['DATE_CREATE'][:10] for s in sd if re.match(r'\d{4}-\d\d-\d\d', s.get('DATE_CREATE') or '')]
    return max(d) if d else ''


def opisat(nazv, sd, slova=('сделка', 'сделки', 'сделок'), voronki=True):
    """«КЦ: 5 сделок (КЦ - Постпродажа ×3, …), в работе 1, последняя от 12.03.2025»."""
    v = collections.Counter(s['ВОРОНКА'] for s in sd)
    n = len(sd)
    t = '%s: %d %s' % (nazv, n, mn(n, *slova))
    if voronki:
        t += ' (%s)' % ', '.join('%s ×%d' % (k, m) for k, m in sorted(v.items(), key=lambda p: (-p[1], p[0])))
    akt = sum(1 for s in sd if s['АКТИВНА'] == 'да')
    if akt:
        t += ', в работе %d' % akt
    d = daty(sd)
    if d:
        t += ', последняя от %s' % data_dmy(d)
    return t


def polya_fixh(sd):
    """Поля fixH по списку сделок компании (копия fixH_bitrix_sverka.polya)."""
    v = collections.Counter(s['ВОРОНКА'] for s in sd)
    info = 'сделок %d: %s' % (len(sd), ', '.join('%s ×%d' % (k, n) for k, n in sorted(v.items(), key=lambda p: (-p[1], p[0]))))
    sc = int(any(re.match(r'СЦ\s*[-–—]', s['ВОРОНКА']) for s in sd))
    meyer_klient = int(any((s['ВОРОНКА'] in ('MEYER-Продажа', 'MEYER-Постпродажа') and s['СТАТУС'] == 'Успешна')
                           or re.match(r'MEYER[- ]СЦ', s['ВОРОНКА']) for s in sd))
    v_rabote = sum(1 for s in sd if s['_ist'] == 'kcsc' and s['АКТИВНА'] == 'да')
    posl = daty(sd)
    return {'bitrix_kc': 1, 'bitrix_kc_info': info, 'bitrix_sdelok': len(sd), 'bitrix_klient_sc': sc,
            'bitrix_klient_meyer': meyer_klient, 'bitrix_v_rabote': v_rabote,
            'bitrix_poslednyaya': data_dmy(posl) or None}


def kratko(s, kak):
    return {'id': s['DEAL_ID'], 'ist': s['_ist'], 'voronka': s['ВОРОНКА'], 'stadiya': s['СТАДИЯ'], 'status': s['СТАТУС'],
            'aktivna': s['АКТИВНА'], 'data': s['DATE_CREATE'][:10], 'kompaniya': s['КОМПАНИЯ'][:100], 'inn': s['INN'], 'kak': kak}


# ---------------------------------------------------------------- индекс сделок
sdelki = chitat_zip(ZIP)
print('выгрузка %s: сделок Meyer %d, КЦ/СЦ %d' % (os.path.basename(ZIP), sum(1 for s in sdelki if s['_ist'] == 'meyer'),
                                                  sum(1 for s in sdelki if s['_ist'] == 'kcsc')))
if not any(s['_ist'] == 'meyer' for s in sdelki) or not any(s['_ist'] == 'kcsc' for s in sdelki):
    raise SystemExit('в zip нет одной из выгрузок (Meyer или КЦ/СЦ) – ничего не делаю')
po_inn = collections.defaultdict(list)
po_tekstu = collections.defaultdict(list)
po_unp = collections.defaultdict(list)
po_unp_tekst = collections.defaultdict(list)
bez_inn_po_imeni = collections.defaultdict(list)
for s in sdelki:
    i = inn_norm(s['INN'])
    if i:
        po_inn[i].append(s)
    syroy = re.sub(r'\D', '', s['INN'])
    if len(syroy) == 9 and not s.get('KPP'):
        po_unp[syroy].append(s)
    for t in (s['TITLE'], s['КОМПАНИЯ'], s['НАЗВАНИЕ_В_РЕКВИЗИТАХ']):
        for x in set(re.findall(r'(?<!\d)(\d{12}|\d{10})(?!\d)', t)):
            po_tekstu[x].append(s)
        for x in set(re.findall(r'(?:ИНН|УНП)\D{0,4}(\d{9})(?!\d)', t, re.I)):
            po_unp_tekst[x].append(s)
    if not i and not syroy:
        for t in (s['КОМПАНИЯ'], s['НАЗВАНИЕ_В_РЕКВИЗИТАХ']):
            c = yadro(t)
            if otlichitelnoe(c):
                bez_inn_po_imeni[c].append(s)


def sdelki_kompanii(inn):
    """-> [(сделка, как найдена)] без повторов; ИНН сделки главнее текста."""
    if len(inn) == 9:
        pryamo = [(s, 'УНП сделки') for s in po_unp.get(inn, [])]
        tekst = [(s, 'УНП в тексте сделки') for s in po_unp_tekst.get(inn, []) if re.sub(r'\D', '', s['INN']) != inn]
    else:
        pryamo = [(s, 'ИНН сделки') for s in po_inn.get(inn, [])]
        tekst = [(s, 'ИНН в тексте сделки') for s in po_tekstu.get(inn, []) if inn_norm(s['INN']) != inn]
    out = {}
    for s, kak in pryamo + tekst:
        out.setdefault(s['_ist'] + s['DEAL_ID'], (s, kak))
    return list(out.values())


def metki_kompanii(inn, naim):
    para = sdelki_kompanii(inn)
    sd = [s for s, _ in para]
    kc = [s for s in sd if s['_ist'] == 'kcsc' and re.match(r'КЦ\s*[-–—]', s['ВОРОНКА'])]
    sc = [s for s in sd if s['_ist'] == 'kcsc' and re.match(r'СЦ\s*[-–—]', s['ВОРОНКА'])]
    prochie = [s for s in sd if s['_ist'] == 'kcsc' and s not in kc and s not in sc]
    mey = [s for s in sd if s['_ist'] == 'meyer']
    prov = [s for s in mey if s['СТАТУС'] == 'Провалена']
    usp = [s for s in mey if s['СТАТУС'] == 'Успешна']
    usp_klient = [s for s in usp if s['ВОРОНКА'] != 'MEYER-Привлечение']
    metki, podr = [], []
    if kc:
        metki.append('КЦ')
        podr.append(opisat('КЦ', kc))
    if sc:
        metki.append('СЦ')
        podr.append(opisat('СЦ', sc))
    if prov:
        metki.append('Meyer провалено')
        podr.append(opisat('Meyer провалено', prov))
    if usp:
        nz = 'Meyer клиент' if usp_klient else 'Meyer привлечение успешно'
        metki.append(nz)
        podr.append(opisat(nz, usp, ('успешная сделка', 'успешные сделки', 'успешных сделок')))
    if prochie:
        for vor, gr in sorted(collections.Counter(s['ВОРОНКА'] for s in prochie).items()):
            podr.append(opisat(vor or 'без воронки', [s for s in prochie if s['ВОРОНКА'] == vor], voronki=False) + ' (не метка)')
    akt_m = [s for s in mey if s['АКТИВНА'] == 'да']
    if akt_m:
        podr.append(opisat('Meyer в работе', akt_m))
    if para:
        kak = collections.Counter(k for _, k in para)
        podr.append('связь: ' + ', '.join('%s ×%d' % (k, n) for k, n in kak.most_common()))
    z = {'bitrix_kc_est': int(bool(kc)), 'bitrix_sc_est': int(bool(sc)), 'bitrix_meyer_provaleno': int(bool(prov)),
         'bitrix_meyer_uspeshno': int(bool(usp)), 'bitrix_metki': ' · '.join(metki) or None,
         'bitrix_metki_podrobno': ' | '.join(podr) or None,
         'bitrix_metki_istochnik': ('%s (fixS)' % METKA) if para else None}
    # активные сделки Meyer – ИНН/УНП/текст, и по точному названию у сделок без ИНН
    akt = [kratko(s, k) for s, k in para if s['_ist'] == 'meyer' and s['АКТИВНА'] == 'да']
    po_imeni = []
    c = yadro(naim)
    if otlichitelnoe(c):
        po_imeni = [kratko(s, 'точное название (у сделки нет ИНН)') for s in bez_inn_po_imeni.get(c, [])
                    if s['_ist'] == 'meyer' and s['АКТИВНА'] == 'да']
    return z, sd, akt, po_imeni


# ---------------------------------------------------------------- каталог и назначения (чтение)
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
komp = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
k.close()
s_ = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
s_.row_factory = sqlite3.Row
nazn = {r['inn']: dict(r) for r in s_.execute('SELECT * FROM company_assignment')}
s_.close()

novoe, zhurnal, aktivnye, po_imeni_vse, probely, rashozhdeniya = {}, {}, [], [], [], []
for inn, c in komp.items():
    z, sd, akt, pim = metki_kompanii(str(inn), c.get('predpriyatie') or '')
    if akt:
        aktivnye.append((inn, c.get('predpriyatie'), akt))
    if pim:
        po_imeni_vse.append((inn, c.get('predpriyatie'), c.get('region'), pim))
    bylo_kc = str(c.get('bitrix_kc') or '') not in ('', '0', '0.0', 'None')
    if sd and not bylo_kc:
        z.update(polya_fixh(sd))
        probely.append(inn)
    elif bylo_kc and not sd:
        rashozhdeniya.append((inn, 'bitrix_kc=1, а сделок по ИНН/тексту нет'))
    elif sd and int(float(c.get('bitrix_sdelok') or 0)) != len(sd):
        rashozhdeniya.append((inn, 'сделок fixH %s, сейчас %d' % (c.get('bitrix_sdelok'), len(sd))))
    novoe[inn] = z
    izm = {p: [c.get(p), v] for p, v in z.items() if c.get(p) != v}
    if izm:
        zhurnal[inn] = izm

# ---------------------------------------------------------------- отчёт
PROD = sorted({a['username'] for a in nazn.values()})
STUP = {4: 800, 3: 600, 2: 400, 1: 200, 0: 0}
str_ = []


def pech(t=''):
    str_.append(t)
    print(t)


pech('компаний в каталоге %d, назначений %d' % (len(komp), len(nazn)))
est = lambda z: any(z[p] for p in ('bitrix_kc_est', 'bitrix_sc_est', 'bitrix_meyer_provaleno', 'bitrix_meyer_uspeshno'))  # noqa: E731
sch = collections.defaultdict(collections.Counter)
primery = collections.defaultdict(list)
for inn, z in novoe.items():
    u = (nazn.get(inn) or {}).get('username') or '—'
    for m in METKI:
        if z['bitrix_metki'] and m in z['bitrix_metki'].split(' · '):
            sch[u][m] += 1
            sch['ВСЕГО'][m] += 1
            if len(primery[m]) < 5:
                primery[m].append(inn)
    if est(z):
        sch[u]['любая метка'] += 1
        sch['ВСЕГО']['любая метка'] += 1
        st = (nazn.get(inn) or {}).get('stupen_ocheredi')
        if st in (1, 2):
            sch[u]['поднимется %d → 600' % STUP[st]] += 1
            sch['ВСЕГО']['поднимется %d → 600' % STUP[st]] += 1
            if len(primery['подъём %d' % STUP[st]]) < 5:
                primery['подъём %d' % STUP[st]].append(inn)
        elif st is not None:
            sch[u]['уже %d' % STUP.get(st, st)] += 1
            sch['ВСЕГО']['уже %d' % STUP.get(st, st)] += 1
kolonki = METKI + ['любая метка', 'поднимется 200 → 600', 'поднимется 400 → 600', 'уже 600', 'уже 800', 'уже 0']
pech('менеджер;' + ';'.join(kolonki))
for u in PROD + ['ВСЕГО']:
    pech('%s;%s' % (u, ';'.join(str(sch[u][kk]) for kk in kolonki)))
pech('примеры ИНН: %s' % json.dumps(primery, ensure_ascii=False))
pech('активных сделок Meyer по ИНН/УНП/тексту: %d %s' % (len(aktivnye), [(i, n, len(a)) for i, n, a in aktivnye]))
for i, n, r, p in po_imeni_vse:
    pech('  ПРОВЕРИТЬ ГЛАЗАМИ (активная Meyer по точному названию, у сделки нет ИНН): %s «%s» (%s): %s' % (
        i, n, r, [(x['id'], x['voronka'], x['stadiya'], x['data'], x['kompaniya']) for x in p]))
pech('пробел fixH (сделки есть, bitrix_kc пуст) – заполняю поля fixH: %d %s' % (
    len(probely), [(i, komp[i].get('predpriyatie')) for i in probely]))
pech('расхождения с полями fixH (не меняю): %d %s' % (len(rashozhdeniya), rashozhdeniya[:15]))
pech('компаний с изменениями: %d' % len(zhurnal))
pech('из них меняется bitrix_metki: %d' % sum(1 for i in zhurnal if 'bitrix_metki' in zhurnal[i]))

if not PRIMENIT:
    pech('СУХОЙ ПРОГОН: ничего не записано (запись – с --primenit)')
    raise SystemExit(0)

# ---------------------------------------------------------------- запись
BEKAP = os.path.join(KOREN, '_bekap', 'fixS-metki-' + VREMYA)
os.makedirs(BEKAP, exist_ok=True)
src = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
dst = sqlite3.connect(os.path.join(BEKAP, 'meyer_baza1.db'))
src.backup(dst)
dst.close()
src.close()
pech('копия каталога (НЕ для отката целиком): %s' % BEKAP)
k = sqlite3.connect(KAT, timeout=30)
k.execute('PRAGMA busy_timeout=30000')
kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
for imya, tip in NOVYE:
    if imya not in kol:
        k.execute('ALTER TABLE company ADD COLUMN %s %s' % (imya, tip))
        pech('добавлена колонка company.%s' % imya)
k.commit()
for popytka in range(10):
    try:
        k.execute('BEGIN IMMEDIATE')
        break
    except sqlite3.OperationalError:
        time.sleep(3)
else:
    raise SystemExit('каталог занят')
n = 0
try:
    for inn, izm in zhurnal.items():
        # read-modify-write: сверяем «было» с тем, что в базе сейчас (кто-то мог записать между чтением и записью)
        tek = k.execute('SELECT %s FROM company WHERE inn=?' % ', '.join(izm), (inn,)).fetchone()
        if tek is None:
            continue
        for (p, (bylo, _st)), t in zip(izm.items(), tek):
            if p in kol and t != bylo:
                raise RuntimeError('%s.%s изменилось после чтения (%r → %r) – перезапусти' % (inn, p, bylo, t))
        cur = k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('%s=?' % p for p in izm),
                        [v[1] for v in izm.values()] + [inn])
        n += cur.rowcount
    k.commit()
except BaseException:
    k.rollback()
    raise
finally:
    k.close()
pech('записано компаний: %d' % n)
put_zh = os.path.join(DROP, 'fixS-metki-zhurnal-%s.json' % VREMYA)
io.open(put_zh, 'w', encoding='utf-8').write(json.dumps({'vremya': VREMYA, 'bekap': BEKAP, 'zip': ZIP, 'izmeneniya': zhurnal,
                                                        'aktivnye_meyer': aktivnye, 'po_imeni_proverit': po_imeni_vse},
                                                       ensure_ascii=False, indent=1))
io.open(os.path.join(DROP, 'fixS-metki-itog-%s.txt' % VREMYA), 'w', encoding='utf-8').write('\n'.join(str_))
print('журнал «было/стало»: %s' % put_zh)
