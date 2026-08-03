# -*- coding: utf-8 -*-
"""Портал поставщиков Москвы: где живёт API сейчас и как читать уже собранное.

ЧТО СЛУЧИЛОСЬ. 30 июля одним днём отсюда сняли 5 681 строку через
`zakupki.mos.ru/api/Cssp/Purchase/Query`. Сейчас тот же адрес молчит, и вывод напрашивался
неверный: «площадка закрылась» или «режут наши адреса». Замер с сервера владельца обычным
urllib, без браузера и без прокси, говорит другое:

    zakupki.mos.ru      200, обычная страница
    roseltorg.ru        200
    evraz.com           200
    mpb.gosnadzor.ru    getaddrinfo failed  (у сервера нет DNS на реестр ЭПБ)

То есть «Connection reset» из песочницы — диагноз песочницы, а не площадки, и тоннель для
сбора не нужен. Сломались три другие вещи, и каждая проверена отдельно:

1. ХОСТ. На `zakupki.mos.ru` ЛЮБОЙ путь `/api/...` отдаёт оболочку SPA с кодом 200 — это
   catch-all маршрут фронтенда, а не ответ приложения. Настоящий API отвечает на
   `old.zakupki.mos.ru`: тот же путь возвращает JSON с `count` и `items`.
2. МЕТОД — GET. POST на `zakupki.mos.ru` даёт 405 от nginx, POST на `old` — честное
   `{"message":"The requested resource does not support http method 'POST'"}`. Значит учить
   браузерный пробник постить бесполезно.
3. ФИЛЬТР ПО ТЕКСТУ ЛЕЖИТ. `filter.nameLike` отвечает 500 в любой обёртке: с
   `order: relevance`, без `withCount`, с пустыми списками регионов и ОКПД, со строковой
   сортировкой, с одним словом «компрессор» вместо фразы. Фильтры по ОКПД
   (`okpdCodes`, `okpd`, `okpdIds`, `okpdCode`) и любые чужие имена полей портал молча
   игнорирует.

КАК ОТЛИЧАТЬ ОДНО ОТ ДРУГОГО, иначе поиск формы превращается в гадание. Признак «поле
чужое» — счётчик РАВЕН счётчику пустого запроса (сейчас 5 052 781, весь портал): фильтр
выброшен, а ответ выглядит успешным. Признак «поле своё, но ломается внутри» — HTTP 500.
Поэтому `naydi_formu` печатает эталон пустого запроса первым и сравнивает с ним каждый
вариант; без эталона «не применился фильтр» читается как «нашлось пять миллионов».

ЧЕГО НЕ ХВАТАЕТ. Одной строки: URL и точной формы `queryDto`, которой пользуется сам фронт
портала сейчас. Её видно только в сетевой панели открытой страницы поиска. Дальше сбор идёт
с сервера обычным GET, без браузера.

Использование:
    python3 portal_moskvy.py forma                  # перебрать формы запроса, найти рабочую
    python3 portal_moskvy.py ocenit <файл.csv>      # оценить уже собранное (см. ниже)
    python3 portal_moskvy.py sobrat <файл.csv> --dto '<json>'   # сбор по известной форме

ОЦЕНКА СОБРАННОГО. В файле 30 июля колонка `centrobezhnyy_predmet` проставлена у всех
5 681 строки, хотя запрос шёл по восьми словам, из которых «центробежный» — лишь одно.
Текст предмета доказывает центробежность у 664 строк, у 383 прямо написано «Компрессор
поршневой» или «Винтовой компрессор», 1 177 — ремонт, ЗИП и услуги, 3 457 — просто
«компрессор» без типа. Ничего не выбрасывается: `ocenit` добавляет две колонки —
`centrobezhnost_stepen` и `sreda_po_predmetu` — и оставляет все строки на месте.
"""
import csv
import json
import re
import sys
import urllib.parse
import urllib.request

csv.field_size_limit(10 ** 7)

STARYY = 'old.zakupki.mos.ru'
NOVYY = 'zakupki.mos.ru'
PUT = '/api/Cssp/Purchase/Query'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

CENTRO = re.compile(r'центробежн|турбокомпрессор|турбовоздуходувк|нагнетател|турбоагрегат|'
                    r'турбогазодувк', re.I)
PORSHEN = re.compile(r'поршнев|винтов|спиральн|мембранн|роторн', re.I)
NE_MASHINA = re.compile(r'ремонт|запчаст|запасн\w+ част|услуг|обслуживани|масло|фильтр|ремень|'
                        r'проектн|монтаж|техническ\w+ обслуж|поставка ЗИП|подшипник|уплотнени',
                        re.I)
GAZ = re.compile(r'природн\w*\s*газ|азот|кислород|аммиак|водород|синтез-газ|\bГПА\b|'
                 r'газоперекач|этилен|пропилен|углекислот', re.I)
VOZDUH = re.compile(r'воздух|воздушн|воздуходувк|пневмо|дутьев', re.I)


def sprosit(dto, baza=STARYY, put=PUT, tajm=60):
    """GET к API. Возвращает (count, items) либо (строка-ошибка, [])."""
    u = f'https://{baza}{put}?queryDto=' + urllib.parse.quote(
        json.dumps(dto, ensure_ascii=False))
    req = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=tajm) as r:
            telo = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return f'HTTP {e.code}', []
    except Exception as e:  # noqa: BLE001
        return f'{type(e).__name__}: {str(e)[:80]}', []
    if telo.lstrip()[:1] not in '{[':
        # 200 с оболочкой SPA — это не ответ приложения, а catch-all фронтенда.
        return 'оболочка SPA (ответ не от API)', []
    d = json.loads(telo)
    return d.get('count'), (d.get('items') or [])


def naydi_formu(slovo='компрессор', formy=None):
    """Перебор форм запроса с печатью эталона пустого запроса."""
    etalon, _ = sprosit({'skip': 0, 'take': 3})
    print(f'пустой запрос: count={etalon}  ← эталон «фильтр не применился»')
    if formy is None:
        formy = [
            ('filter.nameLike', {'filter': {'nameLike': slovo}, 'skip': 0, 'take': 3}),
            ('filter.nameLike + order', {'filter': {'nameLike': slovo},
                                         'order': [{'field': 'relevance', 'desc': True}],
                                         'withCount': True, 'skip': 0, 'take': 3}),
            ('filter.name', {'filter': {'name': slovo}, 'skip': 0, 'take': 3}),
            ('filter.okpdCodes', {'filter': {'okpdCodes': ['28.13.2']}, 'skip': 0, 'take': 3}),
            ('textQuery', {'textQuery': slovo, 'skip': 0, 'take': 3}),
        ]
    rabochie = []
    for imya, dto in formy:
        c, items = sprosit(dto)
        if isinstance(c, str):
            print(f'  {imya:<28} ОШИБКА {c}   ← поле своё, ломается внутри')
            continue
        if c == etalon:
            print(f'  {imya:<28} count={c:<10} проигнорирован (равен эталону)')
            continue
        print(f'  {imya:<28} count={c:<10} ФИЛЬТР РАБОТАЕТ')
        rabochie.append((imya, dto))
        for it in items[:2]:
            print('       ·', (it.get('name') or '')[:110])
    return rabochie


def stepen_centrobezhnosti(predmet):
    p = predmet or ''
    if CENTRO.search(p):
        return 'доказана текстом'
    if PORSHEN.search(p):
        return 'опровергнута текстом (поршневой/винтовой)'
    if NE_MASHINA.search(p):
        return 'не машина (ремонт/ЗИП/услуги)'
    return 'не названа (просто «компрессор»)'


def sreda_predmeta(predmet):
    p = predmet or ''
    g, v = bool(GAZ.search(p)), bool(VOZDUH.search(p))
    return 'и газ, и воздух' if g and v else 'газ' if g else 'воздух' if v else 'не названа'


def ocenit(put_csv):
    """Разметить собранное, не удаляя ни строки."""
    rows = list(csv.DictReader(open(put_csv, encoding='utf-8-sig'), delimiter=';'))
    kol = list(rows[0].keys())
    for k in ('centrobezhnost_stepen', 'sreda_po_predmetu'):
        if k not in kol:
            kol.append(k)
    for r in rows:
        r['centrobezhnost_stepen'] = stepen_centrobezhnosti(r.get('predmet'))
        r['sreda_po_predmetu'] = sreda_predmeta(r.get('predmet'))
    out = put_csv.replace('.csv', '-s-ocenkoy.csv')
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    cel = [r for r in rows if r['centrobezhnost_stepen'] == 'доказана текстом']
    vozd = [r for r in cel if 'воздух' in r['sreda_po_predmetu']]
    inn_vseh = {(r.get('zakazchik_inn') or '').strip() for r in rows} - {''}
    print(f'строк {len(rows)} | ИНН заказчиков {len(inn_vseh)}', file=sys.stderr)
    for z in ('доказана текстом', 'опровергнута текстом (поршневой/винтовой)',
              'не машина (ремонт/ЗИП/услуги)', 'не названа (просто «компрессор»)'):
        print(f'  {sum(1 for r in rows if r["centrobezhnost_stepen"] == z):>5}  {z}',
              file=sys.stderr)
    print(f'центробежных {len(cel)} у '
          f'{len({r["zakazchik_inn"] for r in cel if r.get("zakazchik_inn")})} ИНН, '
          f'из них воздушных {len(vozd)} → {out}', file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rezhim = sys.argv[1]
    if rezhim == 'forma':
        naydi_formu(sys.argv[2] if len(sys.argv) > 2 else 'компрессор')
    elif rezhim == 'ocenit':
        ocenit(sys.argv[2])
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
