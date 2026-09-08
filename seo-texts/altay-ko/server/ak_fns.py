# -*- coding: utf-8 -*-
"""Фаза 4. Открытые данные ФНС по ИНН знаменателя: уплаченные налоги (paytax), среднесписочная численность (sshr2019),
доходы/расходы по бухотчётности (revexp). Скачивание с докачкой по Range (файлы 100-220 МБ), разбор XML из zip потоково,
влив в finansy (istochnik fns-paytax / fns-sshr / fns-revexp) и predpriyatiya.ssch. argv: [бюджет]. Печатает ГОТОВО, когда все три набора разобраны."""
import os, sys, re, json, time, sqlite3, zipfile, requests
import xml.etree.ElementTree as ET
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite'); FNS = os.path.join(AK, 'fns'); os.makedirs(FNS, exist_ok=True)
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0'}
NABORY = {
    'paytax': 'https://file.nalog.ru/opendata/7707329152-paytax/data-20260401-structure-20180110.zip',
    'sshr': 'https://file.nalog.ru/opendata/7707329152-sshr2019/data-20260825-structure-20200408.zip',
    'revexp': 'https://file.nalog.ru/opendata/7707329152-revexp/data-20260825-structure-20180110.zip',
}
SOST = os.path.join(FNS, 'sostoyanie.json')
sost = json.load(open(SOST, encoding='utf-8')) if os.path.exists(SOST) else {}
def sohranit(): json.dump(sost, open(SOST, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
def skachat(name, url):
    dest = os.path.join(FNS, name + '.zip')
    h = requests.head(url, headers=UA, timeout=60, verify=False, allow_redirects=True); total = int(h.headers.get('Content-Length') or 0)
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    if total and have >= total: return True
    with open(dest, 'ab') as f:
        while have < total and time.time() - T0 < BUDGET:
            end = min(have + 20 * 1024 * 1024, total) - 1
            r = requests.get(url, headers={**UA, 'Range': f'bytes={have}-{end}'}, timeout=300, verify=False, stream=True)
            if r.status_code not in (200, 206): time.sleep(5); continue
            for chunk in r.iter_content(1 << 20):
                f.write(chunk); have += len(chunk)
            f.flush()
    print(f'{name}: скачано {have // 2**20} / {total // 2**20} МБ', flush=True)
    return have >= total
c = sqlite3.connect(DB, timeout=120)
nashi = {r[0] for r in c.execute('select inn from predpriyatiya')}
def razobrat(name):
    dest = os.path.join(FNS, name + '.zip'); n = 0
    try: z = zipfile.ZipFile(dest)
    except zipfile.BadZipFile:
        print(name, 'битый zip - перекачка'); os.remove(dest); return False
    for zi in z.infolist():
        if not zi.filename.lower().endswith('.xml'): continue
        with z.open(zi) as fh:
            for ev, el in ET.iterparse(fh, events=('end',)):
                if not el.tag.endswith('Документ'): continue
                inn = None
                for ch in el:
                    if 'СведНП' in ch.tag: inn = ch.get('ИННЮЛ') or ch.get('ИННФЛ')
                if inn in nashi:
                    god = (el.get('ДатаСост') or el.get('ДатаДок') or '')[-4:]
                    if name == 'paytax':
                        summa = 0.0
                        for ch in el:
                            if 'Нал' in ch.tag:
                                for k, v in ch.attrib.items():
                                    if k.startswith('Сум'): summa += float(v or 0)
                        c.execute('insert or replace into finansy values(?,?,?,?,?,?,?,?)', (inn, 'fns-paytax', god, None, None, summa, None, TS)); n += 1
                    elif name == 'sshr':
                        ssch = None
                        for ch in el:
                            if 'ССЧ' in ch.tag: ssch = int(float(ch.get('КолРаб') or 0))
                        if ssch: c.execute('insert or replace into finansy values(?,?,?,?,?,?,?,?)', (inn, 'fns-sshr', god, None, None, None, ssch, TS)); c.execute('update predpriyatiya set ssch=coalesce(ssch,?) where inn=?', (ssch, inn)); n += 1
                    elif name == 'revexp':
                        doh = rash = None
                        for ch in el:
                            if 'ДохРасх' in ch.tag: doh = float(ch.get('СумДоход') or 0); rash = float(ch.get('СумРасход') or 0)
                        if doh: c.execute('insert or replace into finansy values(?,?,?,?,?,?,?,?)', (inn, 'fns-revexp', god, doh, (doh - rash) if rash is not None else None, None, None, TS)); n += 1
                el.clear()
        c.commit()
    print(f'{name}: строк по нашим ИНН {n}', flush=True)
    return True
for name, url in NABORY.items():
    if sost.get(name) == 'razobrano': continue
    if time.time() - T0 > BUDGET: break
    if not skachat(name, url): continue
    if time.time() - T0 > BUDGET - 200: break
    if razobrat(name): sost[name] = 'razobrano'; sohranit()
c.close()
print('состояние:', sost, flush=True)
if all(sost.get(n) == 'razobrano' for n in NABORY): print('ГОТОВО')
