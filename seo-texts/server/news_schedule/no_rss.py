# -*- coding: utf-8 -*-
"""Обход доноров БЕЗ RSS (задача #49-б, п.2): лестница попыток на домен.

ЗАЧЕМ: 145 доноров (56%) не имеют объявленной RSS-ленты и вообще не опрашивались —
сигналы протухали (77 из 861 моложе 30 дней). Этот модуль даёт им регулярный опрос:

  (а) типовые RSS-пути (/rss, /feed, /rss.xml, /feed.xml) — лента часто ЕСТЬ,
      но не объявлена <link>-ом в HTML, поэтому автодискавери news_scan
      (rss_discover) её не увидел;
  (б) sitemap.xml (+ адреса из Sitemap: в robots.txt) — берём URL с lastmod,
      фильтруем свежие, заголовок достаём из самой страницы (h1/title);
  (в) типовые разделы /news, /novosti, /press, /press-centr — HTML-листинг,
      ссылки-заголовки + даты рядом с ними.

Что сработало — запоминается в donors.probe_method/probe_url (миграция —
schedule_db.migrate): следующий прогон идёт СРАЗУ рабочим способом, лестница не
повторяется. Рабочий способ сломался (редизайн/переезд) → честно передискаверим.

Вежливость (жёсткие правила задачи): robots.txt уважается (User-agent: *), пауза
между запросами ОДНОГО хоста >= 3с, таймауты, жёсткий кап страниц на донора.
Весь HTTP идёт через инжектируемую функцию фетча (по умолчанию news_scan._get) —
тесты подсовывают фикстуры и в интернет не ходят."""
import datetime as _dt
import os
import re
import sys
import time
import urllib.parse
import urllib.robotparser

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import news_scan as NS  # реюз: _get (фетч с обходом прокси/TLS-квирков), _rss_items, fresh
import schedule_db as SDB

def _без_www(host):
    """Снять префикс www. — именно ПРЕФИКС, а не набор символов.

    `.lstrip('www.')` принимает НАБОР символов и грызёт начало строки, пока
    встречает «w» или точку: «water-service.ru» превращался в
    «ater-service.ru», «wtc.ru» в «tc.ru», а «www.wwww.ru» вообще в «ru».
    Домен — ключ привязки и основа относительных ссылок, поэтому битый домен
    это либо обход по несуществующему хосту, либо принятая чужая страница.
    """
    return re.sub(r'^www\.', '', (host or '').lower())


# Лестница: порядок = от дешёвого (1 запрос, структурированный ответ) к дорогому.
RSS_PATHS = ('/rss', '/feed', '/rss.xml', '/feed.xml')
SECTIONS = ('/news', '/novosti', '/press', '/press-centr')

HOST_PAUSE = 3.0     # сек между запросами к ОДНОМУ хосту (требование задачи: >= 3с)
MAX_PAGES = 25       # кап HTTP-запросов на донора за прогон (лестница + статьи + robots)
MAX_ARTICLES = 8     # сколько страниц-статей максимум тянем ради заголовка (sitemap-путь)
FETCH_TIMEOUT = 15


# --------------------------------------------------------------- вежливый фетчер
class PoliteFetcher:
    """Вежливый HTTP-обёртка: robots.txt, пауза на хост, кап страниц, учёт
    «хост вообще отвечал» (различаем 'сайт лежит' и 'сайт жив, новостей нет').

    fetch — инжектируемая функция (url, timeout=..) -> str. По умолчанию
    news_scan._get: обход системного прокси + неверифицирующий TLS — региональные
    сайты часто за самоподписанными/Russian-Trusted-CA сертификатами (диагноз в
    news_scan). Исключение из fetch НЕ пробрасывается: один упавший запрос не
    должен ронять ни донора, ни прогон."""

    def __init__(self, fetch=None, host_pause=HOST_PAUSE, max_pages=MAX_PAGES,
                 timeout=FETCH_TIMEOUT):
        self.fetch = fetch or (lambda url, timeout=FETCH_TIMEOUT: NS._get(url, timeout=timeout, tries=1))
        self.host_pause = float(host_pause)
        self.max_pages = int(max_pages)
        self.timeout = timeout
        self._last = {}     # host -> monotonic-время последнего запроса (пауза)
        self._pages = {}    # host -> счётчик запросов (кап)
        self._robots = {}   # host -> (RobotFileParser|None, [sitemap-url, ...])
        self._alive = set()  # хосты, отдавшие хоть один непустой ответ

    def _wait(self, host):
        # >= host_pause между запросами одного хоста; разные хосты друг друга не ждут
        t = self._last.get(host)
        if t is not None:
            dt = self.host_pause - (time.monotonic() - t)
            if dt > 0:
                time.sleep(dt)
        self._last[host] = time.monotonic()

    def _raw(self, url):
        host = urllib.parse.urlsplit(url).netloc.lower()
        self._wait(host)
        self._pages[host] = self._pages.get(host, 0) + 1
        try:
            body = self.fetch(url, timeout=self.timeout) or ''
        except Exception:  # noqa: BLE001 — сбой одного запроса глотаем (устойчивость прогона)
            body = ''
        if body:
            self._alive.add(host)
        return body

    def robots(self, host):
        """robots.txt хоста (кэш на прогон): (парсер|None, [Sitemap-URL...]).
        Пустой/недоступный robots = разрешено всё — стандарт для краулеров."""
        if host not in self._robots:
            body = self._raw(f'https://{host}/robots.txt')
            rp, maps = None, []
            # HTML вместо robots (частый кейс: SPA отдаёт index на любой путь) — игнор
            if body and body.lstrip()[:1] != '<':
                rp = urllib.robotparser.RobotFileParser()
                try:
                    rp.parse(body.splitlines())
                except Exception:  # noqa: BLE001
                    rp = None
                maps = re.findall(r'(?im)^\s*sitemap:\s*(\S+)', body)
            self._robots[host] = (rp, maps)
        return self._robots[host]

    def sitemaps_from_robots(self, host):
        return list(self.robots(host)[1])

    def allowed(self, url):
        host = urllib.parse.urlsplit(url).netloc.lower()
        rp, _ = self.robots(host)
        if rp is None:
            return True
        try:
            return rp.can_fetch('*', url)
        except Exception:  # noqa: BLE001
            return True

    def host_alive(self, host):
        return host.lower() in self._alive

    def get(self, url):
        """GET с вежливостью. '' — если кап исчерпан, robots запретил или фетч не удался."""
        host = urllib.parse.urlsplit(url).netloc.lower()
        if self._pages.get(host, 0) >= self.max_pages:
            return ''
        if not self.allowed(url):
            return ''
        return self._raw(url)


# --------------------------------------------------------------- парсинг дат
# Русские месяцы: [:3] от родительного/именительного ('июля'->'июл'); 'мая'/'май'
# оба явно, чтобы не столкнуться с 'мар' (март).
_MONTHS = {'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'мая': 5, 'май': 5, 'июн': 6,
           'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12}
_D_DMY = re.compile(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b')
_D_YMD = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})')       # ловит и префикс ISO-datetime
_D_RU = re.compile(r'\b(\d{1,2})\s+([а-яА-ЯёЁ]{3,8})\.?\s+(\d{4})')
_D_TIME_TAG = re.compile(r'<time[^>]+datetime=["\']([^"\']+)', re.I)


def _mk(y, mo, d):
    try:
        # полдень — чтобы граница «N дней назад» не дёргалась от таймзоны сайта
        return _dt.datetime(y, mo, d, 12, 0).timestamp()
    except Exception:  # noqa: BLE001 — мусорная дата (32.13.2026) = «даты нет»
        return None


def parse_date(text):
    """Первая распознанная дата в тексте -> epoch; None — даты нет.
    Форматы: 21.07.2026 | 2026-07-21(T...) | 21 июля 2026."""
    text = text or ''
    m = _D_DMY.search(text)
    if m:
        return _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = _D_YMD.search(text)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _D_RU.search(text)
    if m:
        mo = _MONTHS.get(m.group(2).lower()[:3])
        if mo:
            return _mk(int(m.group(3)), mo, int(m.group(1)))
    return None


# --------------------------------------------------------------- листинг (в)
_A_RE = re.compile(r'<a\b[^>]*?href=["\']([^"\'#>]+)["\'][^>]*>(.*?)</a>', re.S | re.I)
_TAG_RE = re.compile(r'<[^>]+>')
# файлы/медиа — не новости, не тратим на них ни запросы, ни провайдера
_SKIP_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.pdf', '.doc',
             '.docx', '.xls', '.xlsx', '.zip', '.rar', '.mp4')


def parse_listing(html, base_url, days=None, min_title=20, ctx=200):
    """HTML-листинг раздела новостей -> [{'title','link','pubDate','date_ts'}].

    Эвристика без DOM-парсера (server/ — stdlib-only): новость = <a> с достаточно
    длинным текстом (короткие «Подробнее»/пункты меню отсеиваются) на ТОМ ЖЕ хосте
    (чужой хост = баннер/репост). Дата ищется рядом со ссылкой: сперва <time
    datetime=...>, затем текстовые форматы; окно поиска обрезается соседними <a>,
    чтобы не утащить дату чужой новости. Без даты ссылку НЕ выбрасываем — «свежесть
    неизвестна» трактуем как свежее (тот же принцип, что news_scan.fresh при
    непарсибельном pubDate); одноразовость гарантирует дедуп seen_news.
    days=None — вернуть всё с date_ts (фильтрует вызывающий)."""
    html = html or ''
    host = _без_www(urllib.parse.urlsplit(base_url).netloc)
    cutoff = (time.time() - days * 86400) if days else None
    matches = list(_A_RE.finditer(html))
    out, seen_links = [], set()
    for i, m in enumerate(matches):
        href = m.group(1).strip()
        title = re.sub(r'\s+', ' ', _TAG_RE.sub(' ', m.group(2))).strip()
        if len(title) < min_title:
            continue
        if any(href.lower().endswith(e) for e in _SKIP_EXT):
            continue
        link = urllib.parse.urljoin(base_url, href)
        lp = urllib.parse.urlsplit(link)
        if lp.scheme not in ('http', 'https') or _без_www(lp.netloc) != host:
            continue
        if link in seen_links:
            continue
        seen_links.add(link)
        # окно поиска даты: ±ctx символов, но не дальше соседних <a> — иначе дата
        # соседней новости «прилипнет» к этой
        lo = max(0, m.start() - ctx)
        if i > 0:
            lo = max(lo, matches[i - 1].end())
        hi = min(len(html), m.end() + ctx)
        if i + 1 < len(matches):
            hi = min(hi, matches[i + 1].start())
        window = html[lo:hi]
        ts = None
        tm = _D_TIME_TAG.search(window)
        if tm:
            ts = parse_date(tm.group(1))
        if ts is None:
            ts = parse_date(_TAG_RE.sub(' ', window))
        if cutoff is not None and ts is not None and ts < cutoff:
            continue          # датированное старьё — не тащим в конвейер
        out.append({'title': title[:200], 'link': link,
                    'pubDate': (time.strftime('%Y-%m-%d', time.localtime(ts)) if ts else ''),
                    'date_ts': ts})
    return out


# --------------------------------------------------------------- sitemap (б)
_SM_BLOCK = re.compile(r'<(url|sitemap)>(.*?)</\1>', re.S | re.I)
_SM_LOC = re.compile(r'<loc>\s*(.*?)\s*</loc>', re.S | re.I)
_SM_LASTMOD = re.compile(r'<lastmod>\s*(.*?)\s*</lastmod>', re.S | re.I)
_H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S | re.I)
_TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.S | re.I)


def parse_sitemap(xml):
    """sitemap -> ('index', [url,...]) для sitemapindex,
    ('urlset', [(loc, lastmod_epoch|None),...]) для карты страниц,
    ('', []) — это вообще не sitemap."""
    xml = xml or ''
    if '<urlset' not in xml and '<sitemapindex' not in xml:
        return ('', [])
    kind = 'index' if '<sitemapindex' in xml else 'urlset'
    out = []
    for m in _SM_BLOCK.finditer(xml):
        blk = m.group(2)
        lm = _SM_LOC.search(blk)
        if not lm:
            continue
        if kind == 'index':
            out.append(lm.group(1))
        else:
            d = _SM_LASTMOD.search(blk)
            out.append((lm.group(1), parse_date(d.group(1)) if d else None))
    return (kind, out)


def _title_of(html):
    """Заголовок статьи: h1 надёжнее (title часто «Новость — Сайт — Регион»)."""
    for rx in (_H1_RE, _TITLE_RE):
        m = rx.search(html or '')
        if m:
            t = re.sub(r'\s+', ' ', _TAG_RE.sub(' ', m.group(1))).strip()
            if t:
                return t[:200]
    return ''


def _sitemap_items(fetcher, sm_url, days, max_articles):
    """sitemap -> свежие URL по lastmod -> заголовки из самих страниц.
    None = способ нерабочий (нет карты / без дат) — НЕ запоминаем его.
    Даты обязательны: без lastmod свежее от архива не отличить, а тянуть сотни
    страниц вслепую — дорого и невежливо. [] = способ рабочий, новостей нет."""
    cutoff = time.time() - days * 86400
    kind, entries = parse_sitemap(fetcher.get(sm_url))
    if not kind:
        return None
    if kind == 'urlset':
        pages = entries
    else:
        # у индекса берём немного дочерних карт: сперва с news/post в имени
        # (обычно именно они несут статьи), затем остальные
        childs = sorted(entries, key=lambda u: (('news' not in u and 'post' not in u), u))
        pages = []
        for cu in childs[:3]:
            k2, e2 = parse_sitemap(fetcher.get(cu))
            if k2 == 'urlset':
                pages += e2
    dated = False
    fresh = []
    for loc, ts in pages:
        if ts is not None:
            dated = True
            if ts >= cutoff:
                fresh.append((loc, ts))
    if not dated:
        return None
    items = []
    # свежайшие первыми; кап статей — это доп. запросы к хосту (кап страниц фетчера
    # всё равно страхует сверху)
    for loc, ts in sorted(fresh, key=lambda t: -t[1])[:max_articles]:
        title = _title_of(fetcher.get(loc))
        if not title:
            continue
        items.append({'title': title, 'link': loc,
                      'pubDate': time.strftime('%Y-%m-%d', time.localtime(ts)),
                      'date_ts': ts})
    return items


# --------------------------------------------------------------- RSS-путь (а)
def _items_from_rss(body, days):
    """Тело ленты -> (лента валидна?, [items]). Парсер и правило свежести — реюз
    news_scan (_rss_items / fresh: непарсибельный pubDate = свежий).
    «Валидна» = структура распарсилась хотя бы в один item: только тогда путь
    можно запоминать как рабочий."""
    if not body or not re.search(r'<(rss|feed|channel)\b', body[:4000], re.I):
        return False, []
    raw = NS._rss_items(body)
    items = [{'title': it['title'][:200], 'link': it['link'],
              'pubDate': it.get('pubDate', ''), 'date_ts': None}
             for it in raw
             if it.get('title') and it.get('link') and NS.fresh(it.get('pubDate', ''), days)]
    return bool(raw), items


# --------------------------------------------------------------- лестница
def probe_ladder(fetcher, domain, days, max_articles=MAX_ARTICLES):
    """Полная лестница по домену. Возврат (method, url, items);
    method: 'rss-path' | 'sitemap' | 'listing' | 'none'."""
    base = f'https://{domain}'
    # (а) необъявленные типовые RSS-пути — самый дешёвый и структурированный источник
    for p in RSS_PATHS:
        ok, items = _items_from_rss(fetcher.get(base + p), days)
        if ok:
            return ('rss-path', base + p, items)
    # (б) sitemap с датами; robots.txt может объявить точный адрес — он приоритетнее
    host = urllib.parse.urlsplit(base).netloc.lower()
    for sm in (fetcher.sitemaps_from_robots(host) + [base + '/sitemap.xml'])[:3]:
        items = _sitemap_items(fetcher, sm, days, max_articles)
        if items is not None:
            return ('sitemap', sm, items)
    # (в) типовые разделы новостей — HTML-листинг с датами
    for s in SECTIONS:
        body = fetcher.get(base + s)
        if not body:
            continue
        raw_all = parse_listing(body, base + s, days=None)
        # «раздел рабочий» = есть хотя бы пара заголовков-ссылок; одиночная ссылка —
        # скорее заглушка/редирект, такое запоминать как метод нельзя
        if len(raw_all) >= 2:
            cutoff = time.time() - days * 86400
            return ('listing', base + s,
                    [it for it in raw_all if it['date_ts'] is None or it['date_ts'] >= cutoff])
    return ('none', '', [])


def poll_known(fetcher, method, url, days, max_articles=MAX_ARTICLES):
    """Опрос УЖЕ известным рабочим способом (быстрый путь без лестницы).
    None = способ сломался — вызывающий уходит на полную лестницу."""
    if method == 'rss-path':
        ok, items = _items_from_rss(fetcher.get(url), days)
        return items if ok else None
    if method == 'sitemap':
        return _sitemap_items(fetcher, url, days, max_articles)
    if method == 'listing':
        body = fetcher.get(url)
        if not body:
            return None
        raw_all = parse_listing(body, url, days=None)
        if len(raw_all) < 2:
            return None
        cutoff = time.time() - days * 86400
        return [it for it in raw_all if it['date_ts'] is None or it['date_ts'] >= cutoff]
    return None


def poll_donor(db, row, fetcher, days, max_articles=MAX_ARTICLES):
    """Полный опрос донора без объявленного RSS: сперва запомненный probe_method,
    при его поломке — лестница заново; результат лестницы фиксируется durable
    (donors.probe_method/probe_url/probed_at через schedule_db).

    Возврат (items, err):
      err=''          — успех (пусть даже 0 новостей);
      err='fetch'     — хост не отдал ни байта (сайт лежит) -> fail_streak у вызывающего;
      err='no-source' — сайт жив, но источник новостей не найден (НЕ ошибка
                        доступности: fail_streak не растёт, лестница повторится
                        через none_retry_days)."""
    domain = row['domain']
    method = (row.get('probe_method') or '').strip()
    url = (row.get('probe_url') or '').strip()
    if method in ('rss-path', 'sitemap', 'listing') and url:
        items = poll_known(fetcher, method, url, days, max_articles)
        if items is not None:
            return items, ''
        # рабочий способ сломался (редизайн/переезд) — передискавери всей лестницей
    method, url, items = probe_ladder(fetcher, domain, days, max_articles)
    SDB.set_probe(db, domain, method, url)
    if method != 'none':
        return items, ''
    return [], ('no-source' if fetcher.host_alive(domain) else 'fetch')
