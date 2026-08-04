# -*- coding: utf-8 -*-
"""Отличить главный сайт предприятия от магазина, который ему принадлежит.

ЧТО ВСКРЫЛА ПРОВЕРКА ПРИГОВОРОВ. Признак «на домене напечатан наш ИНН» я
собирался считать решающим. Список замен показал, что он решает НЕ ТО:

    ПАО «ВИЗ»              viz.ru            → shop.viz.ru
    ООО «ЛЛК-Интернешнл»   lukoil-masla.ru   → ru.lukoil-shop.com
    Завод «Медсинтез»      medsintez.com     → triazavirin.ru
    ИПК «Лазурь»           lazurprint.ru     → books96.ru

Магазин ОБЯЗАН печатать реквизиты продавца — это закон о защите прав
потребителей. Корпоративный сайт не обязан и часто их не печатает. Значит
признак систематически поднимает магазины и продуктовые лендинги над заводскими
сайтами — ровно наоборот тому, что нужно карточке: нам с сайта нужны разделы
«Контакты», «Производство», «Вакансии», телефоны служб, а не корзина.

ДВА РАЗНЫХ ВОПРОСА, КОТОРЫЕ Я ЧУТЬ НЕ СЛИЛ В ОДИН
    принадлежит ли домен юрлицу     ← отвечает ИНН в подвале
    лицо ли это предприятия         ← отвечает состав страниц

Этот ход собирает второй признак: маркеры завода против маркеров лавки, плюс
случай «поддомен против своего же корня» (shop.viz.ru против viz.ru — тут
и спорить не о чем).

Запуск: python sayty_lico_doma.py [--potok N]
"""
import io, json, os, re, ssl, sys, time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

ДОКАЗ = r'C:\seostat\drop\sayty_dokazatelstvo_inn.jsonl'
ПОТОК = r'C:\seostat\drop\sayty_lico_doma.jsonl'
ПОТОКОВ = 8
for i, а in enumerate(sys.argv):
    if а == '--potok' and i + 1 < len(sys.argv):
        ПОТОКОВ = max(1, min(16, int(sys.argv[i + 1])))

ПУТИ = ('', '/contacts', '/kontakty', '/about', '/o-kompanii', '/company')
_КТХ = ssl.create_default_context()
_КТХ.check_hostname = False
_КТХ.verify_mode = ssl.CERT_NONE
_ЗАГ = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9'}

ЛАВКА = (('корзин', 3), ('добавить в корзину', 5), ('оформить заказ', 4),
         ('в корзину', 4), ('купить в один клик', 4), ('доставка и оплата', 2),
         ('способы оплаты', 2), ('личный кабинет', 1), ('товаров в каталоге', 3),
         ('руб./шт', 3), ('₽/шт', 3), ('добавить к сравнению', 3),
         ('избранное', 1), ('акции и скидки', 2), ('розниц', 2))
ЗАВОД = (('вакансии', 3), ('о предприятии', 4), ('производство', 3),
         ('наше производство', 4), ('структура предприятия', 5),
         ('руководство', 3), ('главный инженер', 5), ('отдел снабжения', 5),
         ('отдел кадров', 3), ('цех', 2), ('система менеджмента качества', 3),
         ('охрана труда', 2), ('промышленная безопасность', 4),
         ('закупки', 3), ('поставщикам', 4), ('история завода', 4),
         ('сертификаты', 1), ('телефонный справочник', 5))


def взять(url, таймаут=12):
    зпр = urllib.request.Request(url, headers=_ЗАГ)
    with urllib.request.urlopen(зпр, timeout=таймаут, context=_КТХ) as о:
        сыр = о.read(600000)
    for код in ('utf-8', 'cp1251'):
        try:
            return сыр.decode(код)
        except UnicodeDecodeError:
            continue
    return сыр.decode('utf-8', 'replace')


def опросить(д):
    итог = {'domen': д, 'stranic': 0, 'lavka': 0, 'zavod': 0, 'zagolovok': '',
            'slov_lavki': '', 'slov_zavoda': ''}
    текст = ''
    for сх in ('https://', 'http://'):
        for путь in ПУТИ:
            try:
                текст += ' ' + взять(f'{сх}{д}{путь}')
                итог['stranic'] += 1
            except Exception:
                continue
        if итог['stranic']:
            break
    if not итог['stranic']:
        return итог
    м = re.search(r'<title[^>]*>(.{0,160}?)</title>', текст, re.I | re.S)
    итог['zagolovok'] = ' '.join((м.group(1) if м else '').split())[:120]
    низ = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', текст)).lower()
    бл, бз = [], []
    for сл, вес in ЛАВКА:
        if сл in низ:
            итог['lavka'] += вес
            бл.append(сл)
    for сл, вес in ЗАВОД:
        if сл in низ:
            итог['zavod'] += вес
            бз.append(сл)
    итог['slov_lavki'] = ', '.join(бл[:6])
    итог['slov_zavoda'] = ', '.join(бз[:6])
    return итог


def main():
    домены = []
    видел = set()
    for стр in io.open(ДОКАЗ, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(стр)
        except Exception:
            continue
        д = str(з.get('domen') or '')
        if д and д not in видел:
            видел.add(д)
            домены.append(д)

    сделано = set()
    if os.path.exists(ПОТОК):
        for стр in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                сделано.add(str(json.loads(стр).get('domen')))
            except Exception:
                continue
    очередь = [д for д in домены if д not in сделано]
    print(f'доменов к опросу {len(очередь)} (уже опрошено {len(сделано)})')

    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    стат = Counter()
    примеры = []
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        for исх in пул.map(опросить, очередь):
            ф.write(json.dumps({**исх, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')},
                               ensure_ascii=False) + '\n')
            ф.flush()
            os.fsync(ф.fileno())
            if not исх['stranic']:
                стат['не открылся'] += 1
            elif исх['lavka'] > исх['zavod']:
                стат['ЛАВКА: маркеров магазина больше'] += 1
                if len(примеры) < 12:
                    примеры.append(f"   лавка {исх['domen'][:26]:26} "
                                   f"{исх['lavka']:3}/{исх['zavod']:<3} "
                                   f"{исх['slov_lavki'][:44]}")
            elif исх['zavod'] > исх['lavka']:
                стат['ЗАВОД: маркеров предприятия больше'] += 1
            else:
                стат['поровну или пусто — признак не сработал'] += 1
    ф.close()

    for п in примеры:
        print(п)
    print()
    for к, v in sorted(стат.items()):
        print(f'   {к:48} {v:4}')


if __name__ == '__main__':
    main()
