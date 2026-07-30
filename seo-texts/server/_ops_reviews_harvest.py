# -*- coding: utf-8 -*-
"""Сбор технических ЛПР из БЛАГОДАРСТВЕННЫХ ПИСЕМ и ОТЗЫВОВ на сайтах
поставщиков промышленного (компрессорного и смежного) оборудования.

Зачем. Все государственные реестры (ЕИС, закупки, раскрытие АО, СБИС) отдают
снабженцев и администрацию: главного инженера ни в один реестр не вносят. Он
появляется только там, где о нём написали ДОБРОВОЛЬНО. Отзыв на сайте
поставщика — ровно такое место, и формат идеальный: подпись «Сахно Г.А.
Главный инженер АО «Керамзит»» даёт должность + ФИО + предприятие одной
строкой, и человек уже покупал наш класс техники.

Что делает:
  1) качает страницы отзывов (+ пагинация) с сидов;
  2) ТЕКСТОВЫЕ отзывы — окна вокруг ключей должностей;
     СКАНЫ (img в блоке писем) — ocr_lib.ocr_картинка (tesseract rus);
  3) разбор окон/OCR провайдером (claude-fable-5) в тройки
     должность+ФИО+предприятие (+телефон/почта/дата);
  4) резолв предприятия в ИНН (news_scan.dadata_suggest) с ОТБРАКОВКОЙ
     некоммерческих форм (профсоюз/ТСЖ/СНТ) — сегодня dadata на
     «Новокуйбышевский НПЗ» первой отдавала профсоюз с именем завода внутри;
  5) durable-запись: enrich.db (companies/people/phone/email) + поток
     C:\\seostat\\drop\\reviews_stream.jsonl с flush+fsync.

Запуск:  python _ops_reviews_harvest.py [--apply] [--sites N] [--budget 260]
Без --apply — сухой прогон (в базу не пишет, поток пишет как dry).
Резюмируемость: состояние в C:\\seostat\\drop\\reviews_state.json, сайт
считается сделанным по имени; повторный запуск берёт следующие.
"""
import json
import os
import re
import sys
import time
import threading
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r'C:\sender\server')

import enrich_contacts as EC          # noqa: E402
import enrich_db                      # noqa: E402

try:
    import ocr_lib
except Exception:                     # noqa: BLE001
    ocr_lib = None
try:
    import news_scan as NS
except Exception:                     # noqa: BLE001
    NS = None

ПОТОК = r'C:\seostat\drop\reviews_stream.jsonl'
СЫРЬЁ = r'C:\seostat\drop\reviews_raw.jsonl'
РАЗБОР = r'C:\seostat\drop\reviews_parsed.json'
СОСТ = r'C:\seostat\drop\reviews_state.json'
ИСТОЧНИК = 'отзывы-поставщиков'

# ЭТАПЫ. Провайдерский шлюз с СЕРВЕРА недоступен: замерено на прогоне 30.07 —
# 9 вызовов из 9 упали в TimeoutError, при том что тот же вызов из песочницы
# отвечает за 5-8 секунд. Поэтому конвейер разрезан:
#   --stage ocr      сервер: качает страницы, распознаёт сканы -> reviews_raw.jsonl
#   (между ними)     песочница: разбор провайдером -> reviews_parsed.json на дроп
#   --stage persist  сервер: резолв ИНН (dadata) + запись в enrich.db и поток
# Этап all оставлен на случай, если доступ к шлюзу с сервера появится.

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

# ---------------------------------------------------------------- сиды
# Найдены руками через выдачу и проверены глазами ДО написания парсера
# (директива: не писать парсер, пока не увидел живую подпись).
СИДЫ = [
    # (домен-метка, стартовый url, шаблон пагинации или '')
    ('compressortyt.ru', 'https://www.compressortyt.ru/o-kompanii/reviews/', ''),
    ('compressor-service.ru', 'https://compressor-service.ru/reviews', ''),
    ('pnevmoteh.ru', 'https://www.pnevmoteh.ru/blagodarstvennye-pisma', '?page={n}'),
    ('energopromrus.ru', 'https://energopromrus.ru/otzyvy-i-blagodarstvennye-pisma/', ''),
    ('ost-m.ru', 'https://ost-m.ru/about/priznanie/', ''),
    ('dioksid.ru', 'https://dioksid.ru/otzyivyi-i-blagodarstvennyie-pisma/', ''),
    ('ipce.ru', 'https://ipce.ru/responsess/', ''),
    ('chkz.ru', 'https://www.chkz.ru/about/response/', ''),
]

# ------------------------------------------------------- должности-якоря
# ВНИМАНИЕ: «заместитель главного инженера» обрезанный до «главного инженера»
# завышает роль — поэтому окно берём ШИРОКОЕ и должность сохраняем целиком,
# а решает модель. Здесь только якорь «в этом месте есть должность».
ЯКОРЬ = re.compile(
    r'главн\w*\s+(?:инженер|энергетик|механик|технолог|метролог|конструктор)'
    r'|гл\.?\s*(?:инженер|энергетик|механик|технолог)'
    r'|техническ\w*\s+директор|директор\s+по\s+(?:производств|техни|развити)\w*'
    r'|начальник\w*\s+(?:производств|цеха|отдела|службы|управлени|участка|'
    r'котельн|энергослужб|ремонтн)\w*'
    r'|руководител\w*\s+(?:производств|отдела|службы|направлени|проекта)\w*'
    r'|заместител\w*\s+(?:главн|директор|генеральн)\w*'
    r'|энергетик|главный\s+специалист|ведущий\s+инженер|инженер\s+по\s+'
    r'|ОГЭ|ОГМ|КИПиА|АСУ\s*ТП'
    r'|генеральн\w*\s+директор|исполнительн\w*\s+директор|директор\s+предприятия'
    r'|коммерческ\w*\s+директор|начальник\s+ОМТС|отдел\w*\s+снабжени\w*',
    re.I)

# картинки-кандидаты на скан письма
СКАН_ХИНТ = re.compile(
    r'blagodar|pismo|letter|otzyv|otziv|review|scan|skan|recommend|rekomend'
    r'|благодар|письм|отзыв|/upload/|/files/|/images/|/uploads/', re.I)
СКАН_ШУМ = re.compile(
    r'logo|icon|sprite|banner|placeholder|favicon|avatar|arrow|btn|button'
    r'|mc\.yandex|counter|pixel|watch/|/tg\.|telegram|whatsapp|vk\.|social', re.I)

# некоммерческие/непроизводственные формы — выбрасываем ДО скоринга
НЕКОММ = re.compile(
    r'профсоюз|профессиональн\w+\s+союз|садовод|СНТ\b|ТСЖ\b|ТСН\b|ЖСК\b'
    r'|гаражн|кооператив\s+граждан|религиозн|партия|фонд\s+поддержк'
    r'|адвокатск|нотариальн|ассоциаци\w*\s+профс', re.I)

# «технические» канон-роли enrich_db — ГЛАВНАЯ ЦИФРА замера
ТЕХ_РОЛИ = {'гл.инженер', 'гл.энергетик', 'гл.механик', 'гл.технолог',
            'техдиректор', 'нач.производства', 'нач.цеха', 'АСУ/КИПиА',
            'гл.конструктор'}

_СЧ = {}
_СЧ_L = threading.Lock()
# ИНН, которые мы знали ДО этого прогона: enrich.db + обзвонная база (161761).
# Снимок берём один раз на старте — после upsert_company любая компания стала бы
# «известной», и цифра «новых» превратилась бы в ноль.
_ЗНАЛИ_EDB = set()
_ЗНАЛИ_БАЗА = set()


def снимок_известных():
    """Снимок ИНН из enrich.db. Обзвонную CSV (161761 строка, >100 МБ) здесь НЕ
    читаем: один проход стоит дороже всего прогона. Её сверяем ОДНИМ проходом
    в конце — по уже собранному коротком списку ИНН (EC._base_index)."""
    global _ЗНАЛИ_EDB
    try:
        db = enrich_db.EnrichDB()
        _ЗНАЛИ_EDB = {str(r[0]) for r in
                      db.cx.execute('SELECT inn FROM companies').fetchall() if r[0]}
    except Exception:                                   # noqa: BLE001
        сч('снимок_edb_ошибка')
    сч('знали_edb', len(_ЗНАЛИ_EDB))


def сч(k, n=1):
    with _СЧ_L:
        _СЧ[k] = _СЧ.get(k, 0) + n


def печать_счётчиков(метка):
    print(f'[{метка}] ' + json.dumps(_СЧ, ensure_ascii=False, sort_keys=True),
          flush=True)


# ---------------------------------------------------------------- сеть
def качать(url, timeout=40):
    """Страница текстом. Кодировку определяем ЯВНО: requests.text без charset
    в заголовке считает страницу latin-1 и убивает кириллицу ДО разбора."""
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9'})
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
            ct = r.headers.get('Content-Type', '')
        сч('http_ok')
        return EC._раскодировать(raw, ct)
    except Exception as e:                              # noqa: BLE001
        сч('http_err')
        сч('http_err_' + type(e).__name__)
        return ''


def качать_байты(url, timeout=45, кап=6_000_000):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read(кап)
    except Exception:                                   # noqa: BLE001
        return b''


# ------------------------------------------------------------ провайдер
_ПРОМПТ = (
    'Ниже — куски текста со страницы БЛАГОДАРСТВЕННЫХ ПИСЕМ/ОТЗЫВОВ на сайте '
    'поставщика промышленного оборудования. Внутри могут быть подписи вида '
    '«Иванов И.И., главный энергетик ОАО "Завод"». Часть текста — распознанный '
    'скан, там бывают опечатки распознавания.\n\n'
    'Верни СТРОГО JSON-массив (и ничего кроме него). Один элемент — один '
    'ПОДПИСАВШИЙ отзыв человек:\n'
    '{"фио":"", "должность":"", "предприятие":"", "телефон":"", "почта":"", '
    '"дата":"", "цитата":""}\n\n'
    'Правила:\n'
    '- ДОЛЖНОСТЬ ЦЕЛИКОМ. «Заместитель главного инженера» НЕЛЬЗЯ сокращать до '
    '«главный инженер» — это разные люди и разный вес. Так же «и.о.», '
    '«ведущий», «первый».\n'
    '- ПРЕДПРИЯТИЕ — организация, от имени которой написан отзыв (клиент), '
    'а НЕ сам поставщик, которого благодарят. Пиши с ОПФ, как в тексте.\n'
    '- Менеджеров/сотрудников поставщика, которых хвалят в тексте, НЕ включай.\n'
    '- Если ФИО дано инициалами («Сахно Г.А.») — так и пиши, не выдумывай.\n'
    '- Не угадывай: чего в тексте нет, оставляй пустой строкой. Дату бери '
    'только явную (год достаточно).\n'
    '- «цитата» — до 120 символов исходной подписи, по которой ты решил.\n'
    '- Если подписей нет — верни [].\n\nТЕКСТ:\n')


def провайдер(текст, модель='claude-fable-5', таймаут=120):
    """Разбор куска текста в тройки. Стриминг обязателен — шлюз рубит поток
    примерно на 35-й секунде, поэтому куски маленькие (2-3 тыс. знаков)."""
    key = os.environ.get('PROVIDER_API_KEY', '') or EC._read_secret('PROVIDER_API_KEY')
    if not key or not (текст or '').strip():
        return []
    base = (os.environ.get('PROVIDER_BASE_URL', '')
            or EC._read_secret('PROVIDER_BASE_URL') or 'https://router.cheap').rstrip('/')
    тело = json.dumps({
        'model': модель, 'max_tokens': 2000, 'stream': True,
        'messages': [{'role': 'user', 'content': _ПРОМПТ + текст[:4000]}],
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        base + '/v1/messages', data=тело, method='POST',
        headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json',
                 'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
    куски = []
    try:
        with urllib.request.urlopen(req, timeout=таймаут) as r:
            for сырая in r:
                s = сырая.decode('utf-8', 'replace').strip()
                if not s.startswith('data:'):
                    continue
                s = s[5:].strip()
                if not s or s == '[DONE]':
                    continue
                try:
                    j = json.loads(s)
                except Exception:                       # noqa: BLE001
                    continue
                if j.get('type') == 'content_block_delta':
                    куски.append(j.get('delta', {}).get('text') or '')
        сч('провайдер_ок')
    except Exception as e:                              # noqa: BLE001
        сч('провайдер_ошибка')
        сч('провайдер_err_' + type(e).__name__)
        return []
    т = ''.join(куски).strip()
    m = re.search(r'\[.*\]', т, re.S)
    if not m:
        сч('провайдер_без_json')
        return []
    try:
        д = json.loads(m.group(0))
        return д if isinstance(д, list) else []
    except Exception:                                   # noqa: BLE001
        сч('провайдер_битый_json')
        return []


# ------------------------------------------------------------- разбор
def окна(текст, радиус=420):
    """Куски вокруг якорей должностей, склеенные если пересекаются."""
    точки = []
    for m in ЯКОРЬ.finditer(текст or ''):
        точки.append((max(0, m.start() - радиус), min(len(текст), m.end() + радиус)))
    if not точки:
        return []
    точки.sort()
    слитые = [list(точки[0])]
    for a, b in точки[1:]:
        if a <= слитые[-1][1]:
            слитые[-1][1] = max(слитые[-1][1], b)
        else:
            слитые.append([a, b])
    return [текст[a:b] for a, b in слитые]


def нарезать(куски, кап=2600):
    """Пачки по ~2.6к знаков: шлюз рубит поток на ~35-й секунде."""
    пачки, тек = [], ''
    for к in куски:
        if len(тек) + len(к) > кап and тек:
            пачки.append(тек)
            тек = ''
        тек += ('\n\n---\n' + к) if тек else к
        while len(тек) > кап * 1.6:
            пачки.append(тек[:кап])
            тек = тек[кап:]
    if тек.strip():
        пачки.append(тек)
    return пачки


def сканы(html, база):
    """Адреса картинок-кандидатов на скан благодарственного письма."""
    из = []
    for m in re.finditer(r'<img[^>]+(?:data-src|data-original|src)="([^"]+)"',
                         html or '', re.I):
        u = m.group(1).strip()
        if not u or u.startswith('data:'):
            continue
        if СКАН_ШУМ.search(u) or u.lower().endswith(('.svg', '.gif')):
            continue
        if not СКАН_ХИНТ.search(u):
            continue
        из.append(urllib.parse.urljoin(база, u))
    # ссылки на увеличенные версии/PDF писем
    for m in re.finditer(r'href="([^"]+\.(?:jpe?g|png|pdf))"', html or '', re.I):
        u = m.group(1)
        if СКАН_ШУМ.search(u) or not СКАН_ХИНТ.search(u):
            continue
        из.append(urllib.parse.urljoin(база, u))
    # без дублей; вперёд — те, у кого в адресе прямо сказано «письмо/отзыв»:
    # у pnevmoteh на странице 149 картинок, из них письма — десяток, остальное
    # логотипы клиентов, и без сортировки бюджет OCR уходит в логотипы.
    сильный = re.compile(r'blagodar|pismo|letter|otzyv|otziv|recommend|rekomend'
                         r'|благодар|письм|отзыв', re.I)
    видел, рез = set(), []
    for u in из:
        k = u.split('?')[0]
        if k in видел:
            continue
        видел.add(k)
        рез.append(u)
    рез.sort(key=lambda u: 0 if сильный.search(u) else 1)
    return рез


def без_превью(url):
    """Оригинал картинки вместо превью. На превью 210x300 распознавание даёт
    кашу: подпись под письмом — самый мелкий кегль на листе.
    Три схемы движков: bitrix resize_cache, drupal image styles, /WxH/."""
    u = url
    u = re.sub(r'/upload/resize_cache/(.+?)/\d+_\d+_\d+/', r'/upload/\1/', u)
    u = re.sub(r'(/sites/[^/]+/files)/styles/[^/]+/public/', r'\1/', u)
    u = re.sub(r'/\d{2,4}x\d{2,4}/', '/', u)
    u = u.split('?')[0]
    return u if u != url.split('?')[0] else ''


def распознать(url):
    """Текст со скана. PDF — через doc_text (сам уходит на OCR при коротком
    текстовом слое), картинка — напрямую ocr_lib.ocr_картинка."""
    if url.lower().split('?')[0].endswith('.pdf'):
        try:
            т = EC.doc_text(url) or ''
            сч('pdf_ocr' if т.strip() else 'pdf_пусто')
            return т
        except Exception:                               # noqa: BLE001
            сч('pdf_ошибка')
            return ''
    if not ocr_lib:
        return ''
    blob = b''
    ориг = без_превью(url)
    if ориг:
        blob = качать_байты(ориг)
        if blob:
            сч('скан_оригинал')
    if not blob:
        blob = качать_байты(url)
    if not blob:
        сч('скан_не_скачан')
        return ''
    try:
        т = ocr_lib.ocr_картинка(blob, язык='rus', psm=1, таймаут=110) or ''
    except Exception:                                   # noqa: BLE001
        сч('ocr_ошибка')
        return ''
    if ocr_lib.кириллица(т) and len(т.strip()) > 60:
        сч('ocr_текст')
        return т
    сч('ocr_пусто')
    return ''


# --------------------------------------------------------------- резолв
_ДД_КЭШ = {}


def в_инн(имя, токен):
    """Название предприятия -> ИНН. Некоммерческие формы отбрасываем ДО
    скоринга: dadata на «Новокуйбышевский НПЗ» первой отдавала ПРОФСОЮЗ с
    именем завода внутри. Не подтвердил — не пишем."""
    имя = (имя or '').strip()
    if len(имя) < 4 or not токен or not NS:
        return None
    if НЕКОММ.search(имя):
        сч('имя_некоммерч')
        return None
    if имя in _ДД_КЭШ:
        return _ДД_КЭШ[имя]
    try:
        д = NS.dadata_suggest(имя, токен)
    except Exception:                                   # noqa: BLE001
        сч('dadata_ошибка')
        д = None
    if д and НЕКОММ.search(д.get('name') or ''):
        сч('резолв_некоммерч_отбит')
        д = None
    if д and д.get('confidence') == 'low':
        сч('резолв_low')
    _ДД_КЭШ[имя] = д
    сч('резолв_ок' if д else 'резолв_пусто')
    return д


def свежесть(дата):
    """Правило владельца: до 2 лет свежий, 2-3 года устаревший, старше 3 не
    берём. Даты нет — так и пишем, не выдаём за свежее."""
    m = re.search(r'(19|20)\d{2}', str(дата or ''))
    if not m:
        return 'дата неизвестна', True
    год = int(m.group(0))
    тек = int(time.strftime('%Y'))
    if тек - год <= 2:
        return f'свежий ({год})', True
    if тек - год == 3:
        return f'устаревший ({год})', True
    return f'старый ({год})', False


# ------------------------------------------------------------ хранилище
_ПОТОК_L = threading.Lock()


def дописать(путь, запись):
    """Строка в durable-поток: flush + fsync. Возвращаемый JSON не хранилище —
    песочница при рестарте откатывается к снимку, серверный файл переживает."""
    with _ПОТОК_L:
        try:
            os.makedirs(os.path.dirname(путь), exist_ok=True)
            with open(путь, 'a', encoding='utf-8') as f:
                f.write(json.dumps(запись, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
        except Exception:                               # noqa: BLE001
            сч('поток_ошибка')


def в_поток(запись):
    дописать(ПОТОК, запись)


def сост_читать():
    try:
        return json.load(open(СОСТ, encoding='utf-8'))
    except Exception:                                   # noqa: BLE001
        return {'сделано': []}


def сост_писать(с):
    try:
        with open(СОСТ, 'w', encoding='utf-8') as f:
            json.dump(с, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except Exception:                                   # noqa: BLE001
        pass


# ---------------------------------------------------------------- прогон
def собрать(метка, url, пагинация, сканов=14):
    """ЭТАП 1 (сервер): страницы -> куски текста, годные к разбору.
    Возвращает [(url_первоисточника, текст, вид)] и пишет их в reviews_raw.jsonl."""
    html = качать(url)
    if not html:
        return []
    страницы = [(url, html)]
    if пагинация:
        for n in (2, 3):
            u2 = url + пагинация.format(n=n)
            h2 = качать(u2)
            if h2 and len(h2) > 2000:
                страницы.append((u2, h2))
            time.sleep(0.7)
    сч('страниц', len(страницы))

    задания = []      # (url_первоисточника, текст, вид)
    for u, h in страницы:
        чистый = EC.без_графики(h)                 # SVG-координаты как «телефон»
        текст = EC._текст(чистый)
        w = окна(текст)
        if w:
            сч('окон_текст', len(w))
            for пачка in нарезать(w):
                задания.append((u, пачка, 'текст'))
        сп = сканы(чистый, u)[:сканов]
        сч('сканов_найдено', len(сп))
        for s in сп:
            т = распознать(s)
            if т and ЯКОРЬ.search(т):
                сч('сканов_с_должностью')
                задания.append((s, т[:3500], 'скан'))
            elif т:
                сч('сканов_текст_без_должности')
    for u, т, вид in задания:
        дописать(СЫРЬЁ, {'сайт': метка, 'url': u, 'вид': вид, 'текст': т,
                         'ts': time.strftime('%Y-%m-%dT%H:%M:%S')})
    сч('кусков_сырья', len(задания))
    return задания


def записать(итог, ддток, применять, db):
    """ЭТАП 3 (сервер): разобранные тройки -> резолв ИНН -> enrich.db + поток."""
    записей = []
    for эл in итог:
        фио = (эл.get('фио') or '').strip()
        долж = (эл.get('должность') or '').strip()
        предпр = (эл.get('предприятие') or '').strip()
        if not (фио and предпр):
            сч('неполная_тройка')
            continue
        сч('троек_сырых')
        метка_свеж, брать = свежесть(эл.get('дата'))
        if not брать:
            сч('отброшен_старый')
            continue
        дд = в_инн(предпр, ддток)
        инн = (дд or {}).get('inn') or ''
        роль = enrich_db.EnrichDB._canon_role(долж)
        тел = ''
        for m in EC.phones_in(эл.get('телефон') or ''):
            тел = re.sub(r'\s+', ' ', m.group(0)).strip()
            break
        почта = (эл.get('почта') or '').strip().lower()
        if почта and EC._is_junk_email(почта):
            почта = ''
        зап = {'сайт': эл.get('_сайт') or '', 'url': эл.get('_url'),
               'вид': эл.get('_вид'),
               'фио': фио, 'должность': долж, 'роль': роль,
               'предприятие': предпр, 'инн': инн,
               'резолв_имя': (дд or {}).get('name') or '',
               'уверенность': (дд or {}).get('confidence') or '',
               'окved': (дд or {}).get('okved') or '',
               'телефон': тел, 'почта': почта,
               'дата': эл.get('дата') or '', 'свежесть': метка_свеж,
               'цитата': (эл.get('цитата') or '')[:160],
               'техническая': роль in ТЕХ_РОЛИ,
               'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
               'применено': bool(применять and инн)}
        записей.append(зап)
        if not инн:
            сч('без_инн')
            в_поток(зап)
            continue
        сч('с_инн')
        # НОВАЯ ли компания для нас — считаем ДО записи, иначе после upsert
        # любая станет «известной». Две наши базы: enrich.db и обзвонная CSV.
        зап['в_enrich'] = инн in _ЗНАЛИ_EDB
        if not зап['в_enrich']:
            сч('нет_в_enrich')
        в_поток(зап)
        if роль in ТЕХ_РОЛИ:
            сч('технических')
        if применять:
            окв = (дд or {}).get('okved') or ''
            конк = any(окв.startswith(x) for x in ('28.13', '28.12'))
            db.upsert_company(инн, name=(дд or {}).get('name') or предпр,
                              okved=окв, division='КЦ',
                              is_competitor=1 if конк else None)
            if конк:
                сч('конкурентов')
            db.add_person(инн, фио, post=долж, phone=тел, email=почта,
                          source=ИСТОЧНИК, source_url=эл.get('_url') or '')
            if тел:
                db.add_phone(инн, тел, person=фио, role=долж,
                             source=ИСТОЧНИК, source_url=эл.get('_url') or '')
            if почта:
                db.add_email(инн, почта, role=долж, person=фио,
                             source=ИСТОЧНИК, source_url=эл.get('_url') or '')
            сч('записано_в_базу')
    return записей


def main():
    аргв = sys.argv[1:]
    применять = '--apply' in аргв
    лимит = 8
    бюджет = 260
    for i, a in enumerate(аргв):
        if a == '--sites' and i + 1 < len(аргв):
            лимит = int(аргв[i + 1])
        if a == '--budget' and i + 1 < len(аргв):
            бюджет = int(аргв[i + 1])
    старт = time.time()
    ддток = EC._read_secret('DADATA_TOKEN')
    сч('dadata_token', 1 if ддток else 0)
    снимок_известных()
    db = enrich_db.EnrichDB() if применять else None
    сост = сост_читать()
    сделано = set(сост.get('сделано') or [])
    печать_счётчиков('старт')
    всего = []
    for метка, url, паг in СИДЫ:
        if метка in сделано:
            continue
        if time.time() - старт > бюджет:
            сч('бюджет_кончился')
            break
        if len([m for m, _, _ in СИДЫ if m in сделано]) >= лимит:
            break
        try:
            r = сайт(метка, url, паг, ддток, применять, db)
            всего += r
            сч('сайтов_обработано')
        except Exception as e:                          # noqa: BLE001
            сч('сайт_ошибка')
            print(f'ОШИБКА {метка}: {type(e).__name__}: {str(e)[:200]}', flush=True)
        сделано.add(метка)
        сост['сделано'] = sorted(сделано)
        сост_писать(сост)
        печать_счётчиков('после ' + метка)

    печать_счётчиков('итог')
    тех = [z for z in всего if z['техническая']]
    print('ПРИМЕРЫ:', flush=True)
    for z in (тех or всего)[:12]:
        print('  ', json.dumps({k: z[k] for k in
                                ('сайт', 'фио', 'должность', 'роль', 'предприятие',
                                 'инн', 'вид', 'свежесть', 'url')},
                               ensure_ascii=False), flush=True)
    print(json.dumps({'сайтов': len(сост.get('сделано') or []),
                      'записей': len(всего), 'технических': len(тех),
                      'применено': применять}, ensure_ascii=False), flush=True)
    печать_счётчиков('итог2')


if __name__ == '__main__':
    main()
