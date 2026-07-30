# -*- coding: utf-8 -*-
"""Тип машины по ПОЛНОМУ тексту карточки, а не по названию закупки.

Обе соседние сессии пришли к тому, что людей надо делить по типу машины, и
обе уперлись в одно: у большинства закупок тип в НАЗВАНИИ не указан. У третьей
сессии таких 207 строк, у меня 705 из 964 технических.

Название говорит «поставка компрессора», а марка и тип стоят в комментарии
карточки — там, где заказчик пишет требования. Комментарии у нас есть:
`tp-kartochki.csv` на дропе, колонка с полным текстом.

ВАЖНАЯ ОГОВОРКА, из-за которой этот оп ничего не удаляет. Соседние сессии
подписывают винтовые и поршневые как «не наша машина» — для их задачи
(воздушные центробежные и воздуходувки) это верно. Для базы владельца НЕТ:
«Компрессор Центр» продаёт компрессоры вообще, родной бренд Enger и
дружественные Berg, Cross Air, Dali, Hansmann — это в основном ВИНТОВЫЕ
машины. Поэтому тип только ПОМЕЧАЕТСЯ, а решение, какому направлению какой
список отдать, остаётся за владельцем.

Запуск: python tip_mashiny.py
"""
import csv
import io
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\sender\server')

ДРОП = r'C:\seostat\drop\drop-storage'
ИМЯ = 'tp-lyudi-po-tipu-mashiny.csv'
ПАПКА = r'C:\sender\server'

_ЦЕНТР = re.compile(
    r'центробежн|турбокомпрессор|турбоагрегат|воздуходув|нагнетател|газодувк|'
    r'\bтурбо\b|К-?\d{3}-\d{2}|ЦК[-\s]?\d', re.I)
_ВИНТ = re.compile(r'винтов|поршнев|спиральн|скрол|screw|piston', re.I)


def на_дроп(путь, имя):
    import urllib.request
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=180) as о:
        return о.read()[:200]


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        raise SystemExit(f'нет файла {п}')
    return list(csv.DictReader(
        io.StringIO(open(п, encoding='utf-8-sig', errors='replace').read()),
        delimiter=';'))


def тип(текст):
    т = текст or ''
    ц, в = bool(_ЦЕНТР.search(т)), bool(_ВИНТ.search(т))
    if ц and not в:
        return 'центробежная'
    if в and not ц:
        return 'винтовая/поршневая'
    if ц and в:
        return 'обе упомянуты'
    return 'тип не назван'


def main():
    справ = {r['company_id']: r['inn'].strip()
             for r in читать('tp-inn.csv') if (r.get('inn') or '').strip()}
    лица = [r for r in читать('tp-lica.csv') if справ.get(r.get('company_id'))]
    спис = {r['tender_id']: r.get('predmet', '') for r in читать('tp-spisok.csv')}

    # полный комментарий карточки: колонка ищется по имени, а не по номеру —
    # у соседей набор колонок менялся, и жёсткий индекс тут сломается молча
    карт = {}
    ряды = читать('tp-kartochki.csv')
    поля = list(ряды[0].keys()) if ряды else []
    поле = next((к for к in поля if 'comment' in к.lower() or 'коммент' in к.lower()), '')
    идпол = next((к for к in поля if к.lower() in ('tender_id', 'id', 'tid')), '')
    print(f'колонок в карточках: {len(поля)}, комментарий в «{поле}», id в «{идпол}»')
    if поле and идпол:
        for r in ряды:
            т = (r.get(идпол) or '').strip()
            if т:
                карт[т] = r.get(поле) or ''
    print(f'карточек с комментарием: {sum(1 for v in карт.values() if v)}')

    по_названию = Counter()
    по_полному = Counter()
    строки = []
    компании = defaultdict(set)
    for r in лица:
        if r.get('rol') != 'техническая':
            continue
        тид = (r.get('tender_id') or '').strip()
        назв = спис.get(тид) or r.get('predmet') or ''
        полн = назв + ' ' + (карт.get(тид) or '')
        т1, т2 = тип(назв), тип(полн)
        по_названию[т1] += 1
        по_полному[т2] += 1
        компании[т2].add(справ[r['company_id']])
        строки.append([
            справ[r['company_id']], (r.get('company') or '')[:60],
            (r.get('imya') or '')[:60], (r.get('dolzhnost') or '')[:80],
            (r.get('telefon') or '')[:40], т2, т1,
            'да' if карт.get(тид) else 'нет', назв[:150],
            f'https://www.tender.pro/#/tender/{тид}' if тид else ''])

    print()
    print('=== ТИП ПО НАЗВАНИЮ ЗАКУПКИ (как считали раньше) ===')
    for к, n in по_названию.most_common():
        print(f'  {n:>5}  {к}')
    print('=== ТИП ПО НАЗВАНИЮ ПЛЮС ПОЛНЫЙ КОММЕНТАРИЙ ===')
    for к, n in по_полному.most_common():
        print(f'  {n:>5}  {к:<22} предприятий {len(компании[к])}')
    сдвиг = по_названию['тип не назван'] - по_полному['тип не назван']
    print()
    print(f'РАСКРЫТО КОММЕНТАРИЕМ: {сдвиг} строк, которые по названию были '
          '«тип не назван»')

    путь = os.path.join(ПАПКА, ИМЯ)
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['ИНН', 'компания', 'ФИО', 'должность', 'телефон',
                    'тип_машины', 'тип_по_названию', 'комментарий_был',
                    'предмет', 'источник'])
        в.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())
    print(f'{ИМЯ}: {len(строки)} строк')
    try:
        на_дроп(путь, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')
    print(f'строк {len(строки)}, раскрыто {сдвиг}')


if __name__ == '__main__':
    main()
