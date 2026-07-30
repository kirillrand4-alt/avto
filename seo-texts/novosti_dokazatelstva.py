# -*- coding: utf-8 -*-
"""Доказательства машины из статей и новостей — отдельной базой, каждое со ссылкой и цитатой.

Зачем отдельно. Реестр ЭПБ и закупки говорят «была экспертиза» и «объявлена процедура». Статья
говорит другое и часто больше: ЧТО стоит на площадке и что с ним делают. Живой пример, с
которого владелец и распорядился завести эту базу:

    «Реконструкция центральной компрессорной станции ЦВК цеха №15 с поэтапной безостановочной
     заменой всего оборудования: воздушные центробежные компрессоры, осушители…»
    — АО «Газпромнефть-МНПЗ», cvert.ru

Ни в реестре ЭПБ, ни в закупках такого нет. Это прямое подтверждение ВОЗДУШНОЙ ЦЕНТРОБЕЖНОЙ
машины плюс повод: идёт замена всего оборудования станции.

Как устроено. Три звена, каждое своим инструментом:
1. `news_scan` раннера с нашими запросами — ищет статьи (ключ `xmlriver_queries` читается ТОЛЬКО
   при явном `collectors: ["xmlriver"]`, иначе задание молча уходит на свой каталог триггеров);
2. `fetch_url` раннера — тянет статью целиком: их пайплайн отдаёт ссылку и пересказ события,
   но текст не возвращает;
3. **провайдер** — читает статью и вынимает доказательство машины, цитату, марки и названных
   людей. Свободный текст модели, ровный формат шаблону.

Заслон против выдумки: цитата обязана дословно встречаться в тексте статьи, иначе строка не
пишется. Без цитаты и ссылки строки нет вовсе — это и есть перепроверяемость.

Использование:
    python3 novosti_dokazatelstva.py --iskat [--predel 40]   # запросы → ссылки на статьи
    python3 novosti_dokazatelstva.py --tyanut                # статьи целиком через раннер
    python3 novosti_dokazatelstva.py --razobrat              # статьи → доказательства и люди
"""
import csv
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
DROP = os.path.join(BAZA, 'server', 'drop_client.sh')
RAB = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad'
STATI = os.path.join(RAB, 'stati')
SSYLKI = os.path.join(RAB, 'novosti_ssylki.jsonl')
L = os.path.join(BAZA, 'engineers-lens')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
VYHOD = os.path.join(L, 'DOKAZATELSTVA-iz-novostey.csv')
# Отсев храним, а не только считаем. Отброшенное — это не мусор, а материал, по которому мы
# приняли решение: цитата не нашлась, юрлицо оказалось другим, имени нет в тексте. Решение может
# быть неверным, и тогда единственный способ это увидеть — открыть отброшенное и посмотреть.
# Повторно скачать статью дороже, чем хранить строку.
OTSEV = os.path.join(L, 'OTSEV-iz-novostey.csv')

# Запросы под доказательство машины, а не под людей. Порядок по точности: первым идёт то,
# что в тексте статьи стоит рядом со словами «воздушный» и «центробежный».
ZAPROSY = [
    '{n} воздушный центробежный компрессор',
    '{n} компрессорная станция реконструкция',
    '{n} воздуходувка модернизация очистных',
    '{n} замена компрессорного оборудования',
]


def na_drop(*puti):
    """Выложить итог на дроп сразу после записи, а не «когда вспомню».

    Владелец спросил «но всё сохраняется на дроп?» — и до этого вопроса отсев никуда не
    сохранялся вовсе, только считался. Теперь и итог, и отсев уходят на обменник в конце шага:
    контейнер сессии эфемерный, а соседним сессиям и владельцу файлы нужны без нашего участия.
    """
    for p in puti:
        if p and os.path.exists(p):
            r = subprocess.run(['bash', DROP, 'up', p], capture_output=True, text=True, timeout=600)
            print(f'  на дроп: {os.path.basename(p)} — {(r.stdout or r.stderr).strip()[:90]}',
                  file=sys.stderr)


def imya_kompanii(s):
    return re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО|ГУП|МУП|ФГУП)\s+', '', s or '').strip().strip('"«»')


def shag_iskat(predel=40, pachka=8):
    """Запросы к раннеру пачками по предприятиям очереди; ссылки копим в журнал."""
    rows = list(csv.DictReader(open(OCHERED, encoding='utf-8-sig'), delimiter=';'))
    bylo = set()
    if os.path.exists(SSYLKI):
        for l in open(SSYLKI, encoding='utf-8'):
            try:
                bylo.add(json.loads(l).get('inn'))
            except json.JSONDecodeError:
                pass
    rows = [r for r in rows if r['inn'] not in bylo][:predel]
    print(f'предприятий к поиску: {len(rows)} (пройдено {len(bylo)})', file=sys.stderr)
    f = open(SSYLKI, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = {'запросов': 0, 'материалов': 0, 'предприятий с материалом': 0}

    def odna(gr):
        zapr = [z.format(n=imya_kompanii(r['predpriyatie'])) for r in gr for z in ZAPROSY]
        args = {'op': 'news_scan', 'collectors': ['xmlriver'], 'xmlriver_queries': zapr,
                'xmlriver_engines': ['yandex', 'google'], 'days': 2500, 'max_items': 30,
                'limit': 60}
        p = subprocess.run([sys.executable, KLIENT, 'news_scan',
                            json.dumps(args, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=2400)
        m = re.search(r'\{.*\}', p.stdout, re.S)
        if not m:
            return gr, [], len(zapr), (p.stdout or p.stderr)[-140:]
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            return gr, [], len(zapr), str(e)[:80]
        dd = d.get('data') or d
        return gr, (dd.get('events') or []), len(zapr), ''

    pachki = [rows[i:i + pachka] for i in range(0, len(rows), pachka)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i, (gr, sob, nz, err) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                sch['запросов'] += nz
                if err:
                    print(f'  СБОЙ пачки {i}: {err[:110]}', file=sys.stderr)
                    continue
                # привязка материала к предприятию по запросу, в котором стоит его имя
                for r in gr:
                    im = imya_kompanii(r['predpriyatie']).lower()
                    svoi = [e for e in sob if im and im in (e.get('query') or '').lower()]
                    f.write(json.dumps({'inn': r['inn'], 'predpriyatie': r['predpriyatie'],
                                        'materialy': svoi}, ensure_ascii=False) + '\n')
                    sch['материалов'] += len(svoi)
                    if svoi:
                        sch['предприятий с материалом'] += 1
                f.flush()
                print(f'  пачек {i}/{len(pachki)}: ' + ', '.join(f'{k} {v}' for k, v in sch.items()),
                      file=sys.stderr, flush=True)
    f.close()


def shag_tyanut(pachka=8, predel=300):
    """Статьи целиком: их задание отдаёт ссылку и пересказ, но не текст."""
    os.makedirs(STATI, exist_ok=True)
    zad, karta = [], {}
    for l in open(SSYLKI, encoding='utf-8'):
        try:
            x = json.loads(l)
        except json.JSONDecodeError:
            continue
        for j, e in enumerate(x.get('materialy') or []):
            u = e.get('source_url') or ''
            if not u:
                continue
            imya = f"st_{x['inn']}_{j}.html"
            karta[imya] = {'inn': x['inn'], 'predpriyatie': x['predpriyatie'],
                           'ssylka': u, 'zagolovok': e.get('title') or '',
                           'data': e.get('published') or '', 'istochnik': e.get('source_name') or '',
                           'zapros': e.get('query') or ''}
            if not os.path.exists(os.path.join(STATI, imya)):
                zad.append({'task': 'fetch_url', 'args': {'url': u, 'insecure': True, 'name': imya}})
    json.dump(karta, open(os.path.join(STATI, 'karta.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    zad = zad[:predel]
    print(f'статей к скачиванию: {len(zad)}', file=sys.stderr)
    for k in range(0, len(zad), pachka):
        p = subprocess.run([sys.executable, KLIENT, '--many',
                            json.dumps(zad[k:k + pachka], ensure_ascii=False), '--threads',
                            str(pachka)], capture_output=True, text=True, timeout=1800)
        m = re.search(r'\[.*\]', p.stdout, re.S)
        for r in (json.loads(m.group(0)) if m else []):
            d = (r or {}).get('data') or {}
            if d.get('drop_name') and (d.get('bytes') or 0) > 1500:
                subprocess.run(['bash', DROP, 'down', d['drop_name']], cwd=STATI,
                               capture_output=True, timeout=300)
        print(f'  {min(k + pachka, len(zad))}/{len(zad)}, на диске '
              f'{len([f for f in os.listdir(STATI) if f.endswith(".html")])}',
              file=sys.stderr, flush=True)


PROMPT = """Статья или новость о российском предприятии.

ИЩЕМ ПО ПРЕДПРИЯТИЮ: {predpriyatie} (ИНН {inn}). Всё, что не про него, нам не нужно.

ЗАЧЕМ. ООО «Руспром» продаёт ВОЗДУШНЫЕ ЦЕНТРОБЕЖНЫЕ компрессоры и воздуходувки. Ищем в тексте
два разных сведения, и их нельзя путать:

A. **ДОКАЗАТЕЛЬСТВО МАШИНЫ** — упоминание, что у предприятия есть, ставится, ремонтируется или
   закупается компрессор либо воздуходувка. Нужны: тип (`центробежный`, `поршневой`, `винтовой`,
   `не назван`), среда (`воздух`, `газ`, `не названа`), марка, что именно происходит
   (`есть`, `ремонт`, `реконструкция`, `замена`, `закупка`, `планируют`).
B. **ЛЮДИ** — названные по имени работники ЭТОГО предприятия с должностью, особенно технические:
   главный инженер, главный механик, главный энергетик, технический директор, начальник
   компрессорной, начальник цеха. Директор и руководитель филиала тоже нужны.

ПРАВИЛА, нарушать нельзя:
1. **`citata` обязана быть дословным куском текста статьи.** Не пересказывай. Если дословной
   цитаты нет — не пиши запись вовсе.
2. Ничего не достраивай: ни марок, ни должностей, ни имён.
3. Если статья не про наше предприятие или про другое юрлицо — скажи это в `pochemu` и верни
   пустые списки.
4. Про людей из ДРУГИХ организаций (губернатор, чиновник, поставщик) — не пиши.

5. **ГЛАВНОЕ: убедись, что статья про НУЖНОЕ предприятие.** Выдача поисковика промахивается
   постоянно: по запросу про одну компанию приходит статья про однофамильца, про другой завод
   того же холдинга или вообще про иностранную фирму (в нашей пробе по запросу «технический
   директор» пришла статья про Mercedes). Поэтому верни `nazvanie_v_state` — как предприятие
   названо В САМОМ ТЕКСТЕ, дословно, — и `privyazka`:
   `ИНН в тексте` | `полное название совпало` | `краткое имя совпало` | `похоже, но другое
   юрлицо` | `не про него`.
   **Холдинг это ДРУГОЕ предприятие.** «Газпром нефть» и «Газпромнефть-Московский НПЗ» —
   разные юрлица с разными ИНН; филиал и головная компания тоже разные. Если статья про
   родственное, но не то юрлицо — ставь `похоже, но другое юрлицо` и назови, про какое.

ОТВЕТ — строго JSON:
{"mashiny":[{"tip":"","sreda":"","marka":"","chto_proishodit":"","citata":""}],
 "lyudi":[{"imya":"","dolzhnost":"","citata":""}],
 "pro_nashe_predpriyatie": true, "nazvanie_v_state":"", "privyazka":"", "pochemu":""}"""


def bez_tegov(h):
    h = re.sub(r'(?is)<(script|style|noscript).*?</\1>', ' ', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"'), ('&laquo;', '«'),
                 ('&raquo;', '»'), ('&#39;', "'")):
        h = h.replace(a, b)
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n', h)).strip()


def shag_razobrat(threads=6):
    import gen_provider as G
    G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                     'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}
    karta = json.load(open(os.path.join(STATI, 'karta.json'), encoding='utf-8'))
    fajly = sorted(f for f in os.listdir(STATI) if f.endswith('.html'))
    print(f'статей к разбору: {len(fajly)}', file=sys.stderr)
    client = G.make_client()
    lock = threading.Lock()
    itog, otsev, sch = [], [], {'машин': 0, 'центробежных': 0, 'воздушных': 0, 'людей': 0, 'мимо': 0,
                     'сбоев': 0, 'цитата не найдена': 0, 'имени нет в тексте': 0,
                     'другое юрлицо': 0}

    def klyuchevye(nazv):
        """Различительные куски имени: длинные слова и корни, по которым статью можно узнать."""
        n = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО|ГУП|МУП|ФГУП)\s+', '', nazv or '')
        n = n.strip().strip('"«»')
        slova = [w for w in re.split(r'[\s\-«»"(),]+', n) if len(w) >= 5]
        return slova or ([n] if n else [])

    def odna(f):
        k = karta.get(f) or {}
        tekst = bez_tegov(open(os.path.join(STATI, f), encoding='utf-8', errors='replace').read())
        if len(tekst) < 300:
            return f, None, tekst, 'статья пустая'
        # РУБЕЖ ДО ПРОВАЙДЕРА: если ни одного различительного слова названия в тексте нет,
        # статья заведомо не про нас — и платить за её чтение незачем. Владелец: «главное чтобы
        # предприятие было то что нужно, там бывают промахи». Первый промах ловится механически,
        # второй (родственное юрлицо, филиал, холдинг) — уже провайдером.
        kl = klyuchevye(k.get('predpriyatie', ''))
        nizhe = tekst.lower()
        if kl and not any(w.lower()[:7] in nizhe for w in kl):
            return f, None, tekst, 'название предприятия в тексте не встречается'
        telo = (PROMPT.replace('{predpriyatie}', k.get('predpriyatie', ''))
                      .replace('{inn}', k.get('inn', '')))
        try:
            o = G.call(client, [{'role': 'user', 'content': telo + '\n\nСТАТЬЯ:\n' + tekst[:60000]}],
                       model='claude-fable-5', attempts=3)
            txt = ''.join(b.text for b in o.content if b.type == 'text')
            m = re.search(r'\{.*\}', txt, re.S)
            return f, (json.loads(m.group(0)) if m else None), tekst, ''
        except Exception as e:  # noqa: BLE001
            return f, None, tekst, f'{type(e).__name__}: {str(e)[:70]}'

    def est_citata(c, tekst):
        c = re.sub(r'\s+', ' ', (c or '')).strip()
        return len(c) > 15 and c[:60] in re.sub(r'\s+', ' ', tekst)

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, (f, res, tekst, err) in enumerate(pool.map(odna, fajly), 1):
            with lock:
                k = karta.get(f) or {}
                if err == 'название предприятия в тексте не встречается':
                    sch['имени нет в тексте'] += 1
                    otsev.append({**k, 'prichina': 'имени предприятия нет в тексте статьи',
                                  'kto_otsek': 'шаблон, до провайдера', 'fajl': f,
                                  'nachalo_teksta': re.sub(r'\s+', ' ', tekst)[:300]})
                elif err or not res:
                    sch['сбоев'] += 1
                    otsev.append({**k, 'prichina': err or 'ответ провайдера не разобран',
                                  'kto_otsek': 'сбой', 'fajl': f,
                                  'nachalo_teksta': re.sub(r'\s+', ' ', tekst)[:300]})
                elif not res.get('pro_nashe_predpriyatie') or \
                        'другое юрлицо' in (res.get('privyazka') or ''):
                    sch['другое юрлицо' if 'другое' in (res.get('privyazka') or '') else 'мимо'] += 1
                    otsev.append({**k, 'prichina': (res.get('pochemu') or 'не про наше предприятие')[:200],
                                  'kto_otsek': 'провайдер', 'privyazka': res.get('privyazka') or '',
                                  'nazvanie_v_state': (res.get('nazvanie_v_state') or '')[:70],
                                  'fajl': f, 'nachalo_teksta': re.sub(r'\s+', ' ', tekst)[:300]})
                else:
                    for m_ in res.get('mashiny') or []:
                        if not est_citata(m_.get('citata'), tekst):
                            sch['цитата не найдена'] += 1
                            otsev.append({**k, 'prichina': 'цитата о машине не найдена в тексте',
                                          'kto_otsek': 'заслон против выдумки', 'fajl': f,
                                          'citata_modeli': (m_.get('citata') or '')[:300]})
                            continue
                        sch['машин'] += 1
                        if 'центробеж' in (m_.get('tip') or '').lower():
                            sch['центробежных'] += 1
                        if 'воздух' in (m_.get('sreda') or '').lower():
                            sch['воздушных'] += 1
                        itog.append({**k, 'privyazka': res.get('privyazka') or '',
                                     'nazvanie_v_state': (res.get('nazvanie_v_state') or '')[:70],
                                     'vid_zapisi': 'машина', 'tip': m_.get('tip') or '',
                                     'sreda': m_.get('sreda') or '', 'marka': m_.get('marka') or '',
                                     'chto_proishodit': m_.get('chto_proishodit') or '',
                                     'citata': (m_.get('citata') or '')[:400], 'fajl': f})
                    for c in res.get('lyudi') or []:
                        if not est_citata(c.get('citata'), tekst):
                            sch['цитата не найдена'] += 1
                            otsev.append({**k, 'prichina': 'цитата о человеке не найдена в тексте',
                                          'kto_otsek': 'заслон против выдумки', 'fajl': f,
                                          'imya': c.get('imya') or '',
                                          'citata_modeli': (c.get('citata') or '')[:300]})
                            continue
                        sch['людей'] += 1
                        itog.append({**k, 'privyazka': res.get('privyazka') or '',
                                     'nazvanie_v_state': (res.get('nazvanie_v_state') or '')[:70],
                                     'vid_zapisi': 'человек', 'imya': c.get('imya') or '',
                                     'dolzhnost': c.get('dolzhnost') or '',
                                     'citata': (c.get('citata') or '')[:400], 'fajl': f})
                if i % 20 == 0:
                    print(f'  {i}/{len(fajly)}: ' + ', '.join(f'{a} {b}' for a, b in sch.items()),
                          file=sys.stderr, flush=True)

    cols = ['inn', 'predpriyatie', 'privyazka', 'nazvanie_v_state', 'vid_zapisi', 'tip', 'sreda', 'marka', 'chto_proishodit',
            'imya', 'dolzhnost', 'citata', 'zagolovok', 'data', 'istochnik', 'ssylka', 'zapros',
            'fajl']
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in itog:
            w.writerow(r)
    ocols = ['inn', 'predpriyatie', 'prichina', 'kto_otsek', 'privyazka', 'nazvanie_v_state',
             'imya', 'citata_modeli', 'zagolovok', 'data', 'istochnik', 'ssylka', 'zapros',
             'fajl', 'nachalo_teksta']
    with open(OTSEV, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=ocols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in otsev:
            w.writerow(r)
    na_drop(VYHOD, OTSEV)
    pr = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    print(f'отсев сохранён: {len(otsev)} строк → {OTSEV}', file=sys.stderr)
    print(f'\nИЗ ФАЙЛА: строк {len(pr)}, предприятий {len({r["inn"] for r in pr})}', file=sys.stderr)
    print(f'  записей о машине: {sum(1 for r in pr if r["vid_zapisi"] == "машина")}, '
          f'из них центробежных {sum(1 for r in pr if "центробеж" in r["tip"].lower())}, '
          f'воздушных {sum(1 for r in pr if "воздух" in r["sreda"].lower())}', file=sys.stderr)
    print(f'  людей: {sum(1 for r in pr if r["vid_zapisi"] == "человек")}', file=sys.stderr)
    print(f'  строк без ссылки: {sum(1 for r in pr if not r["ssylka"])} (должно быть 0)',
          file=sys.stderr)
    print(f'  отброшено, цитата не найдена в тексте: {sch["цитата не найдена"]}', file=sys.stderr)
    print(f'  отсеяно ДО провайдера, имени предприятия в статье нет: {sch["имени нет в тексте"]}',
          file=sys.stderr)
    print(f'  отсеяно провайдером как ДРУГОЕ юрлицо: {sch["другое юрлицо"]}, не про нас: {sch["мимо"]}',
          file=sys.stderr)
    import collections as _c
    print('  привязка у оставшихся строк:',
          dict(_c.Counter(r['privyazka'] for r in pr)), file=sys.stderr)
    print(f'→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    if '--iskat' in sys.argv:
        pr = int(sys.argv[sys.argv.index('--predel') + 1]) if '--predel' in sys.argv else 40
        shag_iskat(predel=pr)
    elif '--tyanut' in sys.argv:
        shag_tyanut()
    elif '--razobrat' in sys.argv:
        shag_razobrat()
    else:
        print(__doc__)
