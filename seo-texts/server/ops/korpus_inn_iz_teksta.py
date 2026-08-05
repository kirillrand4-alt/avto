# -*- coding: utf-8 -*-
"""ИНН для корпуса карточек — из текста самих карточек, а не из чужой карты.

ЧТО Я СДЕЛАЛ НЕ ТАК. Час назад объявил корпус (9 021 карточка) заблокированным,
потому что карта `company_id → ИНН` от соседки почти пуста. Но это был ОДИН
путь из нескольких, а «заблокировано» я сказал после первой неудачи.

Путь, который лежал на виду: заказчики сами печатают свои реквизиты в тексте
карточки — «Реквизиты Грузополучателя: ОАО "Невинномысский Азот", ИНН 2631015563».
Соседкин же файл `P25-TP-INN-IZ-KARTOCHEK-3S.csv` этим и построен («подтверждён
4 карточками из 14»), то есть путь проверен, просто я им не воспользовался.

ПРАВИЛО ПРИВЯЗКИ, строгое: ИНН считается принадлежащим компании карточки, если
он встречен в карточках ЭТОГО company_id и НЕ встречается у других company_id.
Один ИНН у двух компаний площадки — признак того, что это ИНН контрагента, а не
заказчика; такие отбрасываю.

Запуск: python korpus_inn_iz_teksta.py [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter, defaultdict

ОБМЕН = r'C:\seostat\drop\drop-storage'
КОРПУС = os.path.join(ОБМЕН, 'tp-kartochki-polnye.csv')
ВЫХОД = os.path.join(ОБМЕН, 'TP-CID-INN-IZ-TEKSTA-1S.csv')
ЦЕЛИ = os.path.join(ОБМЕН, 'tp_korpus_celi.json')
ПРИМЕНИТЬ = '--apply' in sys.argv
_ИНН = re.compile(r'ИНН[\s:№]*([0-9]{10}|[0-9]{12})', re.I)

csv.field_size_limit(10 ** 7)
по_компании = defaultdict(Counter)
имена = {}
карточки = defaultdict(list)
всего = 0
with io.open(КОРПУС, encoding='utf-8-sig', errors='replace') as ф:
    for р in csv.DictReader(ф, delimiter=';'):
        всего += 1
        cid = str(р.get('company_id') or '').strip()
        текст = str(р.get('comment') or '')
        if cid:
            имена[cid] = str(р.get('company') or '')[:70]
            for м in _ИНН.finditer(текст):
                по_компании[cid][м.group(1)] += 1
            карточки[cid].append({'tender_id': str(р.get('tender_id') or ''),
                                  'comment': текст[:6000],
                                  'company': имена[cid],
                                  'organizator': str(р.get('organizator') or '')[:70],
                                  'дата': str(р.get('sozdan') or '')})

# ИНН, встреченный у нескольких company_id, — контрагент, а не заказчик
где_встречен = defaultdict(set)
for cid, счёт in по_компании.items():
    for инн in счёт:
        где_встречен[инн].add(cid)

цб = sqlite3.connect(r'file:C:\seostat\data\p25.db?mode=ro', uri=True)
p25 = {str(и) for и, in цб.execute('SELECT inn FROM company')}
цб.close()
_путь_ц = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
цц = sqlite3.connect('file:' + _путь_ц + '?mode=ro', uri=True)
centro = {str(и) for и, in цц.execute('SELECT inn FROM company')}
цц.close()

c = Counter()
карта = {}
for cid, счёт in по_компании.items():
    свои = {и: n for и, n in счёт.items() if len(где_встречен[и]) == 1}
    if not свои:
        c['ИНН в тексте есть, но все встречаются у разных компаний'] += 1 if счёт else 0
        continue
    инн, n = max(свои.items(), key=lambda x: x[1])
    карта[cid] = {'inn': инн, 'kartochek': n, 'vsego_kartochek': len(карточки[cid]),
                  'nazvanie': имена.get(cid, '')}
    c['company_id привязан к ИНН'] += 1
    if инн in p25:
        c['   и это НАШ покупатель P25'] += 1
    elif инн in centro:
        c['   и это предприятие центробежки'] += 1

цели = []
for cid, з in карта.items():
    if з['inn'] in p25 or з['inn'] in centro:
        for к in карточки[cid]:
            if len(к['comment']) > 40:
                цели.append({**к, 'inn': з['inn'],
                             'свежесть': '', 'url': f"https://www.tender.pro/api/tender/{к['tender_id']}/view_public"})

print('=== ЧИСЛА ===')
print(f'   {"карточек в корпусе":52} {всего:6}')
print(f'   {"различных company_id":52} {len(карточки):6}')
for к, v in sorted(c.items()):
    print(f'   {к:52} {v:6}')
print(f'   {"карточек НАШИХ предприятий с текстом":52} {len(цели):6}')

if not ПРИМЕНИТЬ:
    print('СУХОЙ ПРОГОН')
    raise SystemExit

with io.open(ВЫХОД, 'w', encoding='utf-8-sig', newline='') as ф:
    п = csv.DictWriter(ф, fieldnames=['company_id', 'inn', 'nazvanie', 'kartochek',
                                      'vsego_kartochek'], delimiter=';')
    п.writeheader()
    for cid, з in карта.items():
        п.writerow({'company_id': cid, **з})
    ф.flush(); os.fsync(ф.fileno())
with io.open(ЦЕЛИ, 'w', encoding='utf-8') as ф:
    json.dump({'карточки': цели}, ф, ensure_ascii=False)
    ф.flush(); os.fsync(ф.fileno())
print(f'   карта записана: {os.path.basename(ВЫХОД)}')
print(f'   цели для разбора: {os.path.basename(ЦЕЛИ)}')
