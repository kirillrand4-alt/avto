# -*- coding: utf-8 -*-
"""Тесты лестницы no_rss (#49-б, п.5): парсинг листинга/карты, выбор рабочего
способа и его запоминание, robots.txt, кап страниц. Всё офлайн, на фикстурах."""
import no_rss
from conftest import FakeWeb, render_fixture


# --------------------------------------------------------------- парсинг листинга
def test_parse_listing_dates():
    html = render_fixture('listing.html')
    items = no_rss.parse_listing(html, 'https://vestnik-primer.ru/news', days=30)
    links = [i['link'] for i in items]
    # свежие датированные — есть (обычная дата и <time datetime>)
    assert 'https://vestnik-primer.ru/news/zavod-zapusk' in links
    assert 'https://vestnik-primer.ru/news/moloko-modern' in links
    # без даты = «свежесть неизвестна» → не выбрасываем (одноразовость даст seen_news)
    assert 'https://vestnik-primer.ru/news/bez-daty' in links
    # датированное старьё отфильтровано
    assert all('staraya' not in l for l in links)
    # чужой хост (баннер/реклама) отброшен
    assert all('other-site' not in l for l in links)
    # короткие ссылки («Читать», меню) не считаются новостями
    assert len(items) == 3


def test_parse_listing_relative_links_absolutized():
    html = render_fixture('listing.html')
    items = no_rss.parse_listing(html, 'https://vestnik-primer.ru/news', days=30)
    assert all(i['link'].startswith('https://vestnik-primer.ru/') for i in items)


# --------------------------------------------------------------- парсинг sitemap
def test_parse_sitemap_urlset_and_dates():
    kind, entries = no_rss.parse_sitemap(render_fixture('sitemap.xml'))
    assert kind == 'urlset'
    by_loc = {loc: ts for loc, ts in entries}
    assert by_loc['https://zavod-primer.ru/news/novaya-liniya'] is not None
    assert by_loc['https://zavod-primer.ru/about'] is None          # без lastmod
    assert len(entries) == 3


def test_parse_sitemap_index_detected():
    kind, entries = no_rss.parse_sitemap(render_fixture('sitemap_index.xml'))
    assert kind == 'index'
    assert 'https://zavod-primer.ru/sitemap-news.xml' in entries


# --------------------------------------------------------------- лестница: выбор метода
def test_ladder_finds_undeclared_rss_path():
    fake = FakeWeb({'https://rss-primer.ru/rss.xml': render_fixture('rss.xml')})
    f = no_rss.PoliteFetcher(fetch=fake, host_pause=0)
    method, url, items = no_rss.probe_ladder(f, 'rss-primer.ru', days=30)
    assert method == 'rss-path'
    assert url == 'https://rss-primer.ru/rss.xml'
    # 2 свежих из 3 (старый отсеян по pubDate); «погоду» здесь НЕ фильтруем —
    # капекс-предфильтр живёт выше, в news_cron
    assert len(items) == 2


def test_ladder_sitemap_with_dates_and_titles():
    fake = FakeWeb({
        'https://zavod-primer.ru/sitemap.xml': render_fixture('sitemap.xml'),
        'https://zavod-primer.ru/news/novaya-liniya': render_fixture('article.html'),
    })
    f = no_rss.PoliteFetcher(fetch=fake, host_pause=0)
    method, url, items = no_rss.probe_ladder(f, 'zavod-primer.ru', days=30)
    assert method == 'sitemap'
    assert len(items) == 1
    assert 'порошковой окраски' in items[0]['title']      # заголовок взят из h1 статьи
    assert fake.count('arhiv-2020') == 0                   # старьё из карты не тянули


def test_ladder_sitemap_index_prefers_news_child():
    fake = FakeWeb({
        'https://zavod-primer.ru/sitemap.xml': render_fixture('sitemap_index.xml'),
        'https://zavod-primer.ru/sitemap-news.xml': render_fixture('sitemap.xml'),
        'https://zavod-primer.ru/news/novaya-liniya': render_fixture('article.html'),
    })
    f = no_rss.PoliteFetcher(fetch=fake, host_pause=0)
    method, url, items = no_rss.probe_ladder(f, 'zavod-primer.ru', days=30)
    assert method == 'sitemap'
    assert len(items) == 1


def test_ladder_falls_to_listing(db):
    fake = FakeWeb({'https://vestnik-primer.ru/news': render_fixture('listing.html')})
    f = no_rss.PoliteFetcher(fetch=fake, host_pause=0)
    method, url, items = no_rss.probe_ladder(f, 'vestnik-primer.ru', days=30)
    assert method == 'listing'
    assert url == 'https://vestnik-primer.ru/news'
    assert len(items) == 3


# --------------------------------------------------------------- запоминание метода
def test_poll_donor_memorizes_method_and_reuses(db):
    db.add_donor('vestnik-primer.ru', status='no-rss')
    pages = {'https://vestnik-primer.ru/news': render_fixture('listing.html')}

    fake1 = FakeWeb(pages)
    row = {'domain': 'vestnik-primer.ru', 'probe_method': '', 'probe_url': ''}
    items, err = no_rss.poll_donor(db, row, no_rss.PoliteFetcher(fetch=fake1, host_pause=0), days=30)
    assert err == '' and len(items) == 3
    # первая попытка шла лестницей: RSS-пути были опробованы
    assert fake1.count('/rss') > 0
    pm, pu = db.cx.execute(
        "SELECT probe_method, probe_url FROM donors WHERE domain='vestnik-primer.ru'").fetchone()
    assert pm == 'listing' and pu == 'https://vestnik-primer.ru/news'

    # второй прогон: читаем запомненный способ из БД — лестница НЕ повторяется
    fake2 = FakeWeb(pages)
    row2 = {'domain': 'vestnik-primer.ru', 'probe_method': pm, 'probe_url': pu}
    items2, err2 = no_rss.poll_donor(db, row2, no_rss.PoliteFetcher(fetch=fake2, host_pause=0), days=30)
    assert err2 == '' and len(items2) == 3
    assert fake2.count('/rss') == 0
    assert fake2.count('sitemap') == 0


def test_poll_donor_dead_site_reports_fetch_error(db):
    db.add_donor('dead-primer.ru', status='no-rss')
    fake = FakeWeb({})   # сайт не отдаёт ни байта
    row = {'domain': 'dead-primer.ru', 'probe_method': '', 'probe_url': ''}
    items, err = no_rss.poll_donor(db, row, no_rss.PoliteFetcher(fetch=fake, host_pause=0), days=30)
    assert items == [] and err == 'fetch'


def test_poll_donor_alive_but_no_source(db):
    # сайт жив (robots отвечает), но ни ленты, ни карты, ни раздела новостей
    db.add_donor('alive-primer.ru', status='no-rss')
    fake = FakeWeb({'https://alive-primer.ru/robots.txt': 'User-agent: *\nAllow: /\n'})
    row = {'domain': 'alive-primer.ru', 'probe_method': '', 'probe_url': ''}
    items, err = no_rss.poll_donor(db, row, no_rss.PoliteFetcher(fetch=fake, host_pause=0), days=30)
    assert items == [] and err == 'no-source'
    pm = db.cx.execute("SELECT probe_method FROM donors WHERE domain='alive-primer.ru'").fetchone()[0]
    assert pm == 'none'


# --------------------------------------------------------------- вежливость
def test_robots_disallow_respected():
    fake = FakeWeb({
        'https://blocked-primer.ru/robots.txt': render_fixture('robots_block.txt'),
        # раздел существует, но robots его запрещает — трогать нельзя
        'https://blocked-primer.ru/press': render_fixture('listing.html'),
    })
    f = no_rss.PoliteFetcher(fetch=fake, host_pause=0)
    method, url, items = no_rss.probe_ladder(f, 'blocked-primer.ru', days=30)
    assert method == 'none'
    # ни одного запроса к запрещённым путям (Disallow: /press кроет и /press-centr)
    assert not any(u.rstrip('/').endswith('/press') for u in fake.log)
    assert not any('/press-centr' in u for u in fake.log)


def test_page_cap_limits_requests():
    fake = FakeWeb({})
    f = no_rss.PoliteFetcher(fetch=fake, host_pause=0, max_pages=3)
    for i in range(6):
        f.get(f'https://cap-primer.ru/page{i}')
    # robots.txt + 2 страницы = кап 3; остальные запросы не ушли в сеть
    assert len(fake.log) == 3
