# -*- coding: utf-8 -*-
"""Разбор лидов «ведётся переписка» (владелец 09.11).

1) Компании, которые уже в Битриксе (активная сделка в sdelki_napr по ИНН — любое направление —
   или у лида проставлен bitrix_lead_id), переводятся в «не интересно» (--primenit; штатный
   update_lead_cas с пометкой действия).
2) По остальным — кому напомнить о КП («удалось ознакомиться?»): смотрим наше последнее письмо
   этому адресу после его ответа. Учитываем И письма через панель (confirm_reviews, вложения/
   слова КП-презентация), И письма, отправленные руками прямо из почты ящика (папка «Отправленные»
   по IMAP — их панель не видит). Напомнить = наше последнее письмо позже последнего ответа
   клиента, в нём КП/презентация/вложение, и прошло ≥3 дней.
Только чтение, кроме --primenit (только перевод статуса bitrix-лидов).
    perepiska_razbor.py [--primenit]"""
import email, email.header, email.utils, imaplib, io, json, os, re, sqlite3, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
sys.path.insert(0, r"C:\sender")
for с in open(r"C:\sender\panel.env", encoding="utf-8", errors="replace").read().splitlines():
    if "=" in с and not с.strip().startswith("#"):
        к, з = с.split("=", 1); os.environ.setdefault(к.strip(), з.strip().strip('"'))
from sender.config import Config   # noqa: E402
from sender.store import Store     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db")); c = store._conn
сейчас = datetime.now(timezone.utc)
def цифры(x): return "".join(ч for ч in str(x or "") if ч.isdigit())
лиды = c.execute("SELECT id, lower(email), recipient_id, inn, company_name, bitrix_lead_id, version, created_at FROM leads WHERE status='perepiska'").fetchall()
print("лидов «ведётся переписка»: %d" % len(лиды))
в_битриксе, остальные = [], []
for л in лиды:
    сд = None
    try: сд = c.execute("SELECT meyer, kc, sc, ts FROM sdelki_napr WHERE inn=?", (цифры(л[3]),)).fetchone() if цифры(л[3]) else None
    except sqlite3.Error: pass
    почему = []
    if сд and (сд[0] or сд[1] or сд[2]): почему.append("сделка в работе: " + "+".join(n for n, f in zip(("Meyer", "КЦ", "СЦ"), сд[:3]) if f))
    if л[5]: почему.append("лид передан в Битрикс #%s" % л[5])
    (в_битриксе if почему else остальные).append((л, "; ".join(почему)))
try: print("выгрузка сделок Битрикса от:", c.execute("SELECT max(ts) FROM sdelki_napr").fetchone()[0])
except sqlite3.Error: pass
print("уже в Битриксе: %d → в «не интересно»" % len(в_битриксе))
for л, п in в_битриксе[:40]: print("   #%s %-32s %-34s %s" % (л[0], л[1][:32], str(л[4] or "")[:34], п))
if "--primenit" in sys.argv:
    n = 0
    for л, п in в_битриксе:
        if store.update_lead_cas(int(л[0]), expected_version=л[6], action="владелец 09.11: уже в Битриксе (%s) — из переписки в «не интересно»" % п, status="not_interested"):
            n += 1
    print("переведено в «не интересно»: %d" % n)

# ---------- письма из «Отправленных» ящиков (руками из почты) ----------
адреса = {л[1] for л, _ in остальные if л[1]}
отправлено = defaultdict(list)   # адрес -> [(дата, ящик, тема, вложение?, kp?)]
def дек(v):
    try: return str(email.header.make_header(email.header.decode_header(v or "")))
    except Exception: return str(v or "")
SINCE = (сейчас - timedelta(days=75)).strftime("%d-%b-%Y")
for mb in cfg.mailboxes():
    try:
        im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25); im.login(mb.login, os.getenv(mb.password_env, ""))
    except Exception as ex:  # noqa: BLE001
        print("вход не вышел:", mb.mailbox_id, str(ex)[:40]); continue
    папка = None
    for стр in im.list()[1] or []:
        s = стр.decode("utf-8", "replace") if isinstance(стр, bytes) else str(стр)
        if "\\Sent" in s or re.search(r'"(Sent|Отправленные)"$', s):
            м = re.search(r'"([^"]+)"$', s); папка = м.group(1) if м else "Sent"; break
    try:
        if im.select('"%s"' % (папка or "Sent"), readonly=True)[0] != "OK": im.logout(); continue
        uids = (im.uid("SEARCH", None, "SINCE", SINCE)[1][0] or b"").split()
        for i in range(0, len(uids), 100):
            typ, data = im.uid("FETCH", b",".join(uids[i:i + 100]), "(BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (TO CC DATE SUBJECT)])")
            структ = ""
            for ч in data or []:
                if isinstance(ч, tuple):
                    структ = ч[0].decode("utf-8", "replace")
                    h = email.message_from_bytes(ч[1])
                    кому = {a.lower() for _, a in email.utils.getaddresses([дек(h.get("To")), дек(h.get("Cc"))])}
                    общ = кому & адреса
                    if not общ: continue
                    try: дата = email.utils.parsedate_to_datetime(h.get("Date")).astimezone(timezone.utc)
                    except Exception: continue
                    вл = bool(re.search(r'"(?:attachment|application)"|"(?:PDF|pdf|vnd\.|msword|octet-stream)"', структ, re.I))
                    тема = дек(h.get("Subject"))
                    for a in общ: отправлено[a].append((дата, mb.mailbox_id, тема, вл, "почта"))
    except Exception as ex:  # noqa: BLE001
        print("папка", mb.mailbox_id, str(ex)[:60])
    try: im.logout()
    except Exception: pass
# через панель
КП = re.compile(r"(?i)\bкп\b|коммерческ\w* предложени|презентаци|прайс|опросн\w* лист|расч[её]т|во вложени|прикрепля|направляю")
for em, т, тело, пj in c.execute("SELECT lower(email), COALESCE(decided_at, updated_at), COALESCE(edited_body, body), COALESCE(panel_json,'') FROM confirm_reviews WHERE status='sent' AND kind='reply'"):
    if em in адреса:
        try: дата = datetime.fromisoformat(str(т)[:26]).replace(tzinfo=timezone.utc)
        except Exception: continue
        отправлено[em].append((дата, "панель", "", "vlozheniya" in пj, "панель" + (" КП" if КП.search(тело or "") else "")))
итог, напомнить = Counter(), []
for л, _ in остальные:
    em = л[1]
    отв = c.execute("SELECT max(event_ts) FROM events WHERE event_type='reply' AND (recipient_id=? OR lower(detail_json) LIKE ?)", (л[2], "%" + (em or "@@") + "%")).fetchone()[0]
    try: отв = datetime.fromisoformat(str(отв)[:19]).replace(tzinfo=timezone.utc) if отв else None
    except Exception: отв = None
    наши = sorted(отправлено.get(em, []))
    после = [x for x in наши if not отв or x[0] > отв]
    if not после:
        итог["за нами ход: после ответа клиента мы не писали" if отв else "нет ни ответа, ни нашего письма"] += 1; continue
    посл = после[-1]
    с_кп = any(x[3] or "КП" in x[4] or re.search(r"(?i)кп|предложени|презентац|прайс", x[2] or "") for x in после)
    дней = (сейчас - посл[0]).days
    if с_кп and дней >= 3:
        итог["напомнить о КП (≥3 дней тишины)"] += 1
        напомнить.append((дней, л[0], em, str(л[4] or "")[:30], посл[1], посл[0].strftime("%d.%m"), "вложение" if any(x[3] for x in после) else "КП в тексте/теме"))
    elif с_кп: итог["КП отправлено <3 дней назад, ждём"] += 1
    else: итог["мы ответили, но без КП"] += 1
print("\nостальные %d лидов:" % len(остальные))
for k, n in итог.most_common(): print("  %4d  %s" % (n, k))
print("писем руками из почты нашлось по адресам лидов: %d" % sum(1 for v in отправлено.values() for x in v if x[1] != "панель"))
print("\nНАПОМНИТЬ О КП (дней тишины, лид, адрес, компания, откуда наше письмо, когда, что было):")
for x in sorted(напомнить, reverse=True): print("  %3d  #%s %-30s %-30s %-34s %s %s" % x)
