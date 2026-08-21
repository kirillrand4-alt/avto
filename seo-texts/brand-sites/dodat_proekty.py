#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Подкладывает реальные проекты в задания на ТЗ.

    python3 dodat_proekty.py [--jobs tz-jobs.json,station-jobs.json]

ЗАЧЕМ. Вычитка владельца поставила экспертности 7/10: «не хватает реальных
расчётов, проектов, документов». Проекты у нас есть и лежали мимо: в
projects-index.json 1018 реализованных поставок, из них 705 по брендам
нашей сетки, с оборудованием, отраслью, городом и датой. ТЗ про них не
знали, поэтому блок доказательства во всех 133 заданиях описан общими
словами - «фото объекта или обезличенный проект».

ОБЕЗЛИЧИВАНИЕ. Владелец: «кейсы обезличено публикуем на саттелитах».
Название клиента в задание НЕ кладём вовсе - не «сократить», а не давать:
чего нет в задании, то копирайтер не напишет. Остаются отрасль, город,
модель и год - этого хватает, чтобы проект читался как настоящий.

ЧЕГО НЕ ДЕЛАЕМ. Не выдумываем проекты тем, у кого их нет. У Kraftmann
в индексе ноль поставок, и его задания получат честное «проектов по
этому бренду в индексе нет, блок доказательства строить на фотографиях
из банка или запросить у владельца».

ОТКАТ. Перед правкой заданий рядом кладётся копия .do-proektov.json,
и `--otkat` возвращает всё как было одной командой. Правка идёт в файлы,
из которых генерируются 133 ТЗ, поэтому откат должен быть, а не
«восстановим из гита, если что».

ДВА РЕЖИМА ОБЕЗЛИЧИВАНИЯ. По умолчанию в задание идут отрасль, город,
модель и год. Город в паре с узкой отраслью иногда указывает на конкретное
предприятие - в городе может быть один мясокомбинат. Если это смущает,
`--bez-goroda` убирает город и оставляет отрасль, модель и год: проект
всё ещё читается как настоящий, но опознать заказчика по нему нельзя.
"""
import argparse, collections, json, os, re, sys

DIR = os.path.dirname(os.path.abspath(__file__))
SEO = os.path.dirname(DIR)

# Как бренд записан в индексе проектов -> сайт сетки.
SAYT = {
    'abac': 'abac-kompressor.ru', 'atlas copco': 'ac-kompressor.ru',
    'berg': 'berg-kompressor.ru', 'cross air': 'crossair-compressor.ru',
    'dali': 'dali-kompressor.ru', 'ekomak': 'ekomak-kompressor.com',
    'enger': 'enger-air.ru', 'fini': 'fini-compressor.com',
    'ironmac': 'ironmac-compressor.com', 'kraftmann': 'kraftmann-kompressor.com',
    'remeza': 'remeza-kompressor.ru', 'зиф': 'zif-kompressor.ru',
}
# Тема страницы -> по каким словам в описании оборудования её узнать.
POD_TEMU = {
    'винтовые компрессоры': r'винтов',
    'поршневые компрессоры': r'поршнев',
    'спиральные компрессоры': r'спиральн',
    'дизельные компрессоры': r'дизельн|передвижн',
    'осушители сжатого воздуха': r'осушител',
    'магистральные фильтры': r'фильтр',
    'циклонные сепараторы и влагоотделители': r'сепаратор|влагоотделит|циклон',
    'ресиверы': r'ресивер',
    'дожимные компрессоры и бустеры': r'дожим|бустер|высокого давлен',
    'центробежные компрессоры': r'центробежн',
    'генераторы азота': r'азот',
    'генераторы кислорода': r'кислород',
    'kompressornaya-stanciya': r'станц|компрессорн',
    'mks': r'модульн|контейнер|станц',
    'azotnaya-stanciya': r'азот',
    'azotnaya-stanciya-modulnaya': r'азот',
    'kislorodnaya-stanciya': r'кислород',
    'kislorodnaya-stanciya-modulnaya': r'кислород',
}
GOD = re.compile(r'(20\d\d)')


# Поля журнала, которые в задание не попадают НИКОГДА. Не «сокращаем»
# имя заказчика, а не даём его вовсе: чего нет в задании, того копирайтер
# не напишет. Владелец: «кейсы обезличено публикуем на саттелитах».
NELZYA = ('client', 'title', 'h1', 'url', 'narrative', 'service')


def chistyy(p, bez_goroda=False):
    """Проект без имени клиента, с тем, что можно писать."""
    g = GOD.search(p.get('date') or '')
    out = {
        'отрасль': p.get('sphere') or None,
        'оборудование': (p.get('equipment') or '').strip().strip('"') or None,
        'год': g.group(1) if g else None,
    }
    if not bez_goroda:
        out['город'] = p.get('city') or p.get('city_guess') or None
    return out


def podobrat(vse, tema, predel=8, bez_goroda=False):
    """Проекты под тему страницы, по одному на отрасль, свежие вперёд."""
    rx = POD_TEMU.get(tema)
    podhod = [p for p in vse
              if not rx or re.search(rx, (p.get('equipment') or ''), re.I)]
    if not podhod:
        # Прежде тут молча брались ВСЕ проекты бренда, и задание получало
        # текст «реальные поставки этого бренда» с проектами не по теме.
        # Замер красной команды: 101 задание из 122 получило чужие проекты,
        # включая все станционные. На странице азотной станции блок
        # доказательства строился на поставке винтового компрессора.
        # Проект настоящий, бренд верный - а страница врёт об опыте.
        return [], 0
    podhod.sort(key=lambda p: (GOD.search(p.get('date') or '') or ['0'])[0],
                reverse=True)
    # Разные отрасли информативнее восьми поставок в один цех.
    vzyato, sfery = [], collections.Counter()
    for p in podhod:
        s = p.get('sphere') or '-'
        if sfery[s] >= 2:
            continue
        sfery[s] += 1
        vzyato.append(chistyy(p, bez_goroda))
        if len(vzyato) >= predel:
            break
    return vzyato, len(podhod)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', default='tz-jobs.json,station-jobs.json')
    ap.add_argument('--proekty', default=os.path.join(SEO, 'projects-index.json'))
    ap.add_argument('--bez-goroda', action='store_true',
                    help='не класть город: отрасль, модель и год')
    ap.add_argument('--otkat', action='store_true',
                    help='вернуть задания к состоянию до подкладывания проектов')
    a = ap.parse_args()

    if a.otkat:
        for name in a.jobs.split(','):
            path = os.path.join(DIR, name.strip())
            kopiya = path.replace('.json', '.do-proektov.json')
            if not os.path.exists(kopiya):
                print(f'  {name}: копии нет, откатывать не от чего')
                continue
            jobs = json.load(open(kopiya, encoding='utf-8'))
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(jobs, fh, ensure_ascii=False, indent=1)
                fh.flush(); os.fsync(fh.fileno())
            print(f'  {name}: откачено к {len(jobs)} заданиям без проектов')
        return

    vse = json.load(open(a.proekty, encoding='utf-8'))
    po_saytu = collections.defaultdict(list)
    for p in vse:
        s = SAYT.get((p.get('brand') or '').strip().lower())
        if s:
            po_saytu[s].append(p)
    print(f'проектов в индексе {len(vse)}, по сайтам сетки '
          f'{sum(len(v) for v in po_saytu.values())}')

    for name in a.jobs.split(','):
        path = os.path.join(DIR, name.strip())
        jobs = json.load(open(path, encoding='utf-8'))
        kopiya = path.replace('.json', '.do-proektov.json')
        if not os.path.exists(kopiya):        # копию делаем один раз, до первой правки
            with open(kopiya, 'w', encoding='utf-8') as fh:
                json.dump(jobs, fh, ensure_ascii=False, indent=1)
                fh.flush(); os.fsync(fh.fileno())
        pusto = 0
        for j in jobs:
            tema = j['topic'].split(' (')[0]
            if tema not in POD_TEMU:
                tema = j['slug'].split('--', 1)[1]
            vzyato, vsego = podobrat(list(po_saytu.get(j['site'], [])), tema,
                                     bez_goroda=a.bez_goroda)
            if vzyato:
                j['proekty'] = vzyato
                j['proektov_vsego_po_brendu'] = len(po_saytu.get(j['site'], []))
                j['_pro_proekty'] = (
                    'Реальные поставки этого бренда из журнала проектов. '
                    'Имён заказчиков здесь нет намеренно: на брендовых сайтах '
                    'кейсы публикуем обезличенно. Писать можно отрасль, город, '
                    'модель и год. Блок доказательства строится на них, '
                    'а не на общих словах.')
            else:
                pusto += 1
                j['proekty'] = []
                j['_pro_proekty'] = (
                    'Проектов по этому бренду в журнале нет. Блок '
                    'доказательства строить на фотографиях с поставок '
                    'или написать «данных нет, запросить у владельца». '
                    'Проекты НЕ ВЫДУМЫВАТЬ.')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(jobs, fh, ensure_ascii=False, indent=1)
            fh.flush(); os.fsync(fh.fileno())
        est = len(jobs) - pusto
        print(f'  {name}: проекты подложены в {est} заданий из {len(jobs)}, '
              f'без проектов {pusto}')


if __name__ == '__main__':
    main()
