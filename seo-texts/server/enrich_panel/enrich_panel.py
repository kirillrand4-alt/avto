# -*- coding: utf-8 -*-
"""Панель обогащения (задача #49-а): загрузка списка компаний -> постановка
подписанных заданий раннеру -> прогресс по stage_log -> CSV-выгрузка.

Стек и стиль — как у панели продажников C:\\seostat\\app: FastAPI + Jinja-шаблоны,
никакого React и внешних CDN (свой style.css). Отдельный порт 8013; за Caddy
живёт под /enrich/* (root_path из ENRICH_ROOT_PATH — сам Caddy НЕ трогаем,
блок для владельца в README.md).

Безопасность:
  * Basic-auth на ВСЁ приложение (ENRICH_USERS, формат как OBZVON_USERS:
    «логин:пароль,логин2:пароль2»). Пользователи не заданы -> 503, а не открытая
    панель: забытая переменная не должна означать «пускаем всех».
  * CSRF для POST — same-origin проверка (Sec-Fetch-Site/Origin), как в обзвоне.
  * Никаких путей/команд из формы: файл кладём под СГЕНЕРЁННЫМ именем в
    ENRICH_UPLOADS, исполняются только заранее описанные конвейеры (PIPELINES),
    и то через allowlist-очередь раннера с HMAC-подписью.
"""
import base64
import binascii
import csv
import io
import json
import os
import secrets as _secrets
import time
from urllib.parse import quote, urlparse

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import panel_core as core

DIR = os.path.dirname(os.path.abspath(__file__))


def _parse_users(raw):
    """ENRICH_USERS «логин:пароль,логин2:пароль2» (разделители , или ;) -> dict."""
    users = {}
    for pair in (raw or '').replace(';', ',').split(','):
        pair = pair.strip()
        if not pair or ':' not in pair:
            continue
        login, pwd = pair.split(':', 1)
        if login.strip() and pwd:
            users[login.strip()] = pwd
    return users


def _same_origin(request: Request) -> None:
    """CSRF-защита разрушающих POST (паттерн из app.obzvon): Basic-auth браузер сам
    дошлёт креды на межсайтовую форму, поэтому cross-site отклоняем. Не-браузерные
    клиенты (без Sec-Fetch-Site/Origin/Referer) пропускаем — у них нет жертвы."""
    sfs = request.headers.get('sec-fetch-site')
    if sfs is not None:
        if sfs not in ('same-origin', 'same-site', 'none'):
            raise HTTPException(403, 'Cross-site запрос отклонён.')
        return
    ref = request.headers.get('origin') or request.headers.get('referer')
    if ref and urlparse(ref).netloc != request.headers.get('host', ''):
        raise HTTPException(403, 'Cross-site запрос отклонён.')


def create_app():
    """Фабрика (а не модульный синглтон): тесты создают приложение с тестовым env
    (своя БД/uploads/пользователи), боевой запуск — app внизу модуля."""
    core.load_runner_env()   # DROP_URL/DROP_TOKEN/JOB_SECRET из ключницы раннера
    app = FastAPI(root_path=os.environ.get('ENRICH_ROOT_PATH', '/enrich'),
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.mount('/static', StaticFiles(directory=os.path.join(DIR, 'static')), name='static')
    templates = Jinja2Templates(directory=os.path.join(DIR, 'templates'))
    users = _parse_users(os.environ.get('ENRICH_USERS', ''))

    @app.middleware('http')
    async def basic_auth(request: Request, call_next):
        if not users:   # без пользователей панель НЕ работает (см. докстринг модуля)
            return Response('ENRICH_USERS не настроен', 503)
        hdr = request.headers.get('authorization', '')
        scheme, _, cred = hdr.partition(' ')
        ok = False
        if scheme.lower() == 'basic':
            try:
                login, _, pwd = base64.b64decode(cred.strip()).decode('utf-8').partition(':')
                want = users.get(login, '')
                # compare_digest и на «нет такого логина»: не выдаём тайминг-разницей,
                # какие логины существуют
                ok = bool(want) and _secrets.compare_digest(pwd, want)
            except (binascii.Error, UnicodeDecodeError, ValueError):
                ok = False
        if not ok:
            return Response('Нужна авторизация', 401,
                            headers={'WWW-Authenticate': 'Basic realm="enrich"'})
        return await call_next(request)

    # -- зависимости --------------------------------------------------------
    def get_pdb():
        """Соединение на запрос: дёшево для SQLite и не делит курсоры между потоками."""
        pdb = core.PanelDB()
        try:
            yield pdb
        finally:
            pdb.close()

    def _rp(request: Request) -> str:
        return request.scope.get('root_path', '') or ''

    def _drop():
        return core.DropClient()

    def _secret():
        return os.environ.get('JOB_SECRET', '')

    # -- страницы -----------------------------------------------------------
    @app.get('/')
    def index(request: Request, msg: str = '', pdb: core.PanelDB = Depends(get_pdb)):
        return templates.TemplateResponse(request, 'index.html', {
            'rp': _rp(request), 'msg': msg, 'runs': pdb.list_runs(),
            'max_mb': core.MAX_BYTES // (1024 * 1024), 'max_rows': core.MAX_ROWS,
        })

    @app.post('/upload', dependencies=[Depends(_same_origin)])
    async def upload(request: Request, file: UploadFile = File(...),
                     pdb: core.PanelDB = Depends(get_pdb)):
        rp = _rp(request)
        blob = await file.read(core.MAX_BYTES + 1)   # +1: отличить «ровно лимит» от «больше»
        parsed = core.parse_companies_file(file.filename or '', blob)
        if parsed['error']:
            return RedirectResponse(f'{rp}/?msg={quote(parsed["error"])}', status_code=303)
        if not parsed['accepted']:
            return RedirectResponse(
                f'{rp}/?msg={quote("В файле нет ни одной валидной строки (ИНН 10/12 цифр + название)")}',
                status_code=303)
        # отчёт валидации храним в прогоне (без полного списка принятых — они в run_rows)
        report = {'accepted': len(parsed['accepted']), 'rejected': parsed['rejected'][:200],
                  'rejected_total': len(parsed['rejected'])}
        run_id = pdb.create_run(file.filename or 'без имени', '', parsed['accepted'], report)
        # оригинал — в ENRICH_UPLOADS под СГЕНЕРЁННЫМ именем (пользовательское имя
        # в путь не попадает — только расширение из whitelist парсера)
        ext = '.xlsx' if (file.filename or '').lower().endswith('.xlsx') else '.csv'
        stored = f'run{run_id}-{int(time.time())}{ext}'
        try:
            os.makedirs(core.uploads_dir(), exist_ok=True)
            with open(os.path.join(core.uploads_dir(), stored), 'wb') as f:
                f.write(blob)
            pdb.cx.execute('UPDATE enrich_runs SET stored_file=? WHERE id=?', (stored, run_id))
            pdb.cx.commit()
        except OSError:
            pass    # не смогли сохранить оригинал — прогон всё равно валиден (строки в БД)
        return RedirectResponse(f'{rp}/run/{run_id}', status_code=303)

    @app.get('/run/{run_id}')
    def run_page(request: Request, run_id: int, msg: str = '',
                 pdb: core.PanelDB = Depends(get_pdb)):
        run = pdb.get_run(run_id)
        if run is None:
            raise HTTPException(404, 'Нет такого прогона')
        core.refresh_batches(pdb, _drop(), run_id)   # статусы батчей — с дропа
        run = pdb.get_run(run_id)                    # статус мог обновиться
        try:
            report = json.loads(run.get('report') or '{}')
        except ValueError:
            report = {}
        counts = pdb.stage_counts(run_id)
        selected = set((run['pipelines'] or '').split(',')) - {''}
        # прогресс по конвейерам: сделано = есть хоть одна из done-стадий
        pipe_done = {k: run['total'] - len(pdb.missing_rows(run_id, p.done_stages))
                     for k, p in core.PIPELINES.items()}
        return templates.TemplateResponse(request, 'run.html', {
            'rp': _rp(request), 'msg': msg, 'run': run, 'report': report,
            'counts': counts, 'stage_labels': core.STAGE_LABELS,
            'pipelines': core.PIPELINES, 'selected': selected, 'pipe_done': pipe_done,
            'batches': pdb.batches(run_id), 'results': pdb.latest_results(run_id),
        })

    @app.post('/run/{run_id}/start', dependencies=[Depends(_same_origin)])
    async def run_start(request: Request, run_id: int,
                        pdb: core.PanelDB = Depends(get_pdb)):
        """Запуск и «Докинуть недоделанные» — ОДИН обработчик: submit_run в обоих
        случаях отбирает строки без нужной стадии (идемпотентно по канону stage_log)."""
        rp = _rp(request)
        if pdb.get_run(run_id) is None:
            raise HTTPException(404, 'Нет такого прогона')
        form = await request.form()
        keys = [k for k in core.PIPELINES if form.get(f'p_{k}')]
        if not keys:
            return RedirectResponse(
                f'{rp}/run/{run_id}?msg={quote("Выберите хотя бы один конвейер")}',
                status_code=303)
        try:
            rep = core.submit_run(pdb, _drop(), _secret(), run_id, keys)
        except Exception as e:  # noqa: BLE001 — дроп недоступен и т.п.: показать, не падать
            return RedirectResponse(
                f'{rp}/run/{run_id}?msg={quote("Постановка не удалась: " + str(e)[:120])}',
                status_code=303)
        run = pdb.get_run(run_id)
        merged = sorted(set((run['pipelines'] or '').split(',')) - {''} | set(keys))
        pdb.update_run(run_id, pipelines=','.join(merged),
                       status='запущен' if rep['jobs'] else run['status'])
        parts = [f'поставлено заданий: {rep["jobs"]}']
        for k in keys:
            if k in rep['rows']:
                parts.append(f'{k}: {rep["rows"][k]} строк'
                             + (f' (уже готово {rep["skipped_done"][k]})'
                                if rep['skipped_done'].get(k) else ''))
        if rep['blocked']:
            parts.append('ждут завершения предыдущих батчей: ' + ', '.join(rep['blocked']))
        return RedirectResponse(f'{rp}/run/{run_id}?msg={quote("; ".join(parts))}',
                                status_code=303)

    @app.get('/run/{run_id}/export.csv')
    def export_csv(run_id: int, pdb: core.PanelDB = Depends(get_pdb)):
        run = pdb.get_run(run_id)
        if run is None:
            raise HTTPException(404, 'Нет такого прогона')
        buf = io.StringIO()
        # ; и utf-8-sig — чтобы Excel у продажников открыл без танцев с импортом
        w = csv.writer(buf, delimiter=';')
        w.writerow(['ИНН', 'Название', 'Сайт', 'Лучший email', 'Роль', 'Телефоны', 'Стадии'])
        for r in pdb.export_rows(run_id):
            w.writerow([r['inn'], r['name'], r['site'], r['best_email'], r['role'],
                        r['phones'], r['stages']])
        return Response('\ufeff' + buf.getvalue(), media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition':
                                 f'attachment; filename="enrich-run{run_id}.csv"'})

    return app


app = create_app()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('ENRICH_PORT', '8013')))
