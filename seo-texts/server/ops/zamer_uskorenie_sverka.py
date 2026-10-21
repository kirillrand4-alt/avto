# -*- coding: utf-8 -*-
"""Сверка до/после ускорения /confirm/queue: снимок результата ручки и сравнение.

Запуск: zamer_uskorenie_sverka.py snimok <имя> | sravnit <имя1> <имя2>
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
import hashlib  # noqa: E402
import json  # noqa: E402
ПАПКА = r"C:\sender\server\ops"


def отпечаток(res):
    out = []
    for r in res["pending"]:
        sa = r.get("send_as") or {}
        letter = ((r.get("panel") or {}).get("letter") or {})
        out.append({
            "id": r.get("id"), "email": r.get("email"),
            "mailbox": sa.get("mailbox_id"), "division": sa.get("division"),
            "note": sa.get("note"),
            "options": [(o["mailbox_id"], o["available"]) for o in sa.get("options") or []],
            "mx": r.get("mx_provider"), "svoy": r.get("svoy_server"),
            "sent": r.get("sent"), "proverki": r.get("proverki"),
            "proverki_adresov": r.get("proverki_adresov"),
            "final_body": hashlib.md5(str(letter.get("final_body")).encode()).hexdigest(),
        })
    return {"rows": out, "counts": res.get("counts"), "total": res.get("total"),
            "corp_total": res.get("corp_total"), "blocked_hidden": res.get("blocked_hidden")}


def вызов(**kw):
    t0 = time.perf_counter()
    res = ep(campaign_id=None, limit=kw.get("limit", 50), offset=0,
             order=kw.get("order", "score"), division=kw.get("division"),
             gruppa=kw.get("gruppa"), hide_blocked=kw.get("hide", False),
             p=SimpleNamespace(user_id=0, username="zamer", role="owner"))
    return res, (time.perf_counter() - t0) * 1000


if РЕЖИМ == "snimok":
    имя = sys.argv[2]
    снимок, замеры = {}, {}
    настоящие = confirm.pending(limit=100000)
    гр = None
    try:
        все = store.recipient_groups().get("все") or []
        гр = все[0][0] if все else None
        t0 = time.perf_counter(); store.recipient_groups()
        замеры["groups_povtor_ms"] = round((time.perf_counter() - t0) * 1000)
        снимок["groups"] = все
    except Exception as e:  # noqa: BLE001
        print("groups:", e)
    for ключ, kw in (("score50", {}), ("id50", {"order": "id"}),
                     ("meyer50", {"division": "meyer"}), ("kc50", {"division": "kc"}),
                     ("hide50", {"hide": True}), ("gruppa50", {"gruppa": гр}),
                     ("badge1", {"limit": 1})):
        res, ms = вызов(**kw)
        снимок[ключ] = отпечаток(res)
        замеры[ключ + "_ms"] = round(ms)
    # 150 копий реальных писем — масштаб
    def _много():
        out = []
        for i in range(150):
            r = copy.deepcopy(настоящие[i % len(настоящие)])
            r["id"] = 10_000_000 + i
            out.append(r)
        return out
    _p = confirm.pending
    confirm.pending = lambda **kw: _много()
    for ключ, kw in (("x150_score50", {}), ("x150_score100", {"limit": 100}),
                     ("x150_badge1", {"limit": 1})):
        вызов(**kw)  # прогрев
        res, ms = вызов(**kw)
        снимок[ключ] = отпечаток(res)
        замеры[ключ + "_ms"] = round(ms)
    confirm.pending = _p
    try:
        from sender.api.app import make_app as _m  # noqa: F401
        ручки = [getattr(r, "path", "") for r in app.routes]
        замеры["est_confirm_counts"] = "/confirm/counts" in ручки
    except Exception:  # noqa: BLE001
        pass
    with io.open(os.path.join(ПАПКА, f"_sverka_{имя}.json"), "w", encoding="utf-8") as f:
        json.dump({"snimok": снимок, "zamery": замеры}, f, ensure_ascii=False,
                  default=str)
    print("замеры, мс:", json.dumps(замеры, ensure_ascii=False))
elif РЕЖИМ == "dvoynoy":
    # Старое и новое поведение В ОДНОМ процессе на ОДНОМ замороженном наборе
    # pending: очередь живая (генерация доливает письма), снимки «до/после»
    # с разницей в минуты сравнивать нечестно.
    import inspect as _insp
    замороженные = confirm.pending(limit=100000)
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    if N:
        база = замороженные
        замороженные = []
        for i in range(N):
            r = copy.deepcopy(база[i % len(база)])
            r["id"] = 10_000_000 + i
            замороженные.append(r)
    confirm.pending = lambda **kw: copy.deepcopy(замороженные)
    новый_send_as = confirm.send_as
    assert "kesh" in _insp.signature(новый_send_as).parameters, "новый код не загружен"

    def старый_send_as(row, *, prefer_division=None):
        return новый_send_as(row, prefer_division=prefer_division)
    новые_карты = (store.recipient_mx_map, store.recipient_groups)

    def режим(старый):
        if старый:
            confirm.send_as = старый_send_as
            store.recipient_mx_map = store._recipient_mx_map_bez_kesha
            store.recipient_groups = store._recipient_groups_bez_kesha
        else:
            confirm.send_as = новый_send_as
            store.recipient_mx_map, store.recipient_groups = новые_карты
    гр = (store._recipient_groups_bez_kesha().get("все") or [[None]])[0][0]
    print(f"pending в наборе: {len(замороженные)}")
    for ключ, kw in (("score50", {}), ("id50", {"order": "id"}),
                     ("meyer50", {"division": "meyer"}), ("kc50", {"division": "kc"}),
                     ("hide50", {"hide": True}), ("gruppa50", {"gruppa": гр}),
                     ("score100", {"limit": 100}), ("badge1", {"limit": 1})):
        режим(True); с0, _ = вызов(**kw); с, мс_с = вызов(**kw)
        режим(False); вызов(**kw); н, мс_н = вызов(**kw)
        а, б = отпечаток(с), отпечаток(н)
        а0 = отпечаток(с0)
        контроль = sum(1 for x, y in zip(а0["rows"], а["rows"]) if x != y)
        print(f"     контроль старый-vs-старый: строк с отличием {контроль}")
        for i, (x, y) in enumerate(zip(а["rows"], б["rows"])):
            if x.get("mailbox") != y.get("mailbox"):
                print(f"     строка{i} id={x['id']} ящик старый={x.get('mailbox')} "
                      f"новый={y.get('mailbox')} доступные_старый="
                      f"{sum(1 for o in x['options'] if o[1])} новый="
                      f"{sum(1 for o in y['options'] if o[1])}")
                break
        if а == б:
            итог = "СОВПАДАЕТ"
        else:
            разн = [f"{k}" for k in а if а[k] != б[k] and k != "rows"]
            for i, (x, y) in enumerate(zip(а["rows"], б["rows"])):
                for поле in x:
                    if x[поле] != y.get(поле):
                        разн.append(f"строка{i}.{поле}")
            итог = "РАЗЛИЧИЕ: " + ", ".join(разн[:8])
        print(f"  {ключ:<9} старый {мс_с:7.0f} мс | новый {мс_н:7.0f} мс | "
              f"писем {len(а['rows']):3d} | {итог}")
    режим(True)
    t0 = time.perf_counter(); store.recipient_groups(); t1 = time.perf_counter()
    режим(False); store.recipient_groups(); t2 = time.perf_counter(); store.recipient_groups()
    t3 = time.perf_counter()
    print(f"  /confirm/groups: старый {(t1-t0)*1000:.0f} мс | новый (повтор в 45 с) "
          f"{(t3-t2)*1000:.0f} мс | первый после сброса {(t2-t1)*1000:.0f} мс")
    t0 = time.perf_counter(); confirm.counts()
    print(f"  /confirm/counts (бейдж): {(time.perf_counter()-t0)*1000:.1f} мс")
elif РЕЖИМ == "sravnit":
    a, b = (json.load(io.open(os.path.join(ПАПКА, f"_sverka_{x}.json"),
                              encoding="utf-8")) for x in sys.argv[2:4])
    print("ДО   :", json.dumps(a["zamery"], ensure_ascii=False))
    print("ПОСЛЕ:", json.dumps(b["zamery"], ensure_ascii=False))
    for k in a["snimok"]:
        x, y = a["snimok"][k], b["snimok"].get(k)
        if x == y:
            print(f"  {k:<14} СОВПАДАЕТ ({len(x.get('rows', x)) if isinstance(x, dict) else len(x)})")
            continue
        print(f"  {k:<14} РАЗЛИЧИЕ:")
        if isinstance(x, dict):
            for поле in ("counts", "total", "corp_total", "blocked_hidden"):
                if x.get(поле) != y.get(поле):
                    print(f"     {поле}: {x.get(поле)} -> {y.get(поле)}")
            for i, (rx, ry) in enumerate(zip(x["rows"], y["rows"])):
                for поле in rx:
                    if rx[поле] != ry.get(поле):
                        print(f"     строка {i} id={rx['id']} {поле}: {str(rx[поле])[:120]} -> {str(ry.get(поле))[:120]}")
            if len(x["rows"]) != len(y["rows"]):
                print(f"     строк {len(x['rows'])} -> {len(y['rows'])}")
print("=== ГОТОВО ===")
