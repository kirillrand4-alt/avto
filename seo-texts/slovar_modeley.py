# -*- coding: utf-8 -*-
"""Словарь моделей центробежных компрессоров: собрать всё виденное и разобрать провайдером.

Пункт 9 владельца: «запишите все уже известные нам модели центробежных компрессоров, которые
встречались за всё время, и используйте их для опознавания среды, подходит нам компания или
нет, а также прогона по площадкам».

Три применения, ради которых словарь и делается:
  1. **среда** — по серии видно, воздушная машина или газовая (К-250-61-5 воздушная,
     43ГЦ2-110/12 газовая). Сейчас среда доказывается разбором текста, серия точнее;
  2. **годится ли предприятие** — центробежная машина в списке марок это прямое попадание,
     поршневая или вентилятор — нет;
  3. **прогон по площадкам словами** — обход по ИНН структурно НЕ МОЖЕТ найти новое
     предприятие, он читает нашу же очередь. Слова из словаря — единственный вход к тем,
     кого у нас ещё нет.

НЕ НАЧИНАЮ С НУЛЯ. Первая сессия уже разобрала 300 марок провайдером
(`SLOVAR-MODELEY-1s-RAZOBRANO-PROVAYDEROM.csv`), они берутся как есть и не переспрашиваются.
Её разбор — в основном отрицательный (позиционные обозначения, вентиляторы Ц4-70), то есть
как раз то, что нам нужно отсеять.

ЧТО РАЗБИРАЕМ. Всего в базе 20 343 уникальных «марки», но это в основном мусор разбора:
позиционные номера аппаратов (Н-370-18-1, АВТ-11), обрывки, числа. Отбор честный и назван:
берём марки, встреченные **у двух и более предприятий** (2 904), плюс топ-500 по числу
упоминаний. Марка у одного предприятия — почти всегда его внутреннее позиционное
обозначение, и разбирать 17 тысяч таких значит платить за мусор.
Сколько осталось за бортом — печатается числом, молчаливых потолков нет.

ЗАСЛОН ОТ ВЫДУМКИ. Провайдер однажды выдал нам 32 несуществующих телефона, поэтому:
  * ответ принимается, только если поле `marka` ДОСЛОВНО совпадает с одной из посланных;
    выдуманные строки отбрасываются и считаются отдельно;
  * модель обязана иметь право сказать «не знаю» — в промпте это сказано прямо, а ответы
    «не знаю» считаются нормальным исходом, а не браком;
  * ничего, кроме классификации, у модели не спрашивается: ни телефонов, ни имён.

Использование:
    python3 slovar_modeley.py --sobrat            # только собрать список, без провайдера
    python3 slovar_modeley.py --predel 120        # разобрать первые 120
    python3 slovar_modeley.py --pachka 60 --potok 4
"""
import csv
import json
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
RAB = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad'
CHUZHOY = os.path.join(RAB, 'SLOVAR-MODELEY-1s-RAZOBRANO-PROVAYDEROM.csv')
VYHOD = os.path.join(C, 'SLOVAR-MODELEY-CENTROBEZHNYH.csv')
ISHODNIKI = ['OCHERED-centrobezhnye.csv', 'SVOD-tri-sostoyaniya.csv',
             'SVOD-POLNYY-po-predpriyatiyam.csv']
COLS = ['marka', 'vid', 'sereya', 'proizvoditel', 'sreda', 'uverennost', 'pochemu',
        'predpriyatiy', 'upominaniy', 'goditsya_dlya_poiska', 'kto_razobral']

PROMPT = """Ты инженер по компрессорному оборудованию. Тебе дан список обозначений, извлечённых
из закупок и технических документов российских предприятий. Часть из них — настоящие модели
машин, часть — позиционные обозначения аппаратов на схеме (Н-370-18-1, АВТ-11), обрывки строк
и просто числа.

Разбери КАЖДОЕ обозначение. Отвечай ТОЛЬКО JSON-массивом, без пояснений вокруг.

Для каждого:
  "marka"        — обозначение ДОСЛОВНО как дано, ни одного знака не меняя
  "vid"          — ровно одно из: "центробежный компрессор", "поршневой компрессор",
                   "винтовой компрессор", "турбовоздуходувка/нагнетатель",
                   "вентилятор или дымосос", "насос", "иное оборудование",
                   "позиционное обозначение", "не опознано"
  "sereya"       — серия, если узнаётся (например "К-250", "ЦК", "ГЦ", "Centac"), иначе ""
  "proizvoditel" — завод-изготовитель, если узнаётся, иначе ""
  "sreda"        — "воздух", "газ", "зависит от исполнения" или "неизвестно"
  "uverennost"   — "высокая", "средняя" или "низкая"
  "pochemu"      — одна короткая фраза, по какому признаку определил

ВАЖНО, это важнее полноты ответа: если обозначение тебе не знакомо — ставь
"vid": "не опознано", "uverennost": "низкая". Не достраивай правдоподобную расшифровку.
Придуманная серия хуже честного «не опознано»: по ней мы будем искать несуществующие закупки.

Обозначения:
%s"""


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def sobrat():
    """Все марки с числом упоминаний и числом предприятий."""
    upom = Counter()
    pred = defaultdict(set)
    for f in ISHODNIKI:
        p = os.path.join(L, f)
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            for m in re.split(r'[;,|]', r.get('marki') or r.get('marka') or ''):
                m = m.strip()
                if len(m) < 2:
                    continue
                upom[m] += 1
                if r.get('inn'):
                    pred[m].add(r['inn'])
    return upom, pred


def tekst_iz(otvet):
    """Провайдер отдаёт объект как у SDK, а не строку. `str(otvet)` даёт «<_Msg object at
    0x…>», и разбор молча получает 44 знака мусора вместо ответа — так и вышло на первом
    прогоне. Текст берётся из блоков, и если текстовый блок пуст (модель ответила внутри
    размышления) — из блока размышления."""
    if isinstance(otvet, str):
        return otvet
    bloki = getattr(otvet, 'content', None) or []
    tekst = ''.join(getattr(b, 'text', '') or '' for b in bloki
                    if getattr(b, 'type', '') == 'text')
    if tekst.strip():
        return tekst
    return ''.join(getattr(b, 'text', '') or '' for b in bloki)


def razobrat_otvet(tekst, poslannye):
    """Только то, что действительно спрашивали. Выдуманные марки не проходят.

    Разбор пообъектный, а не всего массива целиком. Причина замерена: при 20 марках в пачке
    ответ обрывается по лимиту токенов на середине, закрывающей скобки массива нет, и
    `json.loads` по куску от '[' до последней ']' падает — вся пачка теряется, хотя
    полтора десятка объектов в ней разобраны полностью. Теперь берётся всё, что успело
    закрыться, а сколько потеряно на обрыве — считается и печатается.
    """
    svoi, chuzhie, bityh = [], 0, 0
    nabor = set(poslannye)
    glub, nachalo = 0, -1
    for n, ch in enumerate(tekst):
        if ch == '{':
            if glub == 0:
                nachalo = n
            glub += 1
        elif ch == '}' and glub:
            glub -= 1
            if glub == 0 and nachalo >= 0:
                try:
                    d = json.loads(tekst[nachalo:n + 1])
                except json.JSONDecodeError:
                    bityh += 1
                    continue
                if not isinstance(d, dict) or 'marka' not in d:
                    continue
                m = (d.get('marka') or '').strip()
                if m in nabor:
                    svoi.append(d)
                else:
                    chuzhie += 1
    if not svoi:
        return [], chuzhie, (f'ни одного разобранного объекта (битых {bityh}, '
                             f'длина ответа {len(tekst)})')
    return svoi, chuzhie, ''


def main():
    predel = dovod('--predel', 10 ** 9)
    pachka = dovod('--pachka', 60)
    potok = dovod('--potok', 4)

    upom, pred = sobrat()
    # Отбор назван прямо: у 2+ предприятий ИЛИ в топ-500 по упоминаниям.
    top500 = {m for m, _ in upom.most_common(500)}
    otobrany = [m for m in upom if len(pred.get(m, ())) > 1 or m in top500]
    est = {r['marka'].strip(): r for r in chitat(CHUZHOY)}
    uzhe = {r['marka'].strip() for r in chitat(VYHOD)}
    nado = [m for m in otobrany if m not in est and m not in uzhe]
    nado.sort(key=lambda m: -upom[m])
    print(f'марок всего {len(upom)}, отобрано {len(otobrany)} '
          f'(у 2+ предприятий или топ-500 по упоминаниям)', file=sys.stderr)
    print(f'  уже разобрано первой сессией {len(est)}, нами {len(uzhe)}, '
          f'к разбору {len(nado)}', file=sys.stderr)
    print(f'  ОСТАВЛЕНО ЗА БОРТОМ {len(upom) - len(otobrany)} марок, встреченных у одного '
          'предприятия и вне топ-500 — это почти всегда его позиционные обозначения',
          file=sys.stderr)

    novyy = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    f = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
        # Чужой разбор вливается как есть, со ссылкой на автора.
        for m, r in est.items():
            w.writerow({'marka': m, 'vid': r.get('chto') or '', 'sereya': '',
                        'proizvoditel': '', 'sreda': '', 'uverennost': '',
                        'pochemu': r.get('priznak') or '',
                        'predpriyatiy': r.get('predpriyatiy') or '',
                        'upominaniy': r.get('upominaniy') or '',
                        'goditsya_dlya_poiska': '', 'kto_razobral': '1-я сессия'})
        f.flush()
        print(f'  влит разбор первой сессии: {len(est)} марок', file=sys.stderr)

    if '--sobrat' in sys.argv:
        f.close()
        return

    import gen_provider
    klient = gen_provider.make_client()
    nado = nado[:predel]
    pachki = [nado[i:i + pachka] for i in range(0, len(nado), pachka)]
    sch = {'разобрано': 0, 'центробежных': 0, 'не опознано': 0, 'выдуманных строк': 0,
           'сбоев': 0}
    lock = threading.Lock()

    def odna(gr):
        spisok = '\n'.join(f'{n}. {m}' for n, m in enumerate(gr, 1))
        # БЕЗ БЛОКА РАЗМЫШЛЕНИЯ. С ним модель тратила все 16 000 токенов на рассуждение и
        # не доходила до ответа: приходило 22 тысячи знаков размышления и НИ ОДНОГО JSON,
        # причём на пачке любого размера — хоть 60 марок, хоть 20. Задача классификации
        # размышления не требует, а бюджет съедает целиком.
        posl = ''
        for popytka in range(4):
            try:
                # ПРЕФИЛЛ ОТВЕТА скобкой. Без него модель, несмотря на прямое «отвечай
                # только JSON», уходила рассуждать прозой на 23 800 знаков и обрывалась по
                # лимиту, не дойдя до JSON вовсе. С префиллом ответ 2 900 знаков и все
                # объекты на месте. Замерено на одной и той же пачке.
                m = gen_provider._raw_stream(
                    [{'role': 'user', 'content': PROMPT % spisok},
                     {'role': 'assistant', 'content': '['}],
                    'claude-fable-5', 16000, thinking=False)
                tekst = '[' + tekst_iz(m)
                if tekst.strip():
                    break
                posl = 'пустой ответ провайдера'
            except Exception as e:
                posl = str(e)[:150]
            time.sleep(min(120, 10 * 2 ** popytka))
        else:
            return gr, None, posl
        svoi, chuzhie, err = razobrat_otvet(tekst, gr)
        return gr, (svoi, chuzhie), err

    with ThreadPoolExecutor(max_workers=potok) as pool:
        for nomer, (gr, rez, err) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                if rez is None:
                    sch['сбоев'] += len(gr)
                    print(f'  СБОЙ пачки {nomer}: {err}', file=sys.stderr, flush=True)
                    continue
                svoi, chuzhie = rez
                if err or not svoi:
                    # Пустой разбор — НЕ «модель ничего не нашла». Раньше эта ветка молчала,
                    # и пачка из 60 марок исчезала без следа: в счётчике ноль, в журнале
                    # ничего. Тот же класс, что «сбой разбора записан как факт».
                    sch['сбоев'] += len(gr)
                    print(f'  ПУСТОЙ РАЗБОР пачки {nomer}: {err or "ни одной своей марки"}',
                          file=sys.stderr, flush=True)
                    continue
                sch['выдуманных строк'] += chuzhie
                for d in svoi:
                    m = d['marka'].strip()
                    vid = (d.get('vid') or '').strip()
                    if 'центробежн' in vid:
                        sch['центробежных'] += 1
                    if 'не опознано' in vid:
                        sch['не опознано'] += 1
                    sch['разобрано'] += 1
                    # Для поиска по площадкам годится только то, что опознано уверенно
                    # и не является позиционным обозначением: иначе обход пойдёт искать
                    # закупки по номеру аппарата чужой схемы.
                    godno = ('да' if ('центробежн' in vid or 'турбовозд' in vid)
                             and (d.get('uverennost') or '') != 'низкая' else '')
                    w.writerow({'marka': m, 'vid': vid, 'sereya': d.get('sereya') or '',
                                'proizvoditel': d.get('proizvoditel') or '',
                                'sreda': d.get('sreda') or '',
                                'uverennost': d.get('uverennost') or '',
                                'pochemu': (d.get('pochemu') or '')[:200],
                                'predpriyatiy': len(pred.get(m, ())),
                                'upominaniy': upom.get(m, 0),
                                'goditsya_dlya_poiska': godno,
                                'kto_razobral': '2-я сессия'})
                f.flush()
                print(f'  {min(nomer*pachka, len(nado))}/{len(nado)}: {sch}',
                      file=sys.stderr, flush=True)
    f.close()
    print(f'готово: {sch}\n→ {VYHOD}', file=sys.stderr)
    if sch['выдуманных строк']:
        print(f'ВНИМАНИЕ: провайдер вернул {sch["выдуманных строк"]} строк с марками, '
              'которых ему не посылали — отброшены заслоном', file=sys.stderr)


if __name__ == '__main__':
    main()
