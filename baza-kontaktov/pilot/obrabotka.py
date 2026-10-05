# -*- coding: utf-8 -*-
"""Обработка выдачи пилота XMLRiver (ТЗ-PILOT-XMLRIVER.md, п. 3–4). Без LLM, без сети.

Чистые функции: нормализация домена, стоп-лист, пост-фильтр минус-слов, порталы,
балл профиля по словарям сегмента, парковки, ИНН/УНП с контрольной суммой,
статус «новые / старые». Сетевая часть (скачать главную) — в proverka_saytov.py.

Самопроверка: python3 obrabotka.py --test
"""
import os
import re
import sys
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
BAZA = os.path.dirname(DIR)

# --- домены -------------------------------------------------------------------------

# Публичные суффиксы второго уровня, на которых регистрируют сайты (eTLD+1 = 3 метки).
_SUFFIX2 = {
    'com.ru', 'net.ru', 'org.ru', 'pp.ru', 'msk.ru', 'spb.ru', 'nov.ru', 'kuban.ru',
    'krasnodar.ru', 'rnd.ru', 'nsk.ru', 'altai.ru', 'ru.com', 'ru.net', 'com.by', 'org.by',
    'net.by', 'gov.by', 'gov.ru', 'edu.ru', 'co.uk', 'com.ua', 'com.kz', 'org.kz',
    'narod.ru', 'ucoz.ru', 'ucoz.net', 'tilda.ws', 'wixsite.com', 'ru.gg', 'blogspot.com',
}
_FREE_MAIL = {
    'mail.ru', 'yandex.ru', 'ya.ru', 'yandex.by', 'yandex.com', 'gmail.com', 'bk.ru',
    'list.ru', 'inbox.ru', 'rambler.ru', 'internet.ru', 'mail.ua', 'yahoo.com', 'hotmail.com',
    'outlook.com', 'icloud.com', 'tut.by', 'ro.ru', 'lenta.ru', 'autorambler.ru', 'myrambler.ru',
    'mail.com', 'live.ru', 'live.com', 'protonmail.com', 'me.com', 'nm.ru', 'pochta.ru',
}


def _idna(label):
    try:
        return label.encode('idna').decode('ascii') if any(ord(c) > 127 for c in label) else label
    except UnicodeError:
        return label


def norm_domain(url_or_host):
    """URL/хост/e-mail → eTLD+1 в нижнем регистре, без www, в punycode (xn--…)."""
    s = (url_or_host or '').strip().lower()
    if not s:
        return ''
    if '@' in s and '//' not in s:
        s = s.rsplit('@', 1)[1]
    s = re.sub(r'^[a-z][a-z0-9+.-]*://', '', s)
    s = s.split('/', 1)[0].split('?', 1)[0].split('#', 1)[0]
    s = s.rsplit('@', 1)[-1].split(':', 1)[0].strip('.')
    if not s or re.fullmatch(r'[\d.]+', s):
        return s
    labels = [_idna(x) for x in s.split('.') if x]
    if labels and labels[0] == 'www':
        labels = labels[1:]
    if len(labels) <= 2:
        return '.'.join(labels)
    if '.'.join(labels[-2:]) in _SUFFIX2:
        return '.'.join(labels[-3:])
    return '.'.join(labels[-2:])


def domain_unicode(d):
    """punycode → кириллица для отчёта (.рф)."""
    try:
        return '.'.join(x.encode('ascii').decode('idna') if x.startswith('xn--') else x
                        for x in d.split('.'))
    except UnicodeError:
        return d


def email_domain(email):
    d = norm_domain(email)
    return '' if (not d or d in _FREE_MAIL) else d


# --- стоп-лист и пост-фильтр ---------------------------------------------------------

def load_stop(path=None):
    """{домен: тип} из stop_domeny.txt (совпадение по суффиксу)."""
    out = {}
    for line in open(path or os.path.join(BAZA, 'stop_domeny.txt'), encoding='utf-8'):
        if not line.strip() or line.startswith('#'):
            continue
        p = line.rstrip('\n').split('\t')
        # хост как записан (без www): запись zen.yandex.ru не должна покрыть весь yandex.ru
        h = p[0].strip().lower()
        h = '.'.join(_idna(x) for x in (h[4:] if h.startswith('www.') else h).split('.'))
        out[h] = p[1].strip() if len(p) > 1 else ''
    return out


_SOC = ('vk.com', 'vk.ru', 'ok.ru', 't.me', 'telegram.me', 'facebook.com', 'instagram.com',
        'youtube.com', 'rutube.ru', 'dzen.ru', 'zen.yandex.ru', 'twitter.com', 'x.com',
        'tiktok.com', 'pinterest.com', 'linkedin.com', 'livejournal.com', 'pikabu.ru')
_PDF_HOST = ('docviewer.yandex.ru', 'disk.yandex.ru', 'drive.google.com', 'docs.google.com',
             'scribd.com', 'studfile.net', 'studref.com', 'studwood.net', 'docplayer.com',
             'docplayer.ru', 'pandia.ru', 'dokumen.pub', 'issuu.com', 'calameo.com', 'cyberleninka.ru',
             'elibrary.ru')
_URL_JUNK = re.compile(r'/(news|novosti|blog|article|articles|stati|forum|vacanc|vakans|job|'
                       r'catalog/firms|firms?/\d|company/\d|org/\d)', re.I)


def stop_type(host, stop):
    """Тип записи стоп-листа, покрывающей хост (по суффиксу), иначе ''."""
    h = (host or '').lower().split(':')[0]
    if h.startswith('www.'):
        h = h[4:]
    parts = h.split('.')
    for i in range(len(parts) - 1):
        suf = '.'.join(parts[i:])
        if suf in stop:
            return stop[suf] or 'stop'
    if re.search(r'(^|\.)gov\.(ru|by)$|(^|\.)edu\.ru$|(^|\.)mo\.ru$', h) or re.match(r'adm(in)?[\w-]*\.', h):
        return 'gos'
    if any(h == s or h.endswith('.' + s) for s in _SOC):
        return 'socset'
    if any(h == s or h.endswith('.' + s) for s in _PDF_HOST):
        return 'pdf_host'
    return ''


def load_post(path=None):
    """{сегмент|global: [фразы]} из блоков [post:*]."""
    out, cur = {}, None
    for line in open(path or os.path.join(BAZA, 'minus_slova.txt'), encoding='utf-8'):
        s = line.strip()
        m = re.match(r'\[(query|post):(\w+)\]', s)
        if m:
            cur = m.group(2) if m.group(1) == 'post' else None
            continue
        if cur and s and not s.startswith('#'):
            out.setdefault(cur, []).append(s.lower())
    return out


def post_hits(segment, title, url, post):
    """Сработавшие пост-фразы по title+url. По ТЗ это понижение/ручная проверка, не отсев,
    но title-попадания global-блока для URL с мусорным путём отсекаем (статьи, новости)."""
    t = f'{title or ""} {url or ""}'.lower()
    hits = [p for p in post.get('global', []) + post.get(segment, []) if p in t]
    if _URL_JUNK.search(url or ''):
        hits.append('url:' + _URL_JUNK.search(url).group(1).lower())
    return hits


def portals(cands, min_segments=5):
    """Домены, встретившиеся в выдаче по ≥5 разным сегментам (+подсегментам) — порталы."""
    return {d for d, c in cands.items() if len(c['segments'] | c['subsegments_full']) >= min_segments
            and len(c['segments']) >= min(min_segments, 3)} | \
           {d for d, c in cands.items() if len(c['segments']) >= min_segments}


# --- профиль сайта --------------------------------------------------------------------
# Основы слов (регулярки начала слова). title и H1 считаются ×2. Стоп-слова снимают балл.

SLOVAR = {
    'exporters': {
        'mark': [r'экспорт', r'вэд\b', r'\bfob\b', r'\bcif\b', r'трейдинг', r'зернов\w* терминал', r'перевалк',
                 r'сдиз', r'фитосанитар', r'export', r'grain', r'oilseed', r'pulses', r'supplier'],
        'tovar': [r'пшениц', r'ячмен', r'кукуруз', r'подсолнечн', r'рапс', r'льносемен', r'\bсо[яи]\b',
                  r'горох', r'\bнут', r'чечевиц', r'жмых', r'шрот', r'wheat', r'barley', r'sunflower'],
        'stop': [r'таможенн\w* брокер', r'логистическ\w* компани'],
    },
    'seeds': {
        'mark': [r'семен(?!н?ой\s+кофе)', r'семян', r'семеновод', r'гибрид', r'оригинатор', r'элит\w*',
                 r'репродукци', r'семенн\w* завод', r'протравлив', r'калибров', r'посевн\w* материал',
                 r'селекци'],
        'stop': [r'семена для дачи', r'интернет-магазин семян', r'сорт\w* кофе', r'семена почтой',
                 r'цветов', r'газон'],
    },
    'food': {
        'mark': [r'производств', r'пищев', r'завод', r'\bцех', r'хассп', r'haccp', r'iso 22000', r'фасовк',
                 r'комбинат'],
        'tovar': [r'\bмук[аиу]', r'круп[аы]', r'\bмасл[оа]', r'молок', r'кондитер', r'хлеб', r'консерв',
                  r'\bсок', r'крахмал', r'комбикорм', r'макарон', r'сахар', r'паток'],
        'stop': [r'\bкафе\b', r'ресторан', r'доставка еды', r'магазин продуктов', r'суши', r'пицц'],
    },
    'elevators': {
        'mark': [r'элеватор(?!н\w* узел)', r'\bхпп\b', r'\bкхп\b', r'зернохранилищ', r'силос',
                 r'приемк\w* зерна', r'приёмк\w* зерна', r'сушк\w* зерна', r'зерносушилк',
                 r'подработк\w* зерна', r'очистк\w* зерна', r'хранени\w* зерна', r'хлебоприемн', r'хлебоприёмн',
                 r'хлебопродукт'],
        'stop': [r'элеваторн\w* узел', r'отоплени', r'\bитп\b', r'теплоснабжени', r'гидроэлеватор', r'\bлифт'],
    },
    'nuts': {
        'mark': [r'орех', r'фундук', r'грецк', r'миндал', r'кешью', r'фисташк', r'кедров\w* орех',
                 r'ядро ореха', r'колк\w* орех', r'обжарк\w* орех', r'калибровк\w* орех'],
        'stop': [r'пиломатериал', r'мебел'],
    },
    'berries': {
        'mark': [r'ягод', r'клубник', r'земляник', r'малин', r'смородин', r'голубик', r'клюкв', r'брусник',
                 r'облепих', r'жимолост', r'шоков\w* заморозк', r'\biqf\b', r'ягодн\w* питомник', r'\bджем',
                 r'конфитюр', r'\bпюре', r'\bморс'],
        'stop': [],
    },
}
_RX = {seg: {k: [re.compile(r'(?<![а-яёa-z])' + p if not p.startswith(r'\b') else p, re.I) for p in v]
             for k, v in d.items()} for seg, d in SLOVAR.items()}
POROG = 4  # балл профиля для «профильного»; подбирается по ручной проверке (п. 6 отчёта)


def _cnt(rxs, text, cap=3):
    """Сколько разных маркеров встретилось (каждый максимум cap раз)."""
    n = 0
    for rx in rxs:
        n += min(len(rx.findall(text)), cap)
    return n


def profile_score(segment, title, h1, body):
    """Балл профиля: маркеры (+товары для экспорта/пищевых) по телу, title и H1 ×2,
    стоп-слова снимают по 2 за каждое."""
    r = _RX[segment]
    head = f'{title or ""} {h1 or ""}'.lower()
    body = (body or '').lower()
    s = _cnt(r['mark'], body) + 2 * _cnt(r['mark'], head, cap=1)
    if 'tovar' in r:
        t = _cnt(r['tovar'], body) + 2 * _cnt(r['tovar'], head, cap=1)
        if segment in ('exporters', 'food'):
            # экспорт без товара — таможня/логистика; «производство» без продукта — что угодно
            s = min(s, 2 * t) + t
        else:
            s += t
    s -= 2 * _cnt(r['stop'], f'{head} {body}', cap=1)
    return s


_PARK = re.compile(r'домен\w* (продаётся|продается|припаркован|зарегистрирован)|this domain (is|may be) for sale|'
                   r'domain is parked|buy this domain|parked free|reg\.ru.{0,40}(парковк|domain)|'
                   r'сайт (в разработке|находится в разработке)|under construction|coming soon|'
                   r'it works!|welcome to nginx|apache2? (ubuntu )?default page|index of /|'
                   r'hosting.{0,30}(успешно|has been) (создан|created)|default web site page', re.I)


def is_parked(status, html_text, visible_text):
    if status is None or status >= 400:
        return False  # «не живой» отдельно
    if _PARK.search(html_text[:20000] or ''):
        return True
    return len((visible_text or '').strip()) < 150


# --- ИНН / УНП --------------------------------------------------------------------------

def inn_ok(s):
    if not s.isdigit():
        return False
    d = [int(c) for c in s]
    if len(s) == 10:
        k = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return sum(a * b for a, b in zip(k, d)) % 11 % 10 == d[9]
    if len(s) == 12:
        k1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        k2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        return (sum(a * b for a, b in zip(k1, d)) % 11 % 10 == d[10]
                and sum(a * b for a, b in zip(k2, d)) % 11 % 10 == d[11])
    return False


def unp_ok(s):
    """УНП РБ: 9 цифр (юрлица/ИП). Контроль: веса 29,23,19,17,13,7,5,3 по mod 11;
    у первого знака-буквы (физлица) контроль не проверяем."""
    if not re.fullmatch(r'\d{9}', s):
        return False
    w = [29, 23, 19, 17, 13, 7, 5, 3]
    c = sum(int(a) * b for a, b in zip(s[:8], w)) % 11
    return c != 10 and c == int(s[8])


_INN_RX = re.compile(r'ИНН(?:\s*/\s*КПП)?\s*[:№]?\s*(\d{10}|\d{12})(?!\d)', re.I)
_UNP_RX = re.compile(r'(?:УНП|UNP)\s*[:№]?\s*(\d{9})(?!\d)', re.I)


def find_inn(text):
    """Первый ИНН с валидной контрольной суммой, стоящий сразу после слова «ИНН»
    (допуск «ИНН/КПП 1234567890/123401001»)."""
    seen = []
    for m in _INN_RX.finditer(text or ''):
        v = m.group(1)
        if inn_ok(v) and v not in seen:
            seen.append(v)
    return seen


def find_unp(text):
    seen = []
    for m in _UNP_RX.finditer(text or ''):
        v = m.group(1)
        if unp_ok(v) and v not in seen:
            seen.append(v)
    return seen


# --- статус «новое / старое» -------------------------------------------------------------

def status(domain, inns, known_domains, known_inns):
    if domain in known_domains:
        return 'old_domain'
    if not inns:
        return 'new_no_inn'
    if any(i in known_inns for i in inns):
        return 'old_inn'
    return 'new'


# --- агрегация выдачи --------------------------------------------------------------------

def aggregate(serp_rows, stop, post):
    """serp_rows: dict(engine, query, segment, subsegment, region, pos, url, title, snippet).
    → (кандидаты {домен: {...}}, воронка {(seg, engine): Counter}, отсеянные {домен: причина})."""
    cands = {}
    dropped = {}
    funnel = defaultdict(lambda: defaultdict(set))
    for r in serp_rows:
        key = (r['segment'], r['engine'])
        url = r.get('url') or ''
        dom = norm_domain(url)
        funnel[key]['urls'].add(url)
        if not dom:
            continue
        funnel[key]['domains'].add(dom)
        host = re.sub(r'^[a-z]+://', '', url.lower()).split('/', 1)[0]
        st = stop_type(host, stop) or stop_type(dom, stop)
        if st:
            dropped.setdefault(dom, 'stop:' + st)
            continue
        ph = post_hits(r['segment'], r.get('title'), url, post)
        c = cands.setdefault(dom, {'domain': dom, 'urls': set(), 'queries': set(), 'segments': set(),
                                   'subsegments': set(), 'subsegments_full': set(), 'regions': set(),
                                   'engines': set(), 'best_pos': 999, 'titles': [], 'post_hits': set(),
                                   'hits_by': defaultdict(set)})
        c['urls'].add(url)
        c['queries'].add(r['query'])
        c['segments'].add(r['segment'])
        c['subsegments'].add(r.get('subsegment') or '')
        c['subsegments_full'].add(f"{r['segment']}/{r.get('subsegment') or ''}")
        c['regions'].add(r.get('region') or '')
        c['engines'].add(r['engine'])
        c['hits_by'][r['engine']].add(r['segment'])
        c['best_pos'] = min(c['best_pos'], int(r.get('pos') or 999))
        if r.get('title') and len(c['titles']) < 3:
            c['titles'].append(r['title'])
        c['post_hits'].update(ph)
    port = {d for d, c in cands.items() if len(c['segments']) >= 5}
    for d in port:
        dropped[d] = 'portal'
        del cands[d]
    for key, f in funnel.items():
        f['after_stop'] = {d for d in f['domains'] if d in cands}
    return cands, funnel, dropped


# --- самопроверка ------------------------------------------------------------------------

def _test():
    assert norm_domain('https://WWW.Agro-Elevator.ru/contacts?x=1') == 'agro-elevator.ru'
    assert norm_domain('http://shop.kuban.ru/') == 'shop.kuban.ru'
    assert norm_domain('https://Зерно.рф/').endswith('.xn--p1ai')
    assert domain_unicode(norm_domain('https://зерно.рф/')) == 'зерно.рф'
    assert norm_domain('mail@Elevator-Altai.RU') == 'elevator-altai.ru'
    assert email_domain('ivanov@mail.ru') == '' and email_domain('a@hpp.ru') == 'hpp.ru'
    assert norm_domain('https://ferma.tilda.ws/') == 'ferma.tilda.ws'
    stop = {'pulscen.ru': 'doska', 'gov.ru': 'gos'}
    assert stop_type('voronezh.pulscen.ru', stop) == 'doska'
    assert stop_type('mcx.gov.ru', stop) == 'gos'
    assert stop_type('vk.com', stop) == 'socset' and stop_type('hpp-altai.ru', stop) == ''
    assert inn_ok('7707083893') and not inn_ok('7707083894')       # Сбербанк
    assert inn_ok('500100732259') and not inn_ok('500100732258')
    assert find_inn('Реквизиты: ИНН 7707083893, КПП 773601001') == ['7707083893']
    assert find_inn('ИНН/КПП 7707083893/773601001') == ['7707083893']
    assert find_inn('тел. 7707083893') == []                         # без слова «ИНН» не берём
    assert find_inn('ИНН 7707083894') == []                          # контрольная сумма
    assert unp_ok('100582333') and find_unp('УНП: 100582333') == ['100582333']
    assert not unp_ok('100582334')
    elev = profile_score('elevators', 'Элеватор Алтая — приёмка зерна', 'Элеватор',
                         'хранение зерна, сушка зерна, зерносушилки, силосы')
    teplo = profile_score('elevators', 'Элеваторный узел отопления', 'Элеваторный узел',
                          'элеваторный узел для ИТП, теплоснабжение')
    assert elev >= POROG > teplo, (elev, teplo)
    exp_ok = profile_score('exporters', 'Экспорт пшеницы и ячменя', '', 'экспорт FOB Новороссийск, пшеница')
    exp_bad = profile_score('exporters', 'Таможенный брокер', '', 'экспорт, ВЭД, таможенный брокер, логистическая компания')
    assert exp_ok >= POROG > exp_bad, (exp_ok, exp_bad)
    assert status('a.ru', [], {'a.ru'}, set()) == 'old_domain'
    assert status('b.ru', ['7707083893'], set(), {'7707083893'}) == 'old_inn'
    assert status('b.ru', ['7707083893'], set(), set()) == 'new'
    assert status('b.ru', [], set(), set()) == 'new_no_inn'
    assert is_parked(200, 'Этот домен продаётся', 'x' * 500)
    assert not is_parked(200, '<p>Элеватор</p>', 'Элеватор ' * 50)
    rows = [{'engine': 'yandex', 'query': 'q', 'segment': s, 'subsegment': '', 'region': '', 'pos': 1,
             'url': 'https://portal.ru/x', 'title': 't'} for s in SLOVAR]
    rows.append({'engine': 'google', 'query': 'q', 'segment': 'nuts', 'subsegment': 'фундук', 'region': 'К',
                 'pos': 3, 'url': 'https://fundук-sad.ru/', 'title': 'Фундук'})
    rows.append({'engine': 'google', 'query': 'q', 'segment': 'nuts', 'subsegment': '', 'region': '',
                 'pos': 1, 'url': 'https://www.vk.com/club1', 'title': 'x'})
    c, f, d = aggregate(rows, {}, {})
    assert 'portal.ru' not in c and d['portal.ru'] == 'portal' and d['vk.com'] == 'stop:socset'
    assert len(c) == 1
    print('ok: все проверки пройдены')


if __name__ == '__main__':
    if '--test' in sys.argv:
        _test()
