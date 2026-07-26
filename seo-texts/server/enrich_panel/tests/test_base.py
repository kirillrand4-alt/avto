# -*- coding: utf-8 -*-
"""Страница «База»: фильтры по индексу обзвона (выручка от/до, хвост N, регион,
направление, почта, сайт), пагинация, «сколько взять», и постановка обогащения
выборки через СУЩЕСТВУЮЩИЙ механизм прогонов (идемпотентно по stage_log).
Приёмочный сценарий владельца: «обогатить каждым видом обогащения компании с
выручкой 100-150 млн и все компании из хвоста» — кликами, см. test_owner_scenario."""
import json

from conftest import OBZVON_ROWS, mark_stage

import panel_core as core

ALL_INNS = [r['ИНН'] for r in OBZVON_ROWS]
REV_100_150 = ['7700000002', '7700000003', '7700000004', '7700000008']
TAIL_4 = ['7700000009', '7700000010', '7700000011', '7700000012']


def _f(**kw):
    """Фильтры через боевой парсер (а не руками собранный dict): тесты ходят
    тем же путём, что form/query панели."""
    return core.parse_base_filters({k: str(v) for k, v in kw.items()})


def _inns(rows):
    return [r['inn'] for r in rows]


# ---------------------------------------------------------------------------
# parse_money — канон разбора выручки (скопирован из callbase)
# ---------------------------------------------------------------------------

def test_parse_money_variants():
    assert core.parse_money('123456789') == 123456789
    assert core.parse_money('123 456 789') == 123456789      # пробелы-разделители
    assert core.parse_money('1\xa0000') == 1000              # NBSP из Excel
    assert core.parse_money('55,3 млрд руб.') == 55.3e9
    assert core.parse_money('120 млн руб.') == 120e6
    assert core.parse_money('424 тыс. руб.') == 424000
    assert core.parse_money('0 руб.') == 0
    assert core.parse_money(150000000) == 150000000.0        # число как есть
    assert core.parse_money('') is None
    assert core.parse_money(None) is None
    assert core.parse_money('н/д') is None


def test_parse_base_filters_types_and_garbage():
    f = core.parse_base_filters({'rev_min': '100', 'rev_max': '150,5', 'tail': '5000',
                                 'region': ' Моск ', 'division': 'KC',
                                 'email': 'yes', 'site': 'no', 'take': '200'})
    assert f['rev_min'] == 100 and f['rev_max'] == 150.5
    assert f['tail'] == 5000 and f['take'] == 200
    assert f['region'] == 'Моск' and f['division'] == 'kc'
    assert f['email'] == 'yes' and f['site'] == 'no'
    g = core.parse_base_filters({'rev_min': 'abc', 'tail': '-5', 'division': 'both',
                                 'email': 'maybe'})
    assert g['rev_min'] is None and g['tail'] == 0
    assert g['division'] == '' and g['email'] == ''


# ---------------------------------------------------------------------------
# Фильтры выборки по индексу
# ---------------------------------------------------------------------------

def test_revenue_range_100_150(obzvon_db):
    ob = core.ObzvonDB()
    try:
        # 150 млн у Дельты лежит ЧЕЛОВЕКОЧИТАЕМОЙ строкой («150 млн руб.») —
        # фолбэк revenue_rub -> revenue обязан её поймать; без выручки (Эта) — мимо
        assert _inns(ob.select(_f(rev_min=100, rev_max=150), 100)) == REV_100_150
        assert ob.count(_f(rev_min=100, rev_max=150)) == 4
    finally:
        ob.close()


def test_revenue_open_ended(obzvon_db):
    ob = core.ObzvonDB()
    try:
        # только «от»: 200 млн и 1,5 млрд проходят, компании без выручки — нет
        assert _inns(ob.select(_f(rev_min=200), 100)) == ['7700000005', '7700000006']
        # только «до»: хвост с 10-13 млн + Альфа 50 млн
        assert _inns(ob.select(_f(rev_max=50), 100)) == ['7700000001'] + TAIL_4
    finally:
        ob.close()


def test_tail_of_base(obzvon_db):
    ob = core.ObzvonDB()
    try:
        assert _inns(ob.select(_f(tail=4), 100)) == TAIL_4
        # хвост больше базы = вся база (не ошибка)
        assert ob.count(_f(tail=999)) == len(ALL_INNS)
    finally:
        ob.close()


def test_combined_filters(obzvon_db):
    ob = core.ObzvonDB()
    try:
        # выручка И направление
        assert _inns(ob.select(_f(rev_min=100, rev_max=150, division='meyer'), 100)) == \
            ['7700000003', '7700000008']
        # выручка И направление И почта — остаётся одна Тета
        assert _inns(ob.select(_f(rev_min=100, rev_max=150, division='meyer',
                                  email='yes'), 100)) == ['7700000008']
        # хвост И направление
        assert _inns(ob.select(_f(tail=4, division='meyer'), 100)) == ['7700000012']
        # регион (кириллица, регистронезависимо) И без сайта
        assert _inns(ob.select(_f(region='моск', site='no'), 100)) == \
            ['7700000002', '7700000004', '7700000007']
    finally:
        ob.close()


def test_take_first_n_of_selection(obzvon_db):
    ob = core.ObzvonDB()
    try:
        assert _inns(ob.select(_f(), 3)) == ALL_INNS[:3]
        assert _inns(ob.select(_f(rev_min=100, rev_max=150), 2)) == REV_100_150[:2]
    finally:
        ob.close()


def test_pagination(obzvon_db):
    ob = core.ObzvonDB()
    try:
        p1 = ob.page(_f(), page=1, per_page=5)
        assert p1['total'] == 12 and p1['pages'] == 3
        assert _inns(p1['rows']) == ALL_INNS[:5]
        p3 = ob.page(_f(), page=3, per_page=5)
        assert _inns(p3['rows']) == ALL_INNS[10:]
        # запредельная страница приводится к последней, а не 500
        assert ob.page(_f(), page=99, per_page=5)['page'] == 3
        # выручка в млн для показа: и из revenue_rub, и из «150 млн руб.»
        by_inn = {r['inn']: r for r in p1['rows']}
        assert by_inn['7700000002']['revenue_mln'] == 100.0
        assert by_inn['7700000004']['revenue_mln'] == 150.0
        assert by_inn['7700000001']['has_email'] and by_inn['7700000001']['has_site']
        assert not by_inn['7700000004']['has_email']
    finally:
        ob.close()


def test_ogrns_lookup(obzvon_db):
    ob = core.ObzvonDB()
    try:
        og = ob.ogrns(['7700000002', '7700000008', '0000000000'])
        assert og == {'7700000002': '1077700000002', '7700000008': '1077700000008'}
    finally:
        ob.close()


def test_stages_for_inns_batch(pdb, env_db):
    mark_stage(env_db, '7700000001', 'site', 'alfa.ru')
    mark_stage(env_db, '7700000001', 'email')
    mark_stage(env_db, '7700000003', 'checko')
    st = pdb.stages_for_inns(['7700000001', '7700000002', '7700000003'])
    assert set(st['7700000001'].split(',')) == {'site', 'email'}
    assert st['7700000003'] == 'checko'
    assert '7700000002' not in st
    assert pdb.stages_for_inns([]) == {}


# ---------------------------------------------------------------------------
# Новые конвейеры hh/opo/zakupki — фактические форматы args из enrich_contacts.py
# ---------------------------------------------------------------------------

def _mkrun(pdb, rows):
    return pdb.create_run('база: тест', '', rows,
                          {'accepted': len(rows), 'rejected': [], 'rejected_total': 0})


def _jobs(drop):
    return sorted(n for n in drop.files if n.startswith('job-'))


def test_hh_single_global_job(pdb, drop, obzvon_db):
    rows = [{'inn': i, 'name': f'К{i}'} for i in ALL_INNS]
    run_id = _mkrun(pdb, rows)
    rep = core.submit_run(pdb, drop, 'test-secret', run_id, ['hh'])
    # hh_signals НЕ принимает список ИНН -> один глобальный скан на постановку
    assert rep['jobs'] == 1
    job = json.loads(drop.files[_jobs(drop)[0]])
    assert job['task'] == 'enrich_contacts' and job['sig']
    assert job['args'] == {'op': 'hh_signals', 'pages': 3}


def test_hh_skipped_when_all_have_stage(pdb, drop, env_db, obzvon_db):
    rows = [{'inn': i, 'name': f'К{i}'} for i in REV_100_150]
    run_id = _mkrun(pdb, rows)
    for i in REV_100_150:
        mark_stage(env_db, i, 'hh', 'вакансий=2')
    rep = core.submit_run(pdb, drop, '', run_id, ['hh'])
    assert rep['jobs'] == 0 and _jobs(drop) == []   # идемпотентно: скан не гоняем


def test_opo_batch_args_with_ogrn(pdb, drop, obzvon_db):
    rows = [{'inn': i, 'name': f'К{i}'} for i in REV_100_150]
    run_id = _mkrun(pdb, rows)
    rep = core.submit_run(pdb, drop, '', run_id, ['opo'])
    assert rep['jobs'] == 1
    job = json.loads(drop.files[_jobs(drop)[0]])
    a = job['args']
    assert a['op'] == 'opo_batch'
    # checko ходит по ОГРН — панель обязана подтянуть его из индекса обзвона
    assert a['companies'][0] == {'ogrn': '1077700000002', 'inn': '7700000002',
                                 'name': 'К7700000002'}
    assert len(a['companies']) == 4
    assert a['out_file'] == f'panel-opo-run{run_id}-7700000002.csv'


def test_opo_batches_of_40(pdb, drop, obzvon_db):
    rows = [{'inn': f'99{i:08d}', 'name': f'Н{i}'} for i in range(45)]
    run_id = _mkrun(pdb, rows)
    rep = core.submit_run(pdb, drop, '', run_id, ['opo'])
    assert rep['jobs'] == 2
    jobs = [json.loads(drop.files[n]) for n in _jobs(drop)]
    assert sorted(len(j['args']['companies']) for j in jobs) == [5, 40]
    # ИНН не из базы обзвона -> ogrn пустой, op честно ответит «нет OGRN»
    assert jobs[0]['args']['companies'][0]['ogrn'] == ''
    # out_file уникален на батч — иначе батчи затирали бы CSV друг друга
    assert len({j['args']['out_file'] for j in jobs}) == 2


def test_zakupki_mass_cap_is_selection_size(pdb, drop, obzvon_db):
    rows = [{'inn': i, 'name': f'К{i}'} for i in TAIL_4]
    run_id = _mkrun(pdb, rows)
    rep = core.submit_run(pdb, drop, '', run_id, ['zakupki'])
    assert rep['jobs'] == 1
    job = json.loads(drop.files[_jobs(drop)[0]])
    # zakupki_mass не принимает ИНН: выборка задаёт только объём (cap)
    assert job['args'] == {'op': 'zakupki_mass', 'cap': 4, 'max_cards': 3}


# ---------------------------------------------------------------------------
# Веб-слой: страница «База» и постановка обогащения кликами
# ---------------------------------------------------------------------------

def test_base_page_lists_companies_and_stages(client, obzvon_db, env_db):
    mark_stage(env_db, '7700000001', 'checko', 'div=kc')
    r = client.get('/base', auth=('kir', 'secret'))
    assert r.status_code == 200
    assert 'ООО Альфа' in r.text and 'ООО Тета' in r.text
    assert 'checko' in r.text                       # стадии видны в списке
    assert 'Обогатить выбранное' in r.text


def test_base_page_without_index_says_so(client):
    # OBZVON_INDEX не задан, боевого C:\sender на тест-машине нет -> честное
    # сообщение, а не 500
    r = client.get('/base', auth=('kir', 'secret'))
    assert r.status_code == 200
    assert 'не найден' in r.text


def test_base_page_filters_and_pagination_links(client, obzvon_db):
    r = client.get('/base', params={'rev_min': '100', 'rev_max': '150'},
                   auth=('kir', 'secret'))
    assert 'ООО Бета' in r.text and 'ООО Дельта' in r.text
    assert 'ООО Альфа' not in r.text                # 50 млн — вне диапазона
    r2 = client.get('/base', params={'tail': '4'}, auth=('kir', 'secret'))
    assert 'Хвост-1' in r2.text and 'ООО Альфа' not in r2.text


def test_base_enrich_creates_run_and_jobs(client, obzvon_db, env_db, webdrop):
    r = client.post('/base/enrich', auth=('kir', 'secret'),
                    data={'rev_min': '100', 'rev_max': '150', 'p_etp': '1'},
                    follow_redirects=True)
    assert r.status_code == 200
    assert 'поставлено заданий: 1' in r.text
    pdb = core.PanelDB(env_db)
    try:
        run = pdb.get_run(1)
        assert run['total'] == 4 and 'выручка 100-150 млн' in run['filename']
        assert [x['inn'] for x in pdb.run_rows(1)] == REV_100_150
    finally:
        pdb.close()
    job = json.loads(webdrop.files[_jobs(webdrop)[0]])
    assert job['args']['op'] == 'etp_fit'
    assert sorted(job['args']['inns']) == REV_100_150


def test_base_enrich_idempotent_skips_done_rows(client, obzvon_db, env_db, webdrop):
    # у двух компаний ОКВЭД уже классифицирован — повторно НЕ ставим (канон топапа)
    mark_stage(env_db, '7700000002', 'checko', 'div=kc')
    mark_stage(env_db, '7700000003', 'checko', 'div=meyer')
    r = client.post('/base/enrich', auth=('kir', 'secret'),
                    data={'rev_min': '100', 'rev_max': '150', 'p_okved': '1'},
                    follow_redirects=True)
    assert 'уже готово 2' in r.text
    job = json.loads(webdrop.files[_jobs(webdrop)[0]])
    assert sorted(job['args']['inns']) == ['7700000004', '7700000008']


def test_base_enrich_take_limits_selection(client, obzvon_db, env_db, webdrop):
    client.post('/base/enrich', auth=('kir', 'secret'),
                data={'p_okved': '1', 'take': '2'})
    pdb = core.PanelDB(env_db)
    try:
        assert [x['inn'] for x in pdb.run_rows(1)] == ALL_INNS[:2]
    finally:
        pdb.close()


def test_base_enrich_huge_selection_requires_take(client, obzvon_db, monkeypatch, webdrop):
    # случайный клик не должен поставить прогон на всю базу: без «сколько взять»
    # выборка больше лимита отклоняется с подсказкой
    monkeypatch.setattr(core, 'MAX_ROWS', 5)
    r = client.post('/base/enrich', auth=('kir', 'secret'),
                    data={'p_okved': '1'}, follow_redirects=True)
    assert 'больше лимита 5' in r.text
    assert _jobs(webdrop) == []


def test_base_enrich_without_pipelines_shows_message(client, obzvon_db, webdrop):
    r = client.post('/base/enrich', auth=('kir', 'secret'),
                    data={'rev_min': '100'}, follow_redirects=True)
    assert 'хотя бы одну стадию' in r.text


def test_base_enrich_cross_site_rejected(client, obzvon_db):
    r = client.post('/base/enrich', auth=('kir', 'secret'), data={'p_etp': '1'},
                    headers={'sec-fetch-site': 'cross-site'})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Приёмочный сценарий владельца — целиком, кликами
# ---------------------------------------------------------------------------

def test_owner_scenario_revenue_range_all_pipelines(client, obzvon_db, env_db, webdrop):
    """«Хочу обогатить каждым видом обогащения компании с выручкой от 100 до
    150 млн»: один POST со всеми чекбоксами -> прогон на 4 компании, по job'у
    (или пачке) на каждый из 7 конвейеров, каждый — с фактическими args своего op."""
    r = client.post('/base/enrich', auth=('kir', 'secret'),
                    data={'rev_min': '100', 'rev_max': '150',
                          **{f'p_{k}': '1' for k in core.PIPELINES}},
                    follow_redirects=True)
    assert r.status_code == 200 and 'поставлено заданий: 7' in r.text
    jobs = [json.loads(webdrop.files[n]) for n in _jobs(webdrop)]
    by_op = {}
    for j in jobs:
        by_op.setdefault(j['args'].get('op', 'base'), []).append(j['args'])
    assert set(by_op) == {'base', 'etp_fit', 'checko_okveds', 'promote_named_email',
                          'hh_signals', 'opo_batch', 'zakupki_mass'}
    # базовое: компании с именами, запись в БД, свой stream-файл прогона
    a = by_op['base'][0]
    assert [c['inn'] for c in a['companies']] == REV_100_150
    assert a['write_db'] and a['resume'] and a['stream_file'] == 'enrich_panel_run1.jsonl'
    # ЕИС по списку ИНН с полным limit (без него op взял бы только 40)
    assert sorted(by_op['etp_fit'][0]['inns']) == REV_100_150
    assert by_op['etp_fit'][0]['limit'] == 4
    # ОКВЭД и best_email — по списку ИНН
    assert sorted(by_op['checko_okveds'][0]['inns']) == REV_100_150
    assert sorted(by_op['promote_named_email'][0]['inns']) == REV_100_150
    # ОПО — по ОГРН из индекса обзвона
    assert [c['ogrn'] for c in by_op['opo_batch'][0]['companies']] == \
        ['1077700000002', '1077700000003', '1077700000004', '1077700000008']
    # массовые сканы: hh — глобальный, закупки — cap размером с выборку
    assert by_op['hh_signals'][0] == {'op': 'hh_signals', 'pages': 3}
    assert by_op['zakupki_mass'][0]['cap'] == 4


def test_owner_scenario_tail_all_pipelines(client, obzvon_db, env_db, webdrop):
    """«...и все компании из хвоста списка»: второй клик — те же чекбоксы, фильтр
    «хвост N». Отдельный прогон, батчи только по хвостовым ИНН."""
    r = client.post('/base/enrich', auth=('kir', 'secret'),
                    data={'tail': '4', **{f'p_{k}': '1' for k in core.PIPELINES}},
                    follow_redirects=True)
    assert r.status_code == 200 and 'поставлено заданий: 7' in r.text
    pdb = core.PanelDB(env_db)
    try:
        assert [x['inn'] for x in pdb.run_rows(1)] == TAIL_4
        assert 'хвост 4' in pdb.get_run(1)['filename']
    finally:
        pdb.close()
    jobs = [json.loads(webdrop.files[n]) for n in _jobs(webdrop)]
    base_args = next(j['args'] for j in jobs if 'op' not in j['args'])
    assert [c['inn'] for c in base_args['companies']] == TAIL_4
    etp = next(j['args'] for j in jobs if j['args'].get('op') == 'etp_fit')
    assert sorted(etp['inns']) == TAIL_4
