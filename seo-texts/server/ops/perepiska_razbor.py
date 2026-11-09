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
import email, email.header, email.utils, imaplib, io, json, os, re, sqlite3, subprocess, sys, time
if "--zapusk" in sys.argv:   # IMAP по всем ящикам дольше 900 с раннера — отсоединённо, вывод в _ops/perepiska-razbor.txt
    л = io.open(r"C:\sender\_ops\perepiska-razbor.txt", "w", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [a for a in sys.argv[1:] if a != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
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
МЕЙЕР = {mb.mailbox_id for mb in cfg.mailboxes() if getattr(mb, "division", "") == "meyer"}
if "--meyer" in sys.argv:   # владелец 09.11: «можешь только мейер проверять»
    def _мейер(л):
        яя = {r[0] for r in c.execute("SELECT DISTINCT mailbox_id FROM messages WHERE recipient_id=? AND status='sent'", (л[2],))}
        яя |= {r[0] for r in c.execute("SELECT DISTINCT mailbox_id FROM events WHERE recipient_id=? AND event_type='reply'", (л[2],))}
        return bool(яя & МЕЙЕР)
    лиды = [л for л in лиды if _мейер(л)]
print("лидов «ведётся переписка»%s: %d" % (" (Meyer)" if "--meyer" in sys.argv else "", len(лиды)))
в_битриксе, остальные = [], []
for л in лиды:
    сд = None
    try: сд = c.execute("SELECT meyer, kc, sc, ts FROM sdelki_napr WHERE inn=?", (цифры(л[3]),)).fetchone() if цифры(л[3]) else None
    except sqlite3.Error: pass
    почему = []
    if сд and (сд[0] or сд[1] or сд[2]): почему.append("сделка в работе: " + "+".join(n for n, f in zip(("Meyer", "КЦ", "СЦ"), сд[:3]) if f))
    if л[5]: почему.append("лид передан в Битрикс #%s" % л[5])
    # владелец 09.11: «битрикс который "передали в битрикс"» — у компании (ИНН) или адреса есть лид в этом статусе
    пб = c.execute("SELECT id FROM leads WHERE status='in_bitrix' AND id<>? AND ((inn=? AND ?<>'') OR lower(email)=?) LIMIT 1",
                   (л[0], л[3] or "", цифры(л[3]), л[1] or "@@")).fetchone()
    if пб: почему.append("у компании лид #%s «передали в Битрикс»" % пб[0])
    (в_битриксе if почему else остальные).append((л, "; ".join(почему)))
try: print("выгрузка сделок Битрикса от:", c.execute("SELECT max(ts) FROM sdelki_napr").fetchone()[0])
except sqlite3.Error: pass
print("уже в Битриксе: %d → в «не интересно»" % len(в_битриксе))
_пр = Counter()
for _, п in в_битриксе:
    for ч in п.split("; "): _пр[re.sub(r"#\d+", "#", ч.split(":")[0])] += 1
print("по признакам:", _пр.most_common())
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
не_вышло = []
def _скан(mb):
    im = _ящик(mb)
    папка = None
    for стр in im.list()[1] or []:
        s = стр.decode("utf-8", "replace") if isinstance(стр, bytes) else str(стр)
        if "\\Sent" in s or re.search(r'"(Sent|Отправленные)"$', s):
            м = re.search(r'"([^"]+)"$', s); папка = м.group(1) if м else "Sent"; break
    if True:
        if im.select('"%s"' % (папка or "Sent"), readonly=True)[0] != "OK": im.logout(); return
        # 09.11: перебор всех «Отправленных» (≈0,2 с на письмо у Яндекса) рвёт соединение —
        # ищем на сервере только письма на адреса лидов (TO и CC)
        _н = set()
        for _а in sorted(адреса):
            for _поле in ("TO", "CC"):
                _н |= set((im.uid("SEARCH", None, "SINCE", SINCE, _поле, '"%s"' % _а)[1][0] or b"").split())
        uids = sorted(_н, key=int)
        for i in range(0, len(uids), 25):
            typ, data = im.uid("FETCH", b",".join(uids[i:i + 25]), "(BODY.PEEK[HEADER.FIELDS (TO CC DATE SUBJECT CONTENT-TYPE)])")
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
                    вл = "multipart/mixed" in str(h.get("Content-Type") or "").lower()   # вложение — по типу письма (BODYSTRUCTURE роняет IMAP Яндекса)
                    тема = дек(h.get("Subject"))
                    for a in общ: отправлено[a].append((дата, mb.mailbox_id, тема, вл, "почта"))
    try: im.logout()
    except Exception: pass

def _ящик(mb):
    im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=40); im.login(mb.login, os.getenv(mb.password_env, ""))
    return im
КЭШ = r"C:\sender\_ops\perepiska-otpravlennye.json"
if "--kesh" in sys.argv and os.path.exists(КЭШ):
    for a, сп in json.load(io.open(КЭШ, encoding="utf-8")).items():
        for x in сп: отправлено[a].append((datetime.fromisoformat(x[0]), x[1], x[2], x[3], x[4]))
    print("«Отправленные» — из кэша")
for mb in ([] if ("--kesh" in sys.argv and os.path.exists(КЭШ)) or "--bez-imap" in sys.argv else cfg.mailboxes()):
    if "--meyer" in sys.argv and mb.mailbox_id not in МЕЙЕР: continue
    for _попытка in range(4):
        try:
            _скан(mb); break
        except Exception as ex:  # noqa: BLE001
            print("ящик %s, попытка %d: %s" % (mb.mailbox_id, _попытка + 1, str(ex)[:60]), flush=True); time.sleep(20 * (_попытка + 1))
    else:
        не_вышло.append(mb.mailbox_id)
print("не удалось прочитать «Отправленные»:", не_вышло or "все прочитаны")
if "--kesh" not in sys.argv and "--bez-imap" not in sys.argv:
    with io.open(КЭШ, "w", encoding="utf-8") as _к:
        json.dump({a: [(x[0].isoformat(), x[1], x[2], x[3], x[4]) for x in сп] for a, сп in отправлено.items()}, _к, ensure_ascii=False)
if False:
    im = None
# через панель
КП = re.compile(r"(?i)\bкп\b|коммерческ\w* предложени|презентаци|прайс|опросн\w* лист|расч[её]т|во вложени|прикрепля|направляю")
for em, т, тело, пj in c.execute("SELECT lower(email), COALESCE(decided_at, updated_at), COALESCE(edited_body, body), COALESCE(panel_json,'') FROM confirm_reviews WHERE status='sent' AND kind='reply'"):
    if em in адреса:
        try: дата = datetime.fromisoformat(str(т)[:26]).replace(tzinfo=timezone.utc)
        except Exception: continue
        отправлено[em].append((дата, "панель", "", "vlozheniya" in пj, "панель" + (" КП" if КП.search(тело or "") else "")))
итог, напомнить, за_нами = Counter(), [], []
for л, _ in остальные:
    em = л[1]
    отв = c.execute("SELECT max(event_ts) FROM events WHERE event_type='reply' AND (recipient_id=? OR lower(detail_json) LIKE ?)", (л[2], "%" + (em or "@@") + "%")).fetchone()[0]
    try: отв = datetime.fromisoformat(str(отв)[:19]).replace(tzinfo=timezone.utc) if отв else None
    except Exception: отв = None
    наши = sorted(отправлено.get(em, []))
    после = [x for x in наши if not отв or x[0] > отв]
    if not после:
        итог["за нами ход: после ответа клиента мы не писали" if отв else "нет ни ответа, ни нашего письма"] += 1
        if отв:
            сн = (c.execute("SELECT json_extract(detail_json,'$.snippet') FROM events WHERE event_type='reply' AND (recipient_id=? OR lower(detail_json) LIKE ?) ORDER BY event_ts DESC LIMIT 1",
                            (л[2], "%" + (em or "@@") + "%")).fetchone() or [""])[0] or ""
            сн = re.split(r"(?m)^\s*>|^-{2,}|^\s*(?:От|From|Кому)\s*:|\d{1,2}\s+\w+\s+20\d\d.{0,60}(?:пишет|wrote|от )", сн)[0]
            за_нами.append(((сейчас - отв).days, л[0], em, str(л[4] or "")[:40], отв.strftime("%d.%m"), re.sub(r"\s+", " ", сн).strip()[:600],
                            "наше последнее: " + (наши[-1][0].strftime("%d.%m") + " " + наши[-1][1] if наши else "нет")))
        continue
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
print("\nЗА НАМИ ХОД (дней с ответа клиента, лид, адрес, компания, дата ответа):")
for x in sorted(за_нами, reverse=True):
    print("  %3d  #%s %s | %s | ответ %s | %s\n       «%s»" % (x[0], x[1], x[2], x[3], x[4], x[6], x[5]))
