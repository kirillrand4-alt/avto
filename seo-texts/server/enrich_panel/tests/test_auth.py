# -*- coding: utf-8 -*-
"""Авторизация и веб-слой: без валидного Basic-auth панель не отдаёт НИЧЕГО,
без настроенных пользователей — тоже (503, а не открытая панель)."""
import io


def test_no_credentials_401(client):
    r = client.get('/', auth=None)
    assert r.status_code == 401
    assert r.headers.get('www-authenticate', '').startswith('Basic')


def test_wrong_password_401(client):
    assert client.get('/', auth=('kir', 'wrong')).status_code == 401


def test_unknown_login_401(client):
    assert client.get('/', auth=('intruder', 'secret')).status_code == 401


def test_valid_credentials_ok(client):
    r = client.get('/', auth=('kir', 'secret'))
    assert r.status_code == 200
    assert 'Журнал прогонов' in r.text


def test_no_users_configured_503(env_db, monkeypatch):
    monkeypatch.delenv('ENRICH_USERS', raising=False)
    from fastapi.testclient import TestClient
    import enrich_panel
    c = TestClient(enrich_panel.create_app())
    assert c.get('/', auth=('kir', 'secret')).status_code == 503


def test_upload_flow_creates_run_and_report(client):
    body = 'ИНН;Название\n7701234567;ООО Ромашка\nплохой;Мусор\n7701234567;Дубль\n'
    r = client.post('/upload', auth=('kir', 'secret'),
                    files={'file': ('list.csv', io.BytesIO(body.encode('utf-8')),
                                    'text/csv')}, follow_redirects=True)
    assert r.status_code == 200
    assert 'принято 1' in r.text
    assert 'ИНН не 10/12 цифр' in r.text and 'дубль ИНН' in r.text
    # журнал на главной видит прогон
    r2 = client.get('/', auth=('kir', 'secret'))
    assert 'list.csv' in r2.text


def test_upload_requires_auth(client):
    r = client.post('/upload', auth=None,
                    files={'file': ('a.csv', io.BytesIO(b'x'), 'text/csv')})
    assert r.status_code == 401


def test_export_csv(client):
    body = 'ИНН;Название\n7701234567;ООО Ромашка\n'
    client.post('/upload', auth=('kir', 'secret'),
                files={'file': ('list.csv', io.BytesIO(body.encode('utf-8')), 'text/csv')})
    r = client.get('/run/1/export.csv', auth=('kir', 'secret'))
    assert r.status_code == 200
    assert 'text/csv' in r.headers['content-type']
    assert 'ИНН;Название' in r.text
    assert '7701234567;ООО Ромашка' in r.text


def test_start_without_pipelines_shows_message(client):
    body = 'ИНН;Название\n7701234567;ООО Ромашка\n'
    client.post('/upload', auth=('kir', 'secret'),
                files={'file': ('list.csv', io.BytesIO(body.encode('utf-8')), 'text/csv')})
    r = client.post('/run/1/start', auth=('kir', 'secret'), data={},
                    follow_redirects=True)
    assert 'Выберите хотя бы один конвейер' in r.text


def test_cross_site_post_rejected(client):
    r = client.post('/run/1/start', auth=('kir', 'secret'), data={'p_base': '1'},
                    headers={'sec-fetch-site': 'cross-site'})
    assert r.status_code == 403
