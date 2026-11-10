# -*- coding: utf-8 -*-
r"""Список ИНН для сбора контактов с коммерческих площадок (B2B-Center и др., шаг 4а плана PLAN_CA_O2_N2.md).

10.11, владелец: «дай список ИНН, для которых надо собрать контакты из b2b». Берём компании ca-spisok.json (ЦА O2/N2),
у которых после ночного обхода нет ЛПР («лпр: да», не чужой номер) ни с сайта, ни среди чистых контактов ЕИС
(ca-zakupki-chistye.jsonl). Порядок: статус категории (ядро -> новая -> по нашим сделкам), затем выручка по убыванию;
первые 50 — пилот. В файле только юрлица и сведения о компании (без ФИО и телефонов людей).
Выход: ca\ca-b2b-spisok.csv (без ЛПР) или ca\ca-b2b-vse.csv (CA_B2B_VSE=1 / --vse: все) (+ дроп). Только чтение.
"""
import csv, io, json, os, sys

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'
sys.path.insert(0, DIR)
import ca_cel  # noqa: E402

ВЕС = {'ядро': 0, 'новая': 1, 'по нашим сделкам': 2}
# 10.11, владелец: «дай список всех, может более актуальные данные принесёт б2б» — --vse: все компании ЦА, с колонкой
# «ЛПР найден»; без флага — только без ЛПР
ВСЕ = '--vse' in sys.argv or os.environ.get('CA_B2B_VSE') == '1' or os.path.exists(os.path.join(ПАПКА, 'ca-b2b-vse.flag'))


def main():
    сп = json.load(io.open(os.path.join(DIR, 'ca-spisok.json'), encoding='utf-8'))['компании']
    зап = {}
    for s in io.open(os.path.join(DIR, 'ca-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('итог') == 'ok':
            зап[з['inn']] = з
    еис = {}
    п = os.path.join(ПАПКА, 'ca-zakupki-chistye.jsonl')
    if os.path.exists(п):
        for s in io.open(п, encoding='utf-8', errors='replace'):
            x = json.loads(s)
            еис.setdefault(x['inn'], set()).add(x['вердикт'])
    строки = []
    for инн, к in сп.items():
        з = зап.get(инн) or {}
        ном = [x for x in з.get('номера') or [] if x.get('чей') != 'другая']
        лпр = [x for x in ном if x.get('лпр') == 'да']
        if лпр and not ВСЕ:
            continue
        кат = [c for c in (к.get('сегм') or '').split(', ') if c]
        вес = min((ВЕС.get(ca_cel.КАТ[c][1], 3) for c in кат if c in ca_cel.КАТ), default=3)
        # 52.10 «складирование» = любые склады (ГСМ, ангары, элеваторы), фруктохранилище не доказано — в конец, не в пилот
        склад = кат == ['n2_rgs'] and str(к.get('осн') or '').startswith('52.10')
        if склад:
            вес = 4
        строки.append({'ИНН': инн, 'Название': к.get('имя') or '', 'Категории': ', '.join(кат),
                       'Статус': min((ca_cel.КАТ[c][1] for c in кат if c in ca_cel.КАТ), key=lambda x: ВЕС.get(x, 3), default=''),
                       'Регион': к.get('регион') or '', 'Выручка, млн': round((к.get('выручка') or 0) / 1e6),
                       'Сайт': з.get('сайт') or к.get('сайт') or '',
                       'Почта найдена': 'да' if any(x.get('почта') for x in ном) else 'нет',
                       'Телефон найден': 'да' if any(x.get('номер') for x in ном) else 'нет',
                       'Контакт ЕИС': ', '.join(sorted(еис.get(инн, []))) or 'нет',
                       'ЛПР найден': 'да (%d)' % len(лпр) if лпр else 'нет',
                       'ИНН на сайте': 'да' if инн in (з.get('инн_живой') or []) else ('нет' if з.get('сайт') else ''),
                       'Примечание': '52.10 складирование: фруктохранилище не подтверждено, проверить' if склад else '',
                       '_вес': вес})
    строки.sort(key=lambda r: (r['_вес'], -r['Выручка, млн']))
    for i, r in enumerate(строки, 1):
        r['№'] = i
        r['Пилот'] = 'да' if i <= 50 else ''
        r.pop('_вес')
    кол = ['№', 'Пилот', 'ИНН', 'Название', 'Категории', 'Статус', 'Регион', 'Выручка, млн', 'Сайт', 'Почта найдена',
           'Телефон найден', 'ЛПР найден', 'ИНН на сайте', 'Контакт ЕИС', 'Примечание']
    вых = os.path.join(ПАПКА, 'ca-b2b-vse.csv' if ВСЕ else 'ca-b2b-spisok.csv')
    with io.open(вых, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=кол, delimiter=';')
        w.writeheader()
        w.writerows(строки)
        f.flush()
        os.fsync(f.fileno())
    import shutil
    shutil.copyfile(вых, os.path.join(ДРОП, os.path.basename(вых)))
    import collections
    print('===ИТОГ===', json.dumps({'в_списке_ЦА': len(сп), 'в_файле': len(строки), 'все': ВСЕ,
                                     'с_ЛПР': sum(1 for r in строки if r['ЛПР найден'] != 'нет'),
                                     'ИНН_на_сайте': sum(1 for r in строки if r['ИНН на сайте'] == 'да'),
                                     'по_статусу': dict(collections.Counter(r['Статус'] for r in строки)),
                                     'склады_52_10': sum(1 for r in строки if r['Примечание']),
                                     'без_почты': sum(1 for r in строки if r['Почта найдена'] == 'нет')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
