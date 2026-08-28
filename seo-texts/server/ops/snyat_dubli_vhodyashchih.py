# -*- coding: utf-8 -*-
"""Снять повторные записи одного и того же входящего письма.

Опрос по UID сменил ключ дедупликации (imap:{uidvalidity}:{ПОРЯДКОВЫЙ}:{вид} →
imap:{uidvalidity}:{UID}:{вид}): на ящиках, где порядковый номер не совпадает с
UID, старые письма легли в журнал ВТОРОЙ раз. Владелец 28.08: «26.08 есть дубли
ответов в статистике? а то я не помню что столько распределял там».

Одно письмо опознаём по Message-ID, а где его нет — по связке ящик + получатель
+ начало текста. Оставляем САМУЮ РАННЮЮ запись (на неё ссылаются лиды и ветки),
лишние удаляем, предварительно переставив ссылки лидов на оставшуюся.
"""
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
БАЗА = r"C:\sender\sender.db"
ТИПЫ = ("reply", "reply_auto", "bounce", "complaint", "dsn")
ЖУРНАЛ = r"C:\sender\_ops\snyatye-dubli-vhodyashchih.jsonl"

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
метки = ",".join("?" * len(ТИПЫ))
события = []
for r in c.execute("SELECT id, event_type, event_ts, mailbox_id, dedup_key, "
                   "       recipient_id, detail_json FROM events "
                   " WHERE event_type IN (%s) AND event_ts >= '2026-07-01'" % метки,
                   list(ТИПЫ)):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    h = d.get("headers") or {}
    события.append(dict(
        id=r["id"], тип=r["event_type"], ts=str(r["event_ts"] or ""),
        ящик=str(r["mailbox_id"] or ""), ключ=str(r["dedup_key"] or ""),
        rid=r["recipient_id"],
        msgid=str(h.get("Message-ID") or "").strip(),
        тема=str(h.get("Subject") or "").strip()[:120],
        текст=" ".join(str(d.get("snippet") or "").split())[:200],
        свежая="zapisano_ts" in d))
print("входящих событий с 01.07: %d" % len(события))

# группы «одно и то же письмо». Message-ID — приговор сам по себе. Где его нет,
# сверяем ящик + получателя + начало текста И держим окно в 6 часов: один и тот
# же автоответчик отвечает одинаково и на второе наше письмо через неделю — это
# два РАЗНЫХ события, а не дубль. Дубль же расходится максимум на один интервал
# опроса: старая запись помечена «когда заметили», новая — датой письма.
ОКНО_ЧАСОВ = 6


def _секунды(ts: str) -> float:
    т = str(ts or "")[:19].replace("T", " ")
    try:
        return time.mktime(time.strptime(т, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return 0.0


группы = defaultdict(list)
for э in события:
    if э["msgid"]:
        ключ = ("mid", э["ящик"], э["msgid"])
    elif э["текст"]:
        ключ = ("txt", э["ящик"], str(э["rid"]), э["текст"])
    else:
        continue
    группы[ключ].append(э)

лишние, по_дням, по_типам, по_ключу = [], defaultdict(int), defaultdict(int), defaultdict(int)
разошлись = 0
for ключ, список in группы.items():
    if len(список) < 2:
        continue
    список.sort(key=lambda x: x["id"])
    оставить = список[0]
    for э in список[1:]:
        # Один день ИЛИ шесть часов. Двух окон надо два, потому что копии
        # разъезжаются по-разному: у писем чужих дней обе записи несут дату
        # письма и расходятся на минуты, а у СЕГОДНЯШНИХ обе несут «когда
        # заметили» — утренний опрос и доскрёб, между ними полсуток.
        свой_день = э["ts"][:10] == оставить["ts"][:10]
        if ключ[0] == "txt" and not свой_день and abs(
                _секунды(э["ts"]) - _секунды(оставить["ts"])) > ОКНО_ЧАСОВ * 3600:
            разошлись += 1
            continue
        лишние.append((э, оставить))
        по_дням[э["ts"][:10]] += 1
        по_типам[э["тип"]] += 1
        по_ключу[ключ[0]] += 1
print("совпал текст, но разошлись во времени (оставляем оба): %d" % разошлись)
print("лишних записей: %d (по Message-ID %d, по тексту %d)"
      % (len(лишние), по_ключу["mid"], по_ключу["txt"]))
print("  по типам: %s" % dict(по_типам))
print("  по дням:  %s" % dict(sorted(по_дням.items())))

# сколько из лишних — сегодняшний доскрёб, а сколько старые
свежих = sum(1 for э, _ in лишние if э["свежая"])
print("  из них принесены сегодняшним доскрёбом: %d, были и раньше: %d"
      % (свежих, len(лишние) - свежих))

ид = [э["id"] for э, _ in лишние]
if ид:
    м = ",".join("?" * len(ид))
    n = c.execute("SELECT COUNT(*) FROM leads WHERE source_event_id IN (%s)" % м,
                  ид).fetchone()[0]
    print("  на них ссылается лидов: %d" % n)
c.close()

print("\n=== что останется в сводке ===")
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
снять = set(ид)
print("%-12s %6s %7s %7s" % ("день", "отпр", "bounce", "ответы"))
for i in range(6, -1, -1):
    д = time.strftime("%Y-%m-%d", time.gmtime(time.time() - i * 86400))
    отпр = c.execute("SELECT COUNT(*) FROM events WHERE event_type='sent' "
                     "  AND event_ts LIKE ?", (д + "%",)).fetchone()[0]
    зн = {}
    for тип in ("bounce", "reply"):
        строки = [x[0] for x in c.execute(
            "SELECT id FROM events WHERE event_type=? AND event_ts LIKE ?",
            (тип, д + "%"))]
        зн[тип] = len([x for x in строки if x not in снять])
    print("%-12s %6d %7d %7d" % (д, отпр, зн["bounce"], зн["reply"]))
c.close()

print("\n=== ОТБИВКИ ПО ДОМЕНАМ (без дублей) ===")
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
по_домену = defaultdict(list)
for r in c.execute(
        "SELECT e.id, e.event_ts, r.email, r.inn FROM events e "
        "  LEFT JOIN recipients r ON r.id = e.recipient_id "
        " WHERE e.event_type='bounce' AND e.event_ts >= '2026-08-22'"):
    if r["id"] in снять:
        continue
    почта = str(r["email"] or "")
    if "@" not in почта:
        continue
    по_домену[почта.split("@")[-1].lower()].append(
        (почта, str(r["event_ts"])[:10], r["inn"]))
повторные = {д: v for д, v in по_домену.items() if len(v) > 1}
адресов = sum(len(v) for v in повторные.values())
print("доменов всего: %d, из них с двумя и более отбивками: %d (%d отбивок)"
      % (len(по_домену), len(повторные), адресов))
print("лишних отбивок из-за повторов: %d"
      % (адресов - len(повторные)))
разные = sum(1 for v in повторные.values()
             if len({а for а, _, _ in v}) > 1)
print("  из них по РАЗНЫМ адресам домена: %d, по одному и тому же: %d"
      % (разные, len(повторные) - разные))
for д, v in sorted(повторные.items(), key=lambda x: -len(x[1]))[:20]:
    print("  %-26s %d :: %s" % (д, len(v),
                                ", ".join("%s %s" % (а.split("@")[0], дн)
                                          for а, дн, _ in v[:6])))
c.close()

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit удалю лишние")
    raise SystemExit(0)

from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
ж = open(ЖУРНАЛ, "a", encoding="utf-8")
удалено = перевязано = 0
try:
    with store.transaction() as conn:
        for э, оставить in лишние:
            перевязано += conn.execute(
                "UPDATE leads SET source_event_id=? WHERE source_event_id=?",
                (оставить["id"], э["id"])).rowcount
            строка = conn.execute("SELECT * FROM events WHERE id=?",
                                  (э["id"],)).fetchone()
            ж.write(json.dumps({"udalyon": dict(строка),
                                "ostavlen": оставить["id"]},
                               ensure_ascii=False, default=str) + "\n")
            conn.execute("DELETE FROM events WHERE id=?", (э["id"],))
            удалено += 1
    ж.flush()
    os.fsync(ж.fileno())
finally:
    ж.close()
print("\nудалено дублей: %d, лидов перевязано: %d (журнал %s)"
      % (удалено, перевязано, ЖУРНАЛ))

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
print("\n=== ДИНАМИКА 7 ДНЕЙ ===")
print("%-12s %6s %7s %8s %7s %8s" % ("день", "отпр", "bounce", "жалобы",
                                     "ответы", "BR%"))
for i in range(6, -1, -1):
    д = time.strftime("%Y-%m-%d", time.gmtime(time.time() - i * 86400))
    зн = {}
    for тип in ("sent", "bounce", "complaint", "reply"):
        зн[тип] = c.execute("SELECT COUNT(*) FROM events WHERE event_type=? "
                            "  AND event_ts LIKE ?", (тип, д + "%")).fetchone()[0]
    br = (100.0 * зн["bounce"] / зн["sent"]) if зн["sent"] else 0.0
    print("%-12s %6d %7d %8d %7d %7.2f%%"
          % (д, зн["sent"], зн["bounce"], зн["complaint"], зн["reply"], br))
c.close()
