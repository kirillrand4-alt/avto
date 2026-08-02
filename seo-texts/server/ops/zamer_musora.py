# -*- coding: utf-8 -*-
"""Сколько мусора снимают новые правила — на всей базе, а не на примерах.

Правила прошли контрольный список из семи живых случаев, но контрольный
список показывает, что правило РАБОТАЕТ, а не сколько оно заденет. Второе
считается только по базе целиком, и считать надо ДО того, как продавец
увидит опустевшую карточку.

Печатает: сколько фактов отсеивается, по каким причинам, и — что важнее —
у скольких компаний после отсева не остаётся НИ ОДНОГО факта. Такая компания
выпадает из работы целиком, и если их много, правило слишком жадное.

Запуск: python zamer_musora.py
"""
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog, centro_medium  # noqa: E402


def main():
    with centro_catalog.connect() as conn:
        кол = centro_catalog.table_columns(conn, 'fact')
        if not кол:
            print('таблицы fact нет')
            return
        ряды = centro_catalog._rows(conn, 'SELECT * FROM fact', ())
    print(f'фактов в базе: {len(ряды)}')

    причины = Counter()
    по_инн = defaultdict(lambda: [0, 0])   # [всего, оставлено]
    for row in ряды:
        item = {
            **row,
            'status': row.get('status') or row.get('chto') or '',
            'model': row.get('model') or row.get('kto_ili_marka') or '',
            'equipment_type': (row.get('equipment_type')
                               or row.get('dolzhnost_ili_tip') or ''),
            'medium': row.get('medium') or row.get('rol') or '',
            'evidence': row.get('evidence') or row.get('chem_dokazano') or '',
            'quote': row.get('quote') or row.get('citata') or '',
        }
        пр = centro_medium.rejection_reason(item)
        причины[пр or 'ОСТАВЛЕН'] += 1
        и = (row.get('inn') or '').strip()
        if и:
            по_инн[и][0] += 1
            if not пр:
                по_инн[и][1] += 1

    всего = sum(причины.values())
    оставл = причины.get('ОСТАВЛЕН', 0)
    print(f'оставлено: {оставл} ({round(100 * оставл / max(1, всего))}%)')
    print('отсеяно по причинам:')
    for пр, n in причины.most_common():
        if пр != 'ОСТАВЛЕН':
            print(f'  {n:>6}  {пр}')

    пусто = [и for и, (в, о) in по_инн.items() if в and not о]
    print()
    print(f'компаний в базе фактов: {len(по_инн)}')
    print(f'у скольких НЕ ОСТАЛОСЬ ни одного факта: {len(пусто)} '
          f'({round(100 * len(пусто) / max(1, len(по_инн)))}%)')
    if пусто:
        print('  ИНН для ручной проверки:', ', '.join(пусто[:10]))
        # показать, ЧТО именно у них сняли — правило может оказаться жадным,
        # и тогда компания выпадает из работы целиком
        for и in пусто[:3]:
            print(f'\n  === {и}, все его факты ===')
            for row in ряды:
                if (row.get('inn') or '').strip() != и:
                    continue
                item = {
                    **row,
                    'status': row.get('status') or row.get('chto') or '',
                    'model': row.get('model') or row.get('kto_ili_marka') or '',
                    'equipment_type': (row.get('equipment_type')
                                       or row.get('dolzhnost_ili_tip') or ''),
                    'medium': row.get('medium') or row.get('rol') or '',
                    'evidence': (row.get('evidence')
                                 or row.get('chem_dokazano') or ''),
                    'quote': row.get('quote') or row.get('citata') or '',
                }
                print(f'    [{centro_medium.rejection_reason(item)}] '
                      f'марка «{item["model"][:40]}» тип «{item["equipment_type"][:30]}» '
                      f'среда «{item["medium"][:20]}»')
                print(f'       цитата: {item["quote"][:150]}')


if __name__ == '__main__':
    main()
