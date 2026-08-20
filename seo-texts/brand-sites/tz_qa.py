#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка готовых ТЗ: пересечение скелетов и числа не из payload.

    python3 tz_qa.py [--tz tz/] [--jobs tz-jobs.json,station-jobs.json]
                     [--porog 40] [--pokazat 15]

Отвечает на вопрос владельца «у нас же не так будет?» - про 92% пересечения
между модульной азотной и модульной кислородной на prokompressor. Обещание
в шаблоне ТЗ не гарантирует ничего, гарантирует только замер, и делать его
надо СЕЙЧАС, по скелетам в ТЗ, а не потом по готовым текстам: переписать
задание стоит один прогон, переписать шестьдесят страниц - месяц.

Меряем две оси, и они про разное:

ВЕРТИКАЛЬ - страницы одного сайта. Это каннибализация: две наши страницы
дерутся за один запрос, и поиск показывает не ту. Именно тут был провал
на prokompressor.

ГОРИЗОНТАЛЬ - одна тема на разных сайтах. Это НЕ каннибализация (владелец
прав: пусть человек зайдёт хоть на все домены выдачи), это риск
аффилиат-фильтра Яндекса. Он снимает все домены одного владельца, кроме
одного, и одинаковый скелет на двенадцати доменах - сильный признак сетки.

Нормализация заголовков снимает то, чем страницы отличаются заведомо:
название газа, тип станции, бренд и падежные окончания. «Как рассчитывается
азотная станция» и «Как рассчитывается кислородная станция» после неё -
один и тот же блок, и это правильно: содержание там одинаковое.

Второй проверкой ловим числа, которых нет в payload. ТЗ на винтовые BERG
велело копирайтеру поставить в таблицу «шум ниже на 2-4 дБА», «КПД выше
на 3-5%», «цена дороже на 15-20%». Ни одной из этих цифр в наших данных
нет, они сочинены. Если такое уедет в текст, его прочитает инженер
заказчика.
"""
import argparse, itertools, json, os, re, sys

DIR = os.path.dirname(os.path.abspath(__file__))

# Слова, которые снимаем при нормализации: ими страницы отличаются заведомо,
# и оставлять их значит объявить непохожими одинаковые по сути блоки.
SNYAT = re.compile(
    r'\b(азотн\w*|кислородн\w*|азота|кислорода|газов\w*|'
    r'модульн\w*|стационарн\w*|контейнерн\w*|блок-контейнер\w*|'
    r'станци\w*|установк\w*|компрессорн\w*|компрессор\w*|модул\w*)\b',
    re.I)
OKONCH = re.compile(r'(ый|ой|ая|ое|ые|ого|ому|ыми|ах|ов|ам|ем|ей|ий|их|им|ую|юю)\b')


def brendy():
    p = os.path.join(DIR, 'brands-allow.json')
    return sorted(json.load(open(p, encoding='utf-8')), key=len, reverse=True)


def norm(h, br):
    h = h.lower()
    for b in br:
        h = h.replace(b.lower(), ' ')
    h = SNYAT.sub(' ', h)
    h = OKONCH.sub('', h)
    h = re.sub(r'[^а-яa-z0-9 ]', ' ', h)
    return ' '.join(sorted(w for w in h.split() if len(w) > 2))


# Заголовок блока приходит в трёх видах, генератор не держит один формат:
#   '### H2: Как выбрать модель', '### Блок 3. Своя генерация (H2)', 'H2: ...'
NUMER = re.compile(r'^(блок|раздел)\s*\d+\s*[.):]?\s*', re.I)
POMETA = re.compile(r'\s*\((?:[^()]*\bh2\b[^()]*)\)\s*$', re.I)
SLUZHEBNYE = re.compile(r'^(первый экран|payload|состав заявки|faq|'
                        r'финальн\w+ призыв|блок доказательства)', re.I)


def skelet(text, br):
    """Заголовки блоков из раздела «Подробная структура страницы»."""
    m = re.search(r'^#{1,3}\s*6\..*?$(.*?)(?=^#{1,3}\s*7\.)', text, re.M | re.S)
    zona = m.group(1) if m else text
    out = []
    for line in zona.splitlines():
        h = re.match(r'^#{2,4}\s*(.+?)\s*$', line)
        h = h.group(1) if h else re.match(r'^\**H2\**\s*[:\-]\s*(.+?)\s*$', line)
        if h is None:
            continue
        t = (h if isinstance(h, str) else h.group(1)).strip(' *')
        t = POMETA.sub('', NUMER.sub('', t))
        t = re.sub(r'^\**H2\**\s*[:\-]\s*', '', t).strip(' *')
        # Служебные блоки есть у каждой страницы, они не признак похожести
        # и не признак различия: считать их значит завышать пересечение.
        if len(t) > 3 and not SLUZHEBNYE.match(t):
            out.append(t)
    return [n for n in (norm(h, br) for h in out) if n]


def peresech(a, b):
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return 100.0 * len(sa & sb) / min(len(sa), len(sb))


# --- числа --------------------------------------------------------------

CHISLO = re.compile(r'(?<![\w,.])(\d{1,3}(?:[  ]\d{3})*|\d+)(?:[.,](\d+))?')
# Единицы, за которыми число - это утверждение о технике, а не нумерация списка
# и не объём текста. Проценты и дБА сюда же: ими сочиняют «тише на 3 дБА».
EDINICY = re.compile(
    r'\s*(кВт|бар|л/мин|м3/мин|м³/мин|литр\w*|л\b|дБА|дБ|%|процент\w*|'
    r'мото?час\w*|час\w*|мес\w*|год\w*|лет\b|руб\w*|₽)', re.I)
# Строки, где числа законны: объём текста, знаки, нумерация разделов, даты.
IGNOR = re.compile(r'знак|символ|ISO|ГОСТ|СанПиН|СП |раздел|пункт|8573|15150|'
                   r'янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек', re.I)


def chisla_v_payload(job):
    """Все числа задания в виде строк, включая округления и части диапазонов."""
    out = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, (int, float)):
            out.add(f'{v:g}')
            out.add(f'{round(float(v)):g}')
        elif isinstance(v, str):
            for m in CHISLO.finditer(v):
                out.add(m.group(1).replace(' ', '').replace(' ', ''))
    walk(job.get('payload'))
    # порядки округления: 598 -> 590, 600
    for s in list(out):
        if s.isdigit() and len(s) >= 2:
            n = int(s)
            out.update({f'{n // 10 * 10}', f'{n // 100 * 100}', f'{round(n, -1)}'})
    return out


def levye_chisla(text, znaem):
    """Числа с технической единицей, которых нет в payload."""
    bad = {}
    for line in text.splitlines():
        if IGNOR.search(line):
            continue
        for m in CHISLO.finditer(line):
            if not EDINICY.match(line[m.end():]):
                continue
            s = m.group(1).replace(' ', '').replace(' ', '')
            if s in znaem or len(s) < 2:
                continue
            ed = EDINICY.match(line[m.end():]).group(1)
            bad.setdefault(f'{s} {ed}', line.strip()[:110])
    return bad


# --- прогон -------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tz', default=os.path.join(DIR, 'tz'))
    ap.add_argument('--jobs', default='tz-jobs.json,station-jobs.json')
    ap.add_argument('--porog', type=float, default=40.0)
    ap.add_argument('--pokazat', type=int, default=15)
    a = ap.parse_args()

    br = brendy()
    jobs = {}
    for name in a.jobs.split(','):
        p = os.path.join(DIR, name.strip())
        if os.path.exists(p):
            for j in json.load(open(p, encoding='utf-8')):
                jobs[j['slug']] = j

    sk, ch = {}, {}
    for name in sorted(os.listdir(a.tz)):
        if not name.endswith('.md'):
            continue
        slug = name[3:-3]
        text = open(os.path.join(a.tz, name), encoding='utf-8').read()
        sk[slug] = skelet(text, br)
        if slug in jobs:
            ch[slug] = levye_chisla(text, chisla_v_payload(jobs[slug]))

    print(f'ТЗ прочитано: {len(sk)}, порог пересечения {a.porog:g}%\n')
    pust = [s for s, v in sk.items() if len(v) < 4]
    if pust:
        print(f'! скелет не разобрался или короче четырёх H2: {len(pust)}')
        for s in pust[:5]:
            print('   ', s, f'({len(sk[s])} H2)')
        print()

    def os_pary(kluch, imya):
        gr = {}
        for s in sk:
            gr.setdefault(kluch(s), []).append(s)
        pary = []
        for g, ss in gr.items():
            for x, y in itertools.combinations(sorted(ss), 2):
                p = peresech(sk[x], sk[y])
                if p >= a.porog:
                    pary.append((p, x, y))
        pary.sort(reverse=True)
        vsego = sum(len(list(itertools.combinations(v, 2))) for v in gr.values())
        print(f'== {imya}: пар {vsego}, выше порога {len(pary)}')
        for p, x, y in pary[:a.pokazat]:
            obshch = sorted(set(sk[x]) & set(sk[y]))
            print(f'   {p:5.1f}%  {x}')
            print(f'           {y}   общих блоков {len(obshch)}')
        if not pary:
            print('   чисто')
        print()
        return pary

    site = lambda s: s.split('--')[0]
    tema = lambda s: s.split('--', 1)[1] if '--' in s else s
    v = os_pary(site, 'ВЕРТИКАЛЬ, страницы одного сайта (каннибализация)')
    g = os_pary(tema, 'ГОРИЗОНТАЛЬ, одна тема на разных сайтах (аффилиат-фильтр)')

    print('== ЧИСЛА, КОТОРЫХ НЕТ В PAYLOAD')
    plohie = {s: d for s, d in ch.items() if d}
    print(f'   ТЗ с сочинёнными числами: {len(plohie)} из {len(ch)}')
    for s, d in sorted(plohie.items(), key=lambda t: -len(t[1]))[:a.pokazat]:
        print(f'   {s}: {len(d)}')
        for k, line in list(d.items())[:3]:
            print(f'       {k:<14} <- {line}')
    print()
    print(f'ИТОГ: вертикаль {len(v)} пар выше порога, горизонталь {len(g)}, '
          f'ТЗ с левыми числами {len(plohie)}')
    return 1 if (v or plohie) else 0


if __name__ == '__main__':
    sys.exit(main())
