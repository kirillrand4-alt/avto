# -*- coding: utf-8 -*-
"""Диагностика (масштаб+эффект правок): почему долго грузится «Подтвердить отправку» (/confirm/queue).

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
    r"C:\seostat\drop\drop-storage\zamer_confirm_out2.txt", "w", encoding="utf-8"))
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


# ---------- 1. размеры и индексы ------------------------------------------- #
print("\n=== 1. ТАБЛИЦЫ ===")
for т in ("confirm_reviews", "messages", "send_log", "events", "recipients",
          "suppression", "addr_probe", "target_verdicts", "mailbox_state",
          "campaigns", "audit_log"):
    try:
        n = raw_conn.execute(f"SELECT COUNT(*) FROM {т}").fetchone()[0]
        инд = [r[1] for r in raw_conn.execute(f"PRAGMA index_list({т})")]
        print(f"  {т:<16} {n:>9}  индексы: {', '.join(инд) or '-'}")
    except sqlite3.Error as e:
        print(f"  {т:<16} ошибка: {e}")
for st, n in raw_conn.execute(
        "SELECT status, COUNT(*) FROM confirm_reviews GROUP BY status"):
    print(f"    confirm_reviews[{st}] = {n}")
r = raw_conn.execute(
    "SELECT COUNT(*), SUM(LENGTH(panel_json)), MAX(LENGTH(panel_json)) "
    "FROM confirm_reviews WHERE status='pending'").fetchone()
print(f"  pending: {r[0]} шт, panel_json всего {(r[1] or 0)/1e6:.1f} МБ, "
      f"макс {(r[2] or 0)/1e3:.0f} КБ")
for et, n in raw_conn.execute(
        "SELECT event_type, COUNT(*) FROM events GROUP BY event_type "
        "ORDER BY 2 DESC LIMIT 8"):
    print(f"    events[{et}] = {n}")
print("  размер файла БД: %.0f МБ" % (os.path.getsize(db_path) / 1e6))

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
deps = Deps(config=cfg, store=store, auth=Auth(store), leaddesk=None,
            analytics=None, gates=gates, sender=sender, suppression=supp,
            confirm=confirm, cards=cards)
app = make_app(deps)
ep = next(r.endpoint for r in app.routes
          if getattr(r, "path", "") == "/confirm/queue")
print(f"\nсборка deps+app: {(time.perf_counter()-t0)*1000:.0f} мс; "
      f"ящиков в конфиге: {len(list(cfg.mailboxes()))}; cards.active={cards.active}")


def вызвать():
    return ep(campaign_id=None, limit=LIMIT, offset=0, order=ORDER,
              division=DIV, gruppa=None, hide_blocked=False,
              p=SimpleNamespace(user_id=0, username="zamer", role="owner"))



# ---------- масштаб и эффект исправлений --------------------------------- #
import copy  # noqa: E402
настоящие = confirm.pending(limit=100000)
N = int(os.environ.get("ZAMER_N", "150"))
def _много():
    out = []
    i = 0
    while len(out) < N and настоящие:
        r = copy.deepcopy(настоящие[i % len(настоящие)])
        r["id"] = 10_000_000 + len(out)
        out.append(r)
        i += 1
    return out
confirm.pending = lambda **kw: _много()


def прогон(имя, **kw):
    сброс()
    _on[0] = True
    t0 = time.perf_counter()
    res = ep(campaign_id=None, limit=kw.get("limit", 50), offset=0,
             order=kw.get("order", "score"), division=kw.get("division"),
             gruppa=kw.get("gruppa"), hide_blocked=False,
             p=SimpleNamespace(user_id=0, username="zamer", role="owner"))
    dt = time.perf_counter() - t0
    _on[0] = False
    q = sum(v[0] for v in STAT.values())
    print(f"  {dt*1000:8.0f} мс  {q:6d} SQL  писем {len(res['pending']):3d}  {имя}")
    return dt


print(f"\n=== МАСШТАБ: pending подменён на {N} копий реальных писем ===")
прогон("как есть, limit=50 (страница оператора)")
прогон("как есть, limit=1 (бейдж в меню, раз в 60 с)", limit=1)
прогон("как есть, limit=100 («показать ещё»)", limit=100)
прогон("как есть, limit=50 division=meyer", division="meyer")
t0 = time.perf_counter()
try:
    g = store.recipient_groups()
    print(f"  {(time.perf_counter()-t0)*1000:8.0f} мс  /confirm/groups "
          f"(recipient_groups, групп {len(g.get('все') or [])})")
except Exception as e:  # noqa: BLE001
    print("  recipient_groups:", e)

print("\n=== ЭФФЕКТ ПРЕДЛАГАЕМЫХ ПРАВОК (имитация в памяти, код панели не меняется) ===")
# (а) can_send_now один раз на ящик за запрос (результат не зависит от письма)
_orig = sender.can_send_now
_кэш = {}
def _can(mid, *, now, manual=False, force=False):
    k = (mid, manual, force)
    if k not in _кэш:
        _кэш[k] = _orig(mid, now=now, manual=manual, force=force)
    return _кэш[k]
sender.can_send_now = _can
_кэш.clear(); прогон("(а) can_send_now кэш на запрос, limit=50")
# (б) + карта MX получателей из кэша (TTL), а не скан recipients на каждый запрос
_mx = store.recipient_mx_map()
_orig_mx = store.recipient_mx_map
store.recipient_mx_map = lambda: _mx
_кэш.clear(); прогон("(а)+(б) + recipient_mx_map из кэша, limit=50")
# (в) + bounce_hard-набор из кэша — оценка отдельно
t0 = time.perf_counter()
raw_conn.execute("SELECT value FROM suppression WHERE reason='bounce_hard'").fetchall()
print(f"  справка: SELECT bounce_hard (весь набор) = {(time.perf_counter()-t0)*1000:.0f} мс на запрос")
_кэш.clear(); прогон("(а)+(б), limit=1 (бейдж)", limit=1)
print("\n=== ГОТОВО ===")
