# -*- coding: utf-8 -*-
"""ШИРОКИЙ проход по реестру ЭПБ — по ВСЕЙ номенклатуре, а не по центробежным.

ЗАЧЕМ ЭТО ОТДЕЛЬНЫЙ ПРОГОН. Всё, что у нас лежало по ЭПБ, собрано под ЗАДАЧУ ПРО
ЦЕНТРОБЕЖНЫЕ: `VAZHNOE-3s-EPB-NASHI-MASHINY.csv` (313 ИНН) и `OTSEV-EPB-1-sessiya.csv`
(266 ИНН) — это один и тот же корпус, отсев добавляет к фактам 20 строк и НОЛЬ новых
предприятий. Словарь прежнего широкого прохода (`epb_shirokiy.py`) тоже центробежный:
десять слов, все про турбо/центробежные. Значит поршневые, винтовые, МКС и генераторы
азота-кислорода этот проход не мог найти в принципе — «их нет» было бы свойством словаря.

Здесь слова покрывают ВСЮ номенклатуру владельца. Реестру больно не делаем: одна страница
за раз, пауза, продолжение с места остановки по потоку.
"""
import json, os, re, sys, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpb_po_inn as M

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
POTOK = os.path.join(L, 'PARK-EPB-SHIROKIY-2S.jsonl')
CUST = re.compile(r'href="/customer/(\d+)"')

SLOVA = [
    # компрессоры всех видов, а не только центробежные
    'компрессор', 'поршневой компрессор', 'винтовой компрессор', 'воздушный компрессор',
    'центробежный компрессор', 'турбокомпрессор', 'дожимной компрессор',
    'мембранный компрессор', 'спиральный компрессор', 'компрессорная установка',
    'компрессорная станция',
    # воздуходувки и нагнетатели
    'воздуходувка', 'турбовоздуходувка', 'газодувка', 'нагнетатель',
    # азот и кислород — вторая половина номенклатуры, её раньше не искали вовсе
    'азотная станция', 'генератор азота', 'азотная установка', 'мембранная азотная',
    'адсорбционная азотная', 'кислородная станция', 'генератор кислорода',
    'кислородная установка', 'воздухоразделительная установка', 'криогенная установка',
    # МКС
    'передвижная компрессорная', 'мобильная компрессорная', 'компрессорная передвижная',
    # подготовка воздуха
    'осушитель воздуха', 'ресивер', 'воздухосборник',
]
# ВТОРОЙ КРУГ — ПО СЕРИЯМ. Слова номенклатуры («компрессор», «генератор азота») находят
# предприятие по РОДУ машины; серия («ТВ-80-1», «4ВМ10-100/8») находит тех, у кого стоит
# ИМЕННО ЭТА машина, и попадает в заводы, чьи заключения названы одним обозначением без
# родового слова. Список серий — от 3-й сессии, хозяина словаря.
_SERII = os.environ.get('SERII', '')
if _SERII and os.path.exists(_SERII):
    SLOVA = [x.strip() for x in open(_SERII, encoding='utf-8') if x.strip()]
    POTOK = os.path.join(L, 'PARK-EPB-SERII-2S.jsonl')

STRANIC = int(os.environ.get('STRANIC', '25'))
PAUZA = float(os.environ.get('PAUZA', '1.2'))


def main():
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
                gotovo.add((z['slovo'], z['stranica']))
            except json.JSONDecodeError:
                pass
    f = open(POTOK, 'a', encoding='utf-8')
    vsego, innov = 0, set()
    for slovo in SLOVA:
        pusto_podryad = 0
        for st in range(1, STRANIC + 1):
            if (slovo, st) in gotovo:
                continue
            qs = {'q': slovo, 'type': 'ТУ'}
            if st > 1:
                qs['page'] = st
            h = M._vzyat(f'{M.BAZA}/conclusions?' + urllib.parse.urlencode(qs), popytok=2)
            if h.startswith('__ОШИБКА__'):
                f.write(json.dumps({'slovo': slovo, 'stranica': st, 'err': h[:70],
                                    'stroki': []}, ensure_ascii=False) + '\n')
                f.flush()
                break
            stroki = []
            for tr in M.TR.findall(h):
                c = CUST.search(tr)
                if not c:
                    continue
                e, o, n, d = (M.EKSPL.search(tr), M.OBEKT.search(tr),
                              M.NOMER.search(tr), M.DATA.search(tr))
                ob = (o.group(1) if o else '')
                stroki.append({'inn': c.group(1),
                               'predpriyatie': (e.group(2) if e else '')[:90],
                               'obekt': ob[:240],
                               'nomer': n.group(2).strip() if n else '',
                               'data': d.group(1) if d else '',
                               'sreda': M.sreda(ob),
                               'ssylka': f'{M.BAZA}/conclusions?exploiter={c.group(1)}'})
            f.write(json.dumps({'slovo': slovo, 'stranica': st, 'err': '',
                                'stroki': stroki}, ensure_ascii=False) + '\n')
            f.flush()
            vsego += len(stroki)
            innov |= {r['inn'] for r in stroki}
            # СТРАНИЦА БЕЗ СТРОК — конец выдачи по слову. Реестр на непонятный параметр
            # отдаёт ту же первую страницу, поэтому считаем два пустых подряд, а не один.
            pusto_podryad = pusto_podryad + 1 if not stroki else 0
            if pusto_podryad >= 2:
                break
            time.sleep(PAUZA)
        print(f'{slovo}: всего строк {vsego}, ИНН {len(innov)}', file=sys.stderr, flush=True)
    print(f'ИТОГО строк {vsego}, разных ИНН {len(innov)}', file=sys.stderr)


main()
