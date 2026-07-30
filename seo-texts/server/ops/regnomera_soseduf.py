# -*- coding: utf-8 -*-
"""Регномера и ссылки по 129 ИНН с планами — для конвейера вложений соседа.

Новая вторая сессия просит «список регномеров по этим ИНН». Отдаю ровно то,
что у меня есть, и НЕ выдаю за регномер закупки то, чем оно не является:

  * `plan_reg_nomer` + `nomer_pozicii` — идентификатор ПЛАНА и позиции в нём.
    Это не номер извещения: вложений у плана нет, у него есть карточка
    позиции. Ссылка на неё — в колонке `ssylka` (orderplan/tru-plan/card).
  * URL закупок ЕИС, которые уже лежат у нас в базе по этим же ИНН
    (источники `zakupki:*`) — вот из них номер извещения достаётся.

Номера извещений по остальным ИНН придётся искать поиском ЕИС по заказчику —
это шаг их конвейера, у меня такого прохода нет, и придумывать его я не буду.

Запуск: python regnomera_soseduf.py
"""
import csv
import io
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ИМЯ = 'plan-223-regnomera-dlya-soseda.csv'
ПАПКА = r'C:\sender\server'
# номер извещения ЕИС: 11 цифр (44-ФЗ) или 32 цифры (223-ФЗ)
_РЕГ = re.compile(r'(?<!\d)(\d{11}|\d{32})(?!\d)')


def на_дроп(путь, имя):
    import urllib.request
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=180) as о:
        return о.read()[:200]


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    инны = [r[0] for r in q(
        "SELECT DISTINCT inn FROM signals WHERE source='ЕИС план 223-ФЗ'"
    ).fetchall()]
    print(f'ИНН с планом: {len(инны)}')
    хочу = set(инны)

    # 1) планы: регномер плана и позиция из выгрузки соседа
    планы = {}
    п = os.path.join(ДРОП, 'plany-zakupki.csv')
    if os.path.exists(п):
        сыр = open(п, encoding='utf-8-sig', errors='replace').read()
        for r in csv.DictReader(io.StringIO(сыр), delimiter=';'):
            и = (r.get('inn') or '').strip()
            if и in хочу and r.get('data_v_budushchem') == 'да':
                планы.setdefault(и, []).append(r)
    print(f'  с позициями плана в выгрузке: {len(планы)}')

    # 2) номера извещений ЕИС, которые уже есть у нас в базе
    сп = ','.join('?' * len(инны))
    извещ = {}
    for таб, кол in (('signals', 'source_url'), ('people', 'source_url'),
                     ('emails', 'source_url'), ('phone_contacts', 'source_url')):
        try:
            ряды = q(f'SELECT inn, {кол} FROM {таб} WHERE inn IN ({сп}) '
                     f"AND {кол} LIKE '%zakupki.gov.ru%'", инны).fetchall()
        except Exception:  # noqa: BLE001
            continue
        for и, у in ряды:
            for м in _РЕГ.findall(у or ''):
                извещ.setdefault(и, set()).add(м)
    print(f'  с номером извещения ЕИС, уже известным базе: {len(извещ)}')

    путь = os.path.join(ПАПКА, ИМЯ)
    строк = 0
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['ИНН', 'заказчик', 'регномер_ПЛАНА', 'номер_позиции',
                    'когда_разместят', 'предмет', 'сумма',
                    'ссылка_на_позицию_плана', 'номера_извещений_из_нашей_базы',
                    'телефонов_в_базе'])
        for и in инны:
            тел = q('SELECT COUNT(*) FROM phone_contacts WHERE inn=?',
                    (и,)).fetchone()[0]
            изв = ' | '.join(sorted(извещ.get(и, ())))
            ряды = планы.get(и) or [{}]
            for r in ряды[:3]:
                в.writerow([
                    и, (r.get('zakazchik') or '')[:80],
                    r.get('plan_reg_nomer') or '', r.get('nomer_pozicii') or '',
                    r.get('planiruemaya_data_razmeshcheniya') or '',
                    (r.get('predmet') or '')[:180], r.get('summa') or '',
                    r.get('ssylka') or '', изв, тел])
                строк += 1
        ф.flush()
        os.fsync(ф.fileno())
    print(f'{ИМЯ}: {строк} строк')
    try:
        на_дроп(путь, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')
    print(f'ИНН {len(инны)}, с планом {len(планы)}, с извещением {len(извещ)}')


if __name__ == '__main__':
    main()
