# -*- coding: utf-8 -*-
"""Патенты предприятий через patenton.ru — запасной вход, когда Google Patents закрыт.

ЗАЧЕМ ВТОРОЙ СБОРЩИК. `patenty_harvest.py` ходит в `patents.google.com/xhr/query`. Замер
03.08: после примерно шестидесяти запросов эндпоинт начал отдавать 503 на ВСЁ, включая
обычную страницу поиска, и пауза не помогает — проверено на 0, 3, 8 и 15 секундах, четыре
запроса на каждой, двенадцать 503 из двенадцати. При этом `google.com` из той же песочницы
отвечает 200, то есть закрыт именно патентный раздел, а не сеть. Ровно на этом же 503
остановился и прошлый заход, записав шесть ложных нулей.

Здесь другой источник: `patenton.ru/search?q=<имя>&page=N`, по 10 записей на страницу,
советские и российские патенты. В выдаче сразу лежат **фамилии изобретателей** — то, ради
чего мы в патенты и ходим.

ЧЕСТНОЕ ОГРАНИЧЕНИЕ, ЧИТАТЬ ПЕРЕД ИСПОЛЬЗОВАНИЕМ ДАННЫХ. Выдача полнотекстовая, а
патентообладателя в ней НЕТ: колонка `attr owner` в разметке — это изобретатели, не
организация. Карточка патента, где патентообладатель есть, закрыта JS-проверкой и из
песочницы не читается (отдаёт страницу-заглушку с загрузчиком). Значит связь «этот человек
работает на этом предприятии» здесь **не доказана** — доказано лишь, что название
предприятия встречается в тексте патента. Поэтому:
  * каждая строка помечена `privyazka = 'упоминание в тексте, патентообладатель не проверен'`;
  * рядом лежит `citata` — кусок текста, где имя предприятия и встретилось, чтобы человек
    мог решить сам;
  * `imya_v_citate` показывает, реально ли имя предприятия попало в приведённый отрывок.
Сливать это с `PATENTY-vse-3s.csv` (Google Patents, где патентообладатель проверен) в одну
колонку нельзя: там связь доказана, здесь — предположена.

Использование:
    python3 patenty_patenton.py <predpriyatiya.csv> <out.csv> [--limit N] [--stranic 3]
                                [--pauza 1.5]
Входной CSV: колонки `inn_zakazchika` и `zakazchik` (как у `patenty_harvest.py`).
"""
import csv
import html
import re
import sys
import time
import urllib.parse
import urllib.request

from patenty_harvest import chistoe_imya, svoy_zayavitel  # noqa: F401  (общие правила имени)

BAZA = 'https://patenton.ru'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

VSEGO = re.compile(r'Найдено документов:\s*([\d\s]+)')
# Разбор поблочно, а не одним жадным шаблоном: если разметка одного поля поедет, строка
# всё равно соберётся, а не обнулится целиком.
BLOK = re.compile(r'<div class="result">(.*?)(?=<div class="result">|<div class="pagination|$)', re.S)
KOD = re.compile(r'class="attr code">([^<]+)<')
LICA = re.compile(r'class="attr owner">([^<]*)<')
IMYA = re.compile(r'class="result-name"[^>]*>(.*?)</a>', re.S)
TEKST = re.compile(r'class="text-preview">(.*?)</p>', re.S)


# ПОИСК МНОГОСЛОВНОГО ИМЕНИ БЕССМЫСЛЕН: движок ищет по ИЛИ, кавычки не помогают.
# Замер: «Мелеузовские минеральные удобрения» — счётчик 10 000 и НИ ОДНОГО документа, где
# все слова есть в отрывке; «Газпром нефтехим Салават» — 2 126 и один. А одно отличительное
# слово работает: «Салаватнефтеоргсинтез» 98, «ПОЛИЭФ» 135, «БЕЛЗАН» 7. Поэтому запрос —
# самое длинное слово имени, не входящее в отраслевой словарь. Из 1 853 наших предприятий
# такое слово есть у 1 626; у остальных запрос честно помечается слабым.
OBSHEE = set("""завод заводы комбинат фабрика производственное производственный объединение
научно исследовательский институт группа компаний компания холдинг корпорация управление
предприятие филиал совместное российское российский россии имени ордена трудового красного
знамени промышленный промышленная промышленность механический механическая муниципальное
унитарное акционерное общество открытое закрытое публичное ограниченной ответственностью
машиностроительный машиностроительное химический химическая металлургический
металлургическая горно обогатительный энергетическая энергетический энерго тепловая
электрическая электро станция рудник шахта карьер водоканал теплосеть теплосети
горводоканал минеральные удобрения продукты питания молочный молочная мясной мясная
хлебный хлебная сахарный спиртовой пивоваренный целлюлозно бумажный картонный цементный
кирпичный стекольный керамический текстильный швейная обувная мебельная нефтехим нефтехимия
деревообрабатывающий нефтеперерабатывающий нефтехимический газоперерабатывающий газпром
роснефть лукойл сибур ростех росатом транснефть металлоинвест северсталь""".split())


def klyuchevoe_slovo(imya):
    """Самое длинное отличительное слово имени. Пусто — значит запрос будет слабым."""
    slova = [w for w in re.split(r'[^А-Яа-яЁёA-Za-z0-9]+', imya) if len(w) >= 6]
    silnye = [w for w in slova if w.lower() not in OBSHEE]
    return max(silnye, key=len) if silnye else ''


def _chisto(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def _vzyat(url, popytok=3):
    for p in range(popytok):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return urllib.request.urlopen(req, timeout=45).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return f'__ОШИБКА__ {type(e).__name__} {getattr(e, "code", "")}'
            time.sleep(2 * (p + 1))


def po_imeni(imya, stranic=3, pauza=1.5):
    """Патенты по имени предприятия. Возвращает (строки, всего_по_счётчику, ошибка)."""
    out, vsego, err = [], 0, ''
    for st in range(1, stranic + 1):
        u = f'{BAZA}/search?q={urllib.parse.quote(imya)}' + (f'&page={st}' if st > 1 else '')
        h = _vzyat(u)
        if h.startswith('__ОШИБКА__'):
            err = h
            break
        if st == 1:
            m = VSEGO.search(_chisto(h))
            vsego = int(re.sub(r'\D', '', m.group(1))) if m else 0
        bloki = BLOK.findall(h)
        if not bloki:
            break
        for b in bloki:
            k, l, n, t = KOD.search(b), LICA.search(b), IMYA.search(b), TEKST.search(b)
            citata = _chisto(t.group(1)) if t else ''
            out.append({'nomer': k.group(1).strip() if k else '',
                        'nazvanie': _chisto(n.group(1))[:200] if n else '',
                        'izobretateli': _chisto(l.group(1))[:300] if l else '',
                        'citata': citata[:300],
                        'ssylka': f'{BAZA}/patent/{k.group(1).strip()}' if k else u})
        if len(out) >= vsego:
            break
        time.sleep(pauza)
    return out, vsego, err


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, out_path = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 40
    stranic = int(sys.argv[sys.argv.index('--stranic') + 1]) if '--stranic' in sys.argv else 3
    pauza = float(sys.argv[sys.argv.index('--pauza') + 1]) if '--pauza' in sys.argv else 1.5

    imena = {}
    for r in csv.DictReader(open(src, encoding='utf-8-sig'), delimiter=';'):
        i = (r.get('inn_zakazchika') or '').strip()
        if i and i not in imena:
            imena[i] = (r.get('zakazchik') or '').strip()
    celi = list(imena)[:limit]
    print(f'предприятий: {len(celi)}, страниц на каждое до {stranic}, пауза {pauza} с',
          file=sys.stderr)

    kol = ['inn', 'predpriyatie', 'zapros', 'zapros_slabyy', 'vsego_po_schetchiku', 'nomer',
           'nazvanie', 'izobretateli', 'imya_v_citate', 'privyazka', 'citata', 'ssylka']
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore')
    w.writeheader()
    vsego_strok, nulevyh, sboev, s_lyudmi = 0, 0, 0, 0
    for k, inn in enumerate(celi, 1):
        polnoe = chistoe_imya(imena[inn])
        q = klyuchevoe_slovo(polnoe)
        slaboe = ''
        if not q:
            # Ни одного отличительного слова: «Мелеузовские минеральные удобрения» без
            # «Мелеузовские» — это набор отраслевых слов, по которым найдётся полстраны.
            # Запрос всё равно делается (пропуск = потерянные данные), но помечается.
            q, slaboe = polnoe, '1'
        if len(q) < 5:
            print(f'[{k}/{len(celi)}] {q!r}: имя короче пяти букв, запрос негодный — пропуск',
                  file=sys.stderr)
            continue
        rows, vsego, err = po_imeni(q, stranic=stranic, pauza=pauza)
        # Ключевые слова имени, чтобы отличить «имя реально в отрывке» от «нашлось
        # где-то в полном тексте, а в отрывке его нет».
        slova = [x.lower() for x in re.split(r'[^А-Яа-яЁёA-Za-z0-9]+', q) if len(x) > 4]
        for r in rows:
            est = any(s in (r['citata'] + ' ' + r['nazvanie']).lower() for s in slova)
            w.writerow({'inn': inn, 'predpriyatie': imena[inn], 'zapros': q,
                        'vsego_po_schetchiku': vsego, 'imya_v_citate': '1' if est else '',
                        'privyazka': 'упоминание в тексте, патентообладатель не проверен',
                        'zapros_slabyy': slaboe, **r})
            if r['izobretateli']:
                s_lyudmi += 1
        vsego_strok += len(rows)
        f.flush()
        if err:
            sboev += 1
            print(f'[{k}/{len(celi)}] {q[:34]:<34} СБОЙ {err[10:]} (взято до сбоя {len(rows)})',
                  file=sys.stderr)
        else:
            if not rows:
                nulevyh += 1
            print(f'[{k}/{len(celi)}] {q[:34]:<34} счётчик {vsego:>5}, взято {len(rows):>3}, '
                  f'всего {vsego_strok}', file=sys.stderr)
        time.sleep(pauza)
    f.close()
    print(f'итого {vsego_strok} строк, из них с фамилиями {s_lyudmi} | '
          f'предприятий без патентов {nulevyh} | СБОЕВ (ноль недостоверен) {sboev} '
          f'→ {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
