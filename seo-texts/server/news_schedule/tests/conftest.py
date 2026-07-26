# -*- coding: utf-8 -*-
"""Обвязка тестов регулярного news-скана (#49-б, п.5).

ЖЁСТКОЕ ПРАВИЛО ЗАДАЧИ: тесты ОФЛАЙН — ни боевого сервера, ни интернета. Весь HTTP
заменён FakeWeb (фикстуры по URL), провайдер/dadata — монкипатчами news_scan
(news_cron зовёт их через атрибуты модуля NS.* именно ради патчабельности)."""
import os
import sys
import time

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)            # news_schedule/ (наши модули)
_SRV = os.path.dirname(_PKG)             # server/ (news_scan, enrich_db)
for _p in (_PKG, _SRV):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FIXTURES = os.path.join(_HERE, 'fixtures')


def _stamp(days_ago, fmt):
    return time.strftime(fmt, time.localtime(time.time() - days_ago * 86400))


def render_fixture(name):
    """Фикстура с датами-плейсхолдерами. Литеральные даты в файлах нельзя:
    «свежесть» относительна моменту прогона тестов — литералы протухли бы через
    месяц и тесты бы тихо позеленели/покраснели. @FRESH_*@ = 2 дня назад,
    @OLD_*@ = 400 дней назад (заведомо за любым разумным окном)."""
    txt = open(os.path.join(FIXTURES, name), encoding='utf-8').read()
    subs = {
        '@FRESH_DMY@': _stamp(2, '%d.%m.%Y'),
        '@OLD_DMY@': _stamp(400, '%d.%m.%Y'),
        '@FRESH_YMD@': _stamp(2, '%Y-%m-%d'),
        '@OLD_YMD@': _stamp(400, '%Y-%m-%d'),
        # RFC2822 для pubDate RSS: %a/%b дают английские имена в C-локали тестов —
        # именно их ждёт email.utils.parsedate (news_scan.fresh)
        '@FRESH_RFC@': _stamp(2, '%a, %d %b %Y 10:00:00 +0300'),
        '@OLD_RFC@': _stamp(400, '%a, %d %b %Y 10:00:00 +0300'),
    }
    for k, v in subs.items():
        txt = txt.replace(k, v)
    return txt


class FakeWeb:
    """Фейковый интернет: url -> тело ответа. Ведёт журнал запросов — тесты
    проверяют, КУДА ходили и сколько (запоминание метода, robots, кап страниц).
    Значение-исключение по URL — бросается (тест устойчивости к падению)."""

    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.log = []

    def __call__(self, url, timeout=15):
        self.log.append(url)
        body = self.pages.get(url, '')
        if isinstance(body, Exception):
            raise body
        return body

    def count(self, substr):
        return sum(1 for u in self.log if substr in u)


@pytest.fixture
def fakeweb():
    return FakeWeb


@pytest.fixture
def db(tmp_path):
    """Свежая enrich.db во временном каталоге + наши миграции."""
    import enrich_db as EDB
    import schedule_db as SDB
    d = EDB.EnrichDB(str(tmp_path / 'enrich.db'))
    SDB.migrate(d)
    return d


@pytest.fixture
def opts_factory(tmp_path):
    """Опции news_cron через его же argparse (тест видит те же дефолты, что боевой
    запуск), но с нулевой паузой и БД/jsonl во временном каталоге."""
    import news_cron

    def make(**over):
        opts = news_cron.build_parser().parse_args([
            '--db', str(tmp_path / 'enrich.db'),
            '--pause', '0',
            '--jsonl', str(tmp_path / 'stream.jsonl'),
        ])
        for k, v in over.items():
            setattr(opts, k, v)
        return opts
    return make
