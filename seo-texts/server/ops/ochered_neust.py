# -*- coding: utf-8 -*-
"""Замер очереди «не установлено»: что по ним вообще есть, прежде чем платить.

ЗАЧЕМ. Владелец разрешил пустить видимые «не установлено» рабочей очередью:
прицельно добрать доказательства и пересудить — либо в «есть» и в работу, либо
скрыть. Прежде чем гонять суд заново (а это деньги за каждую карточку), надо
знать, ПО КОМУ доказательства уже лежат в базе и по кому их нет вовсе: карточка
без единого факта пересудом не изменится, сколько раз её ни суди, и платить за
неё второй раз незачем.

ЧТО СВЕРЯЕМ. Приговор берём из `sud_centro` (enrich.db, серверное хранилище),
видимость — из `hidden_item` панели, факты — из `fact` центробежной базы. Плюс
три файла реестра ЭПБ: влитые наши машины, отсев с причиной и перепрошенные
провайдером строки, где центробежность не была названа словом.

Замер, а не правка: ничего не пишет в базы. Выход — таблица на дроп, чтобы
следующий шаг (доливка + пересуд) шёл по списку, а не по памяти.

Запуск: python ochered_neust.py [--csv]
"""
import csv
import json
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ДРОП = r'C:\seostat\drop\drop-storage'
ФАЙЛЫ_ЭПБ = {
    'влито_наши': 'VAZHNOE-3s-EPB-NASHI-MASHINY.csv',
    'отсев': 'OTSEV-EPB-1-sessiya.csv',
}
ПЕРЕПРОС = 'EPB-pereprosheno-centrobezhnye.csv'
ВЫХОД = 'OCHERED-NEUSTANOVLENO-1s.csv'


def инн_кл(з):
    return ''.join(ч for ч in str(з or '') if ч.isdigit())


def читать(путь, поле='inn'):
    """ИНН -> число строк файла. Файл может лежать на дропе или у раннера."""
    из = Counter()
    if not os.path.exists(путь):
        return из
    csv.field_size_limit(10 ** 7)
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            и = инн_кл(r.get(поле))
            if и:
                из[и] += 1
    return из


def main():
    db = EDB.EnrichDB()
    приговоры = {str(r[0]): (r[1] or '', r[2] or 0, (r[3] or '')[:200])
                 for r in db.cx.execute(
                     'SELECT inn, verdikt, uverennost, pochemu FROM sud_centro')}
    неуст = {и for и, (в, _у, _п) in приговоры.items() if в == 'не установлено'}

    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    кол = [c[1] for c in цб.execute('PRAGMA table_info("company")')]
    имя_к = next((k for k in ('predpriyatie', 'name', 'name_full')
                  if k in кол), 'inn')
    рег_к = 'region' if 'region' in кол else None
    компании = {str(r[0]): (r[1] or '', (r[2] or '') if рег_к else '')
                for r in цб.execute(
                    f'SELECT inn, "{имя_к}"'
                    + (f', "{рег_к}"' if рег_к else ", ''") + ' FROM company')}
    фактов = Counter()
    с_маркой = Counter()
    for и, м in цб.execute("SELECT inn, COALESCE(model,'') FROM fact"):
        фактов[str(и)] += 1
        if m_ok(м):
            с_маркой[str(и)] += 1
    цб.close()

    пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
    скрыты = {str(r[0]) for r in пр.execute(
        "SELECT inn FROM hidden_item WHERE kind='company'")}
    пр.close()

    видимые = sorted(и for и in неуст if и in компании and и not in скрыты)
    эпб = {к: читать(os.path.join(ДРОП, ф)) for к, ф in ФАЙЛЫ_ЭПБ.items()}
    for путь in (os.path.join(r'C:\sender\server', ПЕРЕПРОС),
                 os.path.join(ДРОП, ПЕРЕПРОС)):
        эпб['перепрос'] = читать(путь)
        if эпб['перепрос']:
            break

    итог = {
        'приговоров_всего': len(приговоры),
        'НЕ_УСТАНОВЛЕНО_всего': len(неуст),
        'из_них_скрыто': sum(1 for и in неуст if и in скрыты),
        'ВИДИМЫХ_В_ОЧЕРЕДЬ': len(видимые),
        'без_единого_факта': sum(1 for и in видимые if not фактов[и]),
        'с_фактами_но_без_марки': sum(
            1 for и in видимые if фактов[и] and not с_маркой[и]),
        'с_маркой_в_фактах': sum(1 for и in видимые if с_маркой[и]),
        'есть_строки_ЭПБ_влитые': sum(1 for и in видимые if эпб['влито_наши'][и]),
        'есть_строки_ЭПБ_в_отсеве': sum(1 for и in видимые if эпб['отсев'][и]),
        'ЕСТЬ_ПЕРЕПРОШЕННЫЕ_ЦЕНТРОБЕЖНЫЕ': sum(
            1 for и in видимые if эпб['перепрос'][и]),
        'вообще_нет_следа_ЭПБ': sum(
            1 for и in видимые
            if not (эпб['влито_наши'][и] or эпб['отсев'][и]
                    or эпб['перепрос'][и])),
    }
    print(json.dumps(итог, ensure_ascii=False, indent=1))

    строки = []
    for и in видимые:
        имя, рег = компании[и]
        строки.append({
            'inn': и, 'predpriyatie': имя, 'region': рег,
            'faktov': фактов[и], 'faktov_s_markoy': с_маркой[и],
            'epb_vlito': эпб['влито_наши'][и], 'epb_otsev': эпб['отсев'][и],
            'epb_pereprosheno_cb': эпб['перепрос'][и],
            'pochemu_ne_ustanovleno': приговоры[и][2],
        })
    строки.sort(key=lambda с: (-с['epb_pereprosheno_cb'], -с['faktov_s_markoy'],
                               -с['faktov']))
    print('\nтоп очереди (кому есть что долить):')
    for с in строки[:15]:
        print(f"  {с['inn']} {с['predpriyatie'][:44]:44} факт {с['faktov']:3} "
              f"марок {с['faktov_s_markoy']:2} ЭПБ+{с['epb_pereprosheno_cb']}")

    if '--csv' not in sys.argv or not строки:
        return
    п = os.path.join(r'C:\sender\server', ВЫХОД)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.DictWriter(ф, fieldnames=list(строки[0]), delimiter=';')
        в.writeheader()
        в.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())
    try:
        import urllib.request
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ВЫХОД, data=open(п, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'на дропе: {ВЫХОД} ({len(строки)} строк)')
    except Exception as e:  # noqa: BLE001
        print(f'файл не ушёл на дроп: {e}')


def m_ok(м):
    """Марка считается маркой, если это не пустая строка и не прочерк."""
    м = str(м or '').strip()
    return len(м) >= 2 and м not in ('-', '—', 'нет', 'не указана')


if __name__ == '__main__':
    main()
