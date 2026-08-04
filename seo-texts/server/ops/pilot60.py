# -*- coding: utf-8 -*-
"""Собрать 60 ТИПОВЫХ (не гигантов) целей для пилота поиска ЛПР.

Владелец одобрил пилот 25 ₽: поиск техруководителя в выдаче по 60 предприятиям.
«Типовые, не гиганты» — потому что у Газпрома/Лукойла главный инженер по
холодному звонку недостижим, а у них же сотни фактов и часто газ. Берём:
  * ВИДИМЫЕ (не скрытые),
  * с приговором есть/покупает/планирует (профиль доказан),
  * БЕЗ техЛПР с телефоном (иначе искать нечего),
  * выручка в среднем поясе (не микро и не гигант) — если поле есть,
  * имя без маркеров гигантов (Газпром, Лукойл, Роснефть, СИБУР, Татнефть…).
Кладём jsonl на дроп с полями inn/predpriyatie/name для запроса в серп.
"""
import json, os, re, sqlite3, sys, urllib.request

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ВЫХОД = 'CELI-PILOT-LPR-60.jsonl'
_ГИГАНТ = re.compile(r'газпром|лукойл|роснефт|сибур|татнефт|новатэк|норникел|'
                     r'северсталь|нлмк|ммк|евраз|мечел|уралкали|фосагро|акрон|'
                     r'россет|русал|сургутнефт|башнефт|салават', re.I)
N = 60


def main():
    пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
    скрыты = {str(r[0]) for r in пр.execute(
        "SELECT inn FROM hidden_item WHERE kind='company'")}
    приг = {str(r[0]): (r[1] or '') for r in пр.execute(
        'SELECT inn, verdikt FROM sud_verdikt')}
    пр.close()

    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    кол = [c[1] for c in цб.execute('PRAGMA table_info(company)')]
    рев = next((k for k in ('revenue_rub', 'revenue', 'vyruchka') if k in кол), None)
    выб = 'SELECT inn, predpriyatie' + (f', {рев}' if рев else ", 0") + ' FROM company'
    компании = {str(r[0]): (r[1] or '', r[2] or 0) for r in цб.execute(выб)}
    # у кого уже есть техЛПР с телефоном — тех не берём
    есть = set()
    for и, тел in цб.execute(
            "SELECT inn, COALESCE(phone,'') FROM person WHERE COALESCE(is_tech,0)=1"):
        if len(re.sub(r'\D', '', str(тел))[-10:]) == 10:
            есть.add(str(и))
    for и, зн, ч in цб.execute(
            "SELECT inn, value, COALESCE(person,'') FROM contact "
            "WHERE kind='phone' AND COALESCE(is_tech,0)=1"):
        if ч and len(re.sub(r'\D', '', str(зн))[-10:]) == 10:
            есть.add(str(и))
    цб.close()

    канд = []
    for и, (назв, рв) in компании.items():
        if и in скрыты or и in есть:
            continue
        if приг.get(и) not in ('есть', 'покупает', 'планирует'):
            continue
        if _ГИГАНТ.search(назв):
            continue
        try:
            рв = float(рв or 0)
        except Exception:
            рв = 0
        # средний пояс: 50 млн – 30 млрд (если выручка известна; 0 = неизвестна, берём)
        if рв and not (5e7 <= рв <= 3e10):
            continue
        канд.append((рв, и, назв))
    # сортируем по выручке ВНУТРИ пояса убыв. — крупные из «типовых» первыми
    канд.sort(key=lambda x: -x[0])
    отбор = канд[:N]
    print(f'кандидатов подходящих: {len(канд)}, берём {len(отбор)}')
    for рв, и, назв in отбор[:12]:
        print(f'  {и} {назв[:46]:46} выручка={int(рв):>14,}')

    строки = [json.dumps({'inn': и, 'predpriyatie': назв, 'name': назв,
                          'verdikt': приг.get(и, '')}, ensure_ascii=False)
              for рв, и, назв in отбор]
    данные = ('\n'.join(строки) + '\n').encode('utf-8')
    п = os.path.join(r'C:\sender\server', ВЫХОД)
    with open(п, 'wb') as ф:
        ф.write(данные); ф.flush(); os.fsync(ф.fileno())
    # и на дроп (серп читает --targets с C:\seostat\drop; кладём туда же)
    for путь in (os.path.join(r'C:\seostat\drop', ВЫХОД),):
        try:
            with open(путь, 'wb') as ф:
                ф.write(данные); ф.flush(); os.fsync(ф.fileno())
            print('локально для серпа:', путь)
        except Exception as e:
            print('не записал локально:', str(e)[:80])
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ВЫХОД, data=данные, method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=120).read()
        print('на дропе:', ВЫХОД, len(отбор), 'целей')
    except Exception as e:
        print('на дроп не ушёл:', str(e)[:80])


if __name__ == '__main__':
    main()
