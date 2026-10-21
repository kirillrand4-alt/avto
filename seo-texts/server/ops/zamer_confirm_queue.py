# -*- coding: utf-8 -*-
"""Диагностика: почему долго грузится «Подтвердить отправку» (/confirm/queue).

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
    r"C:\seostat\drop\drop-storage\zamer_confirm_out.txt", "w", encoding="utf-8"))
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


# ---------- 3. полный вызов ручки ----------------------------------------- #
print(f"\n=== 2. ПОЛНЫЙ ВЫЗОВ /confirm/queue limit={LIMIT} order={ORDER} "
      f"division={DIV} ===")
for прогон in (1, 2):
    сброс()
    _on[0] = True
    t0 = time.perf_counter()
    res = вызвать()
    dt = time.perf_counter() - t0
    _on[0] = False
    import json as _j
    размер = len(_j.dumps(res, ensure_ascii=False, default=str))
    print(f"прогон {прогон}: {dt*1000:.0f} мс, писем в ответе "
          f"{len(res['pending'])}, total={res.get('total')}, JSON ответа "
          f"{размер/1e6:.2f} МБ")
печать_sql("последний прогон")

сброс()
pr = cProfile.Profile()
_on[0] = True
pr.enable()
вызвать()
pr.disable()
_on[0] = False
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(35)
print("\n--- cProfile (cumulative, топ-35) ---")
for line in s.getvalue().splitlines():
    if line.strip() and ("sender" in line or "ncalls" in line or "sqlite" in line
                         or "json" in line):
        print("  " + line.replace(r"C:\sender\sender" + "\\", "")[:200])

# ---------- 4. куски по отдельности --------------------------------------- #
print("\n=== 3. КУСКИ ===")


def зам(имя, fn, n=1):
    сброс()
    _on[0] = True
    t0 = time.perf_counter()
    for _ in range(n):
        out = fn()
    dt = (time.perf_counter() - t0) / n
    _on[0] = False
    q = sum(v[0] for v in STAT.values()) / n
    print(f"  {dt*1000:9.1f} мс  ({q:.0f} SQL)  {имя}")
    return out


rows = зам("confirm.pending(limit=100000) [SELECT * + json.loads panel_json]",
           lambda: confirm.pending(limit=100000))
зам("store.confirm_counts()", store.confirm_counts)
зам("store.recipient_mx_map() [скан recipients]", store.recipient_mx_map)
зам("confirm.letter_division x все pending",
    lambda: [confirm.letter_division(r) for r in rows])
стр = rows[:LIMIT]
зам("store.sent_flags(страница)", lambda: store.sent_flags(
    inns=[r.get("inn") for r in стр], emails=[r.get("email") for r in стр]))
try:
    from sender.proverki import собрать_карты
    зам("proverki.собрать_карты(все pending)", lambda: собрать_карты(store, rows))
except Exception as e:  # noqa: BLE001
    print("  собрать_карты:", e)
from datetime import datetime, timezone  # noqa: E402
now = datetime.now(timezone.utc)
mb0 = list(cfg.mailboxes())[0].mailbox_id
зам("gates.check_global() [2x COUNT events за окно]", gates.check_global, 20)
зам(f"gates.check_mailbox(один ящик)", lambda: gates.check_mailbox(mb0), 20)
зам("sender.can_send_now(один ящик, manual=True)",
    lambda: sender.can_send_now(mb0, now=now, manual=True), 20)
зам("store.last_sent_mailbox(among=все ящики)",
    lambda: store.last_sent_mailbox(
        among=[m.mailbox_id for m in cfg.mailboxes()]), 20)
if стр:
    r0 = стр[0]
    зам("cards.divisions(inn) одной строки",
        lambda: cards.divisions(r0.get("inn")) if hasattr(cards, "divisions")
        else cards.division(r0.get("inn")), 20)
    зам("confirm.send_as(одна строка)", lambda: confirm.send_as(r0), 5)
    зам(f"confirm.send_as x {len(стр)} строк страницы",
        lambda: [confirm.send_as(r) for r in стр])
    печать_sql("send_as по странице", 12)
    зам("_signature_for x страница", lambda: [
        _signature_for(deps, "Имя", campaign_id=r.get("campaign_id"),
                       division="kc") for r in стр])
    try:
        from sender.gender_agree import agree_for_mailbox
        зам("agree_for_mailbox x страница", lambda: [
            agree_for_mailbox(((r.get("panel") or {}).get("letter") or {})
                              .get("body") or "", "Имя", cfg, mb0) for r in стр])
    except Exception as e:  # noqa: BLE001
        print("  agree_for_mailbox:", e)

# ---------- 5. планы ------------------------------------------------------- #
print("\n=== 4. EXPLAIN QUERY PLAN ===")
since = "2026-10-07T00:00:00+00:00"
планы = {
    "count sent (check_global)":
        ("SELECT COUNT(*) FROM events e WHERE e.event_type=? AND e.event_ts>=?",
         ("sent", since)),
    "count sent по ящику (check_mailbox)":
        ("SELECT COUNT(*) FROM events e WHERE e.event_type=? AND e.mailbox_id=? "
         "AND e.event_ts>=?", ("sent", mb0, since)),
    "last_sent_mailbox":
        ("SELECT mailbox_id FROM events WHERE event_type IN ('sent','reply_sent') "
         "AND COALESCE(mailbox_id,'')<>'' AND mailbox_id IN (?,?) "
         "ORDER BY id DESC LIMIT 1", (mb0, mb0)),
    "confirm_list pending":
        ("SELECT * FROM confirm_reviews WHERE 1=1 AND status=? AND "
         "(updated_at >= ? OR kind='reply') ORDER BY id ASC LIMIT ? OFFSET ?",
         ("pending", "2000", 100000, 0)),
    "confirm_counts":
        ("SELECT status, COUNT(*) c FROM confirm_reviews GROUP BY status", ()),
    "reply_pending":
        ("SELECT COUNT(*) FROM confirm_reviews WHERE status='pending' "
         "AND kind='reply'", ()),
    "recover_stale_reviews (UPDATE→как SELECT)":
        ("SELECT id FROM confirm_reviews WHERE status='sending_live' "
         "AND updated_at <= ?", ("2026",)),
    "sent_flags":
        ("SELECT inn,email,ts,outcome FROM send_log WHERE inn IN (?,?) OR "
         "email IN (?,?) ORDER BY ts ASC", ("1", "2", "a@b", "c@d")),
    "bounce_hard (собрать_карты)":
        ("SELECT value FROM suppression WHERE reason='bounce_hard'", ()),
}
for имя, (sql, p) in планы.items():
    try:
        t0 = time.perf_counter()
        raw_conn.execute(sql, p).fetchall()
        dt = (time.perf_counter() - t0) * 1000
        план = " | ".join(r[3] for r in raw_conn.execute(
            "EXPLAIN QUERY PLAN " + sql, p))
        print(f"  [{dt:7.1f} мс] {имя}: {план}")
    except sqlite3.Error as e:
        print(f"  {имя}: ошибка {e}")

# ---------- 6. фронт: кто и как зовёт очередь ------------------------------ #
print("\n=== 5. ФРОНТ: вызовы confirmQueue ===")
for п, _д, фф in os.walk(r"C:\sender\sender\web\src"):
    if ".bak" in п or "node_modules" in п:
        continue
    for ф in фф:
        if not ф.endswith((".tsx", ".ts")) or ф == "client.ts":
            continue
        т = io.open(os.path.join(п, ф), encoding="utf-8", errors="replace").read()
        for i, line in enumerate(т.splitlines()):
            if re.search(r"confirmQueue\(|setInterval|refetchInterval|confirmGet\(",
                         line):
                print(f"  {ф}:{i+1}: {line.strip()[:160]}")
print("\n=== ГОТОВО ===")
