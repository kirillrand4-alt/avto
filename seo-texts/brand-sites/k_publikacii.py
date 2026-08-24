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
    'abac-kompressor.ru':      ('bxr-color-button', '/company/contacts/'),        # 21
    'kraftmann-kompressor.com': ('bxr-color-button', '/contacts/'),               # 21
    'remeza-kompressor.ru':    ('bxr-color-button', '/company/contacts/'),        # 33
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
               r'Заполните|Оставьте|Позвоните|Свяжитесь|Расскажите|Присылайте)')
_PRIZYV_BEZ_KLASSA = re.compile(r'^\s*' + _VELITELNOE + r'\b', re.I)


def domen_slaga(slug):
    return DOMEN.get(slug.split('--', 1)[0])


def svezhiy_fajl(slug):
    """Новейший из .final/.RUCHNOY - тот же выбор, что делает конвейер."""
    est = [p for p in (os.path.join(DIR, 'statyi-final', f'{slug}.final.html'),
                       os.path.join(DIR, 'statyi-final', f'{slug}.RUCHNOY.html'))
           if os.path.exists(p)]
    return max(est, key=os.path.getmtime) if est else None


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


def podgotovit(html, domen):
    """Тело к вставке: без H1, без пустых абзацев, с кнопками сайта."""
    klass, kuda = KNOPKI[domen]
    # СНИМАЕМ ВСЕ H1, А НЕ ПЕРВЫЙ. Страница enger-air--azotnaya-stanciya
    # пришла с двумя одинаковыми H1 подряд: снялся первый, второй уехал бы
    # в тело и задвоил заголовок сайта. Дефект чинится в статье и закрыт
    # гейтом, но сборщик обязан быть устойчив и к неожиданному входу -
    # он последний рубеж перед публикацией.
    zagolovki = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.S | re.I)
    zagolovok = re.sub(r'<[^>]+>', '', zagolovki[0]).strip() if zagolovki else ''
    html = re.sub(r'<h1[^>]*>.*?</h1>\s*', '', html, flags=re.S | re.I)
    html = _PUSTOY.sub('', html)

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
        if s_klassom or _PRIZYV_BEZ_KLASSA.match(chistaya):
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
        if m_.start() not in s_knopkoy:
            return f'<p class="cta">{vnutri}</p>'     # выделяем, но без кнопки
        knopok[0] += 1
        return (f'<p class="cta">{vnutri}</p>\n'
                f'<p class="cta-knopka"><a class="{klass}" '
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
