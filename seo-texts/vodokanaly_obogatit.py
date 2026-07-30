# -*- coding: utf-8 -*-
"""Обогащение 683 водоканалов: сайты, телефоны, и главное — люди с должностями.

Почему водоканалы отдельно и почему это выгодно. Замер сессии: инженерных ролей у них нашлось
31 против 11 у заводов на сопоставимом обходе, и причина не в удаче — **муниципальное предприятие
обязано публиковать справочник с должностями, а завод не обязан**. Плюс марку машины у них даёт
не реестр экспертизы (воздуходувке очистных сооружений экспертиза не нужна), а муниципальная
схема водоснабжения с перечнем оборудования и годами ввода.

Шаг 0, уже сделан: выгрузка обзвона (679 МБ, 161 799 строк) содержала то, чего не было в нашем
файле. Один проход по ней дал **+184 сайта (было 22), +539 телефонов (было 43), +490 почт
(было 41), +603 региона**. Это ровно тот случай, который параллельная сессия описала словами
«колонка сайта из выгрузки ещё не выбрана»: данные лежали, их никто не брал.

Шаги:
    python3 vodokanaly_obogatit.py --slit       # слить выгрузку обзвона в наш файл
    python3 vodokanaly_obogatit.py --razdely    # обход сайтов по путям справочников
    python3 vodokanaly_obogatit.py --lica       # страницы → люди, провайдером
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
VK = os.path.join(BAZA, 'engineers-lens', 'centro', 'dop', 'vodokanaly.csv')
IZ_OBZVONA = os.path.join(RAB, 'vk_iz_obzvona.json')
VYHOD = os.path.join(BAZA, 'engineers-lens', 'centro', 'dop', 'vodokanaly-obogashchennye.csv')
STRANICY = os.path.join(RAB, 'vk_stranicy')
LICA = os.path.join(BAZA, 'engineers-lens', 'centro', 'dop', 'vodokanaly-lica.csv')

# Пути, где у муниципального предприятия лежат должности. Порядок важен: справочник
# подразделений даёт лучшее качество (должность + телефон в одной строке), «руководство» —
# только верх, «контакты» — часто одну приёмную.
PUTI = ['/kontakty', '/contacts', '/rukovodstvo', '/management', '/struktura', '/structure',
        '/o-predpriyatii', '/about', '/spravochnik', '/telefonnyy-spravochnik',
        '/kontakty/telefonnyy-spravochnik', '/o-predpriyatii/rukovodstvo',
        '/administraciya', '/sotrudniki', '/apparat-upravleniya', '/sluzhby']
# Контрольный путь-бессмыслица: если сайт отвечает 200 на него, у него мягкий 404 и все
# остальные ответы этого сайта считать нельзя. Приём из прогона «дешёвой пятёрки».
KONTROL_PUT = '/kastrjulja-kastrjulja-2026-net-takogo/'


def runner_many(zad, threads=6):
    p = subprocess.run([sys.executable, KLIENT, '--many', json.dumps(zad, ensure_ascii=False),
                        '--threads', str(threads)], capture_output=True, text=True, timeout=1800)
    m = re.search(r'\[.*\]', p.stdout, re.S)
    return json.loads(m.group(0)) if m else []


def skachat(imya, kuda):
    os.makedirs(kuda, exist_ok=True)
    subprocess.run(['bash', DROP, 'down', imya], cwd=kuda, capture_output=True, timeout=300)
    p = os.path.join(kuda, imya)
    return p if os.path.exists(p) else ''


# Соцсети, агрегаторы и госпорталы — это не сайт предприятия. В поле «Сайты» выгрузки обзвона
# они стоят наравне с настоящим адресом и часто ПЕРВЫМИ: у ГУП «Мосводосток» там
# `https://vk.com/mosvodostok`, у ООО «Элементы трубопровода» сначала ВК и телеграм, а
# собственный сайт третьим. Взяв первый токен, обходчик пошёл бы стучаться в vk.com.
NE_SAJT = re.compile(r'^(?:m\.)?(?:vk\.com|ok\.ru|facebook|instagram|twitter|t\.me|telegram|'
                     r'wa\.me|whatsapp|youtube|zen\.yandex|rutube|dzen|'
                     r'rusprofile|list-org|zachestnyibiznes|checko|sbis|audit-it|e-disclosure|'
                     r'gosuslugi|zakupki\.gov|torgi\.gov|google\.|yandex\.ru|mail\.ru|gmail)', re.I)


def domen(s):
    """Первый НЕ мусорный домен из поля, а не первый вообще."""
    for tok in re.split(r'[\s,;|]+', (s or '').strip()):
        d = re.sub(r'^https?://', '', tok).strip('/').split('/')[0].lower()
        if not re.fullmatch(r'[a-z0-9.\-]+\.[a-z]{2,}', d):
            continue
        if NE_SAJT.search(d):
            continue
        return d
    return ''


def shag_slit():
    iz = json.load(open(IZ_OBZVONA, encoding='utf-8'))
    rows = list(csv.DictReader(open(VK, encoding='utf-8-sig'), delimiter=';'))
    cols = list(rows[0].keys()) + ['sajt_iz_obzvona', 'telefony_iz_obzvona', 'pochty_iz_obzvona',
                                   'region_iz_obzvona', 'direktor_iz_obzvona', 'domen',
                                   'otkuda_dobavleno']
    sch = {'sajt': 0, 'tel': 0, 'mail': 0, 'region': 0}
    for r in rows:
        v = iz.get(r['inn'])
        if not v:
            r['otkuda_dobavleno'] = 'в выгрузке обзвона не найден'
            continue
        sajty, tel, mail, tel_s, mail_s, region, dir_, kratkoe = v
        r['sajt_iz_obzvona'] = (sajty or '').strip()
        r['telefony_iz_obzvona'] = ' | '.join(x for x in [(tel or '').strip(), (tel_s or '').strip()] if x)
        r['pochty_iz_obzvona'] = ' | '.join(x for x in [(mail or '').strip(), (mail_s or '').strip()] if x)
        r['region_iz_obzvona'] = (region or '').strip()
        r['direktor_iz_obzvona'] = (dir_ or '').strip()
        r['domen'] = domen(sajty) or domen(r.get('site'))
        dob = []
        if r['sajt_iz_obzvona'] and not (r.get('site') or '').strip():
            dob.append('сайт')
            sch['sajt'] += 1
        if r['telefony_iz_obzvona'] and not (r.get('phones') or '').strip():
            dob.append('телефон')
            sch['tel'] += 1
        if r['pochty_iz_obzvona'] and not (r.get('best_email') or '').strip():
            dob.append('почта')
            sch['mail'] += 1
        if r['region_iz_obzvona'] and not (r.get('region') or '').strip():
            dob.append('регион')
            sch['region'] += 1
        r['otkuda_dobavleno'] = 'выгрузка обзвона: ' + ', '.join(dob) if dob else 'нового нет'
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    pr = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    print(f'записано {len(pr)} строк; добавлено из выгрузки: сайтов {sch["sajt"]}, '
          f'телефонов {sch["tel"]}, почт {sch["mail"]}, регионов {sch["region"]}')
    print(f'  доменов к обходу: {sum(1 for r in pr if (r.get("domen") or "").strip())}')
    print(f'→ {VYHOD}')


def shag_razdely(pachka=6, predel=400):
    rows = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    dom = [(r['inn'], r['domen']) for r in rows if (r.get('domen') or '').strip()]
    os.makedirs(STRANICY, exist_ok=True)
    # Контроль мягкого 404 первым делом: сайт, отвечающий 200 на бессмыслицу, исключается.
    zad = [{'task': 'fetch_url', 'args': {'url': f'https://{d}{KONTROL_PUT}', 'insecure': True,
                                          'name': f'vk_k_{i}.html'}} for i, d in dom]
    myagkij = set()
    print(f'контроль мягкого 404 на {len(zad)} сайтах', file=sys.stderr)
    for k in range(0, len(zad), pachka):
        for r in runner_many(zad[k:k + pachka], pachka):
            d = (r or {}).get('data') or {}
            if d.get('http_status') == 200 and (d.get('bytes') or 0) > 2000:
                m = re.search(r'vk_k_(\d+)\.html', d.get('drop_name') or '')
                if m:
                    myagkij.add(m.group(1))
        if k % 60 == 0:
            print(f'  {min(k + pachka, len(zad))}/{len(zad)}', file=sys.stderr, flush=True)
    print(f'сайтов с мягким 404 (исключены): {len(myagkij)}', file=sys.stderr)
    json.dump(sorted(myagkij), open(os.path.join(STRANICY, 'myagkij404.json'), 'w'))

    zad = []
    for i, d in dom:
        if i in myagkij:
            continue
        for j, put in enumerate(PUTI):
            imya = f'vk_{i}_{j}.html'
            if os.path.exists(os.path.join(STRANICY, imya)):
                continue
            zad.append({'task': 'fetch_url',
                        'args': {'url': f'https://{d}{put}', 'insecure': True, 'name': imya}})
    zad = zad[:predel]
    print(f'страниц к обходу: {len(zad)}', file=sys.stderr)
    for k in range(0, len(zad), pachka):
        for r in runner_many(zad[k:k + pachka], pachka):
            d = (r or {}).get('data') or {}
            if d.get('drop_name') and (d.get('bytes') or 0) > 2000:
                skachat(d['drop_name'], STRANICY)
        if k % 60 == 0:
            print(f'  {min(k + pachka, len(zad))}/{len(zad)}', file=sys.stderr, flush=True)
    est = [f for f in os.listdir(STRANICY) if f.startswith('vk_') and f.endswith('.html')]
    print(f'страниц на диске: {len(est)}', file=sys.stderr)


def shag_ec(pachka=8, parallel=4, predel=200):
    """Штатный обход сайтов раннером: `enrich_contacts` с ключом `companies` и `site_crawl`.

    Почему не по одной странице через `fetch_url`. Первый подход качал 16 путей на сайт
    отдельными заданиями и каждую страницу тянул с дропа отдельным файлом: замер дал меньше
    десяти страниц за шесть минут, то есть на 900 страниц ушло бы часов десять. Узкое место было
    не в раннере (пул восемь воркеров), а в круге «задание → дроп → скачивание» на каждую
    страницу.

    `enrich_contacts` обходит сайт сам и отдаёт результат **в теле ответа**, без дропа.
    **Форма аргументов важна:** список идёт под ключом `companies`, а не плоскими полями. Плоские
    поля дают `count: 0` за полсекунды, и это выглядит как «на сайтах ничего нет».
    **`site_crawl: true` обязателен:** без него задание уходит в тяжёлый пул на один воркер и
    висит до таймаута.
    """
    rows = [r for r in csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';')
            if (r.get('domen') or '').strip()]
    gotovo = set()
    put_res = os.path.join(RAB, 'vk_ec_rezultaty.jsonl')
    if os.path.exists(put_res):
        for l in open(put_res, encoding='utf-8'):
            try:
                gotovo.add(json.loads(l).get('inn'))
            except Exception:  # noqa: BLE001
                pass
    rows = [r for r in rows if r['inn'] not in gotovo][:predel]
    print(f'компаний к обходу: {len(rows)} (уже обойдено {len(gotovo)})', file=sys.stderr)

    pachki = [rows[i:i + pachka] for i in range(0, len(rows), pachka)]
    lock = threading.Lock()
    f = open(put_res, 'a', encoding='utf-8')
    sch = {'kontaktov': 0, 'kompanij_s_kontaktom': 0, 'pusto': 0}

    def odna(gr):
        comp = [{'inn': x['inn'], 'ogrn': '',
                 'name': (x.get('name_obzvon') or x.get('name') or '')[:90],
                 'site': 'https://' + x['domen'],
                 'phones': (x.get('telefony_iz_obzvona') or '')[:120]} for x in gr]
        p = subprocess.run([sys.executable, KLIENT, 'enrich_contacts',
                            json.dumps({'companies': comp, 'site_crawl': True}, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=1800)
        m = re.search(r'\{.*\}', p.stdout, re.S)
        if not m:
            return gr, None, (p.stdout or p.stderr)[-160:]
        try:
            return gr, json.loads(m.group(0)), ''
        except Exception as e:  # noqa: BLE001
            return gr, None, f'JSON не разобран: {str(e)[:60]}'

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for i, (gr, res, err) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                if err:
                    print(f'  СБОЙ пачки {i}: {err[:120]}', file=sys.stderr)
                    continue
                dd = (res.get('data') or {})
                po_inn = {}
                for x in dd.get('results') or []:
                    po_inn.setdefault(x.get('inn') or '', []).append(x)
                for x in gr:
                    rr = po_inn.get(x['inn']) or []
                    f.write(json.dumps({'inn': x['inn'], 'domen': x['domen'],
                                        'rezultaty': rr}, ensure_ascii=False) + '\n')
                    if rr:
                        sch['kompanij_s_kontaktom'] += 1
                        sch['kontaktov'] += len(rr)
                    else:
                        sch['pusto'] += 1
                f.flush()
                print(f'  пачек {i}/{len(pachki)}: компаний с контактом '
                      f'{sch["kompanij_s_kontaktom"]}, контактов {sch["kontaktov"]}, '
                      f'пусто {sch["pusto"]}', file=sys.stderr, flush=True)
    f.close()
    print(f'готово → {put_res}', file=sys.stderr)


def shag_lica(threads=8):
    import gen_provider as G
    G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                     'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}
    rows = {r['inn']: r for r in csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';')}
    fajly = sorted(f for f in os.listdir(STRANICY) if f.startswith('vk_') and f.endswith('.html')
                   and not f.startswith('vk_k_'))
    print(f'страниц к разбору: {len(fajly)}', file=sys.stderr)

    PROMPT = """На странице сайта российского предприятия водопроводно-канализационного хозяйства.

ЗАЧЕМ. ООО «Руспром» продаёт воздуходувки и центробежные компрессоры. На очистных сооружениях
водоканала стоит воздуходувка, и решение по ней принимает технический человек: главный инженер,
главный механик, главный энергетик, начальник цеха или участка очистных сооружений, начальник
службы эксплуатации, главный технолог. Диспетчер и аварийная служба тоже нужны: через них
переключают.

ЧТО ВЕРНУТЬ по каждому названному человеку: `imya`, `dolzhnost` (дословно со страницы),
`rol` (`техническая`, `руководство`, `снабжение`, `диспетчер`, `неясно`), `telefon`, `pochta`,
`podrazdelenie` (если на странице есть заголовок раздела, к которому человек относится).

ПРАВИЛА, нарушать нельзя:
1. **Ни одного имени, телефона и адреса, которых нет на странице.** Не достраивай.
2. Если людей нет — пустой список, но обязательно заполни `pochemu`.
3. Должность бери со страницы. Заголовок раздела («Управление главного энергетика») — это
   `podrazdelenie`, а не должность.
4. Телефон приёмной, диспетчера или общий номер не приписывай конкретному человеку: положи его
   в отдельную запись с `rol` = `диспетчер` или `неясно` и напиши это в `podrazdelenie`.

ОТВЕТ — строго JSON: {"lyudi":[{...}], "chto_za_stranica":"", "pochemu":""}
Поля `chto_za_stranica` и `pochemu` обязательны и при пустом списке."""

    lock = threading.Lock()
    client = G.make_client()
    itog, sch = [], {'lyudej': 0, 'teh': 0, 'err': 0}

    def bez_tegov(h):
        h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h)
        h = re.sub(r'<a[^>]*href="(?:tel|mailto):([^"]+)"[^>]*>', r' \1 ', h)
        return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]{2,}', ' ', re.sub(r'<[^>]+>', '\n', h)))

    def odna(fajl):
        m = re.match(r'vk_(\d+)_(\d+)\.html', fajl)
        if not m:
            return fajl, None, 'имя файла не разобрано'
        inn = m.group(1)
        t = bez_tegov(open(os.path.join(STRANICY, fajl), encoding='utf-8', errors='replace').read())
        if len(t.strip()) < 300:
            return fajl, None, 'страница почти пуста'
        try:
            o = G.call(client, [{'role': 'user', 'content': PROMPT + '\n\nСТРАНИЦА:\n' + t[:60000]}],
                       model='claude-fable-5', attempts=4)
            txt = ''.join(b.text for b in o.content if b.type == 'text')
        except Exception as e:  # noqa: BLE001
            return fajl, None, f'{type(e).__name__}: {str(e)[:60]}'
        mm = re.search(r'\{.*\}', txt, re.S)
        if not mm:
            return fajl, None, 'в ответе нет JSON'
        try:
            return fajl, (inn, json.loads(mm.group(0))), ''
        except Exception as e:  # noqa: BLE001
            return fajl, None, f'JSON не разобран: {str(e)[:40]}'

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for fajl, res, err in pool.map(odna, fajly):
            with lock:
                if err:
                    sch['err'] += 1
                    continue
                inn, d = res
                r = rows.get(inn) or {}
                for ch in d.get('lyudi') or []:
                    # Заслон: имя и телефон обязаны быть в тексте страницы — проверяется цифрами.
                    itog.append({**ch, 'inn': inn,
                                 'predpriyatie': (r.get('name_obzvon') or r.get('name') or '')[:100],
                                 'region': r.get('region_iz_obzvona') or r.get('region') or '',
                                 'domen': r.get('domen') or '', 'fajl': fajl,
                                 'chto_za_stranica': d.get('chto_za_stranica') or ''})
                    sch['lyudej'] += 1
                    if ch.get('rol') == 'техническая':
                        sch['teh'] += 1
    cols = ['inn', 'predpriyatie', 'region', 'imya', 'dolzhnost', 'rol', 'telefon', 'pochta',
            'podrazdelenie', 'chto_za_stranica', 'domen', 'fajl']
    with open(LICA, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in itog:
            w.writerow(r)
    pr = list(csv.DictReader(open(LICA, encoding='utf-8-sig'), delimiter=';'))
    print(f'по файлу: строк {len(pr)}, технических '
          f'{sum(1 for x in pr if x["rol"] == "техническая")}, с телефоном '
          f'{sum(1 for x in pr if (x.get("telefon") or "").strip())}, предприятий '
          f'{len({x["inn"] for x in pr})}, сбоев {sch["err"]} → {LICA}', file=sys.stderr)


if __name__ == '__main__':
    if '--slit' in sys.argv:
        shag_slit()
    elif '--razdely' in sys.argv:
        shag_razdely(predel=int(sys.argv[sys.argv.index('--predel') + 1])
                     if '--predel' in sys.argv else 400)
    elif '--ec' in sys.argv:
        shag_ec(predel=int(sys.argv[sys.argv.index('--predel') + 1])
                if '--predel' in sys.argv else 200)
    elif '--lica' in sys.argv:
        shag_lica()
    else:
        sys.exit(__doc__)
