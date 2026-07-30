# -*- coding: utf-8 -*-
"""Планы закупок 223-ФЗ → enrich.db: намерение ДО объявления закупки.

Это единственный наш источник, смотрящий ВПЕРЁД. Тендер говорит «уже
покупают», план — «собираются разместить в таком-то месяце». Для звонка это
принципиально разные вещи: в первом случае поставщик уже выбран или почти,
во втором до размещения есть месяцы.

Выгрузку собрала соседняя сессия (`plany-zakupki.csv`, реестр позиций ЕИС и
печатные формы планов). Наш вклад — чистка, потому что ключевой слой там
обманывает двумя способами, и оба видны только на данных:

  1. НАЗВАНИЕ ПРОЕКТА ДОПИСАНО К КАЖДОЙ СТРОКЕ ПЛАНА. У одной ГЭС проект
     назывался «Реконструкция … с заменой турбоагрегатов», и слово
     «турбоагрегат» совпало у ВСЕХ 44 позиций плана — перчатки, мебель,
     постельные принадлежности, спецодежда. Лечится отсечением хвоста
     «в рамках …»: ключ обязан стоять в САМОМ предмете позиции.
  2. «ТУРБОКОМПРЕССОР» ЧАЩЕ ВСЕГО АВТОМОБИЛЬНЫЙ — турбонаддув ДВС, а не наша
     машина. Плюс «воздуходувка» бывает садовой, в комплекте со снегоуборщиком.

После обеих чисток из 336 позиций с датой в будущем остаётся 163 в 129 ИНН.
До чистки было 208 в 133 ИНН — компаний почти столько же, но каждая пятая
позиция была мусором, и продажник получил бы в списке перчатки.

Запуск: python plany_import.py [--dry]
"""
import csv
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

СУХОЙ = '--dry' in sys.argv
ДРОП = r'C:\seostat\drop\drop-storage'
ФАЙЛ = 'plany-zakupki.csv'
ЖУРНАЛ = r'C:\sender\server\plany.jsonl'
ИСТОЧНИК = 'ЕИС план 223-ФЗ'

# хвост «в рамках реализации проекта …» — там живёт название проекта, и по
# нему ключ совпадает у всех позиций плана разом
_ХВОСТ = re.compile(
    r'\s*(?:,\s*)?(?:в рамках|в рамка|для нужд проекта|по объекту|'
    r'в целях реализации)\b.*$', re.I | re.S)
_НАШЕ = re.compile(
    r'компрессор|воздуходув|турбоагрегат|нагнетател|газодувк|воздухоразделит',
    re.I)
# транспорт как ОБЪЕКТ закупки. «двигатель» и «дизель» сюда НЕ входят
# намеренно: «электродвигатель на компрессор» — наша позиция, а не автомобиль
_АВТО = re.compile(
    r'транспортн средств|автомоб|автобус|харвестер|форвардер|экскаватор|'
    r'самосвал|камаз|гараж|тепловоз|локомотив|тягач|погрузчик|снегоубор|'
    r'уборочной техник|стартер|турбокомпрессор.{0,25}(?:двс|двигател|транспорт)',
    re.I)
_ПУСТЫШКА = re.compile(
    r'^\s*(?:приобретение товаров|закупки на сумму|договоры до|'
    r'закупка товаров, работ|прочие закупк|закупки малого)', re.I)


def ядро(предмет):
    """Предмет БЕЗ хвоста с названием проекта."""
    return _ХВОСТ.sub('', предмет or '').strip()


def наше(предмет):
    я = ядро(предмет)
    return bool(_НАШЕ.search(я)) and not _АВТО.search(я) and not _ПУСТЫШКА.match(я)


def _млн(сумма):
    ц = re.sub(r'[^\d,]', '', сумма or '').replace(',', '.')
    try:
        return float(ц) / 1e6
    except ValueError:
        return 0.0


def _срок(т):
    """«07.2026» → «2026-07» для сортировки и записи в сигнал."""
    м = re.match(r'(\d{2})\.(\d{4})', (т or '').strip())
    return f'{м.group(2)}-{м.group(1)}' if м else ''


def main():
    п = os.path.join(ДРОП, ФАЙЛ)
    if not os.path.exists(п):
        raise SystemExit(f'нет файла {п}')
    все = list(csv.DictReader(
        io.StringIO(open(п, encoding='utf-8-sig', errors='replace').read()),
        delimiter=';'))
    буд = [r for r in все if r.get('data_v_budushchem') == 'да']
    сыро = [r for r in буд if _НАШЕ.search(r.get('predmet') or '')]
    чисто = [r for r in буд if r.get('inn') and наше(r.get('predmet'))]
    print(f'позиций в выгрузке: {len(все)}, с датой размещения в будущем: {len(буд)}')
    print(f'  ключ где угодно в тексте: {len(сыро)} поз / '
          f'{len({r["inn"] for r in сыро})} ИНН')
    print(f'  ключ в самом предмете и не автотранспорт: {len(чисто)} поз / '
          f'{len({r["inn"] for r in чисто})} ИНН')
    sys.stdout.flush()

    # по компании — самая ранняя из будущих позиций (звонить надо к ней),
    # при равенстве — самая крупная по сумме
    лучшее = {}
    for r in чисто:
        и = r['inn'].strip()
        ключ = (_срок(r.get('planiruemaya_data_razmeshcheniya')) or '9999-99',
                -_млн(r.get('summa')))
        if и not in лучшее or ключ < лучшее[и][0]:
            лучшее[и] = (ключ, r)
    print(f'компаний с планом: {len(лучшее)}')

    if not СУХОЙ:
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            for и, (_к, r) in лучшее.items():
                ж.write(json.dumps(r, ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())
        print(f'журнал: {ЖУРНАЛ}')

    из_базы = EC._base_index(sorted(лучшее))
    print(f'из базы обзвона нашлось: {len(из_базы)} ИНН из {len(лучшее)}')
    sys.stdout.flush()

    db = EDB.EnrichDB()
    было_к = db.cx.execute('SELECT COUNT(*) FROM companies').fetchone()[0]
    было_с = db.cx.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
    уже = {r[0] for r in db.cx.execute(
        'SELECT inn FROM companies WHERE inn IN (%s)'
        % ','.join('?' * len(лучшее)), sorted(лучшее)).fetchall()}
    print(f'уже есть в базе: {len(уже)}, НОВЫХ предприятий: {len(лучшее) - len(уже)}')

    if not СУХОЙ:
        for и, (_к, r) in лучшее.items():
            б = из_базы.get(и) or {}
            поля = {'name': б.get('name') or (r.get('zakazchik') or '').strip()}
            for ключ, кол in (('site', 'site'), ('city', 'region'), ('okved', 'okved')):
                if б.get(ключ):
                    поля[кол] = б[ключ]
            db.upsert_company(и, **поля)
            db.add_signal(
                и, ИСТОЧНИК,
                event_type=f'план закупки {_срок(r.get("planiruemaya_data_razmeshcheniya"))}',
                what=ядро(r.get('predmet'))[:400], sum=(r.get('summa') or '').strip(),
                source_url=(r.get('ssylka') or '').strip(),
                ts=_срок(r.get('planiruemaya_data_razmeshcheniya')), hotness=3)

    стало_к = db.cx.execute('SELECT COUNT(*) FROM companies').fetchone()[0]
    стало_с = db.cx.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  компании: было {было_к} → стало {стало_к} (+{стало_к - было_к})')
    print(f'  сигналы:  было {было_с} → стало {стало_с} (+{стало_с - было_с})')
    в_источнике = db.cx.execute(
        'SELECT COUNT(*) FROM signals WHERE source=?', (ИСТОЧНИК,)).fetchone()[0]
    print(f'  сигналов источника «{ИСТОЧНИК}»: {в_источнике}')

    # у скольких из этих компаний уже есть человек и телефон — то есть
    # план можно превратить в звонок прямо сейчас
    сп = ','.join('?' * len(лучшее))
    с_людьми = db.cx.execute(
        f'SELECT COUNT(DISTINCT inn) FROM people WHERE inn IN ({сп})',
        sorted(лучшее)).fetchone()[0]
    тех = "','".join(EDB.EnrichDB.TECH_ROLES)
    с_тех = db.cx.execute(
        f"SELECT COUNT(DISTINCT inn) FROM people WHERE role IN ('{тех}') "
        f'AND inn IN ({сп})', sorted(лучшее)).fetchone()[0]
    с_тел = db.cx.execute(
        f'SELECT COUNT(DISTINCT inn) FROM phone_contacts WHERE inn IN ({сп})',
        sorted(лучшее)).fetchone()[0]
    print(f'  из них уже с человеком: {с_людьми}, с техЛПР: {с_тех}, '
          f'с телефоном: {с_тел}')

    print()
    print('=== БЛИЖАЙШИЕ ПЛАНЫ ===')
    for и, (_к, r) in sorted(лучшее.items(),
                             key=lambda x: (x[1][0][0], x[1][0][1]))[:15]:
        б = из_базы.get(и) or {}
        print(f'  {и} {_срок(r.get("planiruemaya_data_razmeshcheniya")):<8} '
              f'{_млн(r.get("summa")):>8.1f} млн  '
              f'{(б.get("name") or r.get("zakazchik") or "")[:26]:<26} '
              f'{ядро(r.get("predmet"))[:46]}')
    print(f'позиций {len(чисто)}, компаний {len(лучшее)}, '
          f'новых {len(лучшее) - len(уже)}')  # хвост для tail


if __name__ == '__main__':
    main()
