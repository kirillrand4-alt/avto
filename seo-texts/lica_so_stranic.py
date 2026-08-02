# -*- coding: utf-8 -*-
"""Подтверждённые сайты → страницы контактов и штата → ЛЮДИ, разбором провайдера.

Это третье звено цепочки, на котором она и рвётся: предприятий с доказанной воздушной
центробежной машиной 2 488, а людей с номером 290. Первые два звена уже работают: состояние
доказано, сайт ищется раннером. Здесь сайт превращается в имя, должность и номер.

Почему провайдером, а не шаблоном. Страница контактов — свободный текст: должность бывает
заголовком раздела, бывает в скобках, бывает в таблице без разметки; телефон приёмной стоит
рядом с личным. Правило прежнее: ровный формат — шаблону, свободный текст — модели.

Почему только ПОДТВЕРЖДЁННЫЕ сайты. Замер по 64 предприятиям: сайт нашёлся у 60, но судья
отверг 29 как «сайт НЕ этой компании», и у 28 из них на сайте были телефоны. Разобрать чужой
сайт значит приписать предприятию чужих людей — порча, которую потом не видно.

Шаги:
    python3 lica_so_stranic.py --puti       # главная → провайдер выбирает пути к людям
    python3 lica_so_stranic.py --stranicy   # скачать страницы контактов по подтверждённым сайтам
    python3 lica_so_stranic.py --lica       # страницы → люди, провайдером
"""
import csv
import glob
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
STRANICY = os.path.join(RAB, 'lica_stranicy')
VYHOD = os.path.join(BAZA, 'engineers-lens', 'centro', 'lica-s-sajtov.csv')
# Страницы, с которых людей не вышло, и имена, отброшенные заслоном, — сохраняем, а не считаем.
OTSEV = os.path.join(BAZA, 'engineers-lens', 'centro', 'lica-s-sajtov-otsev.csv')

# Массовая работа со свободным текстом: выбор путей и разбор страниц на людей. По замеру
# 02.08 deepseek-v4-pro даёт тот же результат, что fable-5, за $0,0033 против $0,1176 — в 35 раз
# дешевле. Медленнее вшестеро, но это фоновая работа. Переопределяется через MODEL_LICA.
MODEL = os.environ.get('MODEL_LICA', 'deepseek-v4-pro')

PUTI = ['/kontakty', '/contacts', '/rukovodstvo', '/management', '/struktura', '/structure',
        '/o-kompanii/rukovodstvo', '/about/management', '/spravochnik', '/sotrudniki']


def na_drop(*puti):
    """Итог и отсев — на обменник сразу после записи. Контейнер сессии эфемерный."""
    for p in puti:
        if p and os.path.exists(p):
            r = subprocess.run(['bash', DROP, 'up', p], capture_output=True, text=True, timeout=600)
            print(f'  на дроп: {os.path.basename(p)} — {(r.stdout or r.stderr).strip()[:90]}',
                  file=sys.stderr)


def podtverzhdennye():
    """ИНН → (сайт, название, адреса страниц штата), только там, где сайт признан своим."""
    out = {}
    for put in glob.glob(os.path.join(RAB, 'sajty_*.jsonl')) + [
            os.path.join(RAB, 'vk_ec_rezultaty.jsonl'),
            os.path.join(RAB, 'vk_ec_bez_sajta.jsonl')]:
        if not os.path.exists(put):
            continue
        for l in open(put, encoding='utf-8'):
            try:
                x = json.loads(l)
            except json.JSONDecodeError:
                continue
            for y in x.get('rezultaty') or []:
                if str(y.get('verified')) not in ('inn', 'provider'):
                    continue
                sajt = (y.get('site') or '').strip()
                if not sajt:
                    continue
                d = out.setdefault(x['inn'], {'sajt': sajt, 'name': x.get('predpriyatie')
                                              or y.get('name') or '', 'staff': []})
                for u in (y.get('staff_search') or []):
                    if u not in d['staff']:
                        d['staff'].append(u)
    return out


def runner_many(zad, threads=6):
    p = subprocess.run([sys.executable, KLIENT, '--many', json.dumps(zad, ensure_ascii=False),
                        '--threads', str(threads)], capture_output=True, text=True, timeout=1800)
    m = re.search(r'\[.*\]', p.stdout, re.S)
    return json.loads(m.group(0)) if m else []


# Замер обрезов на 54 живых страницах (правило владельца: данные не режем, но сначала мерим):
#   html_cap 400 000 — упёрлась 1 страница (ровно 400 000, то есть текст обрезан);
#   ссылок больше 300 — 0 страниц, максимум 135, предел не связывал вовсе;
#   текста больше 40 000 — 1 страница, максимум 165 228, до провайдера доходила четверть.
# Пределы подняты до 2 000 000 / 1 000 / 150 000. Связывали редко, но молча: страница читалась
# как полная, а половина справочника в запрос не попадала.
def zadanie_stranicy(url, imya):
    """Скачать страницу через раннер.

    Раньше здесь был `fetch_url`. После полной перезагрузки сервера он **выпал из allowlist**
    раннера: задание возвращается с «task не в allowlist: fetch_url», и все 260 главных
    «не скачались» — ноль, который выглядел как «сайты недоступны», а был отказом раннера.

    Замена — `browser_probe` с `return_html`: он в allowlist, отдаёт полный HTML (проверено:
    70 478 знаков и 137 ссылок с главной ПАО «Химпром»), а вдобавок умеет Дельфин и решатель
    капч, чего у `fetch_url` не было вовсе. Файл кладём на диск сами: ответ приходит в теле
    задания, а не через дроп.
    """
    KARTA_URL[url.rstrip('/')] = imya
    return {'task': 'browser_probe',
            'args': {'url': url, 'return_html': True, 'html_cap': 2000000, 'wait_ms': 6000}}


# Ответ раннера НЕ возвращает ни `args`, ни произвольный `tag` — проверено живым вызовом.
# Зато в `data` всегда лежит `url`. По нему и раскладываем ответы по именам файлов: это
# надёжнее порядка в списке, который может не совпасть при параллельном исполнении.
KARTA_URL = {}


def sohranit_otvety(otvety, kuda):
    """Ответы браузерной пробы → файлы на диске. Возвращает, сколько страниц легло."""
    n = 0
    for r in otvety:
        d = (r or {}).get('data') or {}
        h = d.get('html') or ''
        u = (d.get('url') or '').rstrip('/')
        imya = KARTA_URL.get(u) or KARTA_URL.get(u + '/')
        if not imya or len(h) <= 1500:
            continue
        open(os.path.join(kuda, imya), 'w', encoding='utf-8').write(h)
        n += 1
    return n


SSYLKI_S_GLAVNOJ = re.compile(r'<a\s[^>]*href\s*=\s*["\']([^"\'#]+)["\'][^>]*>(.{0,120}?)</a>',
                              re.I | re.S)


def shag_puti(pachka=8, predel=400, threads=6):
    """Пути к страницам людей — брать СО СТРАНИЦЫ, а не угадывать. Выбирает провайдер.

    Замер, из-за которого шаг появился: угадывание `/kontakty`, `/rukovodstvo`, `/struktura`
    работало на муниципальных сайтах, а на заводских дало **64 страницы из 408 попыток** —
    остальное 404. Это не бедность источника, а слабость способа: у каждого завода своя
    структура (`/company/management`, `/about/staff`, `/predpriyatie/administraciya`, каталоги
    на поддоменах). Перебирать варианты бесполезно, их бесконечно много.

    Правильный путь: скачать ГЛАВНУЮ (один запрос), вынуть из неё все ссылки с подписями и
    отдать этот список провайдеру — пусть он, зная задачу, выберет те, за которыми стоят люди
    с должностями. Провайдер видит подписи по-русски («Руководство», «Наши специалисты»,
    «Телефонный справочник»), а шаблон видит только латиницу в пути.
    """
    import gen_provider as G
    G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                     'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}
    os.makedirs(STRANICY, exist_ok=True)
    est = podtverzhdennye()
    put_karta = os.path.join(STRANICY, 'puti.json')
    gotovo = json.load(open(put_karta, encoding='utf-8')) if os.path.exists(put_karta) else {}
    nado = [(i, d) for i, d in est.items() if i not in gotovo][:predel]
    print(f'сайтов к разбору главной: {len(nado)} (пройдено {len(gotovo)})', file=sys.stderr)
    if not nado:
        return

    # 1) главная страница каждого сайта — одним запросом на сайт
    zad = []
    for inn, d in nado:
        dom = re.sub(r'^https?://', '', d['sajt']).strip('/').split('/')[0]
        imya = f'gl_{inn}.html'
        if not os.path.exists(os.path.join(STRANICY, imya)):
            zad.append(zadanie_stranicy(f'https://{dom}/', imya))
    print(f'главных к скачиванию: {len(zad)}', file=sys.stderr)
    leglo = 0
    for k in range(0, len(zad), pachka):
        leglo += sohranit_otvety(runner_many(zad[k:k + pachka], pachka), STRANICY)
        if k % 40 == 0:
            print(f'  {min(k + pachka, len(zad))}/{len(zad)}, на диске {leglo}',
                  file=sys.stderr, flush=True)

    PROMPT_PUT = """Список ссылок с главной страницы сайта российского промышленного предприятия.

ЗАЧЕМ. Нужны страницы, где названы РАБОТНИКИ с должностями: руководство, структура, аппарат
управления, телефонный справочник, отделы и службы, контакты подразделений, приёмная. Особенно
ценны страницы технических служб: главный инженер, главный механик, главный энергетик,
компрессорная, энергослужба, служба эксплуатации.

ЧТО ВЕРНУТЬ: до шести адресов, по убыванию вероятности найти там ФИО с должностью.

ПРАВИЛА:
1. Только адреса ИЗ ПОДАННОГО СПИСКА. Ничего не достраивай и не угадывай.
2. Новости, продукция, вакансии, закупки, документы — не нужны, если по подписи не видно, что
   там названы люди.
3. Если подходящего нет — пустой список и заполненное `pochemu`.

ОТВЕТ — строго JSON: {"adresa":["", ...], "pochemu":""}"""

    lock = threading.Lock()
    client = G.make_client()
    sch = {'сайтов': 0, 'с путями': 0, 'путей': 0, 'главная не скачалась': 0, 'сбоев': 0}

    def odna(par):
        inn, d = par
        put = os.path.join(STRANICY, f'gl_{inn}.html')
        if not os.path.exists(put):
            return inn, None, 'главная не скачалась'
        html = open(put, encoding='utf-8', errors='replace').read()
        dom = re.sub(r'^https?://', '', d['sajt']).strip('/').split('/')[0]
        vidno, spisok = set(), []
        for u, podpis in SSYLKI_S_GLAVNOJ.findall(html):
            podpis = re.sub(r'<[^>]+>', ' ', podpis)
            podpis = re.sub(r'\s+', ' ', podpis).strip()[:60]
            if u.startswith(('mailto:', 'tel:', 'javascript')):
                continue
            polnyy = u if u.startswith('http') else f'https://{dom}/' + u.lstrip('/')
            if dom not in polnyy or polnyy in vidno:
                continue
            vidno.add(polnyy)
            spisok.append(f'{polnyy} — {podpis}')
        if not spisok:
            return inn, None, 'на главной нет ссылок'
        try:
            o = G.call_model(MODEL, [{'role': 'user',
                                      'content': PROMPT_PUT + '\n\nССЫЛКИ:\n'
                                      + '\n'.join(spisok[:1000])}], attempts=3)
            txt = ''.join(b.text for b in o.content if b.type == 'text')
            m = re.search(r'\{.*\}', txt, re.S)
            res = json.loads(m.group(0)) if m else None
        except Exception as e:  # noqa: BLE001
            return inn, None, f'{type(e).__name__}: {str(e)[:60]}'
        if not res:
            return inn, None, 'ответ не разобран'
        # заслон: адрес обязан быть из поданного списка, иначе это выдумка
        svoi = [a for a in (res.get('adresa') or []) if any(a == s.split(' — ')[0] for s in spisok)]
        return inn, svoi, ''

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for inn, adresa, err in pool.map(odna, nado):
            with lock:
                sch['сайтов'] += 1
                if err == 'главная не скачалась':
                    sch['главная не скачалась'] += 1
                elif err:
                    sch['сбоев'] += 1
                elif adresa:
                    gotovo[inn] = adresa
                    sch['с путями'] += 1
                    sch['путей'] += len(adresa)
                else:
                    gotovo[inn] = []
                if sch['сайтов'] % 25 == 0:
                    print('  ' + ', '.join(f'{k} {v}' for k, v in sch.items()), file=sys.stderr,
                          flush=True)
    json.dump(gotovo, open(put_karta, 'w', encoding='utf-8'), ensure_ascii=False)
    print('ИТОГ: ' + ', '.join(f'{k} {v}' for k, v in sch.items()), file=sys.stderr)
    print(f'→ {put_karta}', file=sys.stderr)


# Разметка страничной разбивки. Ловим и цифру-ссылку, и словесную, и параметр в адресе.
STRANICA_V_ADRESE = re.compile(r'(?:[?&](?:page|PAGEN_\d+|p|pg|start|offset)=\d+)|/page/\d+|'
                               r'/p/\d+/?$', re.I)
STRANICA_PO_PODPISI = re.compile(r'^\s*(?:\d{1,3}|дал\w+|след\w+|показать\s+ещ|ещ[её]|next|»|→)\s*$',
                                 re.I)


def prodolzheniya(html, dom, otkuda):
    """Ссылки-продолжения списка: страничная разбивка и «показать ещё».

    Замечание владельца: справочник сотрудников часто разбит на страницы, и первая страница —
    это не весь список, а его начало. Если брать только её, потеря молчаливая: страница
    скачалась, люди с неё вынулись, а половины справочника нет, и по числам это не видно.

    Берём ссылки того же домена, у которых либо в адресе признак страницы (`?page=2`,
    `PAGEN_1=3`, `/page/2`), либо подпись — число или «далее», «ещё», «следующая». Отсекаем
    ссылку на саму себя и на первую страницу, чтобы не ходить по кругу.
    """
    out, vidno = [], set()
    for u, podpis in SSYLKI_S_GLAVNOJ.findall(html):
        if u.startswith(('mailto:', 'tel:', 'javascript')):
            continue
        podpis = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', podpis)).strip()
        polnyy = u if u.startswith('http') else (f'https://{dom}/' + u.lstrip('/')
                                                 if u.startswith('/') else
                                                 otkuda.rsplit('/', 1)[0] + '/' + u)
        if dom not in polnyy or polnyy == otkuda or polnyy in vidno:
            continue
        if STRANICA_V_ADRESE.search(polnyy) or STRANICA_PO_PODPISI.match(podpis):
            # страница 1 это и есть то, с чего пришли
            if re.search(r'(?:page|PAGEN_\d+|p|pg)=1\b|/page/1/?$', polnyy, re.I):
                continue
            vidno.add(polnyy)
            out.append(polnyy)
    return out


def shag_stranicy(pachka=8, predel=600):
    os.makedirs(STRANICY, exist_ok=True)
    est = podtverzhdennye()
    print(f'предприятий с подтверждённым сайтом: {len(est)}', file=sys.stderr)
    put_karta = os.path.join(STRANICY, 'puti.json')
    najdennye = json.load(open(put_karta, encoding='utf-8')) if os.path.exists(put_karta) else {}
    if najdennye:
        print(f'путей, выбранных провайдером с главных: '
              f'{sum(len(v) for v in najdennye.values())} по {len(najdennye)} сайтам',
              file=sys.stderr)
    est_sajty = est
    zad, karta, adres_fajla = [], {}, {}
    for inn, d in est.items():
        dom = re.sub(r'^https?://', '', d['sajt']).strip('/').split('/')[0]
        # Порядок: сначала то, что нашёл провайдер на живой главной, потом staff_search раннера,
        # и только в конец — угадывание. Замер: угадывание дало 64 страницы из 408 попыток.
        adresa = (najdennye.get(inn) or []) + d['staff'][:2] + [f'https://{dom}{p}' for p in PUTI]
        # берём не больше шести адресов на сайт; при найденных путях угадывание почти не нужно
        vidno, otobr = set(), []
        for u in adresa:
            if u and u not in vidno:
                vidno.add(u)
                otobr.append(u)
        for j, u in enumerate(otobr[:6]):
            imya = f'lc_{inn}_{j}.html'
            karta[imya] = inn
            adres_fajla[imya] = u
            if not os.path.exists(os.path.join(STRANICY, imya)):
                zad.append(zadanie_stranicy(u, imya))
    json.dump(karta, open(os.path.join(STRANICY, 'karta.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    zad = zad[:predel]
    print(f'страниц к обходу: {len(zad)}', file=sys.stderr)
    for k in range(0, len(zad), pachka):
        sohranit_otvety(runner_many(zad[k:k + pachka], pachka), STRANICY)
        if k % 40 == 0:
            n = len([f for f in os.listdir(STRANICY) if f.endswith('.html')])
            print(f'  {min(k + pachka, len(zad))}/{len(zad)}, на диске {n}', file=sys.stderr,
                  flush=True)
    print(f'страниц на диске: {len([f for f in os.listdir(STRANICY) if f.endswith(".html")])}',
          file=sys.stderr)


PROMPT = """Страница сайта российского промышленного предприятия.

ЗАЧЕМ. ООО «Руспром» продаёт воздушные центробежные компрессоры и воздуходувки. Решение по такой
машине принимает технический человек: главный инженер, главный механик, главный энергетик,
технический директор, главный технолог, начальник компрессорной станции, начальник цеха,
участка, энергослужбы, службы эксплуатации, их заместители.

ЧТО ВЕРНУТЬ по каждому НАЗВАННОМУ человеку: `imya`, `dolzhnost` (дословно со страницы),
`rol` (`техническая`, `руководство`, `снабжение`, `неясно`), `telefon`, `dobavochnyy`, `pochta`,
`podrazdelenie`, `gorod`, `filial`.

ПРО ФИЛИАЛ И ГОРОД — важно, у холдингов иначе люди с разных площадок сольются в одно
предприятие. `filial` — название площадки, завода, филиала или обособленного подразделения,
если человек привязан к нему на странице («Костромская ГРЭС», «Московский НПЗ», «филиал в
Ангарске»). `gorod` — город этой площадки, если он назван. Оба поля дословно со страницы; если
не названы — оставь пустыми, не достраивай по домену и не угадывай по названию компании.

ПРАВИЛА, нарушать нельзя:
1. **Ни одного имени, телефона и почты, которых нет на странице.** Не достраивай.
2. Если людей нет — пустой список и обязательно заполненное `pochemu`.
3. Должность бери со страницы. Заголовок раздела («Управление главного энергетика») это
   `podrazdelenie`, а не должность.
4. Телефон приёмной, диспетчера или общий номер конкретному человеку НЕ приписывай: положи его
   отдельной записью с `rol` = `неясно` и напиши это в `podrazdelenie`.
5. Добавочный номер сохраняй отдельным полем, не выбрасывай: с ним дозваниваются до человека.
6. **Если список людей на странице ОБОРВАН** — есть страничная разбивка, кнопка «показать ещё»,
   ссылки на отдельные страницы подразделений или служб, — перечисли эти адреса в
   `prodolzhenie`. Это важнее, чем кажется: первая страница справочника не равна справочнику,
   и без этого поля потеря будет молчаливой — люди со страницы вынуты, а половины списка нет.
   Адреса бери со страницы дословно, не достраивай.

ОТВЕТ — строго JSON: {"lyudi":[{...}], "chto_za_stranica":"", "prodolzhenie":[], "pochemu":""}"""


def bez_tegov(h):
    h = re.sub(r'(?is)<(script|style|noscript).*?</\1>', ' ', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    h = (h.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
         .replace('&#39;', "'").replace('&laquo;', '«').replace('&raquo;', '»'))
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n', h)).strip()


def shag_lica(threads=8):
    import gen_provider as G
    G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                     'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}
    karta = json.load(open(os.path.join(STRANICY, 'karta.json'), encoding='utf-8'))
    pa = os.path.join(STRANICY, 'adresa.json')
    adresa = json.load(open(pa, encoding='utf-8')) if os.path.exists(pa) else {}
    est = podtverzhdennye()
    fajly = sorted(f for f in os.listdir(STRANICY) if f.endswith('.html'))
    print(f'страниц к разбору: {len(fajly)}', file=sys.stderr)
    client = G.make_client()
    lock = threading.Lock()
    itog, otsev, sch = [], [], {'lyudej': 0, 'teh': 0, 's_nomerom': 0, 'sboev': 0, 'pusto': 0,
                     'stranic_s_prodolzheniem': 0}
    prodolzhenie = {}

    def odna(f):
        put = os.path.join(STRANICY, f)
        tekst = bez_tegov(open(put, encoding='utf-8', errors='replace').read())
        if len(tekst) < 200:
            return f, None, 'страница пустая'
        try:
            o = G.call_model(MODEL, [{'role': 'user',
                                      'content': PROMPT + '\n\nСТРАНИЦА:\n' + tekst[:150000]}],
                             attempts=3)
            txt = ''.join(b.text for b in o.content if b.type == 'text')
            m = re.search(r'\{.*\}', txt, re.S)
            return f, (json.loads(m.group(0)) if m else None), ''
        except Exception as e:  # noqa: BLE001
            return f, None, f'{type(e).__name__}: {str(e)[:70]}'

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, (f, res, err) in enumerate(pool.map(odna, fajly), 1):
            with lock:
                if err or not res:
                    sch['sboev' if err and 'пустая' not in err else 'pusto'] += 1
                    otsev.append({'inn': karta.get(f, ''), 'fajl': f,
                                  'prichina': err or 'ответ провайдера не разобран',
                                  'adres': adresa.get(f, '')})
                else:
                    inn = karta.get(f, '')
                    prod = [a for a in (res.get('prodolzhenie') or []) if isinstance(a, str)]
                    if prod:
                        sch['stranic_s_prodolzheniem'] += 1
                        prodolzhenie[f] = {'inn': inn, 'adresa': prod[:6]}
                    tekst = bez_tegov(open(os.path.join(STRANICY, f), encoding='utf-8',
                                           errors='replace').read())
                    for c in res.get('lyudi') or []:
                        imya = (c.get('imya') or '').strip()
                        # заслон против выдумки: фамилия обязана быть на странице
                        if not imya or imya.split()[0] not in tekst:
                            otsev.append({'inn': karta.get(f, ''), 'fajl': f,
                                          'prichina': 'фамилии нет на странице (заслон против выдумки)',
                                          'imya': imya, 'adres': adresa.get(f, '')})
                            continue
                        tel = (c.get('telefon') or '').strip()
                        sch['lyudej'] += 1
                        if c.get('rol') == 'техническая':
                            sch['teh'] += 1
                        if tel:
                            sch['s_nomerom'] += 1
                        itog.append({'inn': inn, 'predpriyatie': (est.get(inn) or {}).get('name', ''),
                                     'sajt': (est.get(inn) or {}).get('sajt', ''),
                                     'imya': imya, 'dolzhnost': (c.get('dolzhnost') or '').strip(),
                                     'rol': c.get('rol') or '', 'telefon': tel,
                                     'dobavochnyy': (c.get('dobavochnyy') or '').strip(),
                                     'pochta': (c.get('pochta') or '').strip(),
                                     'podrazdelenie': (c.get('podrazdelenie') or '').strip(),
                                     'gorod': (c.get('gorod') or '').strip()[:40],
                                     'filial': (c.get('filial') or '').strip()[:70],
                                     'chto_za_stranica': (res.get('chto_za_stranica') or '')[:80],
                                     'fajl': f})
                if i % 25 == 0:
                    print(f'  {i}/{len(fajly)}: людей {sch["lyudej"]}, технических {sch["teh"]}, '
                          f'с номером {sch["s_nomerom"]}, сбоев {sch["sboev"]}', file=sys.stderr,
                          flush=True)

    ocols = ['inn', 'fajl', 'prichina', 'imya', 'adres']
    with open(OTSEV, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=ocols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in otsev:
            w.writerow(r)
    cols = ['inn', 'predpriyatie', 'filial', 'gorod', 'sajt', 'imya', 'dolzhnost', 'rol',
            'telefon', 'dobavochnyy', 'pochta', 'podrazdelenie', 'chto_za_stranica', 'fajl']
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in itog:
            w.writerow(r)
    pr = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    lyudi = {(r['inn'], ' '.join(r['imya'].lower().split()[:2])) for r in pr}
    teh = {(r['inn'], ' '.join(r['imya'].lower().split()[:2])) for r in pr if r['rol'] == 'техническая'}
    s_nom = {(r['inn'], ' '.join(r['imya'].lower().split()[:2])) for r in pr
             if r['rol'] == 'техническая' and (r['telefon'].strip() or r['dobavochnyy'].strip())}
    print(f'\nИЗ ФАЙЛА: строк {len(pr)}, людей {len(lyudi)}, технических {len(teh)}, '
          f'технических С НОМЕРОМ {len(s_nom)}, предприятий {len({r["inn"] for r in pr})}',
          file=sys.stderr)
    print(f'сбоев провайдера: {sch["sboev"]}, пустых страниц: {sch["pusto"]}', file=sys.stderr)
    put_prod = os.path.join(STRANICY, 'prodolzhenie.json')
    json.dump(prodolzhenie, open(put_prod, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'страниц, где список ОБОРВАН и есть продолжение: {sch["stranic_s_prodolzheniem"]} '
          f'(адреса → {put_prod}, следующий круг качает их)', file=sys.stderr)
    print(f'отсев сохранён: {len(otsev)} строк → {OTSEV}', file=sys.stderr)
    na_drop(VYHOD, OTSEV)
    print(f'→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    if '--puti' in sys.argv:
        shag_puti()
    elif '--stranicy' in sys.argv:
        shag_stranicy()
    elif '--lica' in sys.argv:
        shag_lica()
    else:
        print(__doc__)
