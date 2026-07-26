# -*- coding: utf-8 -*-
"""Постановка заданий: батчи 6-10, подпись совместима с боевым job_runner,
«Запустить»/«Докинуть» идемпотентны (строки с готовой стадией не переотправляются),
незавершённые батчи блокируют дубли."""
import json
import os
import sys

from conftest import mark_stage

import panel_core as core

ROWS = [{'inn': f'77012345{i:02d}', 'name': f'Компания {i}'} for i in range(20)]


def _mkrun(pdb, rows=ROWS):
    return pdb.create_run('t.csv', 'run1.csv', rows,
                          {'accepted': len(rows), 'rejected': [], 'rejected_total': 0})


def _jobs(drop):
    return sorted(n for n in drop.files if n.startswith('job-'))


def test_start_batches_of_8(pdb, drop):
    run_id = _mkrun(pdb)
    rep = core.submit_run(pdb, drop, 'test-secret', run_id, ['base'])
    # 20 строк по 8 = 3 задания
    assert rep['jobs'] == 3 and rep['rows']['base'] == 20
    jobs = [json.loads(drop.files[n]) for n in _jobs(drop)]
    assert [len(j['args']['companies']) for j in jobs] == [8, 8, 4]
    # каждое задание — на задачу из allowlist раннера, с подписью и resume-полями
    for j in jobs:
        assert j['task'] == 'enrich_contacts'
        assert j['sig']
        assert j['args']['write_db'] and j['args']['resume']
        assert j['args']['stream_file'] == f'enrich_panel_run{run_id}.jsonl'


def test_signature_accepted_by_real_job_runner(pdb, drop):
    """Подпись панели должна пройти проверку НАСТОЯЩЕГО job_runner.sig_ok —
    иначе раннер молча выбросит задание («ПОДПИСЬ НЕВЕРНА»)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    import job_runner
    run_id = _mkrun(pdb, ROWS[:3])
    core.submit_run(pdb, drop, 'test-secret', run_id, ['etp'])
    job = json.loads(drop.files[_jobs(drop)[0]])
    old = job_runner.JOB_SECRET
    try:
        job_runner.JOB_SECRET = 'test-secret'
        assert job_runner.sig_ok(job)
        job['args']['inns'].append('0000000000')     # подмена аргументов ломает подпись
        assert not job_runner.sig_ok(job)
        assert job['task'] in job_runner.ALLOW       # задача реально в allowlist
    finally:
        job_runner.JOB_SECRET = old


def test_etp_args_carry_full_limit(pdb, drop):
    """etp_fit без limit берёт только 40 ИНН — панель обязана передать limit=len(batch),
    иначе хвост батча молча не обработается."""
    run_id = _mkrun(pdb, ROWS[:10])
    core.submit_run(pdb, drop, '', run_id, ['etp'])
    jobs = [json.loads(drop.files[n]) for n in _jobs(drop)]
    assert sorted(len(j['args']['inns']) for j in jobs) == [2, 8]   # батчи по 8
    for j in jobs:
        a = j['args']
        assert a['op'] == 'etp_fit' and a['limit'] == len(a['inns'])


def test_topup_only_missing_rows(pdb, drop, env_db):
    run_id = _mkrun(pdb, ROWS[:10])
    rep1 = core.submit_run(pdb, drop, '', run_id, ['okved'])
    assert rep1['rows']['okved'] == 10
    # раннер «выполнил» задания: job-файлы ушли с дропа, у 7 строк появилась стадия
    for n in _jobs(drop):
        drop.delete(n)
    for r in ROWS[:7]:
        mark_stage(env_db, r['inn'], 'checko', 'div=kc')
    core.refresh_batches(pdb, drop, run_id)   # батчи без job/result -> «выполняется»...
    for b in pdb.batches(run_id):             # ...считаем их завершёнными для докидки
        pdb.mark_batch(b['job_id'], 'готов')
    rep2 = core.submit_run(pdb, drop, '', run_id, ['okved'])
    assert rep2['rows']['okved'] == 3 and rep2['skipped_done']['okved'] == 7
    job = json.loads(drop.files[_jobs(drop)[0]])
    assert sorted(job['args']['inns']) == sorted(r['inn'] for r in ROWS[7:10])


def test_topup_zero_when_all_done(pdb, drop, env_db):
    run_id = _mkrun(pdb, ROWS[:5])
    for r in ROWS[:5]:
        mark_stage(env_db, r['inn'], 'etp')
    rep = core.submit_run(pdb, drop, '', run_id, ['etp'])
    assert rep['jobs'] == 0 and rep['rows']['etp'] == 0
    assert _jobs(drop) == []                  # ничего не отправлено — идемпотентно


def test_pending_batches_block_duplicates(pdb, drop):
    """Пока батчи конвейера в работе, повторный клик не должен дублировать job'ы
    (двойной расход xmlriver по тем же строкам)."""
    run_id = _mkrun(pdb, ROWS[:5])
    core.submit_run(pdb, drop, '', run_id, ['base'])
    n_before = len(_jobs(drop))
    rep = core.submit_run(pdb, drop, '', run_id, ['base'])
    assert rep['blocked'] == ['base'] and rep['jobs'] == 0
    assert len(_jobs(drop)) == n_before


def test_refresh_batches_reads_results_and_cleans_drop(pdb, drop):
    run_id = _mkrun(pdb, ROWS[:5])
    core.submit_run(pdb, drop, '', run_id, ['base'])
    jid = pdb.batches(run_id)[0]['job_id']
    # раннер: job удалён, результат выложен
    drop.delete(f'job-{jid}.json')
    drop.up(f'result-{jid}.json', json.dumps(
        {'ok': True, 'id': jid, 'data': {'summary': {'with_email': 4}}}).encode())
    core.refresh_batches(pdb, drop, run_id)
    b = pdb.batches(run_id)[0]
    assert b['status'] == 'готов' and 'with_email' in b['note']
    assert f'result-{jid}.json' not in drop.files     # результат прибран с дропа
    assert pdb.get_run(run_id)['status'] == 'готов'


def test_refresh_batches_marks_errors(pdb, drop):
    run_id = _mkrun(pdb, ROWS[:5])
    core.submit_run(pdb, drop, '', run_id, ['base'])
    jid = pdb.batches(run_id)[0]['job_id']
    drop.delete(f'job-{jid}.json')
    drop.up(f'result-{jid}.json', json.dumps(
        {'ok': False, 'id': jid, 'error': 'timeout 1800s'}).encode())
    core.refresh_batches(pdb, drop, run_id)
    assert pdb.batches(run_id)[0]['status'] == 'ошибка'
    assert pdb.get_run(run_id)['status'] == 'готов (с ошибками)'


def test_promote_single_big_batch(pdb, drop):
    """promote_named_email — БД-операция без внешних запросов: батч крупный,
    20 строк должны уйти ОДНИМ заданием."""
    run_id = _mkrun(pdb)
    rep = core.submit_run(pdb, drop, '', run_id, ['best_email'])
    assert rep['jobs'] == 1
    job = json.loads(drop.files[_jobs(drop)[0]])
    assert job['args']['op'] == 'promote_named_email'
    assert len(job['args']['inns']) == 20
