# -*- coding: utf-8 -*-
"""Скан центробежных компрессоров по всем рабочим тендерным площадкам.

Идея. Реестр ЭПБ показал, что запрос «центробежный компрессор» ловит малую часть парка:
та же машина называется нагнетателем, турбокомпрессором, воздуходувкой, ГПА, ЦНД.
Словарь обозначений собран линзой `smezh` и проверен на реестре. Здесь тот же словарь
раскатывается на площадки — и на текущие процедуры, и на планы закупок.

Что скрипт делает: по каждой паре (площадка × термин) открывает поиск через раннер на
сервере владельца, вытаскивает счётчик найденного и первые организации. Это **разведка
объёмов**, а не выгрузка: смысл в том, чтобы понять, где чего сколько, и уже потом
выгружать прицельно.

Запуск (из песочницы, раннер должен отвечать):
    python3 tender_centro_scan.py                 # все площадки, все термины
    python3 tender_centro_scan.py --only gpb,tektorg --terms "нагнетатель,ЦНД"

Выход: engineers-lens/centro/scan-ploshchadki.csv

------------------------------------------------------------------------------------
ЧТО БЫЛО СЛОМАНО В ПРЕДЫДУЩЕЙ ВЕРСИИ (замер 29.07.2026, разобрано по HTML площадок)

1. ТЭК-Торг — шаблон счётчика промахивался по основе слова.
   Было: `закупк\w+ найден`. Площадка печатает «46 закупок найдено»: у слова «закупка»
   в родительном падеже множественного числа беглая гласная — «закуп-ОК», а не «закупк-».
   Поэтому ловились только числа, оканчивающиеся на 2–4 («22 закупки найдено»,
   «3 закупки найдено») и на 1 («1 закупка найдена»), а всё остальное давало прочерк.
   Ровно так в старом CSV и вышло: 22 и 3 поймались, 46 по «воздуходувка» — нет.
   Стало: основа `закуп\w*`. Проверено: при нулевой выдаче площадка честно печатает
   «0 закупок найдено» и «По вашему запросу ничего не найдено», так что настоящий ноль
   теперь отличается от сбоя разбора.

2. ЕИС — не тот шаблон счётчика и не то поле организации.
   Счётчика «Найдено» на странице планов закупки нет вообще: ЕИС печатает
   «Результаты поиска 33 записей», а при больших объёмах округляет — «более 1 700
   записей». Организация лежит в поле «Заказчик», а старый ORG_PATTERNS искал
   «Заказчики» (во множественном числе, как на ЭТП ГПБ). Отсюда пустые обе колонки.
   Отдельно: раннер по умолчанию ходит через прокси, а прокси не пускает на
   zakupki.gov.ru — `ERR_TUNNEL_CONNECTION_FAILED`. Нужен `proxy=False`
   плюс `ignore_https_errors` (российские госсертификаты).

3. Росэлторг — счётчика в привычном виде на странице нет.
   Площадка не печатает «N процедур найдено»: выдача листается кнопкой «Показать еще».
   Общее число лежит внизу блока подсказки: «Вас может заинтересовать ещё: 379»
   (класс `search-autocomplete__similar-text`), а рядом разбивка по разделам —
   «Закупки активные торги: 10», «Закупки архив торгов: 364», «Имущество архив
   торгов: 5». Сумма разбивки равна общему числу, а число активных совпадает с числом
   карточек на первой странице, то есть 379 — это полный счётчик по запросу.

4. ЭТП ГПБ — счётчик снимался до того, как выдача догрузится.
   Площадка на Nuxt: сервер отдаёт разметку с НЕотфильтрованным списком, фильтр
   применяется после гидратации. При wait_ms=11000 заход иногда успевал схватить
   промежуточное состояние, где счётчик показывает всю площадку — 1 721 331
   предложение — и ни одной карточки (текст страницы 2,2 КБ при 796 КБ HTML).
   Стало: wait_ms=30000 + card_wait_ms, и отдельная пометка в CSV, если счётчик
   вышел заведомо общеплощадочным.

5. Общее: html_cap подняли с 900 000 до 1 500 000. У ГПБ страница весит 850–870 КБ,
   то есть старый потолок стоял вплотную (ловушка «упёршийся html_cap»).

СЕМАНТИКА ПОИСКА (замерена парой заведомо разных слов «турбовоздуходувка нагнетатель»)
  ЭТП ГПБ  — ИЛИ с отсечкой по релевантности. Одиночные: турбовоздуходувка 151,
             нагнетатель 1 242; пара 258. В выдаче по паре есть карточки, где встречается
             только одно из слов (воздуходув- 10 вхождений, нагнет- 12), значит это не И.
             Но 258 меньше 1 242, значит и не чистое объединение: площадка режет хвост.
             Практический вывод: многословный запрос на ГПБ нельзя читать как «столько
             закупок именно центробежных компрессоров» — туда попадают процедуры,
             где есть только слово «компрессор».
  Фабрикант — И. Пара дала «Всего: 0» при 32 и 871 по одиночным словам.
  Прочие площадки на семантику отдельно не проверялись.

Колонка slova_v_vydache в CSV — постоянная проверка этой семантики и заодно защита от
вывода «источник пуст»: она считает, сколько раз основа каждого слова запроса реально
встретилась в тексте выдачи. Ноль вхождений при ненулевом счётчике — повод не верить
строке, а лезть в HTML.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.parse

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, 'engineers-lens', 'centro')
RUNNER_CLIENT = os.environ.get(
    'RUNNER_CLIENT',
    '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad/run_on_server.py')

# Потолок HTML. У ЭТП ГПБ страница 850–870 КБ, прежние 900 000 стояли вплотную.
HTML_CAP = 1500000

# Словарь обозначений центробежных машин. Собран линзой smezh, проверен на реестре ЭПБ:
# «нагнетатель» дал 3 195 записей, «воздуходувка» 1 617, «ЦНД» 297 — при том что прямой
# запрос «центробежный компрессор» давал 2 616. То есть половина парка называется иначе.
TERMS = [
    'центробежный компрессор',
    'нагнетатель',
    'турбокомпрессор',
    'воздуходувка',
    'турбовоздуходувка',
    'ЦНД',
    'компрессорная установка',
]

# Площадки, у которых проверена рабочая точка входа. Для каждой: как строится адрес
# поиска, чем ловится счётчик и с какими параметрами ходить.
#   dolphin — Росэлторг режет датацентровые адреса, ходим антидетект-профилем;
#   proxy   — прокси раннера не пускает на zakupki.gov.ru, там идём напрямую;
#   wait    — ГПБ на Nuxt, выдача появляется только после гидратации.
PLATFORMS = {
    'gpb': dict(
        name='ЭТП ГПБ',
        url=lambda q: f'https://etpgpb.ru/procedures/?search={urllib.parse.quote(q)}',
        # «1 242 предложения» / «151 предложение» — форма слова пляшет по числу,
        # поэтому берём основу «предложени» без окончания
        count=[r'([\d\s  ]{1,12})\|?\s*предложени'],
        # признак незавершённой гидратации: счётчик показывает всю площадку целиком
        obshchee_chislo=1000000,
        wait=30000, card_wait=12000, dolphin=False, proxy=False),
    'tektorg': dict(
        name='ТЭК-Торг 223-ФЗ',
        url=lambda q: f'https://www.tektorg.ru/223-fz/procedures?name={urllib.parse.quote(q)}',
        # «46 | закупок найдено»: основа «закуп», а не «закупк» — у слова «закупка»
        # в род. п. мн. ч. беглая гласная. Старый шаблон `закупк\w+` ловил только
        # «закупки»/«закупка» (числа на 1–4) и молча терял всё остальное.
        count=[r'([\d\s  ]{1,12})\|?\s*закуп\w*\s+найден'],
        zero=['По вашему запросу ничего не найдено'],
        wait=20000, card_wait=0, dolphin=False, proxy=False),
    'tektorg_rn': dict(
        name='ТЭК-Торг, секция Роснефти',
        url=lambda q: f'https://www.tektorg.ru/rosneft/procedures?name={urllib.parse.quote(q)}',
        count=[r'([\d\s  ]{1,12})\|?\s*закуп\w*\s+найден'],
        zero=['По вашему запросу ничего не найдено'],
        wait=20000, card_wait=0, dolphin=False, proxy=False),
    'fabrikant': dict(
        name='Фабрикант',
        url=lambda q: f'https://www.fabrikant.ru/procedure/search?query={urllib.parse.quote(q)}',
        # «Всего: | 0» — число отделено разделителем разметки
        count=[r'Всего[:\s| ]{0,6}([\d\s  ]{1,12})'],
        zero=['По вашему запросу ничего не найдено'],
        wait=22000, card_wait=0, dolphin=False, proxy=False),
    'roseltorg': dict(
        name='Росэлторг',
        url=lambda q: ('https://www.roseltorg.ru/procedures/search?currency=all&query_field='
                       + urllib.parse.quote(q)),
        # Своего «найдено N» у площадки нет, выдача листается кнопкой «Показать еще».
        # Общее число печатается в блоке подсказки внизу списка.
        # ВНИМАНИЕ: внутри фразы стоит перенос строки («заинтересовать\n ещё»),
        # поэтому между словами обязателен \s+, а не пробел
        count=[r'Вас может заинтересовать\s+ещ[её][:\s| ]{0,6}([\d\s  ]{1,12})'],
        # разбивка по разделам — пишем в отдельную колонку
        razbivka=[r'(Закупки\s*[\s|]*активные торги[:\s|]{0,6}[\d\s ]{1,10})',
                  r'(Закупки\s*[\s|]*архив торгов[:\s|]{0,6}[\d\s ]{1,10})',
                  r'(Имущество\s*[\s|]*архив торгов[:\s|]{0,6}[\d\s ]{1,10})'],
        wait=20000, card_wait=0, dolphin=True, proxy=False),
    'eis_plan': dict(
        name='ЕИС, план закупки 223-ФЗ (плановые)',
        url=lambda q: ('https://zakupki.gov.ru/epz/orderplan/search/results.html?searchString='
                       + urllib.parse.quote(q)
                       + '&morphology=on&fz223=on&sortBy=UPDATE_DATE&recordsPerPage=_50'),
        # «Результаты поиска | 33 записей», при больших объёмах ЕИС округляет:
        # «Результаты поиска | более 1 700 записей». Слова «Найдено» на странице нет.
        count=[r'Результаты поиска[\s|]{0,6}(?:более\s*)?([\d\s  ]{1,12})запис'],
        priblizit=[r'Результаты поиска[\s|]{0,6}более'],
        wait=25000, card_wait=0, dolphin=False, proxy=False,
        # zakupki.gov.ru живёт на российских госсертификатах
        https_errors=True),
}

# Извлечение организаций. У ЕИС поле называется «Заказчик» (единственное число), у ЭТП ГПБ
# «Заказчики», у Росэлторга и ТЭК-Торга «Организатор» — старый список знал только про
# множественное число, поэтому ЕИС давала пустую колонку.
ORG_PATTERNS = [
    r'Наименование организации \| ([^|]{5,70})',
    r'Заказчики \| ([^|]{5,70})',
    r'Заказчик \| ([^|]{5,70})',
    r'Организатор \| ([^|]{5,70})',
    r'ОРГАНИЗАТОР \| ([^|]{5,70})',
]

# Подписи полей, которые ловятся теми же шаблонами и попадают в выдачу мусором
# (у ТЭК-Торга первым «организатором» шла подпись столбца).
ORG_MUSOR = ('способ определения', 'наименование организации', 'организатор',
             'заказчик', 'не указан')


def probe(url, p, cap=HTML_CAP):
    args = {'url': url, 'screenshot': False, 'return_html': True, 'html_cap': cap,
            'wait_ms': p.get('wait', 15000),
            'proxy': p.get('proxy', False),
            'ignore_https_errors': p.get('https_errors', True)}
    if p.get('card_wait'):
        args['card_wait_ms'] = p['card_wait']
    if p.get('dolphin'):
        args['dolphin_profile'] = os.environ.get('DOLPHIN_PROFILE', '829115286')
        args['dolphin_keep'] = True
    r = subprocess.run([sys.executable, RUNNER_CLIENT, 'browser_probe',
                        json.dumps(args, ensure_ascii=False)],
                       capture_output=True, timeout=600)
    s = r.stdout.decode('utf-8', 'replace')
    i = s.find('{')
    if i < 0:
        return '', None, 'раннер не вернул JSON'
    try:
        res = json.loads(s[i:])
    except Exception:  # noqa: BLE001
        return '', None, 'битый JSON от раннера'
    d = res.get('data') or {}
    return d.get('html') or '', d.get('http_status'), str(d.get('error') or '')[:70]


def flat(html):
    t = re.sub(r'<script.*?</script>', '', html, flags=re.S)
    t = re.sub(r'<style.*?</style>', '', t, flags=re.S)
    t = re.sub(r'<[^>]+>', ' | ', t).replace('&nbsp;', ' ')
    t = re.sub(r'[ \t]+', ' ', t)
    return re.sub(r'(\s*\|\s*)+', ' | ', t)


def osnova(word):
    """Грубая основа слова: отсекаем окончание, чтобы ловить любые словоформы."""
    w = word.lower()
    return w[:max(5, len(w) - 3)]


def slova_v_vydache(text, zapros):
    """Сколько раз основа каждого слова запроса встретилась в тексте выдачи.

    Это и проверка семантики поиска (при И все слова должны встречаться, при ИЛИ —
    не обязательно), и защита от вывода «источник пуст»: если счётчик ненулевой, а
    слово в тексте не встречается ни разу, разбору верить нельзя.
    """
    low = text.lower()
    return ' '.join(f'{osnova(w)}:{low.count(osnova(w))}' for w in zapros.split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--terms', default='')
    a = ap.parse_args()
    keys = [k.strip() for k in a.only.split(',') if k.strip()] or list(PLATFORMS)
    terms = [t.strip() for t in a.terms.split(',') if t.strip()] or TERMS

    os.makedirs(OUT, exist_ok=True)
    rows = []
    for pk in keys:
        p = PLATFORMS[pk]
        for q in terms:
            url = p['url'](q)
            try:
                html, status, err = probe(url, p)
            except Exception as e:  # noqa: BLE001
                rows.append(dict(ploshchadka=p['name'], zapros=q, naydeno='', status='',
                                 primer='', slova_v_vydache='', url=url,
                                 oshibka=str(e)[:70]))
                print(f'{p["name"][:22]:22} {q[:24]:24} ОШИБКА {str(e)[:40]}', file=sys.stderr)
                continue
            t = flat(html)
            n = ''
            for pat in p['count']:
                m = re.search(pat, t)
                if m:
                    n = re.sub(r'\D', '', m.group(1))
                    break

            zamechaniya = []
            if err:
                zamechaniya.append(err)
            # ловушка «упёршийся потолок»: счётчик мог просто не попасть в разметку
            if len(html) >= HTML_CAP:
                zamechaniya.append('html упёрся в потолок')
            # ГПБ: незавершённая гидратация — счётчик показывает всю площадку
            if n and p.get('obshchee_chislo') and int(n) >= p['obshchee_chislo']:
                zamechaniya.append('фильтр не применился, счётчик общеплощадочный')
            # ЕИС округляет большие числа
            if n and any(re.search(x, t) for x in p.get('priblizit', [])):
                zamechaniya.append('площадка округлила: «более N»')
            # честный ноль отличаем от сбоя по прямой надписи площадки
            if any(z in t for z in p.get('zero', [])):
                zamechaniya.append('площадка написала «ничего не найдено»')
                n = n or '0'
            if not n:
                zamechaniya.append('счётчик не найден в разметке')

            razb = []
            for pat in p.get('razbivka', []):
                razb += [re.sub(r'\s+', ' ', re.sub(r'\s*\|\s*', ' ', x)).strip()
                         for x in re.findall(pat, t)]

            orgs = []
            for pat in ORG_PATTERNS:
                orgs += [x.strip() for x in re.findall(pat, t)]
            orgs = [o for o in dict.fromkeys(orgs)
                    if len(o) > 6 and not o.lower().startswith(ORG_MUSOR)][:3]

            rows.append(dict(ploshchadka=p['name'], zapros=q, naydeno=n, status=status,
                             primer=' / '.join(orgs)[:120],
                             slova_v_vydache=slova_v_vydache(t, q),
                             url=url,
                             oshibka='; '.join(razb + zamechaniya)[:160]))
            print(f'{p["name"][:22]:22} {q[:24]:24} найдено {n or "-":>8}  '
                  f'{"; ".join(zamechaniya)[:46]:46} {orgs[0][:30] if orgs else ""}',
                  file=sys.stderr)

    path = os.path.join(OUT, 'scan-ploshchadki.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, delimiter=';',
                           fieldnames=['ploshchadka', 'zapros', 'naydeno', 'status',
                                       'primer', 'slova_v_vydache', 'url', 'oshibka'])
        w.writeheader()
        w.writerows(rows)
    print(f'\nзаписано {len(rows)} строк -> {path}', file=sys.stderr)


if __name__ == '__main__':
    main()
