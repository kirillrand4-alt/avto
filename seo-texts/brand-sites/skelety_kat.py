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
import argparse, json, os, re as _re, sys, time
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


# Девятый случай, когда моя проверка бракует исправную работу, и причина
# та же, что в прошлые восемь: проверка ищет СЛОВО, а судить надо
# о ПРЕДМЕТЕ. Замер пометил одиннадцать страниц, и на разборе против
# payload выяснилось, что помечено в основном своё же:
#
#   фильтры KRAFTMANN  pressure_bar [16,50] - «фильтры от 16 до 50 бар»
#                      это их собственный паспорт, а не увод на дожимные;
#   поршневые Enger    pressure_bar [40,40] - «работает только на 40 барах»
#                      это факт поршневой линейки, вся она на 40 бар;
#   винтовые DALI      with_dryer 0 - «без ресивера и осушителя» это
#                      ОТСУТСТВИЕ осушителя, странице осушителей оно
#                      не принадлежит.
#
# Отсюда три правила, и все три опираются на данные страницы, а не на её
# слова: число в барах не чужое, если оно в пределах собственного давления
# страницы; отрицание не есть тема; перечисление узлов станции через
# запятую - это состав обвязки, а не разговор про каждый узел.
OTRITSANIE = _re.compile(r'\b(без|не|нет|отсутств\w*|вместо)\b[^,.;:]{0,40}$', _re.I)
BAR_CHISLO = _re.compile(r'(\d+(?:[.,]\d+)?)\s*бар', _re.I)


# Выше обычной цеховой сети. Ниже этой отметки «высокое давление»
# на странице - чужая тема, выше - её собственный паспорт.
VYSOKOE_BAR = 16.0
GOLOE_VD = _re.compile(r'высок\w*\s+давлен|высоконапорн', _re.I)


def _svoyo_davlenie(zagolovok, payload):
    """Разговор о давлении объясняется паспортом самой страницы.

    Два случая. Названы числа - все укладываются в её потолок. Числа
    не названы, сказано просто «высокое давление» - её потолок и правда
    высокий. У винтовых KRAFTMANN 7-15 бар, и там это чужая тема;
    у его же фильтров 16-50 бар, и там это они сами."""
    pb = (payload or {}).get('pressure_bar')
    if not pb:
        return False
    potolok = float(pb[1])
    chisla = [float(x.replace(',', '.')) for x in BAR_CHISLO.findall(zagolovok)]
    if chisla:
        return max(chisla) <= potolok * 1.001
    return bool(GOLOE_VD.search(zagolovok)) and potolok >= VYSOKOE_BAR


# Узлы обвязки. Названы два и более разом - это СОСТАВ станции,
# а не разговор про каждый узел: «станция с ресивером и осушителем»
# принадлежит странице станции, а не странице осушителей.
UZLY = (r'осушител', r'ресивер|воздухосборник', r'фильтр',
        r'сепаратор|влагоотделит|циклон', r'частотн|инвертор')


def _sostav(zagolovok):
    return sum(1 for u in UZLY if _re.search(u, zagolovok, _re.I)) >= 2


def _svoi_schet(zagolovok, payload):
    """Заголовок называет счёт из собственного payload страницы.

    «Встроенный осушитель в 6 моделях» на дизельной странице Cross Air:
    with_dryer там ровно 6. Это перепись СВОЕЙ линейки, а не разговор
    про осушители как товар."""
    p = payload or {}
    schet = {p.get(k) for k in ('n', 'vfd', 'oilfree',
                                'with_receiver', 'with_dryer')}
    schet = {int(v) for v in schet if isinstance(v, (int, float)) and v}
    if not schet:
        return False
    est = {int(x) for x in _re.findall(r'\b(\d{1,5})\b', zagolovok)}
    return bool(est & schet)


def _osnova_temy(tema):
    """Корни слов самой темы, чтобы узнавать её в заголовке."""
    out = []
    for w in _re.findall(r'[а-яё]{5,}', tema.lower()):
        out.append(_re.escape(w[:6]))
    return _re.compile('|'.join(out), _re.I) if out else None


def chuzhie_bloki(tema, bloki, temy_sayta, predel=1, payload=None):
    """Блоки, уводящие на другую страницу этого же сайта.

    Помечается только то, что уводит ПО СУЩЕСТВУ. Слово чужой темы,
    объяснимое собственными данными страницы, не улика."""
    svoya = _osnova_temy(tema)
    out = {}
    for chuzhaya, rx in MARKERY_TEM.items():
        if chuzhaya == tema or chuzhaya not in temy_sayta:
            continue
        n = 0
        for h in bloki:
            m = _re.search(rx, h, _re.I)
            if not m:
                continue
            # своё паспортное давление - не чужая тема
            if _svoyo_davlenie(m.group(0), payload) or _svoyo_davlenie(h, payload):
                continue
            # «без осушителя», «нет моделей с ресивером» - отсутствие узла
            if OTRITSANIE.search(h[:m.start()]):
                continue
            # «станция с ресивером и осушителем» - перечень состава
            if _sostav(h):
                continue
            # «осушитель в 6 моделях», где 6 - это with_dryer самой страницы
            if _svoi_schet(h, payload):
                continue
            # ПОДЛЕЖАЩЕЕ ПРОТИВ ДОПОЛНЕНИЯ. «Особенности ФИЛЬТРАЦИИ при
            # дожиме» - блок про фильтрацию, дожим тут условие. Если своя
            # тема названа в заголовке РАНЬШЕ чужого слова, чужое
            # подчинено, и страница остаётся про своё.
            svoy = svoya.search(h) if svoya else None
            if svoy and svoy.start() < m.start():
                continue
            n += 1
        if n > predel:
            out[chuzhaya] = n
    return out
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
    payl = {j['site']: j.get('payload') or {} for j in jobs}
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
            # Общее правило чужой страницы. Проверяется на КАЖДОЙ теме,
            # не только на комплектующих: угол протекает на весь домен.
            chuzhie = {}
            for st, v in sk.items():
                soder = [h for h in v if h not in SLUZHEBNYE]
                c = chuzhie_bloki(tema, soder, temy_po_saytu.get(st, set()),
                                  payload=payl.get(st))
                if c:
                    chuzhie[st] = c
            if not plohie and not poteri and not tonkie and not sozhran \
                    and not chuzhie:
                return tema, sk, f'чисто с {k + 1}-го захода', time.time() - t0
            last = (f'{len(plohie)} пар выше {porog:g}%'
                    + (f', потеряны темы у {len(poteri)}' if poteri else '')
                    + (f', тонких {len(tonkie)}' if tonkie else '')
                    + (f', угол съел предмет у {len(sozhran)}' if sozhran else '')
                    + (f', уводят на чужую страницу {len(chuzhie)}' if chuzhie else ''))
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
    # Переразвести только названные темы, остальные готовые не трогать.
    ap.add_argument('--temy', default='',
                    help='темы через ; - переразвести заново поверх готовых')
    ap.add_argument('--protekshie', action='store_true',
                    help='переразвести все темы, где хоть один сайт уводит '
                         'на свою же другую страницу')
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

    # Замер протечки по уже готовым скелетам: какие темы переделывать.
    payl = {}
    for j in jobs:
        payl.setdefault(j['topic'].split(' (')[0], {})[j['site']] = j.get('payload') or {}

    protekli = {}
    for tema, sk in gotovo.items():
        for st, v in sk.items():
            c = chuzhie_bloki(tema, [h for h in v if h not in SLUZHEBNYE],
                              temy_po_saytu.get(st, set()),
                              payload=(payl.get(tema) or {}).get(st))
            if c:
                protekli.setdefault(tema, {})[st] = c
    if protekli:
        print('протечка на чужую страницу в готовых скелетах:', flush=True)
        for tema, d in sorted(protekli.items()):
            for st, c in sorted(d.items()):
                kak = '; '.join(f'{k}: {v}' for k, v in c.items())
                print(f'   {tema} / {st}: {kak}', flush=True)

    zanovo = {t.strip() for t in a.temy.split(';') if t.strip()}
    if a.protekshie:
        zanovo |= set(protekli)
    neizvestnye = zanovo - set(po_temam)
    if neizvestnye:
        print(f'нет такой темы: {sorted(neizvestnye)}', file=sys.stderr)
        return 2
    ostalos = [t for t in po_temam if t not in gotovo or t in zanovo]
    print(f'тем к разводке: {len(ostalos)}'
          + (f' (из них заново {len(zanovo)})' if zanovo else '')
          + f', одиночек пропущено: {len(odinochki)}', flush=True)
    if not ostalos:
        print('нечего разводить')
        return 0

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
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
