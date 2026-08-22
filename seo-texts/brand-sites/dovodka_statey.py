#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Доводка статьи линзами: правки «цитата -> замена», применяет код.

    python3 dovodka_statey.py <slug> [<slug> ...] [--only engineer,logic]
    python3 dovodka_statey.py --vse

ОТКУДА ВЗЯТО. Механика приёмки гост-постов (guest-posts/finalize_gp.py,
17 линз, набор построен 03.08 методом «идеи от четырёх ИИ плюс судья
от каждого»). Владелец напомнил, что она у нас есть, и она сильнее того,
что я успел написать: там линза возвращает не сочинение, а строгий формат
с точными правками, и код применяет их детерминированно.

ПОЧЕМУ ЭТО ВАЖНЕЕ, ЧЕМ КАЖЕТСЯ. Три линзы на шести наших статьях дали
около ста восьмидесяти замечаний. Руками столько не применить, а значит
отчёт линз, каким бы точным он ни был, ляжет в папку и умрёт. Правка,
которую применяет код, доходит до текста.

ЧТО НЕ ПЕРЕНЕСЕНО И ПОЧЕМУ. Из семнадцати линз четыре гост-постовые:
link, platform, genre_bridge, audience_level - они про размещение
на чужой площадке с оплаченной ссылкой. У каталожной страницы нет ни
донора, ни оплаченной ссылки, и эти линзы там судили бы пустоту.
Остальные тринадцать переносятся как есть.

ЗАЩИТЫ ОТТУДА ЖЕ, И ИХ НЕ УБИРАТЬ - каждая оплачена аварией:
  _tags_intact  цитата захватывала середину тега, тег превращался
                в мусор, и три линзы потом весь круг чинили обломок;
  _overlaps     правки внутри круга применяются последовательно, линза N
                видит текст после предыдущих. Отсюда дребезг: neutral
                убирает оценочное слово, идущая следом language считает
                результат корявым и пишет обратно. В статью попадает
                вариант той линзы, что стояла позже, НЕ ПОТОМУ ЧТО ОНА
                ПРАВА. Конфликт зон = автоприёмки нет, даже если все
                линзы в итоге дали PASS.
"""
import argparse, os, re, sys, time

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
sys.path.insert(0, DIR)
import gen_provider as G
import gen_statya as S
import sanity

GP = os.path.join(os.path.dirname(DIR), 'guest-posts')
sys.path.insert(0, GP)

# Гост-постовые линзы, не имеющие смысла без донора и оплаченной ссылки.
CHUZHIE = ('link', 'platform', 'genre_bridge', 'audience_level')
KRUGOV = 2
MIN_ZONA = 12          # короче - союзы и предлоги, шум

# ДАТА. Линза engineer на первой же статье «исправила» 18 мая 2026 на 2025,
# обосновав это «датой из будущего». Сегодня 21 августа 2026 - май давно
# прошёл, дата пришла из payload и была верна. Линза внесла ошибку
# в исправный текст, а защиты её пропустили: они смотрят разметку
# и конфликты зон, но не смысл.
#
# Отсюда два вывода. Первый: модели нельзя доверять собственное
# представление о «сегодня» - оно из обучения, а не из календаря.
# Второй, общий: правки, меняющие ТОЛЬКО число, опаснее прочих, потому
# что выглядят аккуратной вычиткой. Числа в наших текстах уже прошли
# карту, payload и арифметические гейты - линза их не пересматривает.
SEGODNYA = os.environ.get('SEGODNYA', '21 августа 2026')
TOLKO_CHISLO = re.compile(r'^[^0-9]*(\d[\d\s.,:/-]*)[^0-9]*$')


def _linzy():
    """Роли из приёмки гост-постов, кроме завязанных на донора.

    Берём модуль целиком, а не разбираем текстом: словарь LENSES там
    собирается из четырёх кусков (LENSES, TEH_LENSES, EXTRA_LENSES,
    CHAIN_LENS) через update. Разбор первого куска регуляркой давал
    восемь линз вместо семнадцати - и молча, что хуже всего."""
    import importlib.util
    p = os.path.join(GP, 'finalize_gp.py')
    spec = importlib.util.spec_from_file_location('finalize_gp', p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['finalize_gp'] = mod
    spec.loader.exec_module(mod)
    return ({k: v for k, v in mod.LENSES.items() if k not in CHUZHIE},
            mod.FMT)


PRAVKA = re.compile(
    r'^\s*[«"`](.+?)[»"`]\s*->\s*[«"`](.*?)[»"`]\s*(?:\|\s*(.*))?$', re.M)


def razobrat(otvet):
    """(прошла ли линза, список правок)."""
    proshla = bool(re.search(r'ВЕРДИКТ:\s*PASS', otvet))
    pravki = [(a.strip(), b.strip(), (c or '').strip())
              for a, b, c in PRAVKA.findall(otvet)]
    return proshla, pravki


def _tegi_cely(html):
    """Разметка не поломана: теги открыты и закрыты, обломков нет."""
    if re.search(r'<[a-z]*<|>[^<>]*>>', html):
        return False
    for t in ('h2', 'p', 'table', 'tr', 'td'):
        if html.lower().count(f'<{t}') != html.lower().count(f'</{t}>'):
            return False
    return True


def _peresechenie(citata, zamena, tronuto):
    """Правит ли линза то, что уже правила другая - см. шапку модуля."""
    for chya, byla_c, byla_z in tronuto:
        for a, b in ((citata, byla_z), (byla_z, citata), (citata, byla_c)):
            a, b = (a or '').strip(), (b or '').strip()
            if len(a) >= MIN_ZONA and len(b) >= MIN_ZONA and (a in b or b in a):
                return chya, byla_c
    return None


def krug(html, sh, linzy, fmt, model, gazovaya, nomer, log):
    tronuto, provalili, primeneno = [], [], 0
    for imya, rol in linzy.items():
        tekst = S._tekst(html)
        zapros = (f'{rol}\n{fmt}\n\n=== ТЕКСТ СТРАНИЦЫ ===\n{tekst}\n'
                  f'=== КОНЕЦ ===\n\nЗаголовки H2 менять НЕЛЬЗЯ: набор блоков '
                  f'посчитан разводкой на двенадцати сайтах, и переименованный '
                  f'заголовок ломает замер на всей сетке.\n'
                  f'СЕГОДНЯ {SEGODNYA}. Даты в тексте пришли из данных '
                  f'компании и верны; «дату из будущего» не искать.')
        # СБОЙ ОДНОЙ ЛИНЗЫ НЕ ИМЕЕТ ПРАВА РОНЯТЬ ПРОГОН. Первый запуск
        # умер целиком на таймауте шлюза («стрим молчит 96 с, шлёт только
        # ping») - и шесть страниц остались вообще без правок, а я отдал
        # их владельцу как готовые. Правки остальных линз от этого
        # не зависят: каждая работает по своей цитате.
        try:
            msg = G.call(None, [{'role': 'user', 'content': zapros}],
                         model=model, attempts=3, max_tokens=8000,
                         thinking_on=False)
        except Exception as e:
            log.append(f'- круг {nomer} / {imya}: СБОЙ ПРОВАЙДЕРА, линза '
                       f'пропущена: {repr(e)[:120]}')
            provalili.append(f'{imya} (сбой связи)')
            continue
        otvet = ''.join(b.text for b in msg.content if b.type == 'text').strip()
        proshla, pravki = razobrat(otvet)
        if proshla and not pravki:
            log.append(f'- круг {nomer} / {imya}: PASS')
            continue
        vzyato = 0
        for citata, zamena, prichina in pravki[:4]:
            if citata not in html:
                log.append(f'  - {imya}: цитата не найдена дословно, мимо: '
                           f'{citata[:60]}')
                continue
            konflikt = _peresechenie(citata, zamena, tronuto)
            if konflikt:
                log.append(f'  - {imya}: КОНФЛИКТ с линзой {konflikt[0]} '
                           f'за зону «{konflikt[1][:50]}», правка отклонена')
                provalili.append('конфликт зон')
                continue
            novyy = html.replace(citata, zamena, 1)
            if not _tegi_cely(novyy):
                log.append(f'  - {imya}: правка ломает разметку, отклонена')
                continue
            if '—' in zamena or '–' in zamena:
                log.append(f'  - {imya}: в замене длинное тире, отклонена')
                continue
            # правка, меняющая только число: цифры уже проверены картой,
            # payload и арифметикой, линза их не пересматривает
            bez_c = re.sub(r'[\d\s.,:/-]+', '', citata)
            bez_z = re.sub(r'[\d\s.,:/-]+', '', zamena)
            if bez_c and bez_c == bez_z and citata != zamena:
                log.append(f'  - {imya}: правка меняет только число '
                           f'(«{citata[:40]}»), отклонена')
                continue
            # ПОТЕРЯ ЧИСЕЛ. Линза teh_skeptik «починила» запись стандарта:
            # «ISO 8573 1-4-1: без масла, с контролируемой влажностью,
            # без механических частиц» -> «ISO 8573-1 класс 1». По форме
            # права (стандарт и правда ISO 8573-1, а 1-4-1 это тройка
            # классов), но в замене осталась одна единица вместо трёх
            # позиций, и «класс 1» перестало значить что-либо: класс 1
            # по чему? Плюс исчезла расшифровка.
            #
            # Правило: замена не имеет права ТЕРЯТЬ числа, бывшие
            # в цитате. Наши числа прошли карту, payload и арифметику -
            # выбрасывать их линза не уполномочена. Полное удаление
            # фрагмента (пустая замена) - отдельный случай, оно
            # осознанное.
            chisla_c = re.findall(r'\d+(?:[.,]\d+)?', citata)
            chisla_z = re.findall(r'\d+(?:[.,]\d+)?', zamena)
            if zamena and len(chisla_c) > len(chisla_z):
                poteryany = [x for x in chisla_c if x not in chisla_z]
                log.append(f'  - {imya}: замена теряет числа '
                           f'{poteryany[:4]}, отклонена')
                continue
            html = novyy
            tronuto.append((imya, citata, zamena))
            vzyato += 1
            log.append(f'  - {imya}: «{citata[:45]}» -> «{zamena[:45]}» '
                       f'({prichina[:40]})')
        primeneno += vzyato
        log.append(f'- круг {nomer} / {imya}: '
                   f'{"PASS" if proshla else "FAIL"}, правок {vzyato}')
        if not proshla:
            provalili.append(imya)
    return html, primeneno, provalili


def odna(slug, out_dir, model, only=None):
    put = os.path.join(DIR, 'statyi', f'{slug}.html')
    ptz = os.path.join(DIR, 'tz', f'TZ-{slug}.md')
    if not (os.path.exists(put) and os.path.exists(ptz)):
        return {'slug': slug, 'itog': 'нет статьи или ТЗ'}
    vse, fmt = _linzy()
    linzy = {k: v for k, v in vse.items() if not only or k in only}
    html = open(put, encoding='utf-8').read()
    sh = S.razobrat_tz(open(ptz, encoding='utf-8').read())
    gaz = bool(re.search(r'azotn|kislorod|mks', slug, re.I))
    log = [f'# Доводка {slug}\n']
    t0, vsego = time.time(), 0
    for n in range(1, KRUGOV + 1):
        html, primeneno, provalili = krug(html, sh, linzy, fmt, model, gaz, n, log)
        vsego += primeneno
        if not provalili:
            break
        linzy = {k: v for k, v in vse.items() if k in provalili}
        if not linzy:
            break
    konflikt = any('КОНФЛИКТ' in s for s in log)
    pret = S.proverit(html, sh, gaz)
    itog = ('нужен ручной разбор: конфликт линз' if konflikt else
            ('есть претензии механики' if pret else 'чисто'))
    os.makedirs(out_dir, exist_ok=True)
    imya = f'{slug}.RUCHNOY.html' if konflikt else f'{slug}.final.html'
    with open(os.path.join(out_dir, imya), 'w', encoding='utf-8') as f:
        f.write(html)
        f.flush(); os.fsync(f.fileno())
    log.insert(1, f'**Итог: {itog}. Правок применено: {vsego}. '
                  f'Файл: {imya}**\n')
    if pret:
        log.append('\n## Механика после доводки\n'
                   + '\n'.join('- ' + p for p in pret))
    with open(os.path.join(out_dir, f'{slug}.log.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(log) + '\n')
        f.flush(); os.fsync(f.fileno())
    return {'slug': slug, 'itog': itog, 'pravok': vsego,
            'sekund': round(time.time() - t0), 'pretenzii': pret}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('slugi', nargs='*')
    ap.add_argument('--vse', action='store_true')
    ap.add_argument('--only', help='линзы через запятую')
    ap.add_argument('--out', default=os.path.join(DIR, 'statyi-final'))
    ap.add_argument('--model', default='claude-fable-5')
    a = ap.parse_args()

    only = {x.strip() for x in a.only.split(',')} if a.only else None
    slugi = a.slugi
    if a.vse:
        slugi = [f[:-5] for f in sorted(os.listdir(os.path.join(DIR, 'statyi')))
                 if f.endswith('.html')]
    if not slugi:
        print('нужен slug или --vse', file=sys.stderr)
        return 2
    vse, _ = _linzy()
    print(f'страниц {len(slugi)}, линз {len(only or vse)}', flush=True)
    for s in slugi:
        r = odna(s, a.out, a.model, only)
        print(f"  {r['slug']}: {r['itog']}"
              + (f", правок {r['pravok']}, {r['sekund']} с" if 'pravok' in r else ''),
              flush=True)
    print(f'\n-> {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
