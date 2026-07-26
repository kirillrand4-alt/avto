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
