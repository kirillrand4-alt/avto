# -*- coding: utf-8 -*-
"""Прогресс прогона считается ТОЛЬКО по stage_log (канон владельца): проверяем
подсчёт стадий, отбор недоделанных и выгрузку CSV-данных."""
import sqlite3

from conftest import mark_stage

ROWS = [{'inn': '7701234567', 'name': 'А'},
        {'inn': '7701234568', 'name': 'Б'},
        {'inn': '500100732259', 'name': 'В'}]


def _mkrun(pdb):
    return pdb.create_run('t.csv', 'run1.csv', ROWS,
                          {'accepted': 3, 'rejected': [], 'rejected_total': 0})


def test_stage_counts_only_run_rows(pdb, env_db):
    run_id = _mkrun(pdb)
    mark_stage(env_db, '7701234567', 'site', 'x.ru')
    mark_stage(env_db, '7701234568', 'site', 'y.ru')
    mark_stage(env_db, '7701234568', 'email', '2 шт')
    mark_stage(env_db, '9999999999', 'site', 'чужой ИНН — не наш прогон')
    counts = pdb.stage_counts(run_id)
    assert counts == {'site': 2, 'email': 1}


def test_missing_rows_any_done_stage_counts_as_done(pdb, env_db):
    run_id = _mkrun(pdb)
    # base «сделан», если есть ЛЮБАЯ из site/site_cand/email
    mark_stage(env_db, '7701234567', 'site')
    mark_stage(env_db, '7701234568', 'email')
    missing = pdb.missing_rows(run_id, ('site', 'site_cand', 'email'))
    assert [r['inn'] for r in missing] == ['500100732259']


def test_missing_rows_survives_restart(env_db, pdb):
    """Рестарт панели = новое соединение; картина прогресса не должна меняться."""
    import panel_core as core
    run_id = _mkrun(pdb)
    mark_stage(env_db, '7701234567', 'etp')
    pdb.close()
    pdb2 = core.PanelDB(env_db)
    try:
        missing = pdb2.missing_rows(run_id, ('etp',))
        assert len(missing) == 2
        assert pdb2.stage_counts(run_id) == {'etp': 1}
    finally:
        pdb2.close()


def test_export_rows_joins_company_email_and_stages(pdb, env_db):
    run_id = _mkrun(pdb)
    cx = sqlite3.connect(env_db)
    cx.execute("INSERT INTO companies(inn, name, site, best_email, phones, updated_at) "
               "VALUES('7701234567', 'ООО А', 'a.ru', 'zakup@a.ru', "
               "'[\"+7 495 000-00-00\"]', '2026-07-26')")
    cx.execute("INSERT INTO emails(inn, email, role, person) "
               "VALUES('7701234567', 'zakup@a.ru', 'снабжение/закупки', 'Иванов')")
    cx.commit()
    cx.close()
    mark_stage(env_db, '7701234567', 'site')
    mark_stage(env_db, '7701234567', 'email')
    rows = pdb.export_rows(run_id)
    assert len(rows) == 3                       # ВСЕ строки прогона, даже пустые
    r = rows[0]
    assert r['site'] == 'a.ru'
    assert r['best_email'] == 'zakup@a.ru'
    assert r['role'] == 'снабжение/закупки'     # роль именно лучшего адреса
    assert r['phones'] == '+7 495 000-00-00'    # JSON-список -> строка
    assert set(r['stages'].split(',')) == {'site', 'email'}
    # необогащённая строка выгружается с исходным названием и пустыми полями
    assert rows[2]['name'] == 'В' and rows[2]['site'] == ''


def test_latest_results_role_of_best_email(pdb, env_db):
    run_id = _mkrun(pdb)
    cx = sqlite3.connect(env_db)
    cx.execute("INSERT INTO companies(inn, name, site, best_email, updated_at) "
               "VALUES('7701234568', 'ООО Б', 'b.ru', 'best@b.ru', '2026-07-26')")
    cx.execute("INSERT INTO emails(inn, email, role, person) "
               "VALUES('7701234568', 'info@b.ru', 'приёмная', '')")
    cx.execute("INSERT INTO emails(inn, email, role, person) "
               "VALUES('7701234568', 'best@b.ru', 'директор', 'Петров')")
    cx.commit()
    cx.close()
    res = pdb.latest_results(run_id)
    assert len(res) == 1
    assert res[0]['role'] == 'директор' and res[0]['person'] == 'Петров'
