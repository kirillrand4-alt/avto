# -*- coding: utf-8 -*-
"""Сверка п.5 (убрать подбор оборудования по ОКВЭД из очереди) на ЗАМОРОЖЕННОМ наборе.

Запуск: zamer_p5_sverka.py zamorozit | snimok <имя> | sravnit <имя1> <имя2>
Снимок пишется в C:\\sender\\server\\ops\\_sverka_<имя>.json (не в базы).

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

РЕЖИМ = sys.argv[1] if len(sys.argv) > 1 else ""

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





import copy  # noqa: E402
import json  # noqa: E402
ПАПКА = r"C:\sender\server\ops"
ЗАМОРОЗКА = os.path.join(ПАПКА, "_p5_frozen.json")
ПОЛЯ_ПОДСКАЗКИ = ("equip_needed", "equip_needed_basis")


def отпечаток(res):
    out = []
    for r in res["pending"]:
        sa = r.get("send_as") or {}
        п = r.get("panel") or {}
        comp = dict(п.get("company") or {})
        подсказка = {k: comp.pop(k, None) for k in ПОЛЯ_ПОДСКАЗКИ}
        letter = п.get("letter") or {}
        out.append({
            "id": r.get("id"), "email": r.get("email"),
            "mailbox": sa.get("mailbox_id"), "letter_division": sa.get("letter_division"),
            "division": sa.get("division"), "note": sa.get("note"),
            "options": [(o["mailbox_id"], o["available"]) for o in sa.get("options") or []],
            "actions": п.get("actions"), "flags": п.get("flags"),
            "company_bez_podskazki": comp,
            "mx": r.get("mx_provider"), "svoy": r.get("svoy_server"),
            "sent": r.get("sent"), "proverki": r.get("proverki"),
            "final_body": letter.get("final_body"),
            "_podskazka": подсказка,
        })
    return {"rows": out, "total": res.get("total"), "corp_total": res.get("corp_total")}


def вызов(**kw):
    t0 = time.perf_counter()
    res = ep(campaign_id=None, limit=kw.get("limit", 50), offset=0,
             order=kw.get("order", "score"), division=kw.get("division"),
             gruppa=None, hide_blocked=kw.get("hide", False),
             p=SimpleNamespace(user_id=0, username="zamer", role="owner"))
    return res, (time.perf_counter() - t0) * 1000


if РЕЖИМ == "zamorozit":
    rows = confirm.pending(limit=100000)
    with io.open(ЗАМОРОЗКА, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, default=str)
    print("заморожено писем:", len(rows))
elif РЕЖИМ == "snimok":
    имя = sys.argv[2]
    замороженные = json.load(io.open(ЗАМОРОЗКА, encoding="utf-8"))
    confirm.pending = lambda **kw: copy.deepcopy(замороженные)
    снимок, замеры = {}, {}
    for ключ, kw in (("score50", {}), ("kc50", {"division": "kc"}),
                     ("meyer50", {"division": "meyer"}), ("hide50", {"hide": True}),
                     ("score_vse", {"limit": 1000})):
        res, ms = вызов(**kw)
        замеры[ключ + "_ms"] = round(ms)   # первый = холодный для score50
        снимок[ключ] = отпечаток(res)
    with io.open(os.path.join(ПАПКА, f"_p5_{имя}.json"), "w", encoding="utf-8") as f:
        json.dump({"snimok": снимок, "zamery": замеры}, f, ensure_ascii=False, default=str)
    print(f"писем в наборе {len(замороженные)}; замеры, мс:", json.dumps(замеры, ensure_ascii=False))
elif РЕЖИМ == "sravnit":
    a, b = (json.load(io.open(os.path.join(ПАПКА, f"_p5_{x}.json"), encoding="utf-8"))
            for x in sys.argv[2:4])
    print("A:", json.dumps(a["zamery"], ensure_ascii=False))
    print("B:", json.dumps(b["zamery"], ensure_ascii=False))
    for k in a["snimok"]:
        x, y = a["snimok"][k], b["snimok"][k]
        разн, подск = [], 0
        if [r["id"] for r in x["rows"]] != [r["id"] for r in y["rows"]]:
            разн.append("СОСТАВ/ПОРЯДОК")
        for поле in ("total", "corp_total"):
            if x[поле] != y[поле]:
                разн.append(поле)
        for rx, ry in zip(x["rows"], y["rows"]):
            for поле in rx:
                if поле == "_podskazka":
                    if rx[поле] != ry[поле]:
                        подск += 1
                elif rx[поле] != ry.get(поле):
                    разн.append(f"id{rx['id']}.{поле}")
        с_подск_a = sum(1 for r in x["rows"] if (r["_podskazka"] or {}).get("equip_needed"))
        с_подск_b = sum(1 for r in y["rows"] if (r["_podskazka"] or {}).get("equip_needed"))
        print(f"  {k:<10} писем {len(x['rows']):3d} | прочие поля: "
              f"{'СОВПАДАЮТ' if not разн else 'РАЗЛИЧИЕ ' + ', '.join(разн[:8])} | "
              f"подсказка отличается у {подск} (с подсказкой: {с_подск_a} -> {с_подск_b})")
print("=== ГОТОВО ===")
