# -*- coding: utf-8 -*-
"""Размеренная отправка напоминаний пилота (владелец 26.10: «не могу протолкнуть
их» — кнопка «В автоотправку» карточки-ответы kind=reply не берёт, у них только
ручное «Отправить» = немедленная отправка). Отсоединённый процесс жмёт штатный
approve по одной карточке:
  * только карточки пилота (_ops/napominaniya-pilot.jsonl), ещё pending;
  * ящик не на паузе, у ящика за сегодня меньше дневного лимита (send_limits
    per_mailbox, иначе 70) — send_reply сам лимиты не смотрит;
  * рабочее окно получателя: будни, 09:00-18:00 по Москве;
  * между письмами случайно 40-90 с, один ящик не чаще раза в 150 с.
Журнал _ops/otpravka-napominaniy.jsonl (fsync), стоп — файл _ops/otpravka-napominaniy.STOP.
    otpravka_napominaniy.py --sukhoy | --zapusk"""
import io
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

ЖУР = r"C:\sender\_ops\otpravka-napominaniy.jsonl"
СТОП = r"C:\sender\_ops\otpravka-napominaniy.STOP"
if "--zapusk" in sys.argv:
    л = io.open(r"C:\sender\_ops\otpravka-napominaniy.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--rabota"], cwd=r"C:\sender",
                         stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(10)
    print("запущен, pid %d, жив %s" % (п.pid, п.poll() is None))
    sys.exit(0)

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402

МСК = timezone(timedelta(hours=3))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def карточки():
    з = [json.loads(s) for s in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8")]
    out = []
    for x in з:
        r = store._conn.execute("SELECT status FROM confirm_reviews WHERE id=?", (x.get("karta"),)).fetchone()
        if r and r[0] == "pending":
            out.append((x["karta"], x["mailbox"], x["email"]))
    return out


def лимит(mb):
    сл = store.get_setting("send_limits") or {}
    if isinstance(сл, str):
        сл = json.loads(сл or "{}")
    return int((сл.get("per_mailbox") or {}).get(mb) or 70)


def ушло_сегодня(mb):
    s = store.get_mailbox_state(mb)
    if not s:
        return 0, False
    посл = str(getattr(s, "last_sent_at", "") or "")
    сегодня = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (int(getattr(s, "sent_today", 0) or 0) if посл[:10] == сегодня else 0), bool(getattr(s, "paused", False))


def окно():
    т = datetime.now(МСК)
    return т.weekday() < 5 and 9 <= т.hour < 18


if "--sukhoy" in sys.argv or "--rabota" not in sys.argv:
    к = карточки()
    from collections import Counter
    по_ящ = Counter(mb for _, mb, _ in к)
    print("pending карточек пилота:", len(к), "| окно сейчас:", окно())
    for mb, n in по_ящ.most_common():
        у, п = ушло_сегодня(mb)
        print("  %-38s карточек %3d | ушло сегодня %3d из %d | пауза %s" % (mb, n, у, лимит(mb), п))
    sys.exit(0)

deps = build_deps(cfg, store, dry_run=False)
ж = io.open(ЖУР, "a", encoding="utf-8")
последний = {}
print(time.strftime("%H:%M:%S"), "старт", flush=True)
while not os.path.exists(СТОП):
    к = карточки()
    if not к:
        print(time.strftime("%H:%M:%S"), "все напоминания разобраны — конец", flush=True)
        break
    if not окно():
        time.sleep(600)
        continue
    сейчас = time.time()
    годные = []
    for kid, mb, em in к:
        у, п = ушло_сегодня(mb)
        if п or у >= лимит(mb) or сейчас - последний.get(mb, 0) < 150:
            continue
        годные.append((kid, mb, em))
    if not годные:
        time.sleep(60)
        continue
    kid, mb, em = random.choice(годные)
    запись = {"karta": kid, "mailbox": mb, "email": em, "ts": datetime.now(timezone.utc).isoformat()}
    try:
        запись["ok"] = bool(deps.confirm.approve(kid, operator="kirill (через Claude, 26.10: протолкнуть напоминания пилота)"))
    except Exception as ex:  # noqa: BLE001
        запись["ok"], запись["oshibka"] = False, str(ex)[:300]
    r = store._conn.execute("SELECT status FROM confirm_reviews WHERE id=?", (kid,)).fetchone()
    запись["status"] = r[0] if r else "?"
    ж.write(json.dumps(запись, ensure_ascii=False) + "\n")
    ж.flush()
    os.fsync(ж.fileno())
    print(time.strftime("%H:%M:%S"), kid, mb, em, запись["status"], запись.get("oshibka", ""), flush=True)
    последний[mb] = time.time()
    if not запись["ok"] and запись["status"] == "pending":
        # не ушло и осталось pending — не долбим ту же карточку подряд
        последний[mb] = time.time() + 1800
    time.sleep(random.uniform(40, 90))
print(time.strftime("%H:%M:%S"), "стоп", flush=True)
