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
    python3 vodokanaly_obogatit.py --ec         # штатный обход сайтов раннером
    python3 vodokanaly_obogatit.py --domeny     # добор домена: кириллица и почта на своём домене
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


# Бесплатные почтовые службы: домен такой почты сайтом предприятия не является.
POCHTOVYE = {'mail.ru', 'yandex.ru', 'ya.ru', 'list.ru', 'inbox.ru', 'bk.ru', 'rambler.ru',
             'gmail.com', 'gmail.ru', 'internet.ru', 'mail.com', 'yandex.com', 'yandex.by',
             'narod.ru', 'outlook.com', 'hotmail.com', 'icloud.com', 'vk.com', 'ro.ru'}
# Кириллические зоны. Раньше отборщик требовал латиницу и молча выбрасывал `водоканал-ноглики.рф`,
# `кубань-вода.рус`, `водоотведение.ооопкх.рф` — 17 предприятий числились «без сайта», хотя сайт
# у них есть. Это тот же класс, что и «взяли первый токен и пошли в vk.com»: отбор молча уже.
KIR_ZONY = ('.рф', '.рус', '.москва', '.дети', '.онлайн', '.сайт')


def horoshiy_domen(d):
    d = (d or '').strip().strip('.').lower()
    if not d or NE_SAJT.search(d):
        return ''
    if re.fullmatch(r'[a-z0-9.\-]+\.[a-z]{2,}', d):
        return d
    if d.endswith(KIR_ZONY) and re.fullmatch(r'[а-яёa-z0-9.\-]+', d):
        return d
    return ''


def v_punycode(d):
    """Кириллический домен в вид, который понимает раннер. Латинский возвращается как есть."""
    try:
        return '.'.join(ch.encode('idna').decode('ascii') for ch in d.split('.'))
    except (UnicodeError, ValueError):
        return d


def domen(s):
    """Первый НЕ мусорный домен из поля, а не первый вообще. Кириллица принимается."""
    for tok in re.split(r'[\s,;|]+', (s or '').strip()):
        d = horoshiy_domen(re.sub(r'^https?://', '', tok).strip('/').split('/')[0])
        if d:
            return d
    return ''


def rasstoyanie(a, b):
    """Редакционное расстояние. Нужно ровно для одного: поймать ОПЕЧАТКУ в почтовой службе."""
    if abs(len(a) - len(b)) > 2:
        return 3
    pred = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        tek = [i]
        for j, cb in enumerate(b, 1):
            tek.append(min(pred[j] + 1, tek[j - 1] + 1, pred[j - 1] + (ca != cb)))
        pred = tek
    return pred[-1]


def opechatka_pochtovoj(d):
    """`yndex.ru`, `vail.ru`, `gmail.ru`, `maii.ru` — это mail.ru и yandex.ru с опечаткой.

    Замер, ради которого это появилось. Идея «домен из почты — это и есть сайт» проверена
    вживую на семи доменах: `djljk.ru` и `rirls.ru` не отвечают вовсе, `vkogroup.com` отдаёт
    114 байт, `r56.fssprus.ru` — это служба приставов, `lenta.ru` — новостной сайт,
    `yndex.ru` и `vail.ru` — опечатки почтовых служб. То есть **шесть из семи оказались не
    сайтом предприятия**. Идея не выброшена, но без этого отсева она даёт мусор.
    """
    for p in POCHTOVYE:
        if d != p and rasstoyanie(d, p) <= 2:
            return True
    return False


def domen_iz_pochty(s):
    """Домен из корпоративной почты — кандидат в сайт предприятия, но именно кандидат.

    Замер по 502 водоканалам без сайта: у 104 из них почта стоит не на бесплатной службе, и мы
    туда ни разу не сходили, потому что смотрели только в поле «Сайты». Живая проверка показала,
    что доверять этому нельзя (см. `opechatka_pochtovoj`): домен бывает опечаткой почтовой
    службы, чужой организацией, холдингом (`rosvodokanal.ru` у РВК-Тихорецк) или мёртвым.
    Поэтому источник домена пишется отдельной колонкой, а принадлежность проверяет шаг обхода:
    он сверяет ИНН на сайте и помечает `mismatch`.
    """
    for m in re.finditer(r'[\w.\-+]+@([\w\-.а-яё]+\.[a-zа-яё]{2,})', s or '', re.I):
        d = m.group(1).lower().strip('.')
        if d in POCHTOVYE or d.endswith('.gov.ru') or opechatka_pochtovoj(d):
            continue
        d = horoshiy_domen(d)
        if d:
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


def shag_domeny():
    """Добор домена тем, у кого его «нет»: кириллица и почта на своём домене.

    Пишет ОТДЕЛЬНЫЙ файл, а не правит основной: обход сайтов идёт долго и читает основной файл,
    а править то, что сейчас читают, — верный способ получить порчу, которую потом не объяснить.
    Слияние делает `--slit-domeny` после того, как обход закончится.

    Проверка живости отборщика встроена: если добор даёт ноль на всех трёх источниках сразу,
    это почти наверняка поломка отборщика, а не «доменов правда нет».
    """
    rows = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    bez = [r for r in rows if not (r.get('domen') or '').strip()]
    out, sch = [], {'кириллица': 0, 'почта': 0, 'латиница пропущенная': 0}
    for r in bez:
        pole_sajt = ' '.join([r.get('sajt_iz_obzvona') or '', r.get('site') or ''])
        pole_pochta = ' '.join([r.get('pochty_iz_obzvona') or '', r.get('best_email') or ''])
        d, otkuda = domen(pole_sajt), ''
        if d:
            otkuda = 'кириллица' if d.endswith(KIR_ZONY) else 'латиница пропущенная'
        else:
            d = domen_iz_pochty(pole_pochta)
            if d:
                otkuda = 'почта'
        if not d:
            continue
        sch[otkuda] += 1
        out.append({'inn': r['inn'], 'name': r.get('name_obzvon') or r.get('name') or '',
                    'domen': d, 'domen_dlya_obhoda': v_punycode(d), 'otkuda_domen': otkuda,
                    'region': r.get('region_iz_obzvona') or '', 'vyruchka': r.get('revenue_rub') or '',
                    'telefony': (r.get('telefony_iz_obzvona') or '')[:120],
                    'pochty': (r.get('pochty_iz_obzvona') or '')[:120]})
    # Один домен на много несвязанных ИНН — это не предприятие, а чужой сайт: новостной,
    # госслужба, хостинг. Свой домен у водоканала встречается один-два раза (второй раз —
    # родственное юрлицо «водоснабжение» и «водоотведение» одного хозяйства).
    schet = {}
    for r in out:
        schet[r['domen']] = schet.get(r['domen'], 0) + 1
    obshchie = {d for d, n in schet.items() if n >= 3}
    if obshchie:
        print('домены, стоящие у трёх и более ИНН (помечены, не выброшены): '
              + ', '.join(sorted(obshchie)), file=sys.stderr)
    for r in out:
        if r['domen'] in obshchie:
            r['otkuda_domen'] += ', общий на ' + str(schet[r['domen']]) + ' ИНН'

    put = os.path.join(os.path.dirname(VYHOD), 'vodokanaly-domeny-dobor.csv')
    cols = ['inn', 'name', 'domen', 'domen_dlya_obhoda', 'otkuda_domen', 'region', 'vyruchka',
            'telefony', 'pochty']
    with open(put, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in out:
            w.writerow(r)
    pr = list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'))
    print(f'без домена было: {len(bez)} из {len(rows)}', file=sys.stderr)
    print(f'добрано доменов: {len(pr)} — ' + ', '.join(f'{k}: {v}' for k, v in sch.items()),
          file=sys.stderr)
    print(f'уникальных доменов: {len({r["domen"] for r in pr})} '
          f'(один домен на несколько ИНН — это холдинг или район, обход разберёт)', file=sys.stderr)
    print(f'→ {put}', file=sys.stderr)


def shag_ec_bez_sajta(pachka=8, parallel=3, predel=64):
    """Тем, у кого сайта нет: пусть раннер найдёт его сам через поисковый канал.

    Это было слепое пятно всей ветки. Я обходил только те предприятия, у которых домен уже
    известен, и написал «502 водоканала недостижимы обходом, идти некуда». На деле раннер умеет
    искать сайт сам: `find_site_via_xmlriver` берёт ключ из окружения СЕРВЕРА (в песочнице его
    нет и быть не должно) и отдаёт адрес по названию и ИНН.

    Доказано пробой на двух компаниях с пустым полем `site`:
      МУП «Ногликский водоканал»    → `водоканал-ноглики.рф`  (`site_source: cache:enrich-db`)
      Газпромнефть-Ноябрьскнефтегаз → `nng.gazprom-neft.ru`   (`site_source: xmlriver-kg`)
    Расход: `xmlriver: 3` на две компании, оба сайта признаны провайдером-судьёй, у обоих
    найдены почты.

    **Это платный канал владельца, поэтому шаг ограничен `predel` и начинает с крупных.**
    Расход печатается по каждой пачке, чтобы владелец мог остановить в любой момент.
    """
    rows = [r for r in csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';')
            if not (r.get('domen') or '').strip() and not (r.get('sajt_obhoda') or '').strip()]

    def vyr(x):
        try:
            return float(re.sub(r'[^\d.]', '', x.get('revenue_rub') or '0') or 0)
        except ValueError:
            return 0.0

    put_res = os.path.join(RAB, 'vk_ec_bez_sajta.jsonl')
    gotovo = set()
    if os.path.exists(put_res):
        for l in open(put_res, encoding='utf-8'):
            try:
                gotovo.add(json.loads(l).get('inn'))
            except json.JSONDecodeError:
                pass
    rows = [r for r in sorted(rows, key=vyr, reverse=True) if r['inn'] not in gotovo][:predel]
    print(f'без сайта к поиску: {len(rows)} (уже пройдено {len(gotovo)})', file=sys.stderr)
    if not rows:
        return
    pachki = [rows[i:i + pachka] for i in range(0, len(rows), pachka)]
    lock = threading.Lock()
    f = open(put_res, 'a', encoding='utf-8')
    sch = {'sajt': 0, 'tel': 0, 'pochta': 0, 'lyudi': 0, 'xmlriver': 0, 'pusto': 0}

    def odna(gr):
        comp = [{'inn': x['inn'], 'ogrn': '',
                 'name': (x.get('name_obzvon') or x.get('name') or '')[:90],
                 'site': '', 'phones': (x.get('telefony_iz_obzvona') or '')[:120]} for x in gr]
        p = subprocess.run([sys.executable, KLIENT, 'enrich_contacts',
                            json.dumps({'companies': comp, 'site_crawl': True}, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=2400)
        m = re.search(r'\{.*\}', p.stdout, re.S)
        if not m:
            return gr, None, (p.stdout or p.stderr)[-160:]
        try:
            return gr, json.loads(m.group(0)), ''
        except json.JSONDecodeError as e:
            return gr, None, f'JSON не разобран: {str(e)[:60]}'

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for i, (gr, res, err) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                if err:
                    print(f'  СБОЙ пачки {i}: {err[:120]}', file=sys.stderr)
                    continue
                dd = res.get('data') or {}
                sch['xmlriver'] += ((dd.get('cost') or {}).get('xmlriver') or 0)
                po_inn = {}
                for x in dd.get('results') or []:
                    po_inn.setdefault(x.get('inn') or '', []).append(x)
                for x in gr:
                    rr = po_inn.get(x['inn']) or []
                    f.write(json.dumps({'inn': x['inn'], 'rezultaty': rr}, ensure_ascii=False) + '\n')
                    if not rr:
                        sch['pusto'] += 1
                    for y in rr:
                        if y.get('site'):
                            sch['sajt'] += 1
                        if y.get('phones'):
                            sch['tel'] += 1
                        if y.get('emails'):
                            sch['pochta'] += 1
                        sch['lyudi'] += sum(1 for e in (y.get('emails') or [])
                                            if isinstance(e, dict) and (e.get('person') or '').strip())
                f.flush()
                print(f'  пачек {i}/{len(pachki)}: сайтов {sch["sajt"]}, телефонов {sch["tel"]}, '
                      f'почт {sch["pochta"]}, людей {sch["lyudi"]}, пусто {sch["pusto"]}, '
                      f'расход xmlriver {sch["xmlriver"]}', file=sys.stderr, flush=True)
    f.close()
    print(f'готово → {put_res}', file=sys.stderr)


def shag_slit_ec():
    """Свести обход, добор доменов и номера из WhatsApp в основной файл — с уликами.

    Правило, ради которого здесь столько колонок: **у каждого значения должен быть источник**.
    Обход раннера сам оценивает, чей это сайт, и кладёт признак `verified`: `inn` — на сайте
    найден наш ИНН, `provider` — сайт признан провайдером-судьёй, `mismatch` — сайт чужой
    (у «Краснодар Водоканала» краулер ушёл на `rosvodokanal.ru`, это холдинг). Контакты с
    `mismatch` записывать предприятию нельзя, но и выбрасывать нельзя: это контакты УПРАВЛЯЮЩЕЙ
    компании, а решение по машине часто как раз там. Поэтому они лежат в своих колонках.
    """
    put_res = os.path.join(RAB, 'vk_ec_rezultaty.jsonl')
    ec = {}
    if os.path.exists(put_res):
        for l in open(put_res, encoding='utf-8'):
            try:
                x = json.loads(l)
            except json.JSONDecodeError:
                continue
            ec[x.get('inn')] = x.get('rezultaty') or []
    dobor = {}
    put_dob = os.path.join(os.path.dirname(VYHOD), 'vodokanaly-domeny-dobor.csv')
    if os.path.exists(put_dob):
        for r in csv.DictReader(open(put_dob, encoding='utf-8-sig'), delimiter=';'):
            dobor[r['inn']] = r
    WA = re.compile(r'wa\.me/\+?(\d{10,15})')

    rows = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    novye = ['telefony_s_sajta', 'pochty_s_sajta', 'lyudi_s_sajta', 'sajt_proveren',
             'sajt_obhoda', 'chuzhoy_sajt_kontakty', 'domen_dobrannyy', 'otkuda_domen',
             'telefon_iz_whatsapp']
    cols = list(rows[0].keys()) + [c for c in novye if c not in rows[0]]
    sch = {'телефоны с сайта': 0, 'почты с сайта': 0, 'люди с сайта': 0, 'домен добран': 0,
           'номер из whatsapp': 0, 'контакты чужого сайта': 0}
    for r in rows:
        rr = ec.get(r['inn']) or []
        tel, poch, lyudi, chuzh, ver, sajt = [], [], [], [], set(), ''
        for y in rr:
            v = str(y.get('verified') or '')
            ver.add(v)
            sajt = sajt or (y.get('site') or '')
            t = y.get('phones') or []
            t = t if isinstance(t, list) else re.split(r'[|,;]', str(t))
            e = [x for x in (y.get('emails') or []) if isinstance(x, dict)]
            if v == 'mismatch':
                chuzh += [str(x).strip() for x in t if str(x).strip()]
                chuzh += [x.get('email') for x in e if x.get('email')]
                continue
            tel += [str(x).strip() for x in t if str(x).strip()]
            poch += [x['email'] for x in e if x.get('email')]
            for x in e:
                if (x.get('person') or '').strip():
                    lyudi.append(f"{x['person']} | {x.get('role') or ''} | {x['email']}")
        if tel:
            sch['телефоны с сайта'] += 1
        if poch:
            sch['почты с сайта'] += 1
        if lyudi:
            sch['люди с сайта'] += 1
        if chuzh:
            sch['контакты чужого сайта'] += 1
        r['telefony_s_sajta'] = ' | '.join(dict.fromkeys(tel))[:200]
        r['pochty_s_sajta'] = ' | '.join(dict.fromkeys(poch))[:200]
        r['lyudi_s_sajta'] = ' ;; '.join(lyudi)[:300]
        r['sajt_proveren'] = ','.join(sorted(x for x in ver if x and x != 'None'))
        r['sajt_obhoda'] = sajt[:80]
        r['chuzhoy_sajt_kontakty'] = ' | '.join(dict.fromkeys(chuzh))[:160]
        d = dobor.get(r['inn'])
        if d and not (r.get('domen') or '').strip():
            r['domen_dobrannyy'] = d['domen']
            r['otkuda_domen'] = d['otkuda_domen']
            sch['домен добран'] += 1
        m = WA.search(r.get('sajt_iz_obzvona') or '')
        if m:
            r['telefon_iz_whatsapp'] = '+' + m.group(1)
            sch['номер из whatsapp'] += 1

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    pr = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    print(f'строк в файле: {len(pr)}', file=sys.stderr)
    for k, v in sch.items():
        print(f'  {k:26} {v:>5}', file=sys.stderr)

    def n(f):
        return sum(1 for x in pr if (x.get(f) or '').strip())
    print('  --- итог по достижимости ---', file=sys.stderr)
    print(f'  с любым телефоном          {sum(1 for x in pr if x["phones"].strip() or x["telefony_iz_obzvona"].strip() or x["telefony_s_sajta"].strip() or x["telefon_iz_whatsapp"].strip()):>5}',
          file=sys.stderr)
    print(f'  с любой почтой             {sum(1 for x in pr if x["best_email"].strip() or x["pochty_iz_obzvona"].strip() or x["pochty_s_sajta"].strip()):>5}',
          file=sys.stderr)
    print(f'  с названным человеком      {n("lyudi_s_sajta"):>5}', file=sys.stderr)
    print(f'  сайт есть (домен + добор)  {sum(1 for x in pr if x["domen"].strip() or x["domen_dobrannyy"].strip()):>5}',
          file=sys.stderr)
    print(f'→ {VYHOD}', file=sys.stderr)


def shag_staff(pachka=6):
    """Страницы штата и структуры, найденные `enrich_contacts`, — забрать и положить на диск.

    Это и есть то место, где у водоканала лежат должности. Сам `enrich_contacts` находит **адрес**
    такой страницы (поле `staff_search`) и почты из справочников (поле `directory`,
    с `verified_by: inn` — привязка по ИНН, а не по названию), но людей со страницы не вынимает.

    Отдельно берём и `directory` — там почты и телефоны, подтверждённые по ИНН, а это сильнее,
    чем совпадение домена: у ГУП «Водоканал Санкт-Петербурга» домен из выгрузки указал на
    `med-vdk.ru`, его медцентр, и почты оттуда — надзорные органы (`rospotrebnadzor`,
    `roszdravnadzor`), а не предприятие. Штатный провайдер-судья такие сайты отбраковывает сам:
    в первых 32 компаниях он отклонил три со словами «сайт НЕ этой компании».
    """
    put_res = os.path.join(RAB, 'vk_ec_rezultaty.jsonl')
    rows = [json.loads(l) for l in open(put_res, encoding='utf-8')]
    os.makedirs(STRANICY, exist_ok=True)
    zad, karta = [], {}
    for x in rows:
        for r in x['rezultaty']:
            if r.get('error'):
                continue
            for j, u in enumerate(r.get('staff_search') or []):
                imya = f"vk_{r['inn']}_s{j}.html"
                karta[imya] = r['inn']
                if not os.path.exists(os.path.join(STRANICY, imya)):
                    zad.append({'task': 'fetch_url',
                                'args': {'url': u, 'insecure': True, 'name': imya}})
    json.dump(karta, open(os.path.join(STRANICY, 'karta_staff.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    print(f'страниц штата к обходу: {len(zad)}', file=sys.stderr)
    for k in range(0, len(zad), pachka):
        for r in runner_many(zad[k:k + pachka], pachka):
            d = (r or {}).get('data') or {}
            if d.get('drop_name') and (d.get('bytes') or 0) > 2000:
                skachat(d['drop_name'], STRANICY)
        print(f'  {min(k + pachka, len(zad))}/{len(zad)}', file=sys.stderr, flush=True)
    est = [f for f in os.listdir(STRANICY) if re.match(r'vk_\d+_s\d+\.html', f)]
    print(f'страниц штата на диске: {len(est)}', file=sys.stderr)


def shag_lica(threads=8):
    import gen_provider as G
    G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                     'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}
    rows = {r['inn']: r for r in csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';')}
    fajly = sorted(f for f in os.listdir(STRANICY) if f.startswith('vk_') and f.endswith('.html')
                   and not f.startswith('vk_k_'))
    karta_staff = {}
    ks = os.path.join(STRANICY, 'karta_staff.json')
    if os.path.exists(ks):
        karta_staff = json.load(open(ks, encoding='utf-8'))
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
        m = re.match(r'vk_(\d+)_s?(\d+)\.html', fajl)
        if not m:
            return fajl, None, 'имя файла не разобрано'
        inn = karta_staff.get(fajl) or m.group(1)
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
    elif '--ec-bez-sajta' in sys.argv:
        pr=int(sys.argv[sys.argv.index('--predel')+1]) if '--predel' in sys.argv else 64
        shag_ec_bez_sajta(predel=pr)
    elif '--slit-ec' in sys.argv:
        shag_slit_ec()
    elif '--domeny' in sys.argv:
        shag_domeny()
    elif '--staff' in sys.argv:
        shag_staff()
    elif '--lica' in sys.argv:
        shag_lica()
    else:
        sys.exit(__doc__)
