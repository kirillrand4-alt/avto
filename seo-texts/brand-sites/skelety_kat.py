#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разводка скелетов категорийных страниц. Только горизонталь.

    python3 skelety_kat.py [--jobs tz-jobs.json] [--out skelety-kat.json]

ЧЕМ ОТЛИЧАЕТСЯ ОТ СТАНЦИОННОЙ РАЗВОДКИ. У станций разводить надо было обе
оси: внутри сайта родительская азотная норовила совпасть с модульной,
потому что обе про один газ. У категорий вертикаль безопасна сама собой -
винтовые, осушители, фильтры и сепараторы это разные товары, им нечем
совпасть. Опасна только горизонталь: «осушители сжатого воздуха»
на одиннадцати доменах пишутся по одной физике и сходятся к одному тексту.

Поэтому здесь один проход: вызов на тему, в нём все сайты с этой темой
разом, как dedup_jobs.py в гост-постах.

ЧЕМ РАЗВОДИМ. У категорий есть то, чего у станций не было: РАЗНЫЙ ТОВАР.
У ABAC винтовые 2,2-75 кВт, у ЗИФ 5,5-711 кВт - это не оттенок подачи,
это разные машины для разных задач, и страницы обязаны читаться по-разному
уже поэтому. Плюс угол сайта, посчитанный по его каталогу для станций,
работает и здесь.

ЗАЩИЩЁННОЕ. Список короче станционного, потому что у товарной категории
несущая тема по сути одна - как выбрать нужное исполнение. Её и держим
на всех сайтах, вместе с блоком под угол сайта. Остальное разводится.
"""
import argparse, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
sys.path.insert(0, DIR)
import gen_provider as G
from tz_qa import norm, peresech, brendy
from skelety import SLUZHEBNYE, proverit

# У товарной категории несущих тем две, и обе про решение о покупке.
# Держат их все сайты, формулируют под свой ассортимент.
NESUSHCHIE_KAT = {
    'подбор по параметрам': r'подбор|выбрат|выбор|как подобрать|под задачу|'
                            r'по расходу|по давлен|по мощност|исполнен',
    # Четвёртый случай, когда моя регулярка бракует исправный скелет:
    # «Капитальные затраты и операционные расходы» это ровно цена владения,
    # а знала регулярка только «расходы на». Ключевые слова всегда уже,
    # чем язык, поэтому список форм ведём щедро.
    'что влияет на цену и владение':
        r'цен|стоимост|владен|обслуживан|расход\w*|экономи|окупа|сервис|'
        r'затрат|капитальн|операционн|бюджет|во сколько',
}


# Страницы, где предмет - отдельный узел, а не станция. На них угол сайта
# особенно опасен: он station-shaped почти у всех доменов.
KOMPLEKTUYUSHCHIE = ('циклонные сепараторы и влагоотделители',
                     'магистральные фильтры', 'осушители сжатого воздуха',
                     'ресиверы')

# ЧУЖАЯ СТРАНИЦА. Владелец 21.08 нашёл, что в скелете винтовых KRAFTMANN
# пять блоков из тринадцати про высокое давление и дожим - при том что
# у винтовых 7-15 бар, а дожимные это ОТДЕЛЬНАЯ страница того же сайта
# на 15-40 бар. Замер по сетке: одиннадцать страниц уводят на соседнюю,
# и KRAFTMANN среди них четырежды, всегда в сторону дожимных.
#
# Причина та же, что с сепараторами Ремезы, только шире: угол сайта
# (у KRAFTMANN - «станция с дожимом до высокого давления») протекает
# на ВСЕ страницы домена. Прежняя защита стояла только на четырёх типах
# комплектующих, а надо на всех.
#
# Правило простое и проверяемое: если у сайта есть отдельная страница
# под тему X, ни одна другая его страница не несёт больше ОДНОГО блока
# про X. Один блок это перелинковка, три - это уже не та страница.
MARKERY_TEM = {
 'дожимные компрессоры и бустеры': r'дожим|бустер|высок\w* давлен|\b[2-9]\d\s*бар|пэт\b',
 'осушители сжатого воздуха': r'осушител|точк\w* рос|рефрижератор',
 'магистральные фильтры': r'фильтрац|магистральн\w* фильтр|картридж',
 'циклонные сепараторы и влагоотделители': r'циклон|влагоотделит|сепаратор',
 'ресиверы': r'воздухосборник',
 'спиральные компрессоры': r'спиральн',
 'поршневые компрессоры': r'поршнев',
 'дизельные компрессоры': r'дизельн|передвижн\w* компрессор',
 'центробежные компрессоры': r'центробежн',
 'генераторы азота': r'генератор\w* азота|азотн\w* установк',
 'генераторы кислорода': r'генератор\w* кислород',
}


def chuzhie_bloki(tema, bloki, temy_sayta, predel=1):
    """Блоки, уводящие на другую страницу этого же сайта."""
    import re as _re
    out = {}
    for chuzhaya, rx in MARKERY_TEM.items():
        if chuzhaya == tema or chuzhaya not in temy_sayta:
            continue
        n = sum(1 for h in bloki if _re.search(rx, h, _re.I))
        if n > predel:
            out[chuzhaya] = n
    return out
import re as _re
STANCIYA = _re.compile(r'станци|модул\w*\b|целиком|одной марки|в составе|'
                       r'обвязк|заводск\w* комплектац|фабричн', _re.I)


def nedostayushchie(bloki):
    import re
    t = ' | '.join(bloki).lower()
    return [k for k, rx in NESUSHCHIE_KAT.items() if not re.search(rx, t, re.I)]


def prompt(tema, jobs, ugly):
    dannye = {}
    for j in jobs:
        p = j['payload']
        f = lambda v: f'{v[0]:g}-{v[1]:g}' if v else None
        dannye[j['site']] = {
            'бренд': j['brand'],
            'угол сайта': ugly.get(j['site'], 'не посчитан'),
            'позиций': p.get('n'),
            'кВт': f(p.get('power_kw')), 'бар': f(p.get('pressure_bar')),
            'л/мин': f(p.get('flow_lmin')),
            'безмасляных': p.get('oilfree'), 'с частотником': p.get('vfd'),
            'с ресивером': p.get('with_receiver'), 'с осушителем': p.get('with_dryer'),
            'ведущий вопрос': j['lead_question'],
        }
    return f"""Перед тобой страница «{tema}» на {len(jobs)} сайтах одной компании.
Каждый сайт торгует своим брендом, и товар у них РАЗНЫЙ.

{json.dumps(dannye, ensure_ascii=False, indent=1)}

ЗАДАЧА. Дай для каждого сайта список заголовков H2 так, чтобы страницы
не читались как один текст с подменённым названием бренда. Поисковик,
увидев столько доменов одного владельца с одинаковым скелетом, оставит
в выдаче один и уберёт остальные.

ЧЕМ РАЗВОДИТЬ, В ПОРЯДКЕ СИЛЫ:
1. РАЗНЫЙ ТОВАР, это главное. Линейка 2,2-75 кВт и линейка 5,5-711 кВт -
   это машины для разных задач: у первой разговор про цех и мастерскую,
   у второй про непрерывное производство и каскады. Смотри числа каждого
   сайта и стройте страницу от них. Где безмасляных ноль - тема чистоты
   воздуха решается фильтрацией, где их сотня - разговор совсем другой.
2. УГОЛ САЙТА - НО ОН ОТЛИЧИЕ, А НЕ ПРЕДМЕТ. Угол окрашивает два-три
   блока, не больше. Предмет страницы остаётся её товаром.

   Проверено на готовых скелетах: у Ремезы угол «станция целиком одной
   марки», и разводка провела его через ВСЮ страницу циклонных сепараторов -
   девять блоков из одиннадцати оказались про станцию: «сепаратор в составе
   готовых станций», «стоимость готовой станции с сепаратором в обвязке»,
   «обслуживание станции целиком». Человек, который ищет «влагоотделитель
   Remeza купить» или модель WS001, у него УЖЕ ЕСТЬ компрессор, и ему
   продают станцию за миллион вместо узла за тридцать тысяч. Страница
   при этом идеально уникальна - и бесполезна.

   Поэтому: блоков, где ведущее слово «станция», «модуль», «целиком»,
   «в составе», «обвязка», на странице комплектующего должно быть
   НЕ БОЛЬШЕ ТРЁХ. Остальные - про сам узел: модели и типоразмеры,
   подбор под имеющийся компрессор, монтаж в существующую магистраль,
   обслуживание и расходники, от чего зависит цена узла.
3. ГЛУБИНА И СЦЕНАРИЙ. Одному домену разбор подбора, другому разбор
   эксплуатации, третьему разбор того, где это НЕ подходит.

НЕ РАЗВОДИТЬ СИНОНИМАМИ. «Как выбрать» и «Критерии выбора» - это один
и тот же блок, так нельзя.

ЧЕГО ВЫНОСИТЬ НЕЛЬЗЯ. Эти темы держат ВСЕ сайты, разница в формулировке
и в том, от каких чисел они идут:
{chr(10).join('   - ' + k for k in NESUSHCHIE_KAT)}
Без них страница перестаёт помогать выбирать и заявку с неё не оставят.
Прошлый заход на станционных страницах вынес такой блок с десяти страниц
из двенадцати ради непохожести - так делать нельзя.

СЛУЖЕБНЫЕ БЛОКИ обязательны на каждой странице, они одинаковые везде
и это правильно: {json.dumps(SLUZHEBNYE, ensure_ascii=False)}. Первый экран
идёт первым, остальные три в конце, в этом порядке.

Содержательных блоков (кроме служебных) не меньше девяти.
Заголовков со знаком вопроса не ставить. Длинных тире не ставить.

ОТВЕТ - только JSON: {{"<сайт>": ["Первый экран", "<H2>", ..., "Финальный призыв"]}}
Все {len(jobs)} сайтов, ключи ровно как в данных выше."""


def po_teme(tema, jobs, ugly, br, porog, model, temy_po_saytu=None, zahodov=3):
    temy_po_saytu = temy_po_saytu or {}
    msgs = [{'role': 'user', 'content': prompt(tema, jobs, ugly)}]
    nuzhno = {j['site'] for j in jobs}
    t0, last = time.time(), ''
    sk = {}
    for k in range(zahodov):
        msg = G.call(None, msgs, model=model, attempts=4, max_tokens=32000)
        text = ''.join(b.text for b in msg.content if b.type == 'text').strip()
        try:
            syr = G.parse_json(msg)
        except Exception as e:
            last = f'не JSON: {repr(e)[:100]}'
            msgs = msgs[:1] + [{'role': 'user', 'content': 'Только JSON. Повтори.'}]
            continue
        sk = {s: [h.replace('—', '-').replace('–', '-').strip() for h in v]
              for s, v in syr.items() if isinstance(v, list)}
        if set(sk) != nuzhno:
            last = f'не те ключи: нет {sorted(nuzhno - set(sk))[:3]}'
        else:
            plohie = proverit(sk, br, porog)
            poteri = {s: nedostayushchie(v) for s, v in sk.items()}
            poteri = {s: v for s, v in poteri.items() if v}
            tonkie = [s for s, v in sk.items()
                      if len([h for h in v if h not in SLUZHEBNYE]) < 9]
            # Угол не должен съедать предмет страницы: на комплектующих
            # больше трёх «станционных» блоков означает, что страница
            # продаёт не то, что человек искал.
            sozhran = {}
            if tema in KOMPLEKTUYUSHCHIE:
                for st, v in sk.items():
                    soder = [h for h in v if h not in SLUZHEBNYE]
                    n = sum(1 for h in soder if STANCIYA.search(h))
                    if n > 3:
                        sozhran[st] = (n, len(soder))
            if not plohie and not poteri and not tonkie and not sozhran:
                return tema, sk, f'чисто с {k + 1}-го захода', time.time() - t0
            last = (f'{len(plohie)} пар выше {porog:g}%'
                    + (f', потеряны темы у {len(poteri)}' if poteri else '')
                    + (f', тонких {len(tonkie)}' if tonkie else '')
                    + (f', угол съел предмет у {len(sozhran)}' if sozhran else ''))
            zam = [f'{x} и {y}: {p:.0f}%, общее: {"; ".join(o[:4])}'
                   for p, x, y, o in plohie[:5]]
            zam += [f'{s}: пропали обязательные темы - {"; ".join(v)}'
                    for s, v in list(poteri.items())[:5]]
            if tonkie:
                zam.append('мало блоков (нужно 9) у: ' + ', '.join(tonkie[:6]))
            for st, c in list(chuzhie.items())[:5]:
                kak = '; '.join(f'{k}: {v} блоков' for k, v in c.items())
                zam.append(f'{st}: страница уводит на ДРУГИЕ страницы этого же '
                           f'сайта ({kak}). У сайта под эти темы есть свои '
                           f'страницы. Оставь не больше одного блока '
                           f'на перелинковку, остальные переделай про «{tema}»')
            for st, (n, vs) in list(sozhran.items())[:5]:
                zam.append(f'{st}: {n} блоков из {vs} про станцию, а страница '
                           f'про «{tema}». Оставь не больше трёх, остальные '
                           f'переделай про сам узел: модели, подбор '
                           f'под имеющийся компрессор, монтаж в магистраль, '
                           f'обслуживание, от чего зависит цена узла')
            msgs = msgs[:1] + [
                {'role': 'assistant', 'content': text},
                {'role': 'user', 'content': 'Не сошлось: ' + last + '.\n'
                 + '\n'.join(zam) + '\nСовпадения разводи разным товаром '
                 'и сценарием, а не удалением темы. Обязательные темы верни '
                 'всем. Ответ - только JSON.'}]
    return tema, sk, f'НЕ СОШЛОСЬ: {last}', time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', default=os.path.join(DIR, 'tz-jobs.json'))
    ap.add_argument('--out', default=os.path.join(DIR, 'skelety-kat.json'))
    ap.add_argument('--porog', type=float, default=40.0)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--model', default='claude-fable-5')
    a = ap.parse_args()

    jobs = json.load(open(a.jobs, encoding='utf-8'))
    br = brendy()
    # Углы сайтов уже посчитаны для станций, берём их же.
    ugly = {}
    p = os.path.join(DIR, 'station-jobs.json')
    if os.path.exists(p):
        for j in json.load(open(p, encoding='utf-8')):
            ugly.setdefault(j['site'], j['ugol_etogo_sayta']['tema'])

    po_temam = {}
    for j in jobs:
        po_temam.setdefault(j['topic'].split(' (')[0], []).append(j)
    # Тема на одном сайте разводить не с кем, скелет ей напишет само ТЗ.
    odinochki = [t for t, v in po_temam.items() if len(v) < 2]
    for t in odinochki:
        po_temam.pop(t)

    temy_po_saytu = {}
    for j in jobs:
        temy_po_saytu.setdefault(j['site'], set()).add(j['topic'].split(' (')[0])

    gotovo = json.load(open(a.out, encoding='utf-8')) if os.path.exists(a.out) else {}
    ostalos = [t for t in po_temam if t not in gotovo]
    print(f'тем к разводке: {len(ostalos)}, одиночек пропущено: {len(odinochki)}',
          flush=True)

    def sohranit():
        with open(a.out, 'w', encoding='utf-8') as fh:
            json.dump(gotovo, fh, ensure_ascii=False, indent=1)
            fh.flush(); os.fsync(fh.fileno())

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(po_teme, t, po_temam[t], ugly, br, a.porog, a.model,
                          temy_po_saytu): t
                for t in ostalos}
        for f in as_completed(futs):
            try:
                tema, sk, info, sec = f.result()
                if sk:
                    gotovo[tema] = sk
                    sohranit()
                print(f'  {tema}: {info} за {sec:.0f} с', flush=True)
            except Exception as e:
                print(f'  СБОЙ {futs[f]}: {repr(e)[:180]}', file=sys.stderr, flush=True)

    sohranit()
    print(f'\nтем разведено: {len(gotovo)} -> {a.out}')


if __name__ == '__main__':
    main()
