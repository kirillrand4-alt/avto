# -*- coding: utf-8 -*-
"""Сканы вложений закупок: читаем глазами модели, а не tesseract.

Зачем так. У параллельной сессии есть `ocr_lib.py` с tesseract, но он собран под сервер-раннер
(`bin/tesseract.exe`), а в песочнице его нет. Зато там же есть функция `гриф_провайдером` —
распознавать гриф со скана глазами модели, — и этот путь нам доступен полностью: страница
рисуется в картинку библиотекой, картинка уходит провайдеру. Клиент `gen_provider` передаёт
`messages` в тело запроса без изменений, поэтому блок с изображением проходит как есть.

Что именно ищем. Замер вложений показал, что сканы среди них — почти сплошь **протоколы**
(«итоговый протокол гкс», «Протокол ЗК 126-21 — Винтовой маслосмазываемый компрессор»). А в
протоколе закупки печатается **состав комиссии**: ФИО и должности, и туда штатно входят главный
инженер, главный механик, главный энергетик. Это не догадка про содержимое, а прямое следствие
того, что за документ мы открыли.

Какие страницы. Первая — шапка с составом комиссии или грифом. Последняя — подписи. Середина
протокола это таблица заявок, там людей нет. Поэтому берём первые две и последнюю.

Заслоны:
- **ни одного ФИО и ни одного номера, которых не видно на изображении** — выдуманный человек
  хуже пропуска, по нему будут звонить;
- роль ставится по названию должности с изображения, а не по догадке; ГИП (главный инженер
  ПРОЕКТА), автомеханик, механик гаража и начальник транспортного цеха техническими не считаются;
- обязательное поле «почему» — иначе честный короткий ответ «людей на странице нет» наш клиент
  принимает за сбой и уходит в оплаченные повторы (это уже случилось сегодня).

Использование:
    python3 skany_provajderom.py [--threads 4] [--limit N] [--dpi 170]
"""
import base64
import csv
import io
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import gen_provider as G

MODEL = 'claude-fable-5'
BAZA = os.path.dirname(os.path.abspath(__file__))
RAB = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad'
FAJLY = os.path.join(RAB, 'eis_fajly')
OUT = os.path.join(BAZA, 'engineers-lens', 'centro', 'eis')
ISTOCHNIK = os.path.join(OUT, 'vlozheniya-tekst.jsonl')

G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                 'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}

PROMPT = """На изображениях — страницы документа закупки российского промышленного предприятия
(чаще всего протокол закупочной комиссии, реже техзадание или извещение). Текстового слоя в файле
нет, это скан.

ЗАЧЕМ. ООО «Руспром» продаёт промышленные воздушные компрессоры и воздуходувки. Нужны люди в
ТЕХНИЧЕСКИХ ролях: главный инженер, главный механик, главный энергетик, начальник цеха или
компрессорной, их заместители, инженер ОГМ/ОГЭ/КИПиА, технический директор. В протоколе они
обычно перечислены в составе комиссии, в техзадании — под грифом «УТВЕРЖДАЮ» или в листе
согласования. Снабженец (ОМТС, отдел закупок) тоже нужен, но помечается отдельно.

ЧТО ВЕРНУТЬ. **Всех названных на странице людей, а не только технических.** Это правило
появилось после проверки глазами: на протоколе ФКП «Комбинат «Каменский» модель вернула пустой
список, а на странице стояли контактное лицо с телефоном и состав комиссии из шести человек.
Причина была в том, что у членов комиссии указана РОЛЬ В КОМИССИИ («Член комиссии»,
«Председатель», «Секретарь»), а не должность на предприятии, и они были отброшены как
нетехнические. Отбрасывать их нельзя: имя без должности — это половина работы, потому что по
имени секретарь предприятия переключает охотнее, чем по должности.

Итак, включай в список:
- контактное лицо закупки, даже если это снабженец;
- **всех членов комиссии**, включая председателя и секретаря;
- подписантов, согласующих, «инициатора мероприятия»;
- любого человека под грифом «УТВЕРЖДАЮ».

По каждому человеку:
- `imya` — как написано на изображении;
- `dolzhnost` — дословно с изображения; если не указана, пустая строка;
- `rol` — `техническая`, `снабжение`, `руководство` или `неясно`. **Если на странице указана
  только роль в комиссии, а должность на предприятии не названа — это `неясно`**, а не повод
  человека пропустить;
- `telefon`, `pochta` — только если они видны рядом с этим человеком;
- `gde` — где именно он стоит: «состав комиссии», «гриф УТВЕРЖДАЮ», «лист согласования»,
  «подпись в конце» и тому подобное.

ПРАВИЛА, нарушать нельзя:
1. **Ни одной фамилии и ни одного номера, которых не видно на изображении.** Не достраивай
   инициалы, не угадывай нечитаемое. Если фамилия читается частично — так и напиши в `imya`
   с пометкой «нечётко».
2. Пустой список — только если на страницах действительно нет ни одного имени. Перед тем как
   вернуть пустой список, перечитай страницу на предмет блоков «Контактное лицо», «Состав
   комиссии», «Присутствовали», «Подписи», «УТВЕРЖДАЮ» — модель уже один раз вернула пусто на
   странице с шестью фамилиями.
3. Не считай технической ролью «главный инженер проекта» и «ГИП» (это проектировщик),
   «механик гаража», «начальник транспортного цеха», «инженер по закупкам», «инженер-сметчик».
4. Председателя и членов комиссии различай: у председателя часто административная должность.

ОТВЕТ — строго JSON, без пояснений:
{"lyudi":[{"imya":"","dolzhnost":"","rol":"","telefon":"","pochta":"","gde":""}],
 "chto_za_dokument":"одной строкой: что это за документ",
 "pochemu":"одно-два предложения: почему людей столько, сколько ты назвал; если список пуст —
 что видно на страницах вместо людей"}

Поля `chto_za_dokument` и `pochemu` обязательны и когда список пуст: наш клиент считает слишком
короткий ответ сбоем провайдера и уходит в повторы, поэтому честное «людей нет» без объяснения
стоит денег впустую."""


def stranicy_png(put, dpi=170, maks_bajt=4_500_000, maks_stranic=8):
    """Страницы документа в картинки.

    Две обрезки, которые здесь были и обе замерены, а не предположены:

    1. **Брал три страницы из N.** Замер: сканы в нашем корпусе на 1-4 страницах, пропускались
       2 страницы из 51 (3 %). Тем не менее убрано: документ до восьми страниц берётся целиком,
       и только у более длинных берутся первые две и последняя.
    2. **Понижал dpi до 90, если картинка не влезала в 1,4 МБ.** Замер: понижение срабатывало
       на **20 страницах из 49**, то есть на 41 % корпуса, а на 90 точках русский текст скана
       часто уже нечитаем. Порог поднят до 4,5 МБ (предел изображения у API выше), понижение
       оставлено только как крайняя мера и **сообщается в вызывающий код**, а не молча.
    """
    import fitz
    with fitz.open(put) as d:
        n = len(d)
        nomera = list(range(n)) if n <= maks_stranic else sorted({0, 1, n - 1})
        out, ponizheno = [], []
        for i in nomera:
            for k in (dpi, 130, 100):
                b = d[i].get_pixmap(dpi=k).tobytes('png')
                if len(b) <= maks_bajt:
                    if k != dpi:
                        ponizheno.append((i + 1, k))
                    break
            out.append((i + 1, b))
        return n, out, ponizheno


def main():
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 4
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 10 ** 9
    dpi = int(sys.argv[sys.argv.index('--dpi') + 1]) if '--dpi' in sys.argv else 170

    rows = [json.loads(l) for l in open(ISTOCHNIK, encoding='utf-8')]
    skany = []
    for r in rows:
        if not r['skan_ili_pusto']:
            continue
        p = os.path.join(FAJLY, r['fajl'])
        if os.path.exists(p) and open(p, 'rb').read(4) == b'%PDF':
            skany.append(r)
    skany = skany[:limit]
    print(f'PDF-сканов к распознаванию: {len(skany)}', file=sys.stderr)

    client = G.make_client()
    lock = threading.Lock()
    itog, sch = [], {'lyudey': 0, 'teh': 0, 'err': 0, 'pusto': 0}

    def odin(r):
        put = os.path.join(FAJLY, r['fajl'])
        try:
            vsego, kartinki, ponizheno = stranicy_png(put, dpi=dpi)
        except Exception as e:  # noqa: BLE001
            return r, None, f'рендер не удался: {type(e).__name__}: {str(e)[:60]}'
        soderzh = [{'type': 'text',
                    'text': f'{PROMPT}\n\nФайл: {r.get("imya_dokumenta") or r["fajl"]}\n'
                            f'Закупка: {r.get("zakupka") or "?"}\nСтраниц в документе: {vsego}\n'
                            f'Ниже страницы: {", ".join(str(n) for n, _ in kartinki)}'
                            + (f'\nВНИМАНИЕ: страницы {ponizheno} отрисованы в пониженном '
                               f'разрешении, часть текста может быть нечитаема — если не '
                               f'разбираешь, скажи об этом в поле «почему», не угадывай.'
                               if ponizheno else '')}]
        for _, b in kartinki:
            soderzh.append({'type': 'image',
                            'source': {'type': 'base64', 'media_type': 'image/png',
                                       'data': base64.b64encode(b).decode()}})
        try:
            o = G.call(client, [{'role': 'user', 'content': soderzh}], model=MODEL, attempts=4)
            txt = ''.join(x.text for x in o.content if x.type == 'text')
        except Exception as e:  # noqa: BLE001
            return r, None, f'{type(e).__name__}: {str(e)[:70]}'
        m = re.search(r'\{.*\}', txt, re.S)
        if not m:
            return r, None, 'в ответе нет JSON'
        try:
            return r, json.loads(m.group(0)), ''
        except Exception as e:  # noqa: BLE001
            return r, None, f'JSON не разобран: {str(e)[:50]}'

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for r, res, err in pool.map(odin, skany):
            with lock:
                if err:
                    sch['err'] += 1
                    print(f'  СБОЙ {r["fajl"]}: {err}', file=sys.stderr)
                    continue
                lyudi = res.get('lyudi') or []
                if not lyudi:
                    sch['pusto'] += 1
                for ch in lyudi:
                    itog.append({**ch, 'fajl': r['fajl'], 'zakupka': r.get('zakupka') or '',
                                 'imya_dokumenta': r.get('imya_dokumenta') or '',
                                 'chto_za_dokument': res.get('chto_za_dokument') or ''})
                    sch['lyudey'] += 1
                    if ch.get('rol') == 'техническая':
                        sch['teh'] += 1
                print(f'  {r["fajl"]}: людей {len(lyudi)} | {(res.get("chto_za_dokument") or "")[:60]}',
                      file=sys.stderr, flush=True)

    p = os.path.join(OUT, 'skany-lica.csv')
    cols = ['zakupka', 'imya_dokumenta', 'chto_za_dokument', 'imya', 'dolzhnost', 'rol',
            'telefon', 'pochta', 'gde', 'fajl']
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in itog:
            w.writerow(r)
    # Отчёт цифрой из записанного файла, а не из счётчика: счётчик не знает про запись.
    pr = list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'))
    print(f'\nпо файлу: строк {len(pr)}, технических {sum(1 for x in pr if x["rol"] == "техническая")}, '
          f'с телефоном {sum(1 for x in pr if (x.get("telefon") or "").strip())}', file=sys.stderr)
    print(f'сканов без людей: {sch["pusto"]}, сбоев: {sch["err"]} → {p}', file=sys.stderr)


if __name__ == '__main__':
    main()
