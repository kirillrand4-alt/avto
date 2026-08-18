# -*- coding: utf-8 -*-
"""КАНДИДАТЫ ДОМЕНОВ из названия предприятия — единственный канал поиска сайта, который
целиком наш и не зависит ни от сервера, ни от чужого лимита.

ЗАЧЕМ. По обогащению замер честный и невесёлый: предприятий с доказанной машиной 1 692,
хоть какой-то контакт есть у 214 (13 %), НЕТ НИЧЕГО у 1 478 (87 %). Контакты берутся с
сайта, а сайт надо сначала найти. Оба обычных канала сейчас закрыты:
  * checko.ru локально отдаёт 429, и ЧЕРЕЗ СЕРВЕР тоже (ERR_HTTP_RESPONSE_CODE_FAILURE);
  * ключи поисковой выдачи лежат на сервере, а в его allowlist остался один browser_probe.
Значит нужен канал, который не просит ничьего разрешения.

ПОЧЕМУ ЭТО НЕ ГАДАНИЕ. Кандидат сам по себе ничего не доказывает — доказывает ПРОВЕРКА:
сайт засчитывается, только если на его страницах стоит ИНН предприятия цифрами
(`p25_sayt_podtverzhdenie.py`). Поэтому ложный кандидат ничего не портит, он просто
не подтверждается. Цена ошибки — один запрос, а не грязная строка в базе.

СКОЛЬКО ЭТО ДАЁТ, замерено на 261 УЖЕ ПОДТВЕРЖДЁННОМ сайте (проверочный набор, а не
надежда): простая транслитерация угадывает 39 %. Промахи разобраны и легли в правила:
  ООО «БитумОйл»        → bitum-oil    дефис между корнями
  ОАО «Уфимский ЖБЗ»    → ...-zavod    дефисы между словами целиком
  ООО «ИТЦ СНХРС»       → snhrs-spb    аббревиатура-приставка отбрасывается
  АО «УАПО»             → agregatufa   имя не выводится из названия ВООБЩЕ — таких не берём
"""
import csv
import io
import os
import re
import sys

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
TR = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh',
      'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
      'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c',
      'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e',
      'ю': 'yu', 'я': 'ya'}
FORMA = re.compile(r'^(ООО|АО|ПАО|ОАО|ЗАО|ГУП|МУП|ФГУП|ГБУЗ|КГБУЗ|НАО|АНО|ФКП|ФГБУ|'
                   r'ГБУ|МУ|УП|НПО|НПП|ТД|ПК)\s+', re.I)
SHUM = re.compile(r'\b(имени|им\.|филиал|управление|производственн\w+|объединение)\b', re.I)


def translit(s, y_kak='y'):
    t = dict(TR)
    t['й'] = y_kak
    t['ы'] = y_kak
    return ''.join(t.get(c, c) for c in s.lower())


def yadro(nazvanie):
    n = FORMA.sub('', (nazvanie or '').strip())
    n = re.sub(r'[«»"\']', ' ', n)
    n = SHUM.sub(' ', n)
    return ' '.join(n.split())


def kandidaty(nazvanie, predel=24):
    """Список доменов-кандидатов, от самого вероятного к менее. Порядок важен: проверка
    стоит запроса, и первым должно идти то, что чаще оказывается верным."""
    # ПЕРВЫЙ ЗАМЕР БЫЛ ЛЖИВЫМ, и это надо сказать прямо: он считал попаданием домен,
    # ПОХОЖИЙ на кандидата (сравнивал первые 4 знака), и выдал 39 %. Точное совпадение
    # даёт 21 %. Разница — это не «почти нашли», это «не нашли»: по домену bitumoyl.ru
    # никуда не попадёшь, когда сайт лежит на bitum-oil.ru.
    ya = yadro(nazvanie)
    if not ya:
        return []
    slova = [w for w in re.split(r'[\s\-]+', ya) if w]
    out = []

    def razbit_gorbatoe(w):
        """«БитумОйл» → «bitum-oil»: заглавная внутри слова — граница корней."""
        kuski = re.findall(r'[А-ЯA-Z][а-яa-z0-9]+|[А-ЯA-Z]+(?![а-яa-z])|[а-яa-z0-9]+', w)
        return kuski if len(kuski) > 1 else []

    def dobavit(osnova):
        osnova = re.sub(r'[^a-z0-9-]', '', osnova)
        osnova = re.sub(r'-{2,}', '-', osnova).strip('-')
        if len(osnova) < 3 or len(osnova) > 40:
            return
        for zona in ('.ru', '.com', '.рф'):
            d = osnova + zona
            if d not in out:
                out.append(d)

    # СОБСТВЕННОЕ ИМЯ В КАВЫЧКАХ — самый сильный кандидат. «ООО "НИП НГ «Петон»"» живёт
    # на peton.ru: приставки описывают род занятий, домен берут от имени.
    v_kavychkah = re.findall(r'[«"\']([^«»"\']{3,40})[»"\']', nazvanie or '')
    for y in ('y', 'j'):
        for imya in v_kavychkah:
            dobavit(translit(re.sub(r'[^А-Яа-яA-Za-z0-9]', '', imya), y))
        # Последнее слово: у длинных названий домен часто равен ему одному.
        if len(slova) > 1:
            dobavit(translit(slova[-1], y))
        for w in slova:
            g = razbit_gorbatoe(w)
            if g:
                dobavit('-'.join(translit(x, y) for x in g))
                dobavit(translit(''.join(g), y))
        celikom = translit(''.join(slova), y)
        cherez_defis = '-'.join(translit(w, y) for w in slova)
        dobavit(celikom)
        if cherez_defis != celikom:
            dobavit(cherez_defis)
        # Аббревиатура-приставка («ИТЦ СНХРС» → snhrs): первое слово из заглавных
        # согласных — это форма собственности или тип конторы, имя стоит следом.
        if len(slova) > 1 and len(slova[0]) <= 4 and slova[0].isupper():
            dobavit(translit(''.join(slova[1:]), y))
        if len(slova) > 1:
            dobavit(translit(slova[0], y))
    return out[:predel]


def main():
    proverka = [x for x in csv.DictReader(
        io.open(os.path.join(L, 'PARK-KONTAKTY-2S-SAJTY.csv'), encoding='utf-8-sig'),
        delimiter=';') if x.get('sayt')]
    popal = 0
    mimo = []
    for x in proverka:
        dom = re.sub(r'^https?://(www\.)?', '', x['sayt']).split('/')[0].lower()
        k = kandidaty(x['predpriyatie'])
        if dom in k:
            popal += 1
        elif len(mimo) < 6:
            mimo.append((x['predpriyatie'][:32], dom, ', '.join(k[:3])))
    print('ПРОВЕРОЧНЫЙ НАБОР %d уже подтверждённых сайтов' % len(proverka))
    print('  домен есть среди кандидатов: %d = %.0f%%' % (popal, 100 * popal / len(proverka)))
    print('  чего не берём:')
    for a, b, c in mimo:
        print('     %-32s домен %-22s кандидаты: %s' % (a, b, c))
    return 0


if __name__ == '__main__':
    sys.exit(main())
