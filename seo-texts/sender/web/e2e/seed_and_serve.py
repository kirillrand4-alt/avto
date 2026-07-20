#!/usr/bin/env python3
"""E2E-харнесс: сеет временную БД (owner+manager+лид) и поднимает serve-api.

Запускается Playwright'ом как webServer. Данные детерминированы — e2e логинится
owner'ом/менеджером и берёт лид. Порт из E2E_API_PORT (default 8099).
"""
import os
import sys
import tempfile
from pathlib import Path

# корень seo-texts в путь (скрипт лежит в sender/web/e2e/)
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("UNSUB_SIGNING_SECRET", "e2e-secret-32-bytes-minimum-length!!")
for i in range(1, 6):
    os.environ.setdefault(f"BOX{i}_PASSWORD", "p")

from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.store import Store, RecipientIn  # noqa: E402
from sender.auth import Auth  # noqa: E402
from sender.leaddesk import LeadDesk  # noqa: E402
from sender.api.app import make_app, build_deps  # noqa: E402


def seed():
    d = Path(tempfile.mkdtemp(prefix="sender-e2e-"))
    db = d / "e2e.db"
    (d / "c.yaml").write_text(BASE_YAML.replace("/tmp/sender.db", str(db)), encoding="utf-8")
    config = Config.load(str(d / "c.yaml"))
    store = Store(str(db))
    store.init_schema()
    auth = Auth(store)
    # owner БЕЗ 2FA (e2e логинится паролем); manager тоже
    auth.create_user(username="kirill", password="ownerpass1", role="owner")
    auth.create_user(username="petrov", password="mgrpass12", role="manager")
    # два лида: один берём в e2e, второй остаётся для «конкуренции»
    desk = LeadDesk(config, store)
    for i, (email, comp) in enumerate([
        ("director@zavod-a.ru", "Завод А"),
        ("glaveng@zavod-b.ru", "Завод Б"),
    ]):
        rid = store.upsert_recipient(RecipientIn(
            email=email, domain=email.split("@")[1], company_name=comp, inn=f"770000000{i}"))
        rec = store.get_recipient(rid)
        desk.push_warm_lead(rec, f"thread-{i}",
                            f"[hot, тел +7495123456{i}] нужен компрессор срочно")
    return config, store


def main():
    config, store = seed()
    app = make_app(build_deps(config, store))
    import uvicorn
    port = int(os.environ.get("E2E_API_PORT", "8099"))
    print(f"[e2e] serve-api на :{port}, БД засеяна (owner=kirill, mgr=petrov, 2 лида)", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
