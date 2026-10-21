# -*- coding: utf-8 -*-
"""п.6 на КОПИИ базы: индексы confirm_reviews — время построения (init_schema нового
кода), ускорение и совпадение ответов GET-ручек ленты. Боевую базу только читает
(backup API), копию удаляет в конце.
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
    r"C:\seostat\drop\drop-storage\zamer_p6_out.txt", "w", encoding="utf-8"))
_cfg_path = r"C:\sender\config.yaml" if os.path.exists(r"C:\sender\config.yaml") \
    else r"C:\sender\sender.yaml"
cfg = Config.load(_cfg_path)
БОЕВАЯ = cfg.get("service.db_path", r"C:\sender\sender.db")
db_path = r"C:\sender\server\ops\_kopiya_p6.db"
import shutil as _sh  # noqa: E402
_своб = _sh.disk_usage(os.path.dirname(db_path)).free
_разм = os.path.getsize(БОЕВАЯ)
print(f"боевая {_разм/1e6:.0f} МБ, свободно {_своб/1e9:.1f} ГБ")
if _своб < 3 * _разм:
    print("СТОП: мало места под копию"); sys.exit(0)
for _х in ("", "-wal", "-shm"):
    if os.path.exists(db_path + _х):
        os.remove(db_path + _х)
_t0 = time.perf_counter()
_src = sqlite3.connect(f"file:{БОЕВАЯ}?mode=ro", uri=True)
_dst = sqlite3.connect(db_path)
_src.backup(_dst)
_dst.close(); _src.close()
print(f"копия базы снята за {time.perf_counter()-_t0:.1f} с")
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




import json  # noqa: E402
P = SimpleNamespace(user_id=0, username="zamer", role="owner")
ids = [r[0] for r in raw_conn.execute("SELECT id FROM leads ORDER BY id DESC LIMIT 12")]
ПЛАНЫ = {
    "poslednie_otvety": ("SELECT id FROM confirm_reviews WHERE kind='reply' AND status IN "
                         "('sent','approved') AND (inn IN (?,?) OR LOWER(COALESCE(email,'')) IN (?,?))",
                         ("1", "2", "a", "b")),
    "dialog: по message_id": ("SELECT COALESCE(cr.edited_body, cr.body) FROM confirm_reviews cr "
                              "WHERE cr.message_id = ? ORDER BY cr.id DESC LIMIT 1", (1,)),
    "dialog: message_id IS NULL+email": ("SELECT 1 FROM confirm_reviews cr WHERE cr.message_id IS NULL "
                                         "AND lower(cr.email) = lower(?) AND cr.campaign_id IS ? "
                                         "ORDER BY cr.id DESC LIMIT 1", ("a@b", 1)),
    "panel_dlya_lida": ("SELECT * FROM confirm_reviews WHERE panel_json IS NOT NULL AND "
                        "(replace(replace(ifnull(inn,''),' ',''),'-','') = ? OR lower(email) = ?) "
                        "ORDER BY id DESC LIMIT 1", ("1", "a@b")),
}


def прогнать(метка):
    out, вр = {}, {}

    def зам(ключ, fn, n=3):
        лучш = None
        for _ in range(n):
            t0 = time.perf_counter()
            r = fn()
            dt = (time.perf_counter() - t0) * 1000
            лучш = dt if лучш is None else min(лучш, dt)
        out[ключ] = json.dumps(r, ensure_ascii=False, sort_keys=True, default=str)
        вр[ключ] = лучш
    зам("/leads", lambda: ручки["/leads"](status=None, assigned_to=None, unassigned=False,
                                           reply_kind=None, napravlenie=None, limit=100,
                                           offset=0, p=P))
    for lid in ids:
        зам(f"/leads/{lid}", lambda: ручки["/leads/{lead_id}"](lead_id=lid, p=P))
        зам(f"/leads/{lid}/dialog", lambda: ручки["/leads/{lead_id}/dialog"](lead_id=lid, p=P))
    print(f"\n=== {метка} ===")
    print(f"  /leads: {вр['/leads']:.0f} мс")
    карт = [v for k, v in вр.items() if k.count("/") == 2 and not k.endswith("dialog")]
    диал = [v for k, v in вр.items() if k.endswith("/dialog")]
    print(f"  карточка /leads/{{id}} ({len(карт)} лидов): средн {sum(карт)/len(карт):.0f} мс, макс {max(карт):.0f} мс")
    print(f"  /leads/{{id}}/dialog ({len(диал)}): средн {sum(диал)/len(диал):.0f} мс, макс {max(диал):.0f} мс")
    for имя, (sql, p) in ПЛАНЫ.items():
        t0 = time.perf_counter(); raw_conn.execute(sql, p).fetchall()
        dt = (time.perf_counter() - t0) * 1000
        план = " | ".join(r[3] for r in raw_conn.execute("EXPLAIN QUERY PLAN " + sql, p))
        print(f"  [{dt:6.1f} мс] {имя}: {план}")
    return out, вр


до, вр_до = прогнать("ДО индексов (копия)")
st2 = Store(db_path)
t0 = time.perf_counter()
st2.init_schema()          # код с правкой п.6: CREATE INDEX IF NOT EXISTS
print(f"\ninit_schema на копии (с построением индексов): {(time.perf_counter()-t0):.1f} с")
print("  индексы confirm_reviews:", [r[1] for r in st2._conn.execute("PRAGMA index_list(confirm_reviews)")])
st2._conn.close()
после, вр_после = прогнать("ПОСЛЕ индексов (копия)")
разн = [k for k in до if до[k] != после.get(k)]
print(f"\nсверка ответов ручек: {len(до)} ответов, различий {len(разн)}" +
      (f": {разн[:10]}" if разн else " — СОВПАДАЮТ"))
raw_conn.close()
store._conn = raw_conn
for _х in ("", "-wal", "-shm"):
    try:
        os.remove(db_path + _х)
    except OSError:
        pass
print("копия удалена:", not os.path.exists(db_path))
print("=== ГОТОВО ===")
