# -*- coding: utf-8 -*-
"""Ревью #48, транспортный слой: гонка «approve во время перегенерации» и
авторизация ручки перегенерации.

Гонка (#71): перегенерация крутится в фоне минуты (LLM-раунды), а кнопка
«Отправить» оставалась активной — фоновый поток мог подменить текст в БД между
тем, что оператор видит на экране, и моментом approve. Теперь на время
перегенерации approve/edit отвечают 409; скип/стоп-лист не блокируются.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.api.app import build_deps, make_app  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402


@pytest.fixture
def client(tmp_path):
    os.environ.update({f"BOX{i}_PASSWORD": "p" for i in range(1, 6)})
    os.environ["UNSUB_SIGNING_SECRET"] = "s" * 32
    (tmp_path / "c.yaml").write_text(
        BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "api.db")),
        encoding="utf-8")
    config = Config.load(str(tmp_path / "c.yaml"))
    store = Store(str(tmp_path / "api.db"))
    store.init_schema()
    deps = build_deps(config, store)
    deps.auth.create_user(username="owner", password="ownerpass", role="owner")
    deps.auth.create_user(username="mgr", password="managerpass", role="manager")
    app = make_app(deps)
    return TestClient(app), store, app


def _tok(c, user="owner", pwd="ownerpass"):
    r = c.post("/auth/login", json={"username": user, "password": pwd})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_decision_blocked_while_regenerating(client):
    c, store, app = client
    h = _tok(c)
    rid = 123
    # фоновый поток перегенерации ещё работает
    app.state.regen_box[rid] = {"running": True, "error": None, "result": None}

    for action in ("approve", "edit"):
        r = c.post(f"/confirm/{rid}/decision", json={"action": action},
                   headers=h)
        assert r.status_code == 409, (action, r.status_code, r.text)
        assert "перегенерация" in r.json()["detail"]

    # скип не блокируется гейтом перегенерации (падает по другой причине —
    # карточки 123 нет), т.е. гейт точечный, а не «всё закрыто»
    r = c.post(f"/confirm/{rid}/decision",
               json={"action": "skip", "reason": "тест"}, headers=h)
    assert r.status_code != 409 or "перегенерация" not in r.json()["detail"]

    # перегенерация закончилась — approve больше не блокируется этим гейтом
    app.state.regen_box[rid]["running"] = False
    r = c.post(f"/confirm/{rid}/decision", json={"action": "approve"},
               headers=h)
    assert "перегенерация" not in (r.json().get("detail") or "")


def test_regenerate_requires_owner(client):
    c, _store, _app = client
    r = c.post("/confirm/1/regenerate", headers=_tok(c, "mgr", "managerpass"))
    assert r.status_code == 403
    # владельцу — не 403 (письма нет в очереди -> честный 409)
    r = c.post("/confirm/1/regenerate", headers=_tok(c))
    assert r.status_code == 409
