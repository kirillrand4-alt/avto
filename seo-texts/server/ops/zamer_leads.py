# -*- coding: utf-8 -*-
"""Диагностика ленты лидов: /leads, /leads/{id}, /leads/{id}/dialog — время, SQL, что зовут.
Ничего не пишет (query_only), LLM не зовёт (reply-draft не трогаем).
Аргументы: [limit=100]

Описание ниже — от родительского замера очереди:

ТОЛЬКО ЧТЕНИЕ. Соединение со sender.db переводится в PRAGMA query_only=ON —
любая запись (в т.ч. recover_stale_reviews внутри pending()) упадёт и будет
погашена тем же except, что и в боевом коде. build_deps НЕ зовём (он гоняет
init_schema). Писем не шлём: Sender собирается dry_run=True, approve не зовём.

Что делает:
  1) размеры таблиц и индексы;
  2) собирает Deps вручную, строит make_app(deps) и вызывает САМУ функцию
     ручки /confirm/queue (как Python-функцию, без HTTP и без авторизации) —
     с трассировкой каждого SQL (число и время по шаблону) и cProfile;
  3) отдельные замеры кусков (pending, карты, send_as, can_send_now, гейты);
  4) EXPLAIN QUERY PLAN тяжёлых запросов.
Аргументы: [limit=50] [order=score] [division=]
"""
import cProfile
import io
import pstats
import re
import sqlite3
import sys
import time
from collections import defaultdict
from types import SimpleNamespace

sys.path.insert(0, r"C:\sender")

from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 50
ORDER = sys.argv[2] if len(sys.argv) > 2 else "score"
DIV = sys.argv[3] if len(sys.argv) > 3 else None

import os  # noqa: E402


class _Tee:
    """Вывод дублируется в файл на дропе: хвост pl_run обрезает начало."""
    def __init__(self, *ss):
        self._ss = ss

    def write(self, x):
        for s in self._ss:
            s.write(x)

    def flush(self):
        for s in self._ss:
            s.flush()


sys.stdout = _Tee(sys.stdout, io.open(
    r"C:\seostat\drop\drop-storage\zamer_leads_out.txt", "w", encoding="utf-8"))
_cfg_path = r"C:\sender\config.yaml" if os.path.exists(r"C:\sender\config.yaml") \
    else r"C:\sender\sender.yaml"
cfg = Config.load(_cfg_path)
db_path = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(db_path)
store._conn.execute("PRAGMA query_only=ON")
print("конфиг:", _cfg_path.split("\\")[-1], "| база:", str(db_path).split("\\")[-1])


# ---------- трассировка SQL ------------------------------------------------ #
STAT = defaultdict(lambda: [0, 0.0])
_on = [False]


def _шаблон(sql):
    s = re.sub(r"\s+", " ", str(sql)).strip()
    s = re.sub(r"\(\?(,\s*\?)+\)", "(?…)", s)
    return s[:150]


class _Cur:
    def __init__(self, cur, key):
        self._c, self._k = cur, key

    def _t(self, fn, *a):
        t0 = time.perf_counter()
        try:
            return fn(*a)
        finally:
            if _on[0]:
                STAT[self._k][1] += time.perf_counter() - t0

    def fetchall(self):
        return self._t(self._c.fetchall)

    def fetchone(self):
        return self._t(self._c.fetchone)

    def fetchmany(self, *a):
        return self._t(self._c.fetchmany, *a)

    def __iter__(self):
        return iter(self.fetchall())

    def __getattr__(self, n):
        return getattr(self._c, n)


class _Conn:
    def __init__(self, conn):
        self._c = conn

    def execute(self, sql, params=()):
        k = _шаблон(sql)
        t0 = time.perf_counter()
        cur = self._c.execute(sql, params)
        if _on[0]:
            STAT[k][0] += 1
            STAT[k][1] += time.perf_counter() - t0
        return _Cur(cur, k)

    def __getattr__(self, n):
        return getattr(self._c, n)


raw_conn = store._conn
store._conn = _Conn(raw_conn)


def печать_sql(заголовок, топ=25):
    всего_n = sum(v[0] for v in STAT.values())
    всего_t = sum(v[1] for v in STAT.values())
    print(f"\n--- SQL: {заголовок}: запросов {всего_n}, время в SQLite "
          f"{всего_t*1000:.0f} мс ---")
    for k, (n, t) in sorted(STAT.items(), key=lambda kv: -kv[1][1])[:топ]:
        print(f"  {t*1000:9.1f} мс  x{n:<6} {k}")


def сброс():
    STAT.clear()


# ---------- 2. сборка deps ------------------------------------------------- #
t0 = time.perf_counter()
from sender.suppression import Suppression  # noqa: E402
from sender.gates import Gates  # noqa: E402
from sender.sender import Sender  # noqa: E402
from sender.company_card import CompanyCards  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.auth import Auth  # noqa: E402
from sender.wiring import Deps  # noqa: E402
from sender.api.app import make_app, _signature_for  # noqa: E402

supp = Suppression(store)
gates = Gates(cfg, store)
cards = CompanyCards(
    index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
sender = Sender(cfg, store, supp, gates, dry_run=True, cards=cards)
confirm = ConfirmSend(cfg, store, supp, sender=sender, cards=cards, probe=None)
from sender.leaddesk import LeadDesk  # noqa: E402
deps = Deps(config=cfg, store=store, auth=Auth(store), leaddesk=LeadDesk(cfg, store),
            analytics=None, gates=gates, sender=sender, suppression=supp,
            confirm=confirm, cards=cards)
app = make_app(deps)
# ТОЛЬКО GET: на /leads/{lead_id} висит ещё и DELETE (мягкое удаление лида)
ручки = {getattr(r, "path", ""): r.endpoint for r in app.routes
         if "GET" in (getattr(r, "methods", None) or set())}
print(f"\nсборка deps+app: {(time.perf_counter()-t0)*1000:.0f} мс; "
      f"ящиков в конфиге: {len(list(cfg.mailboxes()))}; cards.active={cards.active}")


def вызвать():
    return ep(campaign_id=None, limit=LIMIT, offset=0, order=ORDER,
              division=DIV, gruppa=None, hide_blocked=False,
              p=SimpleNamespace(user_id=0, username="zamer", role="owner"))



P = SimpleNamespace(user_id=0, username="zamer", role="owner")
LIMIT_L = int(sys.argv[1]) if len(sys.argv) > 1 else 100
СЛЕДИТЬ = ("equip_for_okved", "send_as", "can_send_now", "recipient_groups",
           "recipient_mx_map", "sent_flags", "_karta_okved", "poslednie_otvety",
           "kopii_avtootveta", "open_counts", "stats", "panel_dlya_lida",
           "_kontakty_kompanii", "karta_kompanii", "history", "dialog_thread")


def прогон(имя, fn, профиль=True):
    сброс()
    pr = cProfile.Profile()
    _on[0] = True
    t0 = time.perf_counter()
    pr.enable()
    try:
        out = fn()
        ошибка = ""
    except Exception as e:  # noqa: BLE001
        import traceback as _tb
        кадры = [f"{f.filename.split(chr(92))[-1]}:{f.lineno}:{f.name}"
                 for f in _tb.extract_tb(e.__traceback__)][-4:]
        out, ошибка = None, f" ОШИБКА {type(e).__name__}: {str(e)[:100]} @ {кадры}"
    pr.disable()
    dt = time.perf_counter() - t0
    _on[0] = False
    q = sum(v[0] for v in STAT.values())
    print(f"\n### {имя}: {dt*1000:.0f} мс, SQL {q}{ошибка}")
    if профиль:
        st = pstats.Stats(pr)
        вызовы = []
        for (файл, стр, функ), (cc, nc, tt, ct, _) in st.stats.items():
            if функ in СЛЕДИТЬ and "sender" in файл:
                вызовы.append((ct, f"{функ} x{nc} = {ct*1000:.0f} мс"))
        for _, s in sorted(вызовы, reverse=True):
            print("    зовёт:", s)
        for k, (n, t) in sorted(STAT.items(), key=lambda kv: -kv[1][1])[:6]:
            print(f"    {t*1000:8.1f} мс x{n:<5} {k[:130]}")
    return out


res = прогон(f"/leads limit={LIMIT_L} (холодный)", lambda: ручки["/leads"](
    status=None, assigned_to=None, unassigned=False, reply_kind=None,
    napravlenie=None, limit=LIMIT_L, offset=0, p=P))
прогон(f"/leads limit={LIMIT_L} (повтор)", lambda: ручки["/leads"](
    status=None, assigned_to=None, unassigned=False, reply_kind=None,
    napravlenie=None, limit=LIMIT_L, offset=0, p=P), профиль=False)
лиды = (res or {}).get("leads") or []
print(f"\nлидов в ответе: {len(лиды)}")
for л in лиды[:3]:
    lid = л.get("id")
    прогон(f"/leads/{lid} (карточка)", lambda: ручки["/leads/{lead_id}"](lead_id=lid, p=P))
    прогон(f"/leads/{lid}/dialog", lambda: ручки["/leads/{lead_id}/dialog"](lead_id=lid, p=P))
    if "/leads/{lead_id}/ssylki" in ручки:
        прогон(f"/leads/{lid}/ssylki", lambda: ручки["/leads/{lead_id}/ssylki"](lead_id=lid, p=P))
print("\nEXPLAIN poslednie_otvety:", " | ".join(r[3] for r in raw_conn.execute(
    "EXPLAIN QUERY PLAN SELECT id FROM confirm_reviews WHERE kind='reply' AND "
    "status IN ('sent','approved') AND (inn IN (?,?) OR LOWER(COALESCE(email,'')) IN (?,?))",
    ("1", "2", "a", "b"))))
for lid in (718, 643, 623):
    print("контроль: лид", lid, "status =", raw_conn.execute(
        "SELECT status, updated_at FROM leads WHERE id=?", (lid,)).fetchone())
print("=== ГОТОВО ===")
