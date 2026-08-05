# -*- coding: utf-8 -*-
"""Что в полном корпусе карточек ещё НЕ разобрано — цель для провайдера.

3-я сессия разобрала корпус правилами (резка текста по меткам ролей) и получила
2900 строк. Гонять провайдера по тем же карточкам — платить второй раз за то же.
Ценность провайдера там, где правило молчит: текст есть, а человека из него не
достали.
"""
import csv, io, json, os, sqlite3
from collections import Counter
ОБМЕН = r'C:\seostat\drop\drop-storage'
кандидаты = [f for f in os.listdir(ОБМЕН) if 'kartochk' in f.lower() and f.endswith('.csv')]
print('файлы карточек на дропе:', кандидаты)
путь = os.path.join(ОБМЕН, 'tp-kartochki-polnye.csv')
if not os.path.exists(путь):
    для = [f for f in кандидаты if 'poln' in f.lower()]
    if для:
        путь = os.path.join(ОБМЕН, для[0])
print('беру:', os.path.basename(путь), os.path.getsize(путь) if os.path.exists(путь) else 'НЕТ')
if not os.path.exists(путь):
    raise SystemExit

цб = sqlite3.connect(r'file:C:\seostat\data\p25.db?mode=ro', uri=True)
наши = {str(и) for и, in цб.execute('SELECT inn FROM company')}
цб.close()

# В КОРПУСЕ НЕТ КОЛОНКИ ИНН — только company_id площадки. Первый прогон отбора
# дал ноль целей именно поэтому: я искал поле, которого в файле нет. Карту
# company_id → ИНН 3-я сессия выложила отдельно, ради этого и выложила.
карта = {}
for имя in ('P25-TP-CID-INN-3S.csv', 'P25-TP-INN-IZ-KARTOCHEK-3S.csv'):
    пк = os.path.join(ОБМЕН, имя)
    if not os.path.exists(пк):
        continue
    for р in csv.DictReader(io.open(пк, encoding='utf-8-sig', errors='replace'),
                            delimiter=';'):
        cid = str(р.get('company_id') or р.get('cid') or '').strip()
        инн_ = ''.join(x for x in str(р.get('inn') or '') if x.isdigit())
        if cid and инн_:
            карта[cid] = инн_
print('карта company_id → ИНН:', len(карта), 'записей')

разобрано = set()
ф3 = os.path.join(ОБМЕН, 'P25-TP-KARTOCHKI-LYUDI-3S.csv')
if os.path.exists(ф3):
    for р in csv.DictReader(io.open(ф3, encoding='utf-8-sig', errors='replace'),
                            delimiter=';'):
        т = str(р.get('tender_id') or '').strip()
        if т:
            разобрано.add(т)
мои = set()
пм = r'C:\seostat\drop\tp_razbor_lyudey.jsonl'
if os.path.exists(пм):
    for s in io.open(пм, encoding='utf-8', errors='replace'):
        try:
            мои.add(str(json.loads(s).get('tender_id')))
        except Exception:
            pass

c = Counter()
цели = []
сыр = io.open(путь, encoding='utf-8-sig', errors='replace')
чтец = csv.DictReader(сыр, delimiter=';')
поля = None
for р in чтец:
    if поля is None:
        поля = list(р.keys())
    инн = ''.join(x for x in str(р.get('inn') or '') if x.isdigit())
    if not инн:
        инн = карта.get(str(р.get('company_id') or '').strip(), '')
    т = str(р.get('tender_id') or р.get('id') or '').strip()
    текст = str(р.get('comment') or р.get('kommentariy') or
                р.get('komment') or р.get('text') or '')
    c['всего карточек'] += 1
    if len(текст) < 40:
        c['текста нет или он короткий'] += 1
        continue
    if инн not in наши:
        c['не наш покупатель P25'] += 1
        continue
    c['НАШ P25 с текстом'] += 1
    if т in разобрано:
        c['   уже разобрана правилом 3-й сессии'] += 1
    elif т in мои:
        c['   уже разобрана моим провайдером'] += 1
    else:
        c['   НИКЕМ не разобрана — цель'] += 1
        цели.append({'inn': инн, 'tender_id': т, 'comment': текст[:6000],
                     'company': str(р.get('company') or р.get('predpriyatie') or ''),
                     'url': str(р.get('url') or ''),
                     'дата': str(р.get('data') or р.get('дата') or ''),
                     'свежесть': str(р.get('svezhest') or '')})
сыр.close()
if цели:
    вых = r'C:\seostat\drop\drop-storage\tp_korpus_celi.json'
    with io.open(вых, 'w', encoding='utf-8') as ф:
        json.dump({'карточки': цели}, ф, ensure_ascii=False)
        ф.flush(); os.fsync(ф.fileno())

print('колонки файла:', поля)
print()
print('=== ЧИСЛА ===')
for к, v in c.items():
    print(f'   {к:44} {v:6}')
