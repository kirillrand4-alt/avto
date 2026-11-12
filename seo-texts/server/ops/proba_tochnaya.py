# -*- coding: utf-8 -*-
"""Точная SMTP-проба адреса (общий модуль, по опыту перепробы кампании 22, 12.11):
PTR 91.206.14.169 = parsercompressor.online, HELO = parsercompressor.online; MX через DNS-over-HTTPS (DNS туннеля Happ
на сервере MX не отдаёт); MAIL FROM <postmaster@parsercompressor.online>, при отказе — пустой; STARTTLS упал —
переподключение без TLS; catch-all — RCPT на случайный адрес в том же разговоре; до двух MX-хостов.
Запись вердикта в три базы: addr_probe (через _save — отбивку доставки не перебивает), enrich.emails, obzvon email_probe."""
import json, random, smtplib, socket, sqlite3, ssl, string, sys, time, urllib.request
sys.path.insert(0, r"C:\sender")
from sender.addr_probe import AddrProbe, классифицировать   # noqa: E402
HELO = "parsercompressor.online"; ОТ = "postmaster@parsercompressor.online"; БД = r"C:\sender\sender.db"
_база = None
def база():
    global _база
    if _база is None: _база = AddrProbe(БД)
    return _база


def _doh(имя, тип):
    """→ (Status, [записи]) по первому ответившему DoH, либо None."""
    for урл in ("https://dns.google/resolve?name=%s&type=%s", "https://cloudflare-dns.com/dns-query?name=%s&type=%s"):
        try:
            д = json.load(urllib.request.urlopen(urllib.request.Request(урл % (имя, тип), headers={"accept": "application/dns-json"}), timeout=20))
            return д.get("Status"), [a.get("data") for a in д.get("Answer", []) if a.get("data")]
        except Exception:  # noqa: BLE001
            continue
    return None


def почты_нет(домен):
    """Владелец 12.11: если домена не существует совсем — честно «нет MX». Приговор только при согласии ДВУХ
    независимых DoH (Google и Cloudflare): NXDOMAIN, либо домен есть, но нет ни MX, ни A/AAAA (по RFC 5321 слать некуда).
    → текст обоснования или "" (не доказано)."""
    ответы = []
    for урл in ("https://dns.google/resolve?name=%s&type=%s", "https://cloudflare-dns.com/dns-query?name=%s&type=%s"):
        try:
            з = lambda т: json.load(urllib.request.urlopen(urllib.request.Request(урл % (домен, т), headers={"accept": "application/dns-json"}), timeout=20))
            мх, а, аааа = з("MX"), з("A"), з("AAAA")
        except Exception:  # noqa: BLE001
            return ""
        if мх.get("Status") == 3: ответы.append("NXDOMAIN"); continue
        есть = lambda д, т: any(x.get("type") == т for x in д.get("Answer", []))
        if мх.get("Status") == 0 and not есть(мх, 15) and not есть(а, 1) and not есть(аааа, 28): ответы.append("нет MX и A")
        else: return ""
    if len(ответы) == 2:
        return "домен не существует (NXDOMAIN по Google и Cloudflare)" if ответы == ["NXDOMAIN", "NXDOMAIN"] else "у домена нет ни MX, ни A (Google и Cloudflare)"
    return ""


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


def _разговор(хост, адрес, от, tls=True):
    s = smtplib.SMTP(хост, 25, timeout=45, local_hostname=HELO)
    try:
        s.ehlo_or_helo_if_needed()
        if tls and s.has_extn("starttls"):
            s.starttls(); s.ehlo()
        мк, мо = s.mail(от)
        if мк >= 400: return мк, "MAIL FROM: " + (мо or b"").decode("utf-8", "replace"), None
        код, сырой = s.rcpt(адрес)
        ответ = (сырой or b"").decode("utf-8", "replace"); ловушка = None
        if 200 <= код < 300:
            случ = "".join(random.choice(string.ascii_lowercase) for _ in range(14)) + "@" + адрес.rsplit("@", 1)[1]
            к2, _ = s.rcpt(случ); ловушка = 200 <= к2 < 300
        return код, ответ, ловушка
    finally:
        try: s.quit()
        except Exception: pass  # noqa: BLE001,E701


def проба(адрес):
    """→ (вердикт, код, ответ, mx)"""
    домен = адрес.rsplit("@", 1)[1]
    мх = mx_doh(домен)
    if мх is None: return "неясно", None, "DoH не ответил", ""
    if not мх:
        почему = почты_нет(домен)
        if почему: return "нет MX", None, почему, ""
        return "неясно", None, "MX нет и по DoH, но домен резолвится (по RFC почта на A-адрес возможна)", ""
    посл = ("неясно", None, "", "")
    for хост in мх[:2]:
        for от, tls in ((ОТ, True), (ОТ, False), ("", True)):
            try:
                код, ответ, ловушка = _разговор(хост, адрес, от, tls)
            except smtplib.SMTPNotSupportedError as ex:
                посл = ("неясно", None, str(ex)[:150], хост); continue
            except (smtplib.SMTPServerDisconnected, ssl.SSLError) as ex:
                посл = ("неясно", None, str(ex)[:150], хост)
                if tls: continue
                break
            except UnicodeEncodeError:
                return "неясно", None, "адрес не-ASCII, проба неприменима", хост
            except (smtplib.SMTPException, OSError, socket.timeout) as ex:
                посл = ("неясно", None, str(ex)[:150], хост); break
            if ответ.startswith("MAIL FROM") and от:
                посл = ("неясно", код, ответ[:150], хост); continue
            в = классифицировать(код, ответ)
            if в == "есть" and ловушка: в = "принимает всё"; ответ += " | домен принимает любой адрес"
            return в, код, ответ[:200], хост
    return посл


def временный(в, код, ответ):
    н = (ответ or "").lower()
    return в == "неясно" and ((код is not None and 400 <= код < 500) or any(x in н for x in (
        "timed out", "greylist", "try again", "temporar", "not connected", "unexpectedly closed", "come back later", "doh не ответил")))


def в_базы(адрес, вер, код, ответ, мх):
    if мх or вер == "нет MX": база()._save(адрес, вер, код, ответ, мх or "")
    ts = int(time.time())
    try:
        cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60); cx.execute("PRAGMA busy_timeout=60000")
        cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=?, probe_answer=? WHERE lower(email)=?", (вер, ts, ответ[:300], адрес)); cx.commit(); cx.close()
        ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
        ox.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT PRIMARY KEY, verdict TEXT, source TEXT, answer TEXT, ts INTEGER)")
        ox.execute("INSERT INTO email_probe (email, verdict, source, answer, ts) VALUES (?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                   "verdict=excluded.verdict, answer=excluded.answer, ts=excluded.ts", (адрес, вер, "smtp-server", ответ[:300], ts)); ox.commit(); ox.close()
    except Exception as ex: print("базы: %s" % str(ex)[:80], flush=True)  # noqa: BLE001,E701
