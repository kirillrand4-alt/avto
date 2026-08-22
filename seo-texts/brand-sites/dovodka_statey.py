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
import sanity

GP = os.path.join(os.path.dirname(DIR), 'guest-posts')
sys.path.insert(0, GP)

# Гост-постовые линзы, не имеющие смысла без донора и оплаченной ссылки.
# ЛИНЗЫ, ЗАВЯЗАННЫЕ НА ЧУЖУЮ ПЛОЩАДКУ. Первые четыре исключены сразу:
# они подставляют {donor} и проверяют правила донора, которых у нас нет.
#
# neutral добавлена 22.08, и это была моя пропущенная. Она называется
# «аудитор рекламной нейтральности» и следит, чтобы статья НЕ читалась
# как реклама: без призывов «купить/заказать/обратитесь», без имени
# бренда вне якорей ссылок. Для гост-поста это обязательное требование
# площадки. На НАШЕЙ странице каталога - прямо противоположное:
# призывы там главное («главное чтобы привод к лиду был» - владелец),
# а бренд называть надо.
#
# Поймано на живой правке: neutral заменила «обычно готовим КП в течение
# часа» на «готовим расчёт», пометив КП как коммерческое давление.
# Владелец 22.08 подтвердил час как настоящую практику, и КП - это
# ровно то, ради чего страница написана.
CHUZHIE = ('link', 'platform', 'genre_bridge', 'audience_level', 'neutral')
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
# Единица счёта из наших данных. Заменять её на «модель», «единица»,
# «наименование» нельзя: это разные величины.
# Слова, которыми утверждение приписывается источнику. Снять их значит
# превратить чужое заявление в наше обещание.
_ATRIBUCIYA = re.compile(
    r'заявленн\w*|заявля\w*|по\s+данным\s+производител\w*|'
    r'по\s+каталогу|по\s+паспорт\w*|производител\w*\s+указыва\w*|'
    r'в\s+каталоге\s+указан\w*|обычно\b', re.I)
_EDINICA = re.compile(r'\d+\s*позици\w*', re.I)
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
            _porog_svoey_stranicy(mod.FMT))


# ПОРОГ ГОСТ-ПОСТА НЕ ГОДИТСЯ СВОЕЙ СТРАНИЦЕ. Формат приёмки гост-постов
# говорит: «PASS - вердикт по умолчанию, FAIL только если без правки
# статью нельзя отдавать на публикацию, "можно улучшить" = PASS».
# Для ЧУЖОЙ площадки это верно: лишняя правка там хуже недоправки,
# редактор донора видит наш текст один раз.
#
# На СВОЕЙ странице каталога наоборот. Замер владельца 22.08: тринадцать
# линз вернули PASS на текстах, в которых восемь отчётных ролей нашли
# 92 критичных замечания. Порог был единственной причиной.
#
# Владелец: «у нас же было в гость постах сколько то линз и правили
# сразу, почему нельзя сразу так же». Можно и нужно - но с порогом
# своей страницы.
_STARYY_POROG = 'ПОРОГ: PASS - вердикт по умолчанию.'
_NOVYY_POROG = """ПОРОГ: это НАША СОБСТВЕННАЯ страница каталога, а не гостевой материал
на чужой площадке. Правь всё, что делает страницу хуже для инженера
или закупщика: неточность, число без условий, призыв, не говорящий
что человек получит, довод, повторенный трижды, абзац, из которого
нечего вынести, обещание, которого мы не выполним.

PASS ставь, только если править нечего. Молчание из вежливости здесь
дороже придирки: непоправленный текст уйдёт на двенадцать сайтов.

ОТДЕЛЬНО отмечай то, что виновато НЕ В ТЕКСТЕ, А В ЗАДАНИИ - строкой
«ЗАДАНИЕ: <в чём дело>». Такое чинится в генераторе и сразу на всей
сетке из 133 страниц, правка одной страницы там бесполезна."""


def _porog_svoey_stranicy(fmt):
    i = fmt.find(_STARYY_POROG)
    if i < 0:
        return fmt
    konec = fmt.find('Формат ответа СТРОГО:', i)
    return fmt[:i] + _NOVYY_POROG + '\n\n' + fmt[konec:]


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


def _zagolovki(html):
    """Тексты H2 в документе, нормализованные."""
    return [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', z)).strip().lower()
            for z in re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.S | re.I)]


def pochemu_nelzya(citata, zamena, html, tronuto, sh=None):
    """Почему правку применять нельзя. Пусто - можно.

    Вынесено сюда, потому что охранников теперь двое: доводка
    по собственным линзам и мост от отчётных линз (pravki_po_linzam.py).
    Разойдись они - и одна из дорог осталась бы без защиты, причём
    молча.
    """
    if citata not in html:
        return 'цитата не найдена дословно'
    konflikt = _peresechenie(citata, zamena, tronuto)
    if konflikt:
        return f'конфликт с линзой {konflikt[0]} за зону «{konflikt[1][:40]}»'
    novyy = html.replace(citata, zamena, 1)
    if not _tegi_cely(novyy):
        return 'правка ломает разметку'
    # БЛОК СКЕЛЕТА НЕ УДАЛЯЕТСЯ ПРАВКОЙ. Линза убрала целиком H2
    # «Собственная генерация против криогенной станции» - формально
    # правка как правка: разметка цела, чисел не потеряно. А набор
    # блоков посчитан разводкой на двенадцати сайтах, и потерянный блок
    # ломает замер на всей сетке, не на одной странице.
    #
    # В промпте это сказано, но правило, держащееся на послушании
    # модели, - не правило.
    if sh and sh.get('h2'):
        bylo = _zagolovki(html)
        stalo = _zagolovki(novyy)
        propali = [z for z in bylo if z not in stalo]
        if propali:
            return f'правка удаляет блок скелета: «{propali[0][:60]}»'
    if '—' in zamena or '–' in zamena:
        return 'в замене длинное тире'
    bez_c = re.sub(r'[\d\s.,:/-]+', '', citata)
    bez_z = re.sub(r'[\d\s.,:/-]+', '', zamena)
    if bez_c and bez_c == bez_z and citata != zamena:
        return 'правка меняет только число'
    if _EDINICA.search(citata) and not _EDINICA.search(zamena):
        return 'правка подменяет единицу счёта'
    chisla_c = re.findall(r'\d+(?:[.,]\d+)?', citata)
    chisla_z = re.findall(r'\d+(?:[.,]\d+)?', zamena)
    if zamena and len(chisla_c) > len(chisla_z):
        poteryany = [x for x in chisla_c if x not in chisla_z]
        return f'замена теряет числа {poteryany[:4]}'
    # НОВОЕ ЧИСЛО В ЗАМЕНЕ ПРОВЕРЯЕТСЯ ГЕЙТАМИ. Охранники ловили потерю
    # чисел, но не их ПОЯВЛЕНИЕ, и линза этим воспользовалась: заменила
    # «порядка десяти кубометров воздуха на кубометр кислорода»
    # (подтверждено разбором паспортов: 9,2-13,3) на «порядка 4-5
    # кубометров» - выдумку вдвое ниже реальности. Число не потеряно,
    # разметка цела, единица та же, и правка прошла бы.
    #
    # Линза правит текст, но за факты отвечают гейты, и её замена
    # обязана им подчиняться наравне с текстом генератора.
    # АТРИБУЦИЯ НЕ СНИМАЕТСЯ ПРАВКОЙ. Линза seo_yandex убрала слово
    # «заявленная» из фразы «Заявленная производителем экономия
    # составляет 20-30%», сочтя его канцелярским штампом. Штамп-то штамп,
    # но 20-30% - это заявление производителя из каталога ENGER, а не наш
    # замер, и без оговорки фраза становится нашим обещанием.
    #
    # Число цело, единица та же, гейты молчат - и правка прошла бы.
    if _ATRIBUCIYA.search(citata) and not _ATRIBUCIYA.search(zamena):
        return 'правка снимает ссылку на источник утверждения'
    # Гейты гоняются по замене ВСЕГДА, а не только при новых числах:
    # «Компрессор Atlas Copco производства Швеции» чисел не добавляет,
    # а утверждение о заводе вносит.
    for imya, proverka in (('воздух/газ', sanity.vozduh_na_gaz),
                           ('страна завода', sanity.strana_zavoda),
                           ('давление газа', sanity.davlenie_gaza),
                           ('срок КП', sanity.srok_kp)):
        if proverka(zamena):
            novye = [x for x in chisla_z if x not in chisla_c]
            hvost = f', числа {novye[:3]}' if novye else ''
            return f'замена не проходит гейт «{imya}»{hvost}'
    return ''


# КОГДА ПЕРЕСЕЧЕНИЕ ЗОН - ЭТО ПОВОД ПОЗВАТЬ ЧЕЛОВЕКА.
#
# Разбор первой страницы ночного прогона: 39 правок применено, 17 помечено
# конфликтом, файл ушёл как «нужен ручной разбор». Из этих семнадцати
# ни один не был спором. Три разных случая, и все три - не спор:
#
# 1. Линза конфликтует САМА С СОБОЙ («logic: конфликт с линзой logic»).
#    Это просто второй заход той же роли, спорить не с кем.
# 2. Предложено ровно то, что уже стоит в тексте: зона «форель при 20°C
#    потребляет 300», правка - «форель при 20°C потребляет 300-400»,
#    а «300-400» там уже написано предыдущей линзой. Подтверждение,
#    а не возражение.
# 3. Линза правит РЕЗУЛЬТАТ чужой правки. Это обычная последовательная
#    редактура: текст живой, лежит в документе, его читают следующие.
#    Проверка пересечения не отличала её от спора и метила конфликтом
#    любую вторую правку в уже тронутом месте.
#
# Спор, стоящий человека, один: две линзы расходятся В ФАКТЕ. Признак
# деоретический - НАБОР ЧИСЕЛ. Правка, меняющая числа живого текста,
# спорит с тем, кто эти числа поставил. Правка, меняющая только слова
# вокруг тех же чисел, - вопрос вкуса, и его решает порядок применения.
#
# Мягкость тут не от лени: отклонена правка в любом случае, документ
# от этого не меняется. Меняется только пометка на файле. А пометка,
# которая стоит на каждой странице, не значит ничего - это уже было
# с близкими ролями ниже и повторяется здесь.
BLIZKIE = {('seo_google', 'seo_yandex'), ('seo_yandex', 'seo_google'),
           ('seo', 'seo_yandex'), ('seo_yandex', 'seo'),
           ('seo', 'seo_google'), ('seo_google', 'seo'),
           ('teh_technolog', 'engineer'), ('engineer', 'teh_technolog'),
           ('teh_skeptik', 'engineer'), ('engineer', 'teh_skeptik'),
           ('teh_razmernost', 'engineer'), ('engineer', 'teh_razmernost'),
           ('language', 'logic'), ('logic', 'language'),
           ('depth', 'engineer'), ('engineer', 'depth')}

_CHISLA_ZONY = re.compile(r'\d+(?:[.,]\d+)?')


def nuzhen_razbor(imya, chya, citata, zamena):
    """Стоит ли пересечение зон того, чтобы страницу смотрел человек."""
    if imya == chya:
        return False                      # сама с собой не спорит
    if (imya, chya) in BLIZKIE:
        return False                      # близкие роли, не два мнения
    if zamena.strip() == citata.strip():
        return False                      # предложено то же самое
    return _CHISLA_ZONY.findall(citata) != _CHISLA_ZONY.findall(zamena)


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
        # Находки, которые чинятся в ЗАДАНИИ, а не в тексте. Это то,
        # ради чего заводился второй набор линз: правка одной страницы
        # тут бесполезна, а генератор чинит сразу все 133.
        for z in re.findall(r'^\s*ЗАДАНИЕ:\s*(.+)$', otvet, re.M):
            log.append(f'- ЗАДАНИЕ [{imya}]: {z.strip()[:200]}')
        proshla, pravki = razobrat(otvet)
        if proshla and not pravki:
            log.append(f'- круг {nomer} / {imya}: PASS')
            continue
        vzyato = 0
        for citata, zamena, prichina in pravki[:4]:
            # ОХРАННИКИ ОДНИ НА ВСЕХ. Здесь стояла своя копия проверок,
            # и когда я вынес их в pochemu_nelzya, эта копия осталась
            # жить рядом - то есть защита, добавленная в общую функцию,
            # сюда не доезжала. Ровно так мимо прошла защита от удаления
            # блока скелета: линза убрала H2 «Собственная генерация
            # против криогенной станции», разметка цела, чисел
            # не потеряно, и правка применилась.
            otkaz = pochemu_nelzya(citata, zamena, html, tronuto, sh)
            if otkaz:
                metka = ''
                if 'конфликт' in otkaz:
                    provalili.append('конфликт зон')
                    peres = _peresechenie(citata, zamena, tronuto)
                    if peres and nuzhen_razbor(imya, peres[0], citata, zamena):
                        metka = ' [РАЗБОР]'
                log.append(f'  - {imya}: {otkaz}, правка отклонена '
                           f'(«{citata[:44]}»){metka}')
                continue
            novyy = html.replace(citata, zamena, 1)
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
    dlya_zadaniya = [s for s in log if s.startswith('- ЗАДАНИЕ [')]
    chuzhie_spory = [x for x in log if '[РАЗБОР]' in x]
    konflikt = bool(chuzhie_spory)
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
            'k_zadaniyu': len(dlya_zadaniya),
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
