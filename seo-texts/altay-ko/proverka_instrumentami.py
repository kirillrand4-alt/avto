# -*- coding: utf-8 -*-
"""Шаг 3. Свод идей в уникальные приёмы и проверка каждого приёма по документам инструментов.

3а. Свод: все идеи (metalinzy-idei.jsonl) -> уникальные приёмы (priyomy.json); каждая идея
    обязана попасть ровно в один приём, непопавшие доприписываются вторым вызовом.
3б. Проверка: каждый приём против трёх документов (PARK-2S-INSTRUMENTY-peredacha.md,
    INSTRUMENTY-I-PRIYOMY.md, DOKA-kakoy-skript-chto-delaet.md как замена отсутствующего
    INSTRUMENTY-KAK-POLZOVATSYA.md). Статус «реализовано»/«частично» засчитывается ТОЛЬКО
    с дословной цитатой, которая найдена в документе механически. Два контрольных приёма
    (заведомо реализованный и заведомо нет) проверяют сам классификатор.

Запуск (из seo-texts/):  python3 altay-ko/proverka_instrumentami.py [--tolko svod|proverka]
"""
import json, os, re, sys, time, threading, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from gen_provider import make_client, call  # noqa: E402

MODEL = 'claude-fable-5'
F_IDEI = os.path.join(HERE, 'metalinzy-idei.jsonl')
F_PRIYOMY = os.path.join(HERE, 'priyomy.json')
F_PROVERKA = os.path.join(HERE, 'proverka-priyomov.jsonl')
DOKI = ['PARK-2S-INSTRUMENTY-peredacha.md', 'INSTRUMENTY-I-PRIYOMY.md', 'DOKA-kakoy-skript-chto-delaet.md']
PACHKA = 12
_lock = threading.Lock()


def _parse(msg):
    text = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', text, re.S)
        return json.loads(m.group(0))


def sprosit(client, prompt):
    msg = call(client, [{'role': 'user', 'content': prompt}], model=MODEL, attempts=3)
    return _parse(msg)


def idei_ploskie():
    out = []
    for l in open(F_IDEI, encoding='utf-8'):
        r = json.loads(l)
        for i, x in enumerate(r['idei'], 1):
            out.append({'id': f'{r["linza_id"]}-{i}', 'linza': r['imya'], 'meta': r['meta'], **x})
    return out


PROMPT_SVOD = """Ниже {n} идей от разных линз, как найти предприятия Алтайского края, использующие
компрессорное оборудование. Многие идеи повторяют друг друга (тот же источник и тот же механизм).
Сведи их в УНИКАЛЬНЫЕ ПРИЁМЫ. Приём = один источник (реестр/сайт/API/документ) + один механизм
поиска. Два разных механизма на одном источнике - два приёма. Один и тот же механизм на
однотипных источниках (пять торговых площадок теми же словами) - один приём с перечислением.
Правила:
- КАЖДЫЙ id идеи должен попасть ровно в один приём; не теряй ни одного id;
- название приёма конкретное: источник + что делаем (до 120 знаков);
- istochnik: адрес/имя источника; klass: прямое | косвенное | кандидат | контроль/метод
  (для приёмов про сшивку, дедупликацию, оценку полноты, контроли);
- cena: дёшево | средне | дорого (по большинству идей приёма).
Верни СТРОГО JSON: {{"priyomy":[{{"nazvanie":"...","istochnik":"...","klass":"...","cena":"...",
"sut":"1-2 предложения, как именно делаем","idei":["id","id"]}}]}}

ИДЕИ:
{idei}"""

PROMPT_DOPRIPISKA = """Есть список приёмов (id + название + суть) и несколько идей, которые не были
отнесены ни к одному приёму. Для каждой идеи укажи id существующего приёма, куда она относится,
либо предложи НОВЫЙ приём (id "NEW-<n>") в том же формате. Верни СТРОГО JSON:
{{"privyazki":[{{"ideya_id":"...","priyom_id":"P0xx или NEW-1"}}],
"novye":[{{"id":"NEW-1","nazvanie":"...","istochnik":"...","klass":"...","cena":"...","sut":"..."}}]}}

ПРИЁМЫ:
{priyomy}

ИДЕИ БЕЗ ПРИЁМА:
{idei}"""


PROMPT_SLIYANIE = """Ниже список приёмов поиска предприятий Алтайского края с компрессорным оборудованием,
собранных независимо разными ракурсами. Между ними много дублей: тот же источник и тот же механизм.
Слей их в ГРУППЫ уникальных приёмов. Правило: группа = один источник + один механизм; разные механизмы
на одном источнике - разные группы; один механизм на однотипных источниках (пять торговых площадок
теми же словами) - одна группа. КАЖДЫЙ id должен попасть ровно в одну группу; не теряй ни одного id.
Название группы конкретное: источник + что делаем, до 110 знаков. Больше ничего не пиши.
Верни СТРОГО компактный JSON: {{"g":[{{"n":"название","c":["id","id"]}}]}}

ПРИЁМЫ:
{priyomy}"""


def _bolshinstvo(vals, default=''):
    from collections import Counter
    vals = [v for v in vals if v]
    return Counter(vals).most_common(1)[0][0] if vals else default


def _sliyanie(client, items, metka):
    """items: список dict с id, nazvanie, istochnik, klass, cena, sut, idei. Возвращает группы того же вида."""
    txt = '\n'.join(f'{p["id"]} | {p["nazvanie"][:110]} | {str(p.get("istochnik", ""))[:60]}' for p in items)
    d = sprosit(client, PROMPT_SLIYANIE.format(priyomy=txt))
    po_id = {p['id']: p for p in items}
    naznacheno = set()
    out = []
    for g in d.get('g', []):
        chleny = [c for c in g.get('c', []) if c in po_id and c not in naznacheno]
        if not chleny:
            continue
        naznacheno.update(chleny)
        m = [po_id[c] for c in chleny]
        out.append({'id': f'{metka}-{len(out) + 1}', 'nazvanie': g.get('n', '') or m[0]['nazvanie'],
                    'istochnik': _bolshinstvo([x.get('istochnik') for x in m]),
                    'klass': _bolshinstvo([x.get('klass') for x in m]), 'cena': _bolshinstvo([x.get('cena') for x in m]),
                    'sut': m[0].get('sut', ''), 'lokalnye': [l for x in m for l in x.get('lokalnye', [x['id']])],
                    'idei': [i for x in m for i in x['idei']]})
    poteryany = [p for p in items if p['id'] not in naznacheno]
    for p in poteryany:
        out.append({**p, 'id': f'{metka}-{len(out) + 1}', 'lokalnye': p.get('lokalnye', [p['id']])})
    return out, len(poteryany)


def svod(client, nitey=3):
    idei = idei_ploskie()
    po_meta = {}
    for x in idei:
        po_meta.setdefault(x['id'].split('-')[0], []).append(x)
    print(f'свод: идей {len(idei)}, металинз {len(po_meta)}')
    f_lok = os.path.join(HERE, 'priyomy-lokalnye.json')
    if os.path.exists(f_lok):
        lokalnye = json.load(open(f_lok, encoding='utf-8'))
        print(f'  локальные приёмы взяты из файла: {len(lokalnye)}')
    else:
        lokalnye = []

        def odna(mid):
            pr, ost = _svod_odnogo(client, po_meta[mid], mid)
            return mid, pr, ost

        with ThreadPoolExecutor(nitey) as ex:
            for f in as_completed([ex.submit(odna, m) for m in sorted(po_meta)]):
                mid, pr, ost = f.result()
                lokalnye.extend(pr)
                print(f'  {mid}: идей {len(po_meta[mid])}, локальных приёмов {len(pr)}, разложено поштучно {ost}')
        json.dump(lokalnye, open(f_lok, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # уровень 1: слияние по пачкам из 3 металинз
    metas = sorted(po_meta)
    pachki = [metas[i:i + 3] for i in range(0, len(metas), 3)]

    def odna_pachka(k):
        ms = pachki[k]
        items = [p for p in lokalnye if p['id'].split('-')[0] in ms]
        g, ost = _sliyanie(client, items, f'G{k + 1}')
        return k, len(items), g, ost

    promezh = []
    with ThreadPoolExecutor(nitey) as ex:
        for f in as_completed([ex.submit(odna_pachka, k) for k in range(len(pachki))]):
            k, n, g, ost = f.result()
            promezh.extend(g)
            print(f'  уровень 1, пачка {k + 1} ({"+".join(pachki[k])}): {n} -> {len(g)} групп, не вошло {ost}')
    json.dump(promezh, open(os.path.join(HERE, 'priyomy-promezh.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # уровень 2: общее слияние
    fin, ost = _sliyanie(client, promezh, 'F')
    pr = []
    for i, g in enumerate(fin, 1):
        pr.append({**g, 'id': f'P{i:03d}'})
    vse = {x['id'] for x in idei}
    pokryto = {iid for p in pr for iid in p['idei']}
    print(f'  уровень 2: {len(promezh)} -> {len(pr)} приёмов, не вошло {ost}, идей покрыто {len(pokryto)}/{len(vse)}')
    json.dump({'priyomy': pr, 'poteryany': sorted(vse - pokryto)}, open(F_PRIYOMY, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    return pr


PROMPT_PROVERKA = """Ниже три документа команды о том, какие инструменты (скрипты, операции раннера,
каналы данных) УЖЕ написаны и проверены живыми запусками. Затем - список приёмов поиска предприятий
Алтайского края с компрессорным оборудованием. Для КАЖДОГО приёма определи:
  status:
    "реализовано" - в документах есть готовый инструмент/операция/канал, который делает именно это
                    (пусть и без фильтра по региону, если фильтр тривиален - ИНН на 22);
    "частично"    - инструмент есть для соседней задачи или соседнего источника, нужна доработка
                    (другие слова, другой раздел сайта, новый парсер поля, регион не режется);
    "нет"         - в документах нет инструмента для этого источника/механизма;
    "закрыт"      - документы прямо говорят, что источник/канал сейчас не работает или недоступен.
  chem      - имя скрипта/операции/канала из документов (дословно), пусто если "нет"
  citata    - ДОСЛОВНАЯ цитата из документов (40-200 знаков, без изменений, без многоточий внутри),
              подтверждающая status; для "нет" - пусто. Без дословной цитаты статус не засчитается.
  dokument  - имя файла, откуда цитата
  chto_dodelat - что именно надо дописать/поменять, чтобы приём заработал под Алтайский край (1-2 предложения)
  sloy      - откуда доступен источник по документам: песочница | сервер | оба | неизвестно
Верни СТРОГО JSON: {{"proverka":[{{"id":"P0xx","status":"...","chem":"...","citata":"...","dokument":"...",
"chto_dodelat":"...","sloy":"..."}}]}}

=== ДОКУМЕНТ 1: PARK-2S-INSTRUMENTY-peredacha.md ===
{d1}

=== ДОКУМЕНТ 2: INSTRUMENTY-I-PRIYOMY.md ===
{d2}

=== ДОКУМЕНТ 3: DOKA-kakoy-skript-chto-delaet.md ===
{d3}

=== ПРИЁМЫ ===
{priyomy}"""

KONTROL = [
    {'id': 'K-DA', 'nazvanie': 'Прогнать список ИНН края по карточкам эксплуатанта monitor-pb.ru/customer/<ИНН> и взять все заключения ЭПБ',
     'istochnik': 'monitor-pb.ru', 'klass': 'прямое', 'sut': 'по каждому ИНН открыть карточку и снять заключения с датами'},
    {'id': 'K-NET', 'nazvanie': 'Запросить у оператора сотовой связи обезличенные данные о плотности абонентов рядом с цехами и по ним найти работающие компрессорные',
     'istochnik': 'операторы связи', 'klass': 'кандидат', 'sut': 'купить геоаналитику и сопоставить с адресами предприятий'},
]


def _norm(s):
    return re.sub(r'\s+', ' ', s.replace('ё', 'е').replace('«', '"').replace('»', '"')
                  .replace('“', '"').replace('”', '"').replace('’', "'").replace('`', '')).strip().lower()


def _citata_v_dokah(cit, doki_norm):
    """Цитата засчитана, если КАЖДЫЙ её фрагмент (разделители «…», «...», « ... ») длиной >= 20 знаков
    найден в одном и том же документе дословно (после нормализации пробелов/кавычек/ё)."""
    if len(cit) < 25:
        return None
    frag = [f.strip() for f in re.split(r'…|\.\.\.', cit) if len(f.strip()) >= 20]
    if not frag:
        return None
    for n, tn in doki_norm.items():
        if all(_norm(f) in tn for f in frag):
            return n
    return None


def proverka(client, nitey):
    doki = {n: open(os.path.join(HERE, n), encoding='utf-8').read() for n in DOKI}
    doki_norm = {n: _norm(t) for n, t in doki.items()}
    pr = json.load(open(F_PRIYOMY, encoding='utf-8'))['priyomy']
    gotovo = {json.loads(l)['id'] for l in open(F_PROVERKA, encoding='utf-8')} if os.path.exists(F_PROVERKA) else set()
    ochered = [p for p in pr if p['id'] not in gotovo]
    kontrol = [k for k in KONTROL if k['id'] not in gotovo]
    pachki = [ochered[i:i + PACHKA] for i in range(0, len(ochered), PACHKA)]
    if kontrol:
        if pachki:
            pachki[0] = kontrol + pachki[0]
        else:
            pachki = [kontrol]
    print(f'проверка: приёмов {len(pr)}, готово {len(gotovo)}, пачек {len(pachki)}')

    def odna(pachka):
        t = time.time()
        txt = '\n'.join(f'{p["id"]} | {p["nazvanie"]} | источник: {p.get("istochnik","")} | класс: {p.get("klass","")} | суть: {p.get("sut","")}'
                        for p in pachka)
        d = sprosit(client, PROMPT_PROVERKA.format(d1=doki[DOKI[0]], d2=doki[DOKI[1]], d3=doki[DOKI[2]], priyomy=txt))
        out = []
        ids = {p['id'] for p in pachka}
        for r in d.get('proverka', []):
            if r.get('id') not in ids:
                continue
            cit = r.get('citata') or ''
            nayd = _citata_v_dokah(cit, doki_norm)
            r['citata_naydena'] = bool(nayd)
            r['dokument_fakt'] = nayd or ''
            if r.get('status') in ('реализовано', 'частично', 'закрыт') and not nayd:
                r['status_ishodnyy'] = r['status']
                r['status'] = 'не подтверждено цитатой'
            out.append(r)
        with _lock:
            with open(F_PROVERKA, 'a', encoding='utf-8') as f:
                for r in out:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
                f.flush(); os.fsync(f.fileno())
        return f'пачка {pachka[0]["id"]}..{pachka[-1]["id"]}: ответов {len(out)}/{len(pachka)}, {round(time.time()-t)} с'

    with ThreadPoolExecutor(nitey) as ex:
        futs = {ex.submit(odna, p): p[0]['id'] for p in pachki}
        for f in as_completed(futs):
            try:
                print('  ', f.result())
            except Exception as e:
                print('  СБОЙ', futs[f], repr(e)[:200])


def itog():
    if not os.path.exists(F_PROVERKA):
        return
    rows = [json.loads(l) for l in open(F_PROVERKA, encoding='utf-8')]
    from collections import Counter
    c = Counter(r['status'] for r in rows)
    print('ИТОГ проверки:', dict(c))
    for r in rows:
        if r['id'].startswith('K-'):
            print('  КОНТРОЛЬ', r['id'], '->', r['status'], '|', r.get('chem'), '| цитата найдена:', r['citata_naydena'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--tolko', choices=['svod', 'proverka'], default=None)
    ap.add_argument('--nitey', type=int, default=3)
    a = ap.parse_args()
    client = make_client()
    if a.tolko in (None, 'svod'):
        svod(client, a.nitey)
    if a.tolko in (None, 'proverka'):
        proverka(client, a.nitey)
    itog()
