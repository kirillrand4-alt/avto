#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пакет к публикации: тело статьи плюс кнопки той разметки, что на сайте.

    python3 k_publikacii.py [--out k-publikacii]

ЧЕМ ЭТО НЕ ПРЕДПРОСМОТР. Предпросмотр (sobrat_paket.py) заворачивает
статью в страницу с CSS сайта, чтобы ПОСМОТРЕТЬ. Здесь наоборот: отдаём
голый фрагмент, который вставляется в CMS, а оформит его сайт сам.

ТРИ РЕШЕНИЯ, КОТОРЫЕ ЗДЕСЬ ПРИНЯТЫ, И ПОЧЕМУ.

1. H1 В ТЕЛО НЕ КЛАДЁМ. На всех двенадцати сайтах заголовок первого
   уровня уже стоит на странице - проверено по выгрузке. Второй H1
   в тексте это не украшение, а дефект разметки. Наш заголовок уходит
   в meta.csv: захочет владелец сменить заголовок страницы - возьмёт
   оттуда.

2. ПРИЗЫВ НЕ СТАНОВИТСЯ НАДПИСЬЮ НА КНОПКЕ. Замер по 184 призывам:
   медиана 117 знаков, длиннее 90 знаков - 133 штуки. Такую фразу
   на кнопку не положить, она развалит вёрстку. Поэтому призыв остаётся
   абзацем, а под ним встаёт КОРОТКАЯ кнопка, как это и сделано на самих
   сайтах («Получить КП», «Оставить заявку»).

   Надпись кнопки берётся из САМОГО призыва по его же обещанию, а не
   сочиняется: сказано про КП - «Получить КП», про расчёт - «Получить
   расчёт», про подбор - «Подобрать оборудование». Новых обещаний
   кнопка не даёт.

3. КЛАСС КНОПКИ - РОДНОЙ ДЛЯ САЙТА, ГДЕ ОН ЕСТЬ. Классы вытащены из
   выгрузки живых сайтов, каждый подтверждён количеством применений
   на странице. Где своей заявочной кнопки нет, берём bootstrap
   («btn btn-primary»): бутстрап подключён на всех двенадцати,
   проверено по выгрузке, так что кнопка не окажется голой.
"""
import argparse
import csv
import glob
import json
import os
import re

DIR = os.path.dirname(os.path.abspath(__file__))

# Кнопки живых сайтов. Первое поле - класс, второе - куда ведём.
# Классы взяты из sayty-syrye/*.html, в скобках - сколько раз класс
# встречается на выгруженной странице (доказательство, что он рабочий,
# а не остался от старой темы).
KNOPKI = {
    # Тема красит .bxr-color-button жёлтым, а текст оставляет белым - на живом
    # сайте кнопка идёт с инлайновым color:#000, иначе надпись нечитаема
    # (белое по жёлтому даёт контраст около 1,9:1). Повторяем то же самое.
    'abac-kompressor.ru':      ('bxr-color-button', '/company/contacts/', 'color:#1a1a1a'),  # 21
    'kraftmann-kompressor.com': ('bxr-color-button', '/contacts/'),               # 21
    'remeza-kompressor.ru':    ('bxr-color-button', '/company/contacts/', 'color:#1a1a1a'),  # 33
    'dali-kompressor.ru':      ('btn btn-outline-primary btn-request-kp',
                                '/company/contacts/'),                            # 20
    'ac-kompressor.ru':        ('ac-btn ac-btn-primary', '/company/zakaz/'),
    'enger-air.ru':            ('enger-btn enger-btn--primary', '/company/contacts/'),  # 7
    # Своей заявочной кнопки в выгрузке нет - берём бутстрап, он подключён.
    'berg-kompressor.ru':      ('btn btn-primary', '/contacts/'),
    'crossair-compressor.ru':  ('btn btn-primary', '/about/contacts/'),
    'fini-compressor.com':     ('btn btn-primary', '/about/contacts/'),
    'ironmac-compressor.com':  ('btn btn-primary', '/company/contacts/'),
    'ekomak-kompressor.com':   ('btn btn-primary', '/contacts/'),
    'zif-kompressor.ru':       ('btn btn-primary', '/company/where-buy/'),
}

# Приставка слага -> домен. Слаг вида «berg-kompressor--vintovye».
DOMEN = {
    'abac-kompressor': 'abac-kompressor.ru',
    'ac-kompressor': 'ac-kompressor.ru',
    'berg-kompressor': 'berg-kompressor.ru',
    'crossair-compressor': 'crossair-compressor.ru',
    'dali-kompressor': 'dali-kompressor.ru',
    'ekomak-kompressor': 'ekomak-kompressor.com',
    'enger-air': 'enger-air.ru',
    'fini-compressor': 'fini-compressor.com',
    'ironmac-compressor': 'ironmac-compressor.com',
    'kraftmann-kompressor': 'kraftmann-kompressor.com',
    'remeza-kompressor': 'remeza-kompressor.ru',
    'zif-kompressor': 'zif-kompressor.ru',
}

# Надпись кнопки по обещанию самого призыва. Порядок важен: КП сильнее
# расчёта, расчёт сильнее подбора - берём самое конкретное обещание.
NADPISI = (
    (re.compile(r'\bКП\b|коммерческое предложение', re.I), 'Получить КП'),
    (re.compile(r'рассчита|расчёт|расчет', re.I),          'Получить расчёт'),
    (re.compile(r'подбер|подбор|подобра', re.I),           'Подобрать оборудование'),
    (re.compile(r'замер|выезд|обследова', re.I),           'Вызвать инженера'),
)
NADPIS_PO_UMOLCHANIYU = 'Оставить заявку'


def nadpis(fraza):
    for pravilo, slovo in NADPISI:
        if pravilo.search(fraza):
            return slovo
    return NADPIS_PO_UMOLCHANIYU


# ПРИЗЫВ БЕЗ КЛАССА - ВСЁ РАВНО ПРИЗЫВ.
#
# Замер по собранному пакету: из 133 страниц 88 не имеют НИ ОДНОГО
# абзаца с class="cta". Не потому, что призыва там нет, - он есть
# на 77 из этих 88, просто написан обычным абзацем. Генератор ставит
# класс не всегда, а гейт считает призывы только сверху (потолок 6)
# и снизу не спрашивает, поэтому страница без единого размеченного
# призыва проходит.
#
# Цена ровно та, о которой спросил владелец: две трети страниц легли бы
# так, что призыв неотличим от текста и кнопки под ним нет.
#
# ФОРМА, ПО КОТОРОЙ УЗНАЁМ: абзац НАЧИНАЕТСЯ с повелительного наклонения
# из закрытого списка. Проверено двумя случайными выборками, 27 абзацев
# из 27 - настоящие призывы. Правило со вторым условием (обещание после
# тире) точнее по форме, но берёт лишь 220 абзацев из 328: половина
# призывов написана через двоеточие или вторым предложением.
_VELITELNOE = (r'(?:Пришлите|Отправьте|Сообщите|Укажите|Напишите|Опишите|'
               r'Заполните|Оставьте|Позвоните|Свяжитесь|Расскажите|Присылайте|'
               r'Назовите|Перечислите|Уточните|Дайте знать)')
_PRIZYV_BEZ_KLASSA = re.compile(r'^\s*' + _VELITELNOE + r'\b', re.I)

# ОТВЕТ В FAQ - НЕ ПРИЗЫВ, ЧЕМ БЫ ОН НИ НАЧИНАЛСЯ.
#
# Правило выше поймало и ответы: на вопрос «Что делать, если точные
# параметры азота неизвестны?» ответ честно начинается с «Пришлите...».
# Превратив его в серую плашку с кнопкой, я оставил вопрос будто без
# ответа - заголовок, под ним сразу плашка. Осмотр снимков поймал это
# на двух сайтах независимо, замер дал 61 такой вопрос на 55 страницах.
#
# Признак надёжный: вопрос FAQ размечен h3, и ответ идёт сразу за ним.
_POSLE_VOPROSA = re.compile(r'</h3>\s*$', re.I)


def domen_slaga(slug):
    return DOMEN.get(slug.split('--', 1)[0])


def svezhiy_fajl(slug):
    """Новейший из .final/.RUCHNOY - тот же выбор, что делает конвейер."""
    est = [p for p in (os.path.join(DIR, 'statyi-final', f'{slug}.final.html'),
                       os.path.join(DIR, 'statyi-final', f'{slug}.RUCHNOY.html'))
           if os.path.exists(p)]
    return max(est, key=os.path.getmtime) if est else None


_DATA_OBNOVL = re.compile(r'<p[^>]*>\s*(?:<em>)?\s*(?:Дата обновления|Обновлено)[^<]{0,40}(?:</em>)?\s*</p>', re.I)
_PUSTOY = re.compile(r'<p>\s*(?:<em>\s*</em>|<strong>\s*</strong>|&nbsp;)?\s*</p>', re.I)


# ПОТОЛОК КНОПОК НА СТРАНИЦУ.
#
# Разметить призыв и поставить под ним кнопку - разные решения. Призывов
# на странице бывает много и это ЧЕСТНО: у dali--azotnaya-stanciya их
# семнадцать, все настоящие, по одному на раздел. А семнадцать цветных
# коробок с кнопками - стена, читать её невозможно.
#
# Число шесть не выдумано: ровно такой потолок стоит в гейте призывов
# («повторяющийся призыв перестаёт работать»). Гейт считал только те,
# что размечены классом, и прозы не видел, поэтому страница с семнадцатью
# призывами его прошла.
#
# Текст призывов НЕ ТРОГАЕМ - это содержание, и решать про него владельцу.
# Ограничиваем только кнопки, и распределяем их по странице ровно, всегда
# оставляя первую и последнюю: читатель встречает кнопку и в начале, и
# в конце, а между ними они не идут подряд.
POTOLOK_KNOPOK = 6


def _gde_knopki(vsego):
    """Номера призывов, под которыми встанет кнопка."""
    if vsego <= POTOLOK_KNOPOK:
        return set(range(vsego))
    shag = (vsego - 1) / (POTOLOK_KNOPOK - 1)
    return {round(i * shag) for i in range(POTOLOK_KNOPOK)}


# СЛУЖЕБНЫЕ ИМЕНА БЛОКОВ НАРУЖУ НЕ ВЫХОДЯТ.
#
# Скелет ТЗ называет блоки так, как удобно РАЗВОДКЕ по двенадцати сайтам:
# «Первый экран», «Блок доказательства», «Финальный призыв». Генератор
# обязан воспроизвести набор H2 дословно - это проверяет гейт, и правильно
# делает: потерянный блок ломает замер пересечения по всей сетке.
#
# Но это ВНУТРЕННИЕ имена. Читатель, увидевший заголовок «Блок
# доказательства», сразу понимает, что текст собран машиной. Замер:
# 132 страницы из 133 несут хотя бы одно такое имя - «Первый экран» 120,
# «Блок доказательства» 122, «Финальный призыв» 121.
#
# Поэтому имена меняются ЗДЕСЬ, на выходе к публикации, а не в статье:
# внутри сетка остаётся сверяемой, наружу уходит человеческий заголовок.
#
# «Первый экран» и «Финальный призыв» - это метки НАД содержимым, которому
# заголовок не нужен вовсе: под первым идёт вступление (его накрывает H1
# страницы), под вторым - призыв, который говорит сам за себя. Их снимаем.
#
# «Блок доказательства» переименовываем, а не снимаем: под ним настоящий
# раздел. Имя выбрано так, чтобы не соврать - выборка показала, что там
# и реальные объекты («установлен на предприятии»), и типовые проекты
# («типовой проект кислородной станции»). «Пример решения» верно для обоих,
# а «Реализованный проект» для половины было бы неправдой.
SNYAT_ZAGOLOVOK = ('Первый экран', 'Финальный призыв')
PEREIMENOVAT = {'Блок доказательства': 'Пример решения'}


def _zagolovki_k_publikacii(html):
    """Снять служебные H2, переименовать остальные, починить оглавление."""
    ubrannye = set()

    def h2(m_):
        vnutri = m_.group(2)
        t = re.sub(r'<[^>]+>', '', vnutri).strip()
        yakor = re.search(r'id="([^"]+)"', m_.group(1) or '')
        if t in SNYAT_ZAGOLOVOK:
            if yakor:
                ubrannye.add(yakor.group(1))
            return ''
        if t in PEREIMENOVAT:
            return f'<h2{m_.group(1)}>{PEREIMENOVAT[t]}</h2>'
        return m_.group(0)

    html = re.sub(r'<h2([^>]*)>(.*?)</h2>\s*', h2, html, flags=re.S | re.I)

    # ОГЛАВЛЕНИЕ ОБЯЗАНО ПЕРЕЖИТЬ ПРАВКУ ЗАГОЛОВКОВ. Снятый H2 оставляет
    # в нём ссылку в никуда, переименованный - старое имя. И то и другое
    # читатель видит сразу: пустой пункт или ссылка, ведущая не туда.
    def oglavlenie(m_):
        blok = m_.group(0)
        for yak in ubrannye:
            blok = re.sub(r'<a href="#' + re.escape(yak) + r'">.*?</a>\s*(?:<br>)?\s*',
                          '', blok, flags=re.S)
        for staroe, novoe in PEREIMENOVAT.items():
            blok = re.sub(r'(<a href="#[^"]+">)' + re.escape(staroe) + r'(</a>)',
                          r'\g<1>' + novoe + r'\g<2>', blok)
        # ХВОСТ ОТ ВЫРЕЗАННОГО ПУНКТА, И ТОЛЬКО ОН.
        #
        # Раньше здесь стояло «убрать разделитель перед тегом», и это
        # срезало ВСЕ запятые списка: у ссылок разделитель как раз и стоит
        # перед следующим тегом («</a>, <a href=...»). Оглавление слипалось
        # в сплошную строку, где не видно, где кончается один пункт:
        # «...для непрерывного цикла Чистота азота и удельный расход...».
        #
        # Убираем ровно три случая: сдвоенный разделитель на месте
        # вырезанного пункта, разделитель в самом начале списка и висящий
        # в конце.
        blok = re.sub(r'([;,])\s*(?:[;,]\s*)+', r'\1 ', blok)
        blok = re.sub(r'(<p class="na-stranice">[^<]*?)[;,]\s*', r'\1', blok)
        blok = re.sub(r'[;,]\s*(?=\s*</p>)', '', blok)
        blok = re.sub(r'<br>\s*(?=</p>)', '', blok)
        # «ссылка , ссылка .» - пробел перед знаком препинания остаётся
        # от вырезанного пункта и просто от сборки списка через разделитель
        blok = re.sub(r'\s+([;,.])', r'\1', blok)
        return blok

    html = re.sub(r'<p class="na-stranice">.*?</p>', oglavlenie, html, flags=re.S)
    return html


def podgotovit(html, domen):
    """Тело к вставке: без H1, без пустых абзацев, с кнопками сайта."""
    zapis = KNOPKI[domen]
    klass, kuda = zapis[0], zapis[1]
    stil = f' style="{zapis[2]}"' if len(zapis) > 2 else ''
    # СНИМАЕМ ВСЕ H1, А НЕ ПЕРВЫЙ. Страница enger-air--azotnaya-stanciya
    # пришла с двумя одинаковыми H1 подряд: снялся первый, второй уехал бы
    # в тело и задвоил заголовок сайта. Дефект чинится в статье и закрыт
    # гейтом, но сборщик обязан быть устойчив и к неожиданному входу -
    # он последний рубеж перед публикацией.
    zagolovki = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.S | re.I)
    zagolovok = re.sub(r'<[^>]+>', '', zagolovki[0]).strip() if zagolovki else ''
    html = re.sub(r'<h1[^>]*>.*?</h1>\s*', '', html, flags=re.S | re.I)
    html = _PUSTOY.sub('', html)
    html = _zagolovki_k_publikacii(html)

    # ДАТА ОБНОВЛЕНИЯ - В КОНЕЦ, А НЕ В СЕРЕДИНУ.
    # На четырёх страницах она встала перед блоком FAQ, и после неё шло
    # ещё до трёх тысяч знаков текста. Читатель принимает такую строку
    # за конец статьи и дальше не идёт.
    md = _DATA_OBNOVL.search(html)
    if md:
        posle = re.sub(r'<[^>]+>', '', html[md.end():]).strip()
        if len(posle) > 400:
            html = html[:md.start()] + html[md.end():] + '\n' + md.group(0)

    # ТАБЛИЦУ ОБОРАЧИВАЕМ В ПРОКРУТКУ.
    # Замер на телефоне: страница ironmac--azotnaya-stanciya свёрстана
    # на 519 px при экране 390 - пятиколоночная таблица распирает
    # контейнер, и уезжает вбок ВСЯ статья, а не только таблица.
    # Правый край плашек призыва при этом обрезан.
    html = re.sub(r'(?<!<div class="tablica-prokrutka">)(<table)',
                  r'<div class="tablica-prokrutka">\1', html)
    html = html.replace('</table>', '</table></div>')

    # ДВА ПРОХОДА. Сначала находим ВСЕ призывы - и размеченные классом,
    # и написанные обычным абзацем, - чтобы знать их общее число. Только
    # зная его, можно разложить кнопки по потолку. За один проход это
    # не сделать: решение про третий призыв зависит от того, сколько их
    # окажется дальше.
    ABZAC = re.compile(r'<p(?: class="cta")?>(.*?)</p>', re.S)

    nayden = []
    for m_ in ABZAC.finditer(html):
        chistaya = re.sub(r'<[^>]+>', '', m_.group(1)).strip()
        if not chistaya:
            continue
        s_klassom = m_.group(0).startswith('<p class="cta">')
        if s_klassom or (_PRIZYV_BEZ_KLASSA.match(chistaya)
                         and not _POSLE_VOPROSA.search(html[:m_.start()])):
            nayden.append(m_.start())
    s_knopkoy = {nayden[i] for i in _gde_knopki(len(nayden))} if nayden else set()

    knopok = [0]

    def perepisat(m_):
        vnutri = m_.group(1)
        chistaya = re.sub(r'<[^>]+>', '', vnutri).strip()
        s_klassom = m_.group(0).startswith('<p class="cta">')
        if not chistaya:
            return '' if s_klassom else m_.group(0)   # пустой призыв - не призыв
        if not (s_klassom or _PRIZYV_BEZ_KLASSA.match(chistaya)):
            return m_.group(0)
        if not s_klassom and _POSLE_VOPROSA.search(html[:m_.start()]):
            return m_.group(0)          # это ответ на вопрос, а не призыв
        if m_.start() not in s_knopkoy:
            # ПЛАШКА БЕЗ КНОПКИ ХУЖЕ ОБЫЧНОГО АБЗАЦА. Сначала я выделял
            # все призывы, а кнопку давал только части - на dali--azotnaya-
            # stanciya вышло семнадцать серых плашек, из них одиннадцать
            # без единой кнопки. Читатель видит выделенный блок, тянется
            # ткнуть, а ткнуть некуда. Поэтому призыв без кнопки остаётся
            # обычным абзацем: содержание на месте, ложного обещания нет.
            return f'<p>{vnutri}</p>'
        knopok[0] += 1
        return (f'<p class="cta">{vnutri}</p>\n'
                f'<p class="cta-knopka"><a class="{klass}"{stil} '
                f'href="https://{domen}{kuda}">{nadpis(chistaya)}</a></p>')

    html = ABZAC.sub(perepisat, html)
    html = re.sub(r'\n{3,}', '\n\n', html).strip() + '\n'
    return html, zagolovok, knopok[0], len(nayden)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(DIR, 'k-publikacii'))
    a = ap.parse_args()

    slugi = sorted(os.path.basename(p)[3:-3]
                   for p in glob.glob(os.path.join(DIR, 'tz', 'TZ-*.md')))
    po_saytam, propusk = {}, []
    for slug in slugi:
        dom = domen_slaga(slug)
        put = svezhiy_fajl(slug)
        if not dom or not put:
            propusk.append((slug, 'нет домена' if not dom else 'нет файла'))
            continue
        html = open(put, encoding='utf-8').read()
        telo, zagolovok, knopok, prizyvov = podgotovit(html, dom)
        meta = {}
        mp = os.path.join(DIR, 'statyi', f'{slug}.meta.json')
        if os.path.exists(mp):
            try:
                meta = json.load(open(mp, encoding='utf-8'))
            except Exception:
                pass
        papka = os.path.join(a.out, dom)
        os.makedirs(papka, exist_ok=True)
        with open(os.path.join(papka, f'{slug}.html'), 'w', encoding='utf-8') as f:
            f.write(telo)
        po_saytam.setdefault(dom, []).append({
            'Файл': f'{slug}.html',
            'H1': zagolovok,
            'Title': meta.get('title', ''),
            'Description': meta.get('description', ''),
            'Знаков': meta.get('znakov', ''),
            'Призывов': prizyvov,
            'Кнопок': knopok,
            'Источник': os.path.basename(put),
        })

    for dom, stroki in po_saytam.items():
        with open(os.path.join(a.out, dom, 'meta.csv'), 'w',
                  encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(stroki[0].keys()), delimiter=';')
            w.writeheader()
            w.writerows(stroki)

    vsego = sum(len(v) for v in po_saytam.values())
    knopok = sum(s['Кнопок'] for v in po_saytam.values() for s in v)
    print(f'сайтов {len(po_saytam)}, страниц {vsego}, кнопок проставлено {knopok}')
    for dom in sorted(po_saytam):
        kl = KNOPKI[dom][0]
        print(f'   {dom:26} {len(po_saytam[dom]):3} стр.  кнопка class="{kl}"')
    for slug, pochemu in propusk:
        print(f'   ПРОПУЩЕНА {slug}: {pochemu}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
