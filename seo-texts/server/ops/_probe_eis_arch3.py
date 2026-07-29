# -*- coding: utf-8 -*-
r"""РАЗБОР НУЛЯ: почему у 24 компаний из 30 архивный проход не дал ни одного
человека. Ноль проверяем так же тщательно, как находку.

Читаем durable-поток eis_archive_stream.jsonl (он на сервере и переживает
рестарт) и печатаем по каждой компании: сколько позиций отдал ЕИС по актуальным
и по архивным окнам, сколько карточек открылось, сколько отклонила привязка,
сколько людей вышло. Плюс имя и выручка из companies — чтобы видеть, кто это.
"""
import io
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПОТОК = r'C:\seostat\drop\eis_archive_stream.jsonl'


def main():
    db = EDB.EnrichDB()
    e = db.cx
    строки = {}
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            d = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        строки[d.get('inn')] = d       # последняя запись по ИНН
    out = {'записей_в_потоке': len(строки), 'разрез': {}, 'компании': []}
    к = {'нет_позиций_в_еис': 0, 'всё_старше_3_лет': 0,
         'карточки_есть_людей_нет': 0, 'привязка_отклонила_всё': 0,
         'люди_есть': 0, 'ошибка': 0}
    for inn, d in строки.items():
        try:
            r = e.execute('SELECT name, revenue_rub FROM companies WHERE inn=?',
                          (inn,)).fetchone()
        except Exception:  # noqa: BLE001
            r = e.execute('SELECT name FROM companies WHERE inn=?', (inn,)).fetchone()
            r = (r[0] if r else '', None)
        имя = (r[0] if r else '') or ''
        выр = (r[1] if r and len(r) > 1 else None)
        зап = {'inn': inn, 'имя': имя[:46],
               'выручка_млрд': (round(float(выр) / 1e9, 1) if выр else None),
               'акт_поз': d.get('актуальных_позиций'),
               'арх_поз': d.get('архивных_позиций'),
               'старше3': d.get('отброшено_старше_3_лет'),
               'карт': d.get('карточек_всего'),
               'откр': d.get('открыто_карточек'),
               'откл': d.get('карточек_отклонено_привязкой'),
               'ошиб': d.get('карточек_ошибка'),
               'сырых': d.get('сырых_записей'),
               'людей': d.get('людей'), 'из_акт': d.get('людей_из_актуальных'),
               'причины': d.get('причины')}
        if d.get('error'):
            зап['error'] = d['error']
            к['ошибка'] += 1
        elif (d.get('людей') or 0) > 0:
            к['люди_есть'] += 1
        elif not (d.get('актуальных_позиций') or 0) and not (d.get('архивных_позиций') or 0):
            к['нет_позиций_в_еис'] += 1
        elif not (d.get('карточек_всего') or 0):
            к['всё_старше_3_лет'] += 1
        elif (d.get('карточек_отклонено_привязкой') or 0) >= (d.get('карточек_всего') or 0):
            к['привязка_отклонила_всё'] += 1
        else:
            к['карточки_есть_людей_нет'] += 1
        out['компании'].append(зап)
    out['разрез'] = к
    out['компании'].sort(key=lambda z: -(z['арх_поз'] or 0))
    print('РАЗРЕЗ ' + json.dumps(к, ensure_ascii=False), flush=True)
    print(json.dumps(out['компании'], ensure_ascii=False, indent=1)[:9000], flush=True)
    print('РАЗРЕЗ ' + json.dumps(к, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
