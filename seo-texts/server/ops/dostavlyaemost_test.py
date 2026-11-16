# -*- coding: utf-8 -*-
"""Перекрёстная проверка доставляемости (владелец 16.11: «сделай перекрёстную проверку на доставляемость, отправив
3-4 письма»). Шлёт 4 письма тем же путём, что панель (Sender._build_mime + _deliver: те же From/Message-ID/
List-Unsubscribe, подпись как в боевых письмах), крест-накрест между НАШИМИ рабочими ящиками:
  2 газовых письма КЦ (текст из расписания кампании 23)  → ящики Meyer;
  2 письма Meyer из партии провалов (перефраз)          → ящики КЦ.
Через --proverit смотрит по IMAP у получателей, где письмо: INBOX или Spam (по Message-ID). Журнал _ops/dostavlyaemost.jsonl.
    dostavlyaemost_test.py --otpravit | --proverit"""
import imaplib, io, json, os, random, re, sqlite3, sys, time
from email.utils import formataddr, format_datetime
from datetime import datetime, timezone
for с in io.open(r"C:\sender\panel.env", encoding="utf-8-sig"):
    if "=" in с and not с.lstrip().startswith("#"):
        к, v = с.split("=", 1); os.environ.setdefault(к.strip(), v.strip().strip('"'))
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.wiring import build_deps
from sender.dtos import RenderedMessage
ЖУР = r"C:\sender\_ops\dostavlyaemost.jsonl"
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db")
ящ = {m.mailbox_id: m for m in cfg.mailboxes()}
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
пауз = {r[0] for r in c.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1")}
раб = lambda н: sorted(mb for mb, m in ящ.items() if m.division == н and mb not in пауз)

if "--otpravit" in sys.argv:
    s = build_deps(cfg, st, dry_run=False).sender
    random.seed(int(time.time()))
    газ = c.execute("SELECT subject, body_rendered, mailbox_id FROM messages WHERE campaign_id=23 AND status='scheduled' AND body_rendered LIKE '%Меня зовут%' ORDER BY random() LIMIT 2").fetchall()
    # подпись Meyer — как в последнем отправленном письме Meyer
    мейер_мб = set(раб("meyer"))
    подп = None
    for (br, mb) in c.execute("SELECT body_rendered, mailbox_id FROM messages WHERE status='sent' AND body_rendered LIKE '%С уважением%' ORDER BY id DESC LIMIT 400"):
        if mb in ящ and ящ[mb].division == "meyer":
            подп = (br[br.rfind("С уважением"):], mb); break
    мей = [json.loads(x) for x in io.open(r"C:\sender\_ops\meyer-partiya.jsonl", encoding="utf-8")]
    мей = [з for з in мей if з.get("status") == "ок" and з.get("perefraz")]
    random.shuffle(мей)
    план = []
    for (тема, тело, mb_src), куда in zip(газ, random.sample(раб("meyer"), 2)):
        от = mb_src if mb_src in ящ and mb_src not in пауз else random.choice(раб("kc"))
        план.append(("газ КЦ", от, куда, тема, тело))
    for з, куда in zip(мей[:2], random.sample(раб("kc"), 2)):
        от = random.choice(раб("meyer"))
        имя = (ящ[от].from_name or "").split(",")[0].split()[0]
        тело = з["pismo"].replace("ИМЯ_ОТПРАВИТЕЛЯ", имя)
        if подп:
            старое_имя = (ящ[подп[1]].from_name or "").split(",")[0].strip()
            новое = (ящ[от].from_name or "").split(",")[0].strip()
            тело += "\n\n" + подп[0].replace(старое_имя, новое)
        план.append(("Meyer провалы", от, куда, з["tema"], тело))
    for вид, от, куда, тема, тело in план:
        mb = ящ[от]
        mid = s._gen_message_id(от)
        hdr = {"Message-ID": mid, "Date": format_datetime(datetime.now(timezone.utc)), "From": formataddr((mb.from_name, от)),
               "To": куда, "Subject": тема, "MIME-Version": "1.0"}
        hdr.update(s._list_unsubscribe_headers(s._make_unsub_token(0, 0), mb))
        try:
            s._deliver(mb, от, куда, s._build_mime(hdr, RenderedMessage(subject=тема, body=тело)))
            ок = "отправлено"
        except Exception as ex:  # noqa: BLE001
            ок = "ошибка: %s" % str(ex)[:150]
        з = {"vid": вид, "ot": от, "kuda": куда, "tema": тема, "mid": mid, "rez": ок, "ts": datetime.now(timezone.utc).isoformat()}
        with io.open(ЖУР, "a", encoding="utf-8") as ф: ф.write(json.dumps(з, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
        print(вид, от, "->", куда, "|", тема, "|", ок, flush=True)
        time.sleep(15)

if "--proverit" in sys.argv:
    # все папки ящика, последние 40 писем в каждой, сверка Message-ID в заголовке (поиск IMAP по заголовку у Яндекса не работает)
    for з in [json.loads(x) for x in io.open(ЖУР, encoding="utf-8")]:
        if not з["rez"].startswith("отправлено"): continue
        mb = ящ[з["kuda"]]; где = "не найдено"; нужн = з["mid"].strip().strip("<>").lower()
        try:
            im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=60); im.login(mb.login, os.environ.get(mb.password_env, ""))
            папки = []
            for стр in im.list()[1] or []:
                м = re.search(rb'"([^"]+)"\s*$|(\S+)\s*$', стр)
                if м: папки.append((м.group(1) or м.group(2)).decode())
            for п in папки:
                try:
                    т, д = im.select('"%s"' % п, readonly=True)
                    if т != "OK": continue
                    n = int(д[0] or 0)
                    if not n: continue
                    т, д = im.fetch("%d:%d" % (max(1, n - 39), n), "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
                    if any(isinstance(x, tuple) and нужн in x[1].decode("latin-1").lower() for x in д):
                        где = п; break
                except Exception:  # noqa: BLE001
                    continue
            im.logout()
        except Exception as ex:  # noqa: BLE001
            где = "IMAP ошибка: %s" % str(ex)[:80]
        print("%-14s %-40s -> %-40s | %s" % (з["vid"], з["ot"], з["kuda"], где))
