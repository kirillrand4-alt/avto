# -*- coding: utf-8 -*-
"""Второй, тщательный заход по ВСЕМ снятым из кампании 22 за «неясно»/«отказ пробе» (владелец 12.11: «перепроверь все,
может получится выжать больше»). Чем отличается от обычной пробы:
  * PTR у 91.206.14.169 теперь есть (parsercompressor.online), HELO = parsercompressor.online — прямая и обратная сходятся;
  * MX через DNS-over-HTTPS (DNS туннеля Happ на сервере MX не отдаёт), пробуем до двух MX-хостов по приоритету;
  * MAIL FROM: <postmaster@parsercompressor.online> — пустой отправитель часть серверов режет («Backscatter»,
    «Issue MAIL FROM before RCPT»); если отправителя не приняли — повтор с пустым;
  * STARTTLS упал — переподключаемся без TLS (раньше это давало «Server not connected»);
  * catch-all: на том же соединении RCPT на случайный адрес; принял — «принимает всё»;
  * временные ответы (4xx, greylisting, таймауты, обрывы) — до трёх кругов с паузой 15 и 30 минут.
Вердикт пишется в три базы (addr_probe через _save — отбивку доставки не перебивает, enrich.emails, obzvon email_probe).
«есть»/«принимает всё» — карточку возвращаем в прежнее состояние. Остальные остаются снятыми.
Журнал _ops/gaz-pereproba2.jsonl (резюмируемо).   gaz_pereproba2.py --zapusk | [--bez-vozvrata]"""
import io, json, os, random, smtplib, socket, sqlite3, string, subprocess, sys, time, urllib.request
from collections import Counter
from datetime import datetime, timezone
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "gaz-pereproba2.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, r"C:\sender")
from sender.addr_probe import AddrProbe, классифицировать   # noqa: E402
HELO = "parsercompressor.online"; ОТ = "postmaster@parsercompressor.online"
ЖУР = os.path.join(ОПС, "gaz-pereproba2.jsonl"); БД = r"C:\sender\sender.db"
c = sqlite3.connect(БД, timeout=60)
база = AddrProbe(БД)
готово = {}
if os.path.exists(ЖУР):
    for с in io.open(ЖУР, encoding="utf-8"):
        try: з = json.loads(с); готово[з["email"]] = з
        except (ValueError, KeyError): pass
снятые = {}
for с in io.open(os.path.join(ОПС, "gaz-snyat-neyasnye.jsonl"), encoding="utf-8"):
    з = json.loads(с); снятые[з["email"]] = з


def mx_doh(домен):
    for урл in ("https://dns.google/resolve?name=%s&type=MX", "https://cloudflare-dns.com/dns-query?name=%s&type=MX"):
        try:
            д = json.load(urllib.request.urlopen(urllib.request.Request(урл % домен, headers={"accept": "application/dns-json"}), timeout=20))
            мх = sorted((int(a["data"].split()[0]), a["data"].split()[-1].rstrip(".")) for a in д.get("Answer", []) if a.get("type") == 15)
            мх = [х for _, х in мх if х and х != "."]
            if мх or д.get("Status") in (0, 3): return мх
        except Exception:  # noqa: BLE001
            continue
    return None


def разговор(хост, адрес, от, tls=True):
    """(код, ответ, catch_all|None)"""
    s = smtplib.SMTP(хост, 25, timeout=45, local_hostname=HELO)
    try:
        s.ehlo_or_helo_if_needed()
        if tls and s.has_extn("starttls"):
            s.starttls(); s.ehlo()
        мк, мо = s.mail(от)
        if мк >= 400:
            return мк, "MAIL FROM: " + (мо or b"").decode("utf-8", "replace"), None
        код, сырой = s.rcpt(адрес)
        ответ = (сырой or b"").decode("utf-8", "replace")
        ловушка = None
        if 200 <= код < 300:
            случ = "".join(random.choice(string.ascii_lowercase) for _ in range(14)) + "@" + адрес.rsplit("@", 1)[1]
            к2, _ = s.rcpt(случ); ловушка = 200 <= к2 < 300
        return код, ответ, ловушка
    finally:
        try: s.quit()
        except Exception: pass  # noqa: BLE001,E701


def проба(адрес):
    домен = адрес.rsplit("@", 1)[1]
    мх = mx_doh(домен)
    if мх is None: return "неясно", None, "DoH не ответил", ""
    if not мх: return "неясно", None, "MX нет и по DoH (приговор не выносим)", ""
    посл = ("неясно", None, "", "")
    for хост in мх[:2]:
        for от, tls in ((ОТ, True), (ОТ, False), ("", True)):
            try:
                код, ответ, ловушка = разговор(хост, адрес, от, tls)
            except smtplib.SMTPNotSupportedError as ex:
                посл = ("неясно", None, str(ex)[:150], хост); continue
            except (smtplib.SMTPServerDisconnected, ssl_err) as ex:
                посл = ("неясно", None, str(ex)[:150], хост)
                if tls: continue        # возможно, упал TLS — пробуем без него
                break
            except (smtplib.SMTPException, OSError, socket.timeout) as ex:
                посл = ("неясно", None, str(ex)[:150], хост); break
            if ответ.startswith("MAIL FROM") and от:
                посл = ("неясно", код, ответ[:150], хост); continue
            в = классифицировать(код, ответ)
            if в == "есть" and ловушка: в = "принимает всё"; ответ += " | домен принимает любой адрес"
            return в, код, ответ[:200], хост
    return посл


import ssl   # noqa: E402
ssl_err = ssl.SSLError


def в_базы(адрес, вер, код, ответ, мх):
    база._save(адрес, вер, код, ответ, мх)
    ts = int(time.time())
    try:
        cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60); cx.execute("PRAGMA busy_timeout=60000")
        cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=?, probe_answer=? WHERE lower(email)=?", (вер, ts, ответ[:300], адрес)); cx.commit(); cx.close()
        ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
        ox.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT PRIMARY KEY, verdict TEXT, source TEXT, answer TEXT, ts INTEGER)")
        ox.execute("INSERT INTO email_probe (email, verdict, source, answer, ts) VALUES (?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                   "verdict=excluded.verdict, answer=excluded.answer, ts=excluded.ts", (адрес, вер, "smtp-server", ответ[:300], ts)); ox.commit(); ox.close()
    except Exception as ex: print("базы: %s" % str(ex)[:80], flush=True)  # noqa: BLE001,E701


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


def временный(в, код, ответ):
    н = (ответ or "").lower()
    return в == "неясно" and ((код is not None and 400 <= код < 500) or any(x in н for x in (
        "timed out", "greylist", "try again", "temporar", "not connected", "unexpectedly closed", "come back later", "doh не ответил")))


сч = Counter(); вернули = 0
for круг, пауза in ((1, 0), (2, 900), (3, 1800)):
    очередь = []
    for адрес, з in снятые.items():
        ст = c.execute("SELECT status FROM confirm_reviews WHERE id=?", (з["karta"],)).fetchone()
        if not ст or ст[0] != "skipped": continue          # уже вернули (в т.ч. первым заходом)
        г = готово.get(адрес)
        if г and (г.get("krug", 0) >= круг or not г.get("vremenny")): continue
        очередь.append((адрес, з))
    if not очередь: break
    if пауза:
        print("круг %d: %d адресов с временным ответом, ждём %d мин" % (круг, len(очередь), пауза // 60), flush=True); time.sleep(пауза)
    print("круг %d: %d адресов" % (круг, len(очередь)), flush=True)
    for i, (адрес, з) in enumerate(очередь, 1):
        try: в, код, ответ, мх = проба(адрес)
        except Exception as ex: в, код, ответ, мх = "неясно", None, "сбой: %s" % str(ex)[:120], ""  # noqa: BLE001,E701
        if мх: в_базы(адрес, в, код, ответ, мх)
        запись = {"email": адрес, "karta": з["karta"], "krug": круг, "itog": в, "kod": код, "otvet": ответ, "mx": мх,
                  "vremenny": временный(в, код, ответ)}
        if в in ("есть", "принимает всё") and "--bez-vozvrata" not in sys.argv:
            запись["vozvrat"] = вернуть(з); вернули += запись["vozvrat"].startswith("возвращена")
        готово[адрес] = запись
        with io.open(ЖУР, "a", encoding="utf-8") as ф:
            ф.write(json.dumps(запись, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
        сч["круг %d: %s" % (круг, в)] += 1
        if i % 20 == 0: print("  %d/%d %s, вернули %d" % (i, len(очередь), dict(сч), вернули), flush=True)
        time.sleep(2)
print("ИТОГ ПЕРЕПРОБЫ 2:", dict(сч), "вернули:", вернули, flush=True)
print("карточки 22:", c.execute("SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=22 GROUP BY status").fetchall(), flush=True)
