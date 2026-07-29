# -*- coding: utf-8 -*-
r"""Контакты с ДВУХ тендерных площадок, которых у нас не было: ТЭК-Торг и Tender.pro.

Почему именно эти две (наблюдение владельца 2026-07-23, проверял руками):
  * **ТЭК-Торг** (tektorg.ru) — контур Роснефти и Интер РАО, то есть прямо целевые
    по компрессорам компании. Извещение показывает контактное лицо БЕЗ логина.
  * **Tender.pro** — КОММЕРЧЕСКИЕ тендеры среднего бизнеса, которых в ЕИС нет в
    принципе. Контакт там лежит В СВОБОДНОМ ТЕКСТЕ комментария, а не в поле.

Чем это отличается от `ops/sales_eis.py`: тот ходит в ЕИС (44/223-ФЗ). Компания,
не подпадающая под эти законы, в ЕИС не существует вовсе — а на Tender.pro она
закупается, и на ТЭК-Торге лежит её коммерческая секция.

ФОРМА ИСТОЧНИКОВ (снята живьём, а не по документации):

ТЭК-Торг — Next.js с server-side rendering. В `<script id="__NEXT_DATA__">`
лежит `props.pageProps.procedureItem` с ГОТОВЫМИ полями:
    inn, kpp, organizerName            <- ПРИВЯЗКА: ИНН организатора прямо в JSON
    contactPerson, contactPhone, contactEmail
    dates.datePublished                <- фильтр свежести
Разбирать HTML не нужно вообще. Проверено на примере владельца: АО «РНПК»,
ИНН 6227007322 -> «Деркач Надежда Юрьевна», 7-4912-933001,
DerkachNY@rnpk.rosneft.ru (/rosneft/procedures/19356771).
ВАЖНО: сайт закрыт защитой Variti для чужих IP (бесконечный 307 + страница
«сеанс прерван системой защиты от ботов»), а с СЕРВЕРА владельца открывается
обычным urllib. Поэтому op серверный, из песочницы его гонять нельзя.

Tender.pro — обычный HTML. Карточка `/api/tender/<id>/view_public` открыта без
логина, контакт сидит в блоке «Комментарий:» свободным текстом:
    «Информация от управляющего отбором ...: Труш Наталья Вячеславовна
     е-mail Nataliya.Trush@rusal.com, 8-39162-27617»
Поиск компании по ИНН есть: `/api/companies/list?search_type=company&inn=<ИНН>`.
Архив берётся `tender_state=100` («Все»), до 200 строк на страницу (`by=200`).

ПРИВЯЗКА ЗАКРЫТА ПО УМОЛЧАНИЮ (ловушка «Криогенмаш/криогенное машиностроение»):
  * ТЭК-Торг: пишем, только если `procedureItem.inn` РАВЕН нашему ИНН;
  * Tender.pro: нужен ИНН на карточке компании И совпадение id организатора
    тендера с найденной карточкой. Не совпало — пропускаем, а не пишем.

СВЕЖЕСТЬ (правило владельца): до 2 лет — свежий, 2–3 года — помечаем
«устаревший», старше 3 лет НЕ БЕРЁМ ВООБЩЕ. Дата закупки хранится у контакта.

ДЕДУП ПО ЧЕЛОВЕКУ: один снабженец ведёт десятки закупок. Схлопываем по
нормализованному телефону/почте внутри компании, оставляя САМУЮ СВЕЖУЮ закупку
как source_url.

DURABLE: enrich.db (people/phone_contacts/emails/signals/stage_log) +
`C:\seostat\drop\tender_platforms_stream.jsonl` с flush+fsync. Резюмируемо по
stage_log: пройденные ИНН пропускаются.

Запуск:
    python tender_platforms.py [бюджет_сек] [--apply] [--limit N]
                               [--source tektorg|tenderpro|both] [--base sales|core|both]
Без `--apply` — СУХОЙ ПРОГОН: ничего не пишет в базу, только считает и печатает.
"""
import io
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

# --------------------------------------------------------------- параметры
БЮДЖЕТ = 420.0
ПРИМЕНИТЬ = '--apply' in sys.argv
ЛИМИТ = 0
ИСТОЧНИК = 'both'
БАЗА_ИМЯ = 'both'
_св = [a for a in sys.argv[1:] if not a.startswith('--')]
if _св:
    try:
        БЮДЖЕТ = float(_св[0])
    except ValueError:
        pass
for i, a in enumerate(sys.argv):
    if a == '--limit' and i + 1 < len(sys.argv):
        ЛИМИТ = int(sys.argv[i + 1])
    if a == '--source' and i + 1 < len(sys.argv):
        ИСТОЧНИК = sys.argv[i + 1]
    if a == '--base' and i + 1 < len(sys.argv):
        БАЗА_ИМЯ = sys.argv[i + 1]
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\tender_platforms_stream.jsonl'
СЕЙЧАС = time.time()
ГОД = 365.25 * 86400
# Правило владельца: >3 лет не брать вовсе, 2–3 года — метка «устаревший».
ПРЕДЕЛ_ЛЕТ = 3.0
УСТАРЕЛО_ЛЕТ = 2.0
# «горячий» предмет закупки — повод для сигнала
ГОРЯЧЕЕ = re.compile(
    r'компрессор|воздуходувк|турбовоздуходувк|осушител\w+\s+воздух|'
    r'фильтр|азот\w*|кислород\w*|\bМКС\b|мембранн\w+\s+газоразделит|'
    r'винтов\w+\s+блок|ресивер|пневмосет|сжат\w+\s+воздух', re.I)

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE
import http.cookiejar as _cj   # noqa: E402
_OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=_ctx),
    urllib.request.HTTPCookieProcessor(_cj.CookieJar()))


def дай(url, timeout=35):
    r = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml'})
    with _OP.open(r, timeout=timeout) as f:
        raw = f.read()
        ct = f.headers.get('Content-Type', '')
    # НЕ raw.decode('utf-8'): дефект дня — windows-1251 страницы теряли
    # кириллицу ДО разбора и источник выглядел пустым
    return EC._раскодировать(raw, ct)


# ------------------------------------------------------------- утилиты
_ПОЧТА = re.compile(r'(?<![\w.\-])[A-Za-z0-9][\w.\-]{0,48}@[\w\-]+(?:\.[\w\-]+)+')
# телефон в свободном тексте: код 3–5 цифр (дефект дня: жёсткие 3 цифры теряли
# номера райцентров), допускаем «доб.»
_ТЕЛ = re.compile(
    r'(?<![\d.\-])((?:\+7|8|7)[\s\-()]*\d{3,5}[\s\-()]*\d{2,3}[\s\-()]*\d{2}'
    r'[\s\-()]*\d{2,3}(?:\s*(?:доб|вн|внутр)\.?\s*[№:]?\s*\d{1,5})?)')
_РЕКВ_РЯДОМ = re.compile(r'(ИНН|ОГРН|КПП|БИК|р/?с|к/?с|счет|счёт)\s*[:№]?\s*$', re.I)
_ФИО3 = re.compile(r'([А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{3,})')
_ФИО_ИН = re.compile(r'([А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]?\.?)')
# служебные словосочетания, которые выглядят как ФИО
_НЕ_ФИО = re.compile(
    r'служб\w+\s+довери|горяч\w+\s+лини|электронн\w+|торгов\w+\s+площад|'
    r'росси\w+\s+федерац|обществ\w+\s+ограничен|акционерн\w+\s+обществ|'
    r'коммерческ\w+\s+предложен|техническ\w+\s+заданн|запрос\w*\s+предложен', re.I)
# должность рядом с человеком (для роли). Технические — первыми.
_ДОЛЖН = re.compile(
    r'((?:главн\w+|зам\w*\.?\s*главн\w+)\s+(?:инженер\w*|энергетик\w*|механик\w*|'
    r'технолог\w*|конструктор\w*|металлург\w*)'
    r'|техническ\w+\s+директор\w*|директор\w*\s+по\s+(?:производств|техни|развити|закуп|снабж)\w*'
    r'|начальник\w*\s+(?:отдела|управления|службы|цеха|производства|бюро|сектора|группы)'
    r'(?:\s+[а-яё]+){0,3}'
    r'|руководител\w*\s+(?:отдела|направления|группы|проекта|службы|департамента)'
    r'(?:\s+[а-яё]+){0,3}'
    r'|начальник\w*\s+[а-яё]+(?:\s+[а-яё]+){0,2}'
    r'|ведущ\w+\s+(?:инженер\w*|специалист\w*|эксперт\w*)(?:\s+[а-яё]+){0,2}'
    r'|инженер\w*(?:\s+по\s+[а-яё]+)?'
    r'|специалист\w*(?:\s+по\s+[а-яё]+)?'
    r'|менеджер\w*(?:\s+по\s+[а-яё]+)?'
    r'|управляющ\w+\s+(?:отбором|тендером|закупкой)'
    r'|эксперт\w*(?:\s+по\s+[а-яё]+)?)', re.I)
# служебные адреса/номера самих площадок — не контакт компании
_ШУМ_ДОМЕН = ('tender.pro', 'tektorg.ru', 'proventus-pro.ru', 'help.tender.pro',
              'roseltorg.ru', 'sberbank-ast.ru')
_ШУМ_ТЕЛ = ('4952151438', '8002503268', '4957348118', '4997058118', '8002343456')


def тел10(s):
    d = re.sub(r'\D', '', s or '')
    return d[-10:] if len(d) >= 10 else ''


def чистый_тел(s):
    """«8-39162-27617» -> нормализованный вид с сохранением добавочного."""
    s = re.sub(r'\s+', ' ', (s or '')).strip(' .,;:')
    return s[:60]


def мусорная_почта(e):
    e = (e or '').lower()
    if not e or '@' not in e:
        return True
    dom = e.split('@')[-1]
    if any(dom == d or dom.endswith('.' + d) for d in _ШУМ_ДОМЕН):
        return True
    try:
        if EC._is_junk_email(e):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def мусорный_тел(t):
    d = тел10(t)
    return (not d) or d in _ШУМ_ТЕЛ


def лет_назад(дата_iso):
    """Годы от даты до сегодня. Пусто -> None (неизвестно)."""
    if not дата_iso:
        return None
    s = str(дата_iso)
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', s)
    if not m:
        m2 = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', s)
        if not m2:
            return None
        g = (m2.group(3), m2.group(2), m2.group(1))
    else:
        g = m.groups()
    try:
        t = time.mktime((int(g[0]), int(g[1]), int(g[2]), 12, 0, 0, 0, 1, -1))
    except Exception:  # noqa: BLE001
        return None
    return (СЕЙЧАС - t) / ГОД


def свежесть(лет):
    if лет is None:
        return 'неизвестна'
    if лет <= УСТАРЕЛО_ЛЕТ:
        return 'свежий'
    if лет <= ПРЕДЕЛ_ЛЕТ:
        return 'устаревший'
    return 'просрочен'


# --------------------------------------------------- разбор свободного текста
def люди_из_текста(текст):
    """[{person, post, phone, email}] из свободного текста комментария.

    Форма подсмотрена на живых карточках Tender.pro: контакт стоит одним
    предложением («обращаться к начальнику отдела оборудования Евгению Епишеву,
    тел. 8-923-654-00-34»), либо блоком «ФИО / e-mail X / телефон Y».
    Поэтому режем на предложения и собираем кластер вокруг КАЖДОГО контакта,
    а не «первое ФИО + первый телефон со всей страницы» (склейка приёмной с
    чужим добавочным — ошибка 4.7 из передачи).
    """
    t = re.sub(r'[ \t]+', ' ', текст or '')
    if not t.strip():
        return []
    куски = [x for x in re.split(r'(?:\n+|(?<=[.;!?])\s+)', t) if x.strip()]
    люди, i = [], 0
    while i < len(куски):
        окно = ' '.join(куски[max(0, i - 1):i + 2])
        кус = куски[i]
        почты = [e.lower() for e in _ПОЧТА.findall(кус) if not мусорная_почта(e)]
        телы = []
        for m in _ТЕЛ.finditer(кус):
            перед = кус[max(0, m.start() - 18):m.start()]
            if _РЕКВ_РЯДОМ.search(перед):
                continue                       # ОГРН/ИНН, притворяющийся телефоном
            if not мусорный_тел(m.group(1)):
                телы.append(чистый_тел(m.group(1)))
        if not (почты or телы):
            i += 1
            continue
        фио = ''
        for рег in (_ФИО3, _ФИО_ИН):
            for кандидат in рег.findall(окно):
                if not _НЕ_ФИО.search(кандидат):
                    фио = кандидат.strip()
                    break
            if фио:
                break
        д = _ДОЛЖН.search(окно)
        должность = re.sub(r'\s+', ' ', д.group(1)).strip(' .,;:')[:120] if д else ''
        люди.append({'person': фио, 'post': должность,
                     'phone': телы[0] if телы else '',
                     'phones': телы[:4], 'email': почты[0] if почты else '',
                     'emails': почты[:4]})
        i += 1
    return люди


# ------------------------------------------------------------ ТЭК-Торг
ТТ = 'https://www.tektorg.ru'
ТТ_СЕКЦИИ = ('223-fz', '44-fz', 'rosneft', 'rosnefttkp', 'inter_rao',
             'market', 'sale', 'tenders', 'vitrina')


def _next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html or '', re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:  # noqa: BLE001
        return None


def тт_поиск(запрос, максимум=12):
    """Ссылки на процедуры по текстовому поиску (по всем секциям сразу)."""
    try:
        h = дай(ТТ + '/procedures?name=' + urllib.parse.quote(запрос))
    except Exception:  # noqa: BLE001
        return []
    L = re.findall(r'href="(/[a-z0-9_\-]+/procedures/\d+)"', h)
    вид, из_ = set(), []
    for x in L:
        if x not in вид:
            вид.add(x)
            из_.append(x)
    return из_[:максимум]


def тт_карточка(путь):
    """procedureItem карточки ТЭК-Торга или None."""
    try:
        h = дай(ТТ + путь)
    except Exception:  # noqa: BLE001
        return None
    d = _next_data(h)
    if not d:
        return None
    pi = ((d.get('props') or {}).get('pageProps') or {}).get('procedureItem')
    return pi if isinstance(pi, dict) else None


def тт_по_компании(inn, имя, бюджет_карточек=10):
    """[находка] по одной компании. ПРИВЯЗКА: procedureItem.inn == inn."""
    находки, проверено, чужих = [], 0, 0
    запросы = сокращения_имени(имя)
    видел = set()
    for q in запросы:
        if time.time() - НАЧАЛО > БЮДЖЕТ or проверено >= бюджет_карточек:
            break
        for путь in тт_поиск(q, максимум=бюджет_карточек):
            if путь in видел or проверено >= бюджет_карточек:
                continue
            видел.add(путь)
            if time.time() - НАЧАЛО > БЮДЖЕТ:
                break
            pi = тт_карточка(путь)
            проверено += 1
            if not pi:
                continue
            если_инн = str(pi.get('inn') or '').strip()
            if если_инн != str(inn):
                чужих += 1
                continue                        # рубеж закрыт по умолчанию
            дата = ((pi.get('dates') or {}).get('datePublished') or '')
            лет = лет_назад(дата)
            if лет is not None and лет > ПРЕДЕЛ_ЛЕТ:
                continue
            предмет = ' '.join(str(pi.get(k) or '') for k in
                               ('name', 'procedureName', 'subject', 'title'))
            for л in (pi.get('lots') or [])[:4]:
                if isinstance(л, dict):
                    предмет += ' ' + str(л.get('name') or л.get('lotName') or '')
            находки.append({
                'url': ТТ + путь, 'person': (pi.get('contactPerson') or '').strip(),
                'post': '', 'phone': чистый_тел(pi.get('contactPhone') or ''),
                'email': (pi.get('contactEmail') or '').strip().lower(),
                'дата': дата[:10], 'лет': лет, 'свежесть': свежесть(лет),
                'предмет': re.sub(r'\s+', ' ', предмет).strip()[:200],
                'организатор': pi.get('organizerName') or '',
                'площадка': 'tektorg'})
    return находки, проверено, чужих


_СТОП_ИМЯ = re.compile(
    r'\b(общество|с|ограниченной|ответственностью|акционерное|публичное|непубличное|'
    r'открытое|закрытое|ооо|оао|зао|пао|ао|нао|компания|фирма|группа|завод|'
    r'производственн\w*|торгов\w*|коммерческ\w*|научно|дом|объединение)\b', re.I)


def сокращения_имени(имя):
    """Запросы для текстового поиска: сначала кавычечное ядро («КРЕМНИЙ»),
    потом два значимых слова. Общие слова («завод», «группа») отдельным
    запросом НЕ идут — они приводят чужие компании."""
    имя = re.sub(r'\s+', ' ', (имя or '')).strip()
    вар = []
    m = re.findall(r'[«"]([^»"]{3,60})[»"]', имя)
    for x in m:
        x = x.strip()
        if x and x.lower() not in [v.lower() for v in вар]:
            вар.append(x)
    очищ = _СТОП_ИМЯ.sub(' ', имя)
    слова = [w for w in re.split(r'[^А-Яа-яЁёA-Za-z0-9\-]+', очищ) if len(w) >= 4]
    if слова:
        к = ' '.join(слова[:2])
        if к.lower() not in [v.lower() for v in вар]:
            вар.append(к)
    return вар[:2]


# ------------------------------------------------------------ Tender.pro
ТП = 'https://www.tender.pro'


def тп_компания(inn):
    """(company_id, имя) на Tender.pro или (None, '') — с ПРОВЕРКОЙ ИНН."""
    try:
        h = дай(f'{ТП}/api/companies/list?search_type=company&inn={inn}')
    except Exception:  # noqa: BLE001
        return None, ''
    f = re.findall(r'company-card__name "><a href="/api/company/(\d+)/view[^"]*"'
                   r'[^>]*>([^<]{0,90})</a>', h)
    if not f:
        return None, ''
    return f[0][0], f[0][1].strip()


def тп_тендеры(cid, inn):
    """(список [{id, дата, имя}], инн_подтверждён). tender_state=100 = «Все»,
    то есть ВМЕСТЕ С АРХИВОМ (правило владельца: архив даёт больше ФИО)."""
    try:
        h = дай(f'{ТП}/api/company/{cid}/view?active_tab=purchases'
                f'&tender_state=100&by=200', timeout=50)
    except Exception:  # noqa: BLE001
        return [], False
    плоско = re.sub(r'<[^>]+>', ' ', h)
    подтв = str(inn) in re.findall(r'(?<!\d)(\d{10,12})(?:/\d{9})', плоско)
    строки = []
    for blk in h.split('<li class="tender-list__item')[1:]:
        m = re.search(r'href="/api/tender/(\d+)/view_public"[^>]*>\s*(.{0,220}?)</a>',
                      blk, re.S)
        if not m:
            continue
        d = re.search(r'Создан:</span>&nbsp;<span class="c-text">([\d.]+)</span>', blk)
        строки.append({'id': m.group(1), 'дата': d.group(1) if d else '',
                       'имя': re.sub(r'\s+', ' ',
                                     re.sub(r'<[^>]+>', '', m.group(2))).strip()[:150]})
    return строки, подтв


def тп_карточка(tid):
    """{org_id, org, комментарий, заголовок} карточки тендера."""
    try:
        h = дай(f'{ТП}/api/tender/{tid}/view_public', timeout=40)
    except Exception:  # noqa: BLE001
        return None
    org = re.search(r'Организатор конкурса:</div><!-- div --><a '
                    r'href="/api/company/(\d+)/view"[^>]*title="([^"]{0,220})"', h)
    cm = re.search(r'Комментарий:</div><!-- div -->(.*?)</div><!-- div --></div>',
                   h, re.S)
    c = cm.group(1) if cm else ''
    c = re.sub(r'<br\s*/?>', '\n', c)
    c = re.sub(r'</p>', '\n', c)
    c = re.sub(r'<[^>]+>', ' ', c)
    c = (c.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&amp;', '&')
         .replace('&mdash;', '—').replace('&laquo;', '«').replace('&raquo;', '»'))
    c = re.sub(r'[ \t]+', ' ', c).strip()
    # служебный хвост про работу на ЭТП — не контакт компании
    m = re.search(r'По вопросам регистрации|Заявки принимаются строго через ЭТП|'
                  r'Вы вправе предоставить любую информацию|'
                  r'Данный запрос предложений не является торгами', c)
    ядро = c[:m.start()] if m else c
    заг = re.search(r'<h1[^>]*>(.{0,400}?)</h1>', h, re.S)
    return {'org_id': org.group(1) if org else '', 'org': org.group(2) if org else '',
            'комментарий': ядро[:6000],
            'заголовок': (re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', заг.group(1))).strip()[:200]
                          if заг else '')}


def тп_по_компании(inn, бюджет_карточек=14):
    """[находка] по одной компании Tender.pro."""
    cid, имя = тп_компания(inn)
    if not cid:
        return [], {'карточка': 0}
    строки, подтв = тп_тендеры(cid, inn)
    диаг = {'карточка': 1, 'cid': cid, 'имя': имя, 'подтв': подтв,
            'тендеров': len(строки), 'открыто': 0}
    if not подтв:
        # ИНН на странице компании не подтвердился — привязка недоказуема
        return [], диаг
    годные = []
    for s in строки:
        лет = лет_назад(s['дата'])
        if лет is not None and лет > ПРЕДЕЛ_ЛЕТ:
            continue
        годные.append((лет, s))
    годные.sort(key=lambda x: (x[0] if x[0] is not None else 99))
    диаг['годных'] = len(годные)
    находки = []
    for лет, s in годные[:бюджет_карточек]:
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        c = тп_карточка(s['id'])
        диаг['открыто'] += 1
        if not c:
            continue
        if c['org_id'] and c['org_id'] != str(cid):
            continue                            # организатор другой — не наш контакт
        for ч in люди_из_текста(c['комментарий']):
            if not (ч['phone'] or ч['email']):
                continue
            находки.append({
                'url': f'{ТП}/api/tender/{s["id"]}/view_public',
                'person': ч['person'], 'post': ч['post'], 'phone': ч['phone'],
                'email': ч['email'], 'дата': s['дата'], 'лет': лет,
                'свежесть': свежесть(лет),
                'предмет': (s['имя'] or c['заголовок'])[:200],
                'организатор': c['org'] or имя, 'площадка': 'tenderpro',
                'сырьё': c['комментарий'][:400]})
    return находки, диаг


# ------------------------------------------------------------ дедуп + запись
def схлопнуть(находки):
    """Дедуп ПО ЧЕЛОВЕКУ внутри компании: ключ — нормализованный телефон или
    почта (один снабженец ведёт десятки закупок). Оставляем САМУЮ СВЕЖУЮ
    закупку как source_url и объединяем поля."""
    по_ключу = {}
    for f in находки:
        ключ = (f.get('email') or '').lower() or тел10(f.get('phone') or '') \
            or (f.get('person') or '').lower()
        if not ключ:
            continue
        было = по_ключу.get(ключ)
        if было is None:
            по_ключу[ключ] = dict(f)
            continue
        # свежее (меньше лет) — выигрывает по url/дате
        л1 = было.get('лет')
        л2 = f.get('лет')
        if (л2 is not None) and (л1 is None or л2 < л1):
            было['url'], было['дата'], было['лет'] = f['url'], f['дата'], f['лет']
            было['свежесть'] = f['свежесть']
        for поле in ('person', 'post', 'phone', 'email', 'предмет'):
            if not было.get(поле) and f.get(поле):
                было[поле] = f[поле]
        было['повторов'] = было.get('повторов', 1) + 1
    return list(по_ключу.values())


def записать(db, inn, находки, стат):
    """В enrich.db: people + phone_contacts + emails + signals."""
    for f in находки:
        роль_текст = f.get('post') or ''
        роль = EDB.EnrichDB._canon_role(роль_текст) if роль_текст else ''
        источник = f['площадка']
        url = f['url']
        # источник + свежесть видны в поле source, чтобы выгрузка могла
        # отделить «устаревший» без обращения к дате
        src = f"{источник}:{f['свежесть']}:{f.get('дата') or ''}"
        if f.get('person'):
            db.add_person(inn, f['person'], post=роль_текст, phone=f.get('phone') or '',
                          email=f.get('email') or '', source=src, source_url=url,
                          observed_at=(_iso(f.get('дата')) or ''))
            стат['людей'] += 1
        if f.get('phone') and not мусорный_тел(f['phone']):
            db.cx.execute(
                'INSERT OR IGNORE INTO phone_contacts'
                '(inn, phone, person, role, source, source_url, updated_at) '
                'VALUES(?,?,?,?,?,?,?)',
                (str(inn), f['phone'], f.get('person') or '',
                 роль or 'снабжение/закупки', src, url,
                 time.strftime('%Y-%m-%dT%H:%M:%S')))
            стат['телефонов'] += 1
            if роль in EDB.EnrichDB.TECH_ROLES:
                стат['тел_технич'] += 1
        if f.get('email') and not мусорная_почта(f['email']):
            db.add_email(inn, f['email'], role=(роль_текст or 'закупки'),
                         person=f.get('person') or '', source=src, source_url=url)
            стат['почт'] += 1
        if ГОРЯЧЕЕ.search(f.get('предмет') or ''):
            db.add_signal(inn, source=источник, event_type='закупка',
                          what=(f.get('предмет') or '')[:400], source_url=url,
                          hotness=2, ts=(_iso(f.get('дата')) or ''))
            стат['сигналов'] += 1
    db.cx.commit()


def _iso(d):
    if not d:
        return ''
    m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', str(d))
    if m:
        return f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
    m = re.match(r'(\d{4}-\d{2}-\d{2})', str(d))
    return m.group(1) if m else ''


# ------------------------------------------------------------ прогон
def компании():
    сп, вид = [], set()
    if БАЗА_ИМЯ in ('core', 'both'):
        try:
            for x in json.load(open(r'C:\sender\server\core396.json', encoding='utf-8')):
                i = str(x.get('inn') or '').strip()
                if i and i not in вид:
                    вид.add(i)
                    сп.append({'inn': i, 'name': x.get('name', ''),
                               'rev': int(x.get('revenue_rub') or 0)})
        except Exception:  # noqa: BLE001
            pass
    if БАЗА_ИМЯ in ('sales', 'both'):
        try:
            b = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
        except Exception:  # noqa: BLE001
            try:
                b = json.load(open(r'C:\sender\server\sales_base.json', encoding='utf-8'))
            except Exception:  # noqa: BLE001
                b = {}
        for строки in (b.values() if isinstance(b, dict) else []):
            for x in строки:
                i = str(x.get('inn') or '').strip()
                if i and i not in вид:
                    вид.add(i)
                    сп.append({'inn': i, 'name': x.get('name', ''), 'rev': 0})
    сп.sort(key=lambda c: -c['rev'])
    return сп


def main():
    db = EDB.EnrichDB()
    СТАДИЯ = 'tender_platforms'
    сп = компании()
    # резюм по СЕРВЕРНОМУ stage_log, а не по локальному чекпоинту
    осталось = set(db.stage_missing([c['inn'] for c in сп], СТАДИЯ)) if ПРИМЕНИТЬ \
        else {c['inn'] for c in сп}
    todo = [c for c in сп if c['inn'] in осталось]
    if ЛИМИТ:
        todo = todo[:ЛИМИТ]
    стат = {'режим': 'ПРИМЕНЯЮ' if ПРИМЕНИТЬ else 'сухой',
            'источник': ИСТОЧНИК, 'база': БАЗА_ИМЯ,
            'в_очереди': len(todo), 'обработано': 0,
            'тт_карточек': 0, 'тт_чужих': 0, 'тт_находок': 0,
            'тп_компаний': 0, 'тп_подтв': 0, 'тп_карточек': 0, 'тп_находок': 0,
            'после_дедупа': 0, 'людей': 0, 'телефонов': 0, 'тел_технич': 0,
            'почт': 0, 'сигналов': 0, 'ошибок': 0}
    print('СТАРТ ' + json.dumps(стат, ensure_ascii=False), flush=True)
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    замок = threading.Lock()
    примеры = []

    def работа(c):
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            return
        inn, имя = c['inn'], c['name']
        находки, диаг = [], {}
        try:
            if ИСТОЧНИК in ('tenderpro', 'both'):
                н, д = тп_по_компании(inn)
                находки += н
                диаг['tp'] = д
            if ИСТОЧНИК in ('tektorg', 'both') and time.time() - НАЧАЛО <= БЮДЖЕТ:
                н, пров, чуж = тт_по_компании(inn, имя)
                находки += н
                диаг['tt'] = {'проверено': пров, 'чужих': чуж, 'находок': len(н)}
        except Exception as ex:  # noqa: BLE001
            диаг['err'] = repr(ex)[:120]
        свёрнуто = схлопнуть(находки)
        зап = {'inn': inn, 'name': имя[:70], 'диаг': диаг,
               'находок': len(находки), 'после_дедупа': len(свёрнуто),
               'контакты': свёрнуто[:12], 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}
        with замок:
            ф.write(json.dumps(зап, ensure_ascii=False) + '\n')
            ф.flush()
            os.fsync(ф.fileno())
            стат['обработано'] += 1
            if диаг.get('err'):
                стат['ошибок'] += 1
            tt = диаг.get('tt') or {}
            стат['тт_карточек'] += tt.get('проверено', 0)
            стат['тт_чужих'] += tt.get('чужих', 0)
            стат['тт_находок'] += tt.get('находок', 0)
            tp = диаг.get('tp') or {}
            стат['тп_компаний'] += tp.get('карточка', 0)
            стат['тп_подтв'] += 1 if tp.get('подтв') else 0
            стат['тп_карточек'] += tp.get('открыто', 0)
            стат['тп_находок'] += len([x for x in находки
                                       if x['площадка'] == 'tenderpro'])
            стат['после_дедупа'] += len(свёрнуто)
            if свёрнуто and len(примеры) < 12:
                примеры.append({'inn': inn, 'name': имя[:45],
                                'к': свёрнуто[:2]})
            if ПРИМЕНИТЬ:
                try:
                    записать(db, inn, свёрнуто, стат)
                    db.mark_stage(inn, СТАДИЯ,
                                  f'найдено {len(свёрнуто)}')
                except Exception as ex:  # noqa: BLE001
                    стат['ошибок'] += 1
                    зап['write_err'] = repr(ex)[:120]
            if стат['обработано'] % 10 == 0:
                print('.. ' + json.dumps(стат, ensure_ascii=False), flush=True)

    # скромная параллельность: обе площадки ходим напрямую, банить нельзя
    with ThreadPoolExecutor(max_workers=4) as пул:
        list(пул.map(работа, todo))
    ф.close()
    стат['осталось'] = len(todo) - стат['обработано']
    стат['секунд'] = round(time.time() - НАЧАЛО, 1)
    print('ПРИМЕРЫ ' + json.dumps(примеры, ensure_ascii=False)[:3000], flush=True)
    print('ИТОГ ' + json.dumps(стат, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
    os._exit(0)
