# -*- coding: utf-8 -*-
"""Общие фикстуры: временная enrich.db с таблицами обогащения (как их создаёт
enrich_db.py на сервере), фейковый дроп и приложение с тестовым окружением.

Env выставляется ДО импорта модулей панели, потому что create_app()/PanelDB
читают его в момент вызова — каждая фикстура даёт себе чистую БД и каталоги."""
import os
import sqlite3
import sys

import pytest

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DIR)
# sender/company_card.py — настоящий билдер индекса обзвона: фикстура строит
# тестовый obzvon-index.db ИМ ЖЕ, а не копией схемы, которая молча разъедется
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(DIR)), 'sender'))

# минимальная копия таблиц обогащения из enrich_db._SCHEMA: панель их ЧИТАЕТ,
# создавать в боевой БД не должна — поэтому в тестах создаём сами
ENRICH_TABLES = """
CREATE TABLE IF NOT EXISTS companies(
  inn TEXT PRIMARY KEY, name TEXT, division TEXT, okved TEXT, region TEXT, pxr REAL,
  site TEXT, cand_site TEXT, activity TEXT, is_competitor INTEGER DEFAULT 0, verified TEXT,
  best_email TEXT, phones TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS emails(
  inn TEXT, email TEXT, role TEXT, person TEXT, mx_ok INTEGER, source TEXT,
  source_url TEXT, updated_at TEXT, UNIQUE(inn, email));
CREATE TABLE IF NOT EXISTS stage_log(
  inn TEXT, stage TEXT, detail TEXT, ts TEXT, UNIQUE(inn, stage));
"""


@pytest.fixture
def env_db(tmp_path, monkeypatch):
    """Чистая временная enrich.db + каталог загрузок; env как у боевой службы."""
    db_path = str(tmp_path / 'enrich.db')
    cx = sqlite3.connect(db_path)
    cx.executescript(ENRICH_TABLES)
    cx.commit()
    cx.close()
    monkeypatch.setenv('ENRICH_DB', db_path)
    monkeypatch.setenv('ENRICH_UPLOADS', str(tmp_path / 'uploads'))
    monkeypatch.setenv('ENRICH_ROOT_PATH', '')     # тесты ходят без префикса /enrich
    monkeypatch.setenv('RUNNER_ENV', str(tmp_path / 'no-such.env'))  # ключницу не читаем
    monkeypatch.setenv('DROP_URL', 'http://drop.invalid')  # реальный дроп недостижим
    monkeypatch.setenv('DROP_TOKEN', 'test-token')
    monkeypatch.setenv('JOB_SECRET', 'test-secret')
    return db_path


@pytest.fixture
def pdb(env_db):
    import panel_core as core
    d = core.PanelDB(env_db)
    yield d
    d.close()


class FakeDrop:
    """Дроп в памяти: панель кладёт job-файлы, тест проверяет что и сколько."""

    def __init__(self):
        self.files = {}

    def list(self):
        return [{'name': n, 'bytes': len(b), 'mtime': 0} for n, b in self.files.items()]

    def up(self, name, blob):
        self.files[name] = blob

    def down(self, name):
        return self.files[name]

    def delete(self, name):
        self.files.pop(name, None)


@pytest.fixture
def drop():
    return FakeDrop()


@pytest.fixture
def client(env_db, monkeypatch):
    """TestClient поверх create_app() с Basic-auth пользователем kir:secret."""
    monkeypatch.setenv('ENRICH_USERS', 'kir:secret')
    from fastapi.testclient import TestClient
    import enrich_panel
    return TestClient(enrich_panel.create_app())


def mark_stage(db_path, inn, stage, detail=''):
    """Пишем стадию так же, как enrich_db.mark_stage (успех = строка в stage_log)."""
    cx = sqlite3.connect(db_path)
    cx.execute('INSERT INTO stage_log(inn, stage, detail, ts) VALUES(?,?,?,?) '
               'ON CONFLICT(inn, stage) DO UPDATE SET detail=excluded.detail',
               (str(inn), stage, detail, '2026-07-26T00:00:00'))
    cx.commit()
    cx.close()


# ---------------------------------------------------------------------------
# Индекс базы обзвона для страницы «База» (тестовый, но настоящим билдером)
# ---------------------------------------------------------------------------

def _ob(inn, name, base='Компрессор Центр', region='', rev_rub='', rev='',
        emails='', site_emails='', sites='', ogrn=''):
    """Строка CSV базы обзвона по именам колонок выгрузки (36 колонок; остальные
    пустые — build_obzvon_index требует лишь наличия заголовков)."""
    return {'ИНН': inn, 'Краткое': name, 'База': base, 'Регион': region,
            'Выручка, руб.': rev_rub, 'Выручка': rev, 'Emails': emails,
            'Email с сайта': site_emails, 'Сайты': sites, 'ОГРН': ogrn}


# Порядок строк = «порядок базы» (тесты хвоста на него опираются).
# Выручка в диапазоне 100-150 млн: 0002 (100), 0003 (120), 0004 (150 —
# ЧЕЛОВЕКОЧИТАЕМОЙ строкой, проверка фолбэка), 0008 (130).
OBZVON_ROWS = [
    _ob('7700000001', 'ООО Альфа', region='Москва', rev_rub='50 000 000',
        emails='info@alfa.ru', sites='alfa.ru', ogrn='1077700000001'),
    _ob('7700000002', 'ООО Бета', region='Москва', rev_rub='100 000 000',
        emails='info@beta.ru', ogrn='1077700000002'),
    _ob('7700000003', 'ООО Гамма', base='Meyer', region='Санкт-Петербург',
        rev_rub='120 000 000', sites='gamma.ru', ogrn='1077700000003'),
    _ob('7700000004', 'ООО Дельта', region='Московская область',
        rev='150 млн руб.', ogrn='1077700000004'),
    _ob('7700000005', 'ООО Эпсилон', base='Meyer', region='Казань',
        rev_rub='200 000 000', emails='op@eps.ru', ogrn='1077700000005'),
    _ob('7700000006', 'ООО Дзета', region='Новосибирск', rev='1,5 млрд руб.',
        sites='dzeta.ru', ogrn='1077700000006'),
    _ob('7700000007', 'ООО Эта', region='Москва', ogrn='1077700000007'),
    _ob('7700000008', 'ООО Тета', base='Meyer', region='Москва',
        rev_rub='130 000 000', emails='sale@teta.ru', sites='teta.ru',
        ogrn='1077700000008'),
    _ob('7700000009', 'Хвост-1', region='Пермь', rev_rub='10 000 000'),
    _ob('7700000010', 'Хвост-2', region='Пермь', rev_rub='11 000 000',
        emails='mail@tail2.ru'),
    _ob('7700000011', 'Хвост-3', region='Пермь', rev_rub='12 000 000'),
    _ob('7700000012', 'Хвост-4', base='Meyer', region='Пермь',
        rev_rub='13 000 000'),
]


def make_obzvon_index(db_path, rows):
    """Собрать тестовый obzvon-index.db настоящим company_card.build_obzvon_index:
    гарантия «та же схема, что на сервере» (задача требует фикстуру по схеме
    company_card, и надёжнее всего — сам билдер)."""
    import company_card as cc
    header = list(cc._CSV_TO_INDEX.keys())
    lines = [';'.join(header)]
    for r in rows:
        rec = {h: '' for h in header}
        rec.update(r)
        lines.append(';'.join(str(rec[h]) for h in header))
    cc.build_obzvon_index(iter(lines), db_path)


@pytest.fixture
def obzvon_db(tmp_path, monkeypatch):
    """Тестовый индекс обзвона + env OBZVON_INDEX (панель читает его per-request)."""
    path = str(tmp_path / 'obzvon-index.db')
    make_obzvon_index(path, OBZVON_ROWS)
    monkeypatch.setenv('OBZVON_INDEX', path)
    return path


@pytest.fixture
def webdrop(monkeypatch, drop):
    """Подмена DropClient панели на дроп в памяти — веб-тесты постановки заданий
    проверяют job-файлы, не выходя в сеть."""
    import panel_core as core
    monkeypatch.setattr(core, 'DropClient', lambda *a, **k: drop)
    return drop
