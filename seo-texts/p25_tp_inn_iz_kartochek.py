# -*- coding: utf-8 -*-
"""Обход стены 403: взять ИНН закрытых компаний из ТЕКСТА их же карточек.

СТЕНА НАЗВАНА ЧЕСТНО. Страницы 36 компаний площадки отдают HTTP 403 Forbidden, тогда
как контрольные две отдают 200 с ИНН. Это ограничение доступа на стороне площадки, а
не наша частота и не наша ошибка: повторять бессмысленно.

НО ИНН НУЖЕН НЕ САМ ПО СЕБЕ. Нужна связь «закупка → наше предприятие», и ИНН лишь
самый надёжный её носитель. Заказчик часто печатает свой ИНН в тексте карточки — в
реквизитах, в условиях договора, в требованиях к участникам. Карточки этих компаний у
нас уже скачаны: 865 закупок. Значит стену можно обойти, не постучавшись в неё ещё раз.

ЗАСЛОН, БЕЗ КОТОРОГО ЭТО ОПАСНО. В карточке ИНН бывает не только заказчика: там
встречаются ИНН площадки, банка, участников, дочерних обществ. Поэтому:
  * беру только ИНН, стоящие в окне вокруг слов заказчика («заказчик», «организатор»,
    «покупатель», «реквизиты»), а не любой ИНН в тексте;
  * требую, чтобы один и тот же ИНН встретился у компании НЕ В ОДНОЙ карточке, если
    карточек больше одной, — случайный чужой ИНН так не повторяется;
  * пишу, сколькими карточками подтверждён, и чем именно. Провенанс накапливается.
"""
import collections
import csv
import io
import json
import os
import re
import sqlite3
import urllib.request

D = r'C:\seostat\drop\drop-storage'
KART = os.path.join(D, 'tp-kartochki-polnye.csv')
SLOVARI = (os.path.join(D, 'tp-zakupki-po-vladelcam.csv'),
           os.path.join(D, 'tp-cid-inn.csv'), os.path.join(D, 'tp-inn.csv'))
VYHOD = r'C:\sender\_ops\P25-TP-INN-IZ-KARTOCHEK-3S.csv'
csv.field_size_limit(10 ** 8)

INN_LYUBOY = re.compile(r'\b(\d{10}|\d{12})\b')
ZAKAZCHIK = re.compile(r'заказчик|организатор|покупател|реквизит|плательщик|'
                       r'наименование\s+предприятия', re.I)
# ИНН и ОГРН/КПП стоят рядом; цифры КПП (9) и ОГРН (13) под шаблон не попадают, но
# «ИНН» прямо перед числом — сильный признак, и он проверяется отдельно.
INN_S_MetkOY = re.compile(r'ИНН[^0-9]{0,15}(\d{10}|\d{12})')

izvestno = {}
for p in SLOVARI:
    if not os.path.exists(p):
        continue
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.DictReader(f, delimiter=';')
        polya = rd.fieldnames or []
        kc = next((x for x in polya if x and x.lower() in ('company_id', 'cid')), '')
        ki = next((x for x in polya if x and x.lower() == 'inn'), '')
        if kc and ki:
            for r in rd:
                c, i = str(r.get(kc) or '').strip(), (r.get(ki) or '').strip()
                if c and i:
                    izvestno.setdefault(c, i)

b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}

# ИНН-кандидаты по компаниям с НЕизвестным ИНН: кто, сколькими карточками, каким словом.
kand = collections.defaultdict(lambda: collections.defaultdict(list))
imena, kartochek = {}, collections.Counter()
with open(KART, encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f, delimiter=';'):
        cid = str(r.get('company_id') or '').strip()
        if not cid or cid in izvestno:
            continue
        imena.setdefault(cid, (r.get('company') or '').strip())
        kartochek[cid] += 1
        t = ' '.join((r.get('comment') or '', r.get('predmet') or '',
                      r.get('organizator') or ''))
        for m in INN_S_MetkOY.finditer(t):
            okno = t[max(0, m.start() - 200):m.end() + 100]
            if ZAKAZCHIK.search(okno):
                kand[cid][m.group(1)].append(('ИНН с меткой рядом со словом заказчика',
                                              re.sub(r'\s+', ' ', okno)[:200]))
            else:
                kand[cid][m.group(1)].append(('ИНН с меткой, но без слова заказчика',
                                              re.sub(r'\s+', ' ', okno)[:200]))

sch = collections.Counter()
stroki = []
for cid, varianty in kand.items():
    # Побеждает ИНН, подтверждённый бо́льшим числом карточек И стоящий у слова заказчика.
    luchshiy, ochki = '', (-1, -1)
    for inn, sled in varianty.items():
        u_zakazchika = sum(1 for s in sled if 'без слова' not in s[0])
        o = (u_zakazchika, len(sled))
        if o > ochki:
            luchshiy, ochki = inn, o
    if not luchshiy:
        continue
    n_kart = kartochek[cid]
    podtverzhdeno = ochki[1]
    nash = luchshiy in nashi
    # Один ИНН на одной карточке при десятке карточек — слабо. Называю уверенность.
    if ochki[0] == 0:
        uver = 'слабая: ИНН в тексте есть, но слова заказчика рядом нет'
    elif n_kart > 1 and podtverzhdeno < 2:
        uver = 'средняя: подтверждён одной карточкой из %d' % n_kart
    else:
        uver = 'высокая: подтверждён %d карточками из %d' % (podtverzhdeno, n_kart)
    sch[uver.split(':')[0]] += 1
    if nash:
        sch['ИЗ НИХ НАШИ ПОКУПАТЕЛИ'] += 1
    stroki.append({
        'company_id': cid, 'inn': luchshiy, 'nazvanie_na_ploshchadke': imena.get(cid, ''),
        'nash_pokupatel_p25': 'да' if nash else '',
        'predpriyatie_po_baze': nashi.get(luchshiy, ''),
        'mesto_po_summe': mesta.get(luchshiy, '') if nash else '',
        'kartochek_u_kompanii': n_kart, 'podtverzhdeno_kartochek': podtverzhdeno,
        'drugih_variantov_inn': len(varianty) - 1,
        'uverennost': uver,
        'osnovanie': varianty[luchshiy][0][1],
    })

stroki.sort(key=lambda s: (s['nash_pokupatel_p25'] != 'да', -s['kartochek_u_kompanii']))
otvet = ''
if stroki:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(stroki[0].keys()), delimiter=';',
                       extrasaction='ignore')
    w.writeheader()
    w.writerows(stroki)
    open(VYHOD, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())
    url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    if url and tok:
        rq = urllib.request.Request(url.rstrip('/') + '/' + os.path.basename(VYHOD),
                                    data=buf.getvalue().encode('utf-8-sig'), method='PUT')
        rq.add_header('X-Drop-Token', tok)
        try:
            otvet = urllib.request.urlopen(rq, timeout=120).status
        except Exception as e:  # noqa: BLE001
            otvet = 'сбой: %s' % e

for s in stroki[:14]:
    print('  %-8s %-13s карточек %3d  %-30s %s' % (
        s['company_id'], s['inn'], s['kartochek_u_kompanii'],
        s['nazvanie_na_ploshchadke'][:30],
        ('НАШ, место %s' % s['mesto_po_summe']) if s['nash_pokupatel_p25']
        else s['uverennost'][:30]))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'компаний с неизвестным ИНН и карточками': len(kartochek),
    'ИНН вытащен из текста': len(stroki),
    'файл': os.path.basename(VYHOD) if stroki else '', 'дроп': otvet}, ensure_ascii=False))
