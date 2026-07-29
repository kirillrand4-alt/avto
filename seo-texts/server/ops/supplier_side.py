# -*- coding: utf-8 -*-
"""Контакты компании из закупок, где она ПОСТАВЩИК (мысль владельца 29.07).

До сих пор ЕИС спрашивали только про заказчика. Компания, не подпадающая под
44/223-ФЗ, для нас в ЕИС не существовала вовсе — а таких в базе много, это
частные заводы. При этом госзаказчикам они поставляют, и в карточке контракта
опубликован блок поставщика с телефоном и почтой, поданными В ЕГО СОБСТВЕННОЙ
заявке. То есть контакт нашей цели, добытый из ЧУЖОЙ закупки.

Проверка принадлежности встроена и обязательна: окно блока поставщика
засчитывается, только если в нём стоит НАШ ИНН. Заказчик на той же странице и
выше по тексту, и без этой проверки его контакты уехали бы нашей компании —
ровно та подмена, на которой уже обожглись с чужим работодателем на hh.

Роль такого контакта честно ожидается сбытовой или контрактной, а не
инженерной. Ценность в другом: по компаниям, где у нас нет ничего, это разница
между нулём и живым названным человеком с номером.

Побочный улов — ЗАКАЗЧИКИ нашей цели, то есть её клиенты. Складываем их в
сигналы: расширять по ним базу или нет, решает владелец.

Резюмируемо: supplier_side_stream.jsonl. По умолчанию СУХОЙ ПРОГОН.
Запуск: python supplier_side.py [бюджет_сек] [--apply] [--inn ИНН] [--limit N]
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 1200.0
ПРИМЕНИТЬ = '--apply' in sys.argv
ОДИН = (sys.argv[sys.argv.index('--inn') + 1] if '--inn' in sys.argv else '')
ЛИМИТ = int(sys.argv[sys.argv.index('--limit') + 1]
            if '--limit' in sys.argv else 100000)
ПОТОК = r'C:\seostat\drop\supplier_side_stream.jsonl'
НАЧАЛО = time.time()

db = EDB.EnrichDB()
e = db.cx


def цели():
    if ОДИН:
        return [ОДИН]
    из, было = [], set()
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    for строки in БАЗА.values():
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in было:
                было.add(i)
                из.append(i)
    сделано = set()
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                j = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not j.get('err'):
                сделано.add(str(j.get('inn')))
    return [i for i in из if i not in сделано][:ЛИМИТ]


def main():
    todo = цели()
    out = {'целей': len(todo), 'пройдено': 0, 'с_контрактами': 0,
           'карточек': 0, 'контактов': 0, 'телефонов': 0, 'почт': 0,
           'заказчиков_найдено': 0, 'ошибок': 0,
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)',
           'примеры': []}
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    for inn in todo:
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        итог = {'inn': inn}
        try:
            r = EC.find_zakupki_supplier(inn, max_cards=5) or {}
            if r.get('error') and not r.get('cards'):
                итог['err'] = str(r['error'])[:80]
                raise RuntimeError(итог['err'])
            карточки = r.get('cards') or []
            out['карточек'] += len(карточки)
            if карточки:
                out['с_контрактами'] += 1
            заказчики = [x for x in (r.get('customers') or []) if x]
            out['заказчиков_найдено'] += len(set(заказчики))
            найдено = 0
            for c in карточки:
                for ч in (c.get('people') or []):
                    тел = (ч.get('phone') or '').strip()
                    поч = (ч.get('email') or '').lower().strip()
                    фио = (ч.get('person') or '').strip()
                    if not (тел or поч):
                        continue
                    найдено += 1
                    out['контактов'] += 1
                    роль = EDB.EnrichDB._canon_role(ч.get('post') or '') or 'сбыт'
                    if len(out['примеры']) < 16:
                        out['примеры'].append(
                            {'инн': inn, 'фио': фио, 'должность': ч.get('post'),
                             'тел': тел, 'почта': поч,
                             'ссылка': (c.get('url') or '')[:80]})
                    if тел and list(EC.phones_in(тел)):
                        out['телефонов'] += 1
                        if ПРИМЕНИТЬ:
                            e.execute(
                                'INSERT OR IGNORE INTO phone_contacts(inn, phone,'
                                ' person, role, source, source_url, updated_at) '
                                'VALUES(?,?,?,?,?,?,datetime("now"))',
                                (inn, тел, фио, роль, 'контракт: мы поставщик',
                                 c.get('url') or ''))
                    if поч:
                        out['почт'] += 1
                        if ПРИМЕНИТЬ:
                            db.add_email(inn, поч, role=роль, person=фио,
                                         source='контракт: мы поставщик',
                                         source_url=c.get('url') or '')
                    if фио and ПРИМЕНИТЬ:
                        db.add_person(inn, фио, post=ч.get('post') or '',
                                      phone=тел, email=поч,
                                      source='контракт: мы поставщик',
                                      source_url=c.get('url') or '')
            # клиенты нашей цели — как сигнал, а не как контакт
            if ПРИМЕНИТЬ and заказчики:
                db.add_signal(inn, source='ЕИС',
                              event_type='поставляет госзаказчикам',
                              what='заказчики: ' + '; '.join(
                                  sorted(set(заказчики))[:4])[:180],
                              source_url=(карточки[0].get('url') if карточки
                                          else ''), hotness=2)
            итог['контактов'] = найдено
            итог['карточек'] = len(карточки)
        except Exception as ex:  # noqa: BLE001
            итог.setdefault('err', f'{type(ex).__name__}: {str(ex)[:70]}')
            out['ошибок'] += 1
        if ПРИМЕНИТЬ:
            e.commit()
        out['пройдено'] += 1
        ф.write(json.dumps(итог, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
    ф.close()
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
    print(json.dumps({k: v for k, v in out.items() if k != 'примеры'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
