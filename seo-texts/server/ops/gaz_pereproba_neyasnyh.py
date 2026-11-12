# -*- coding: utf-8 -*-
"""Повторная проба адресов, снятых из кампании 22 за «неясно»/«отказ пробе» (владелец 12.11: вариант 3).
  * отказы из-за нашей обратной записи (PTR/hostname) — не перепробуем: без PTR ответ будет тот же;
  * MX для ВСЕХ адресов берём через DNS-over-HTTPS (dns.google, запасной cloudflare): 12.11 на сервере включён туннель
    Happ (xray), его DNS 172.19.0.2 на MX-запросы не отвечает вовсе (даже для mail.ru), а UDP к 8.8.8.8 перехватывается;
    MX не нашёлся и по DoH — приговор НЕ выносим, остаётся «неясно»;
  * таймауты, обрывы, прочие отказы — проба заново с ожиданием 45 с, HELO = parsercompressor.online (имя ведёт на наш IP).
Новый вердикт пишется в три базы (addr_probe, enrich.emails, obzvon email_probe). «есть»/«принимает всё» — карточку
возвращаем в прежнее состояние (одобрена → сообщение снова в расписании; ждала — снова ждёт). Прочие остаются снятыми.
Журнал _ops/gaz-pereproba-neyasnyh.jsonl (резюмируемо).   gaz_pereproba_neyasnyh.py --zapusk [--zanovo] [--bez-vozvrata]"""
import io, json, os, re, sqlite3, subprocess, sys, time
from collections import Counter
from datetime import datetime, timezone
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "gaz-pereproba-neyasnyh.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, r"C:\sender")
from sender.addr_probe import AddrProbe   # noqa: E402
ЖУР = os.path.join(ОПС, "gaz-pereproba-neyasnyh.jsonl")
БД = r"C:\sender\sender.db"
сделано = set()
if "--zanovo" in sys.argv and os.path.exists(ЖУР):
    os.rename(ЖУР, ЖУР + ".%d" % int(time.time()))
if os.path.exists(ЖУР):
    for с in io.open(ЖУР, encoding="utf-8"):
        try: сделано.add(json.loads(с)["email"])
        except (ValueError, KeyError): pass
снятые = {}
for с in io.open(os.path.join(ОПС, "gaz-snyat-neyasnye.jsonl"), encoding="utf-8"):
    з = json.loads(с); снятые[з["email"]] = з
c = sqlite3.connect(БД, timeout=60)
ответы = {em: a for em, a in c.execute("SELECT lower(email), COALESCE(answer,'') FROM addr_probe")}
проба = AddrProbe(БД, helo="parsercompressor.online", timeout=45.0, pause_sec=3.0, per_domain=10 ** 6)


def mx_doh(домен):
    import urllib.request
    for урл in ("https://dns.google/resolve?name=%s&type=MX", "https://cloudflare-dns.com/dns-query?name=%s&type=MX"):
        try:
            з = urllib.request.Request(урл % домен, headers={"accept": "application/dns-json"})
            д = json.load(urllib.request.urlopen(з, timeout=20))
            мх = sorted((int(a["data"].split()[0]), a["data"].split()[-1].rstrip(".")) for a in д.get("Answer", []) if a.get("type") == 15)
            мх = [х for _, х in мх if х]
            return (мх[0] if мх else None), урл.split("/")[2]
        except Exception:  # noqa: BLE001
            continue
    return None, "DoH не ответил"


def в_базы(адрес, вер, ответ_):
    ts = int(time.time())
    try:
        cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60); cx.execute("PRAGMA busy_timeout=60000")
        cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=?, probe_answer=? WHERE lower(email)=?", (вер, ts, str(ответ_)[:300], адрес))
        cx.commit(); cx.close()
    except Exception as ex: print("enrich: %s" % str(ex)[:80], flush=True)  # noqa: BLE001,E701
    try:
        ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
        ox.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT PRIMARY KEY, verdict TEXT, source TEXT, answer TEXT, ts INTEGER)")
        ox.execute("INSERT INTO email_probe (email, verdict, source, answer, ts) VALUES (?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                   "verdict=excluded.verdict, answer=excluded.answer, ts=excluded.ts", (адрес, вер, "smtp-server", str(ответ_)[:300], ts))
        ox.commit(); ox.close()
    except Exception as ex: print("обзвон: %s" % str(ex)[:80], flush=True)  # noqa: BLE001,E701


def вернуть(з):
    for _п in range(12):
        try:
            т = datetime.now(timezone.utc).isoformat(timespec="seconds")
            р = c.execute("SELECT status, message_id FROM confirm_reviews WHERE id=?", (з["karta"],)).fetchone()
            if not р or р[0] != "skipped": return "карточка уже не снята"
            c.execute("UPDATE confirm_reviews SET status=?, reason=NULL, updated_at=? WHERE id=?", (з["byl_status"], т, з["karta"]))
            if р[1]:
                c.execute("UPDATE messages SET status=?, last_error=NULL WHERE id=? AND status='skipped'",
                          ("scheduled" if з["byl_status"] == "approved" else "pending_review", р[1]))
            c.commit(); return "возвращена (%s)" % з["byl_status"]
        except sqlite3.OperationalError as ex:
            if "locked" not in str(ex): raise
            time.sleep(10)
    return "база занята"


сч = Counter()
for адрес, з in снятые.items():
    if адрес in сделано: continue
    а = ответы.get(адрес, "")
    if re.search(r"(?i)hostname|PTR|reverse|IP name lookup", а):
        итог = {"email": адрес, "karta": з["karta"], "itog": "пропуск: отказ по нашей обратной записи", "bylo": а[:150]}
    else:
        домен = адрес.rsplit("@", 1)[-1]
        хост, откуда = mx_doh(домен)
        if not хост:
            итог = {"email": адрес, "karta": з["karta"], "itog": "MX не найден и по DoH (%s) — оставлено неясно" % откуда, "bylo": а[:150]}
            with io.open(ЖУР, "a", encoding="utf-8") as ф:
                ф.write(json.dumps(итог, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
            сч[итог["itog"]] += 1; continue
        проба._mx[домен] = хост
        try:
            рез = проба.probe(адрес, force=True)
        except Exception as ex:  # noqa: BLE001
            рез = {"verdict": "неясно", "answer": str(ex)[:200]}
        вер = str(рез.get("verdict") or "неясно")
        в_базы(адрес, вер, рез.get("answer") or "")
        итог = {"email": адрес, "karta": з["karta"], "itog": вер, "otvet": str(рез.get("answer") or "")[:200], "bylo": а[:150],
                "mx_cherez": откуда}
        if вер in ("есть", "принимает всё") and "--bez-vozvrata" not in sys.argv:
            итог["vozvrat"] = вернуть(з)
    сч[итог["itog"]] += 1
    with io.open(ЖУР, "a", encoding="utf-8") as ф:
        ф.write(json.dumps(итог, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
    if sum(сч.values()) % 20 == 0: print("%d: %s" % (sum(сч.values()), dict(сч)), flush=True)
print("ИТОГ ПЕРЕПРОБЫ:", dict(сч), flush=True)
print("карточки 22:", c.execute("SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=22 GROUP BY status").fetchall(), flush=True)
