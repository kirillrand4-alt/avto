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


def svod(client):
    idei = idei_ploskie()
    kratko = '\n'.join(f'[{x["id"]}] {x["ideya"][:260]} || где: {str(x.get("gde_brat",""))[:140]}'
                       for x in idei)
    print(f'свод: идей {len(idei)}, знаков в промпте {len(kratko)}')
    d = sprosit(client, PROMPT_SVOD.format(n=len(idei), idei=kratko))
    pr = d['priyomy']
    for i, p in enumerate(pr, 1):
        p['id'] = f'P{i:03d}'
    vse = {x['id'] for x in idei}
    naznacheno = {}
    for p in pr:
        for iid in p['idei']:
            naznacheno.setdefault(iid, p['id'])
    poteryany = sorted(vse - set(naznacheno))
    lishnie = sorted(set(naznacheno) - vse)
    print(f'  приёмов {len(pr)}, идей привязано {len(naznacheno)}, потеряно {len(poteryany)}, выдуманных id {len(lishnie)}')
    if poteryany:
        po_id = {x['id']: x for x in idei}
        kr = '\n'.join(f'[{i}] {po_id[i]["ideya"][:260]}' for i in poteryany)
        krp = '\n'.join(f'{p["id"]} {p["nazvanie"]} :: {p["sut"][:150]}' for p in pr)
        d2 = sprosit(client, PROMPT_DOPRIPISKA.format(priyomy=krp, idei=kr))
        novye = {n['id']: n for n in d2.get('novye', [])}
        for pv in d2.get('privyazki', []):
            pid = pv['priyom_id']
            if pid.startswith('NEW'):
                n = novye.get(pid)
                if n is None:
                    continue
                if 'real_id' not in n:
                    n['real_id'] = f'P{len(pr)+1:03d}'
                    pr.append({**{k: v for k, v in n.items() if k not in ('id', 'real_id')},
                               'id': n['real_id'], 'idei': []})
                pid = n['real_id']
            for p in pr:
                if p['id'] == pid and pv['ideya_id'] in vse and pv['ideya_id'] not in naznacheno:
                    p['idei'].append(pv['ideya_id']); naznacheno[pv['ideya_id']] = pid
        poteryany = sorted(vse - set(naznacheno))
        print(f'  после доприписки: приёмов {len(pr)}, потеряно {len(poteryany)}')
    # убрать выдуманные id
    for p in pr:
        p['idei'] = [i for i in p['idei'] if i in vse]
    json.dump({'priyomy': pr, 'poteryany': poteryany}, open(F_PRIYOMY, 'w', encoding='utf-8'),
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
            nayd = None
            if len(cit) >= 25:
                cn = _norm(cit)
                for n, tn in doki_norm.items():
                    if cn in tn:
                        nayd = n; break
                # мягкая проверка: первые 60 знаков цитаты
                if nayd is None:
                    for n, tn in doki_norm.items():
                        if cn[:60] in tn:
                            nayd = n; break
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
        svod(client)
    if a.tolko in (None, 'proverka'):
        proverka(client, a.nitey)
    itog()
