# -*- coding: utf-8 -*-
"""Завести письма партии «провалы Meyer» (журнал _ops/meyer-partiya.jsonl, статус «ок») карточками в «Подтвердить
отправку». Владелец 17.11: «заведи письма которые получились в "подтвердить отправку"».
  • кампания «Meyer провалы 17.11» — клон шагов кампании 11 «Партия 935 — Meyer»;
  • ящик — по кругу из рабочих ящиков Meyer (не на паузе), ИМЯ_ОТПРАВИТЕЛЯ → имя из from_name ящика;
  • подпись в тело не кладём — её добавляет система при отправке (как в остальных письмах Meyer);
  • адреса mail.ru (и прочие mail.ru-домены) раскиданы по очереди равномерно;
  • перед заводом: стоп-лист (email/домен/ИНН), мёртвый адрес (заслон подтверждения), Meyer писал < 15 дней,
    одна карточка на адрес в этой кампании. Если у адреса висит карточка в другой кампании — заводим, но
    помечаем в panel_json (est_drugaya_kartochka) и считаем в итоге.
  • АВТООТПРАВКИ НЕТ: карточки pending, отправка только по команде владельца.
Повторный запуск добавляет только новые «ок» (после пересборки ошибок). Журнал _ops/meyer-karty-1711.jsonl (fsync).
    meyer_partiya_karty.py [--primenit] [--zapusk]   (лог _ops/meyer-karty.log)"""
import io, itertools, json, os, re, sqlite3, sys, time
from collections import Counter
from datetime import datetime, timedelta, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config               # noqa: E402
from sender.confirm import ConfirmSend         # noqa: E402
from sender.store import Store                 # noqa: E402
from sender.suppression import Suppression     # noqa: E402
from sender.ai_quota import build_ai_quota     # noqa: E402

ПРИМ = "--primenit" in sys.argv
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:   # отдельным процессом: обрыв связи не рвёт завод
    import subprocess
    л = io.open(os.path.join(ОПС, "meyer-karty.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(3); print("запущен, pid %d" % п.pid); sys.exit(0)
ЖУР = os.path.join(ОПС, "meyer-partiya.jsonl")
ЖУР_К = os.path.join(ОПС, "meyer-karty-1711.jsonl")
ИМЯ_КАМП = "Meyer провалы 17.11"
БАЗА = 11
МАИЛРУ = re.compile(r"@(mail|inbox|list|bk|internet)\.ru$|@mail\.ua$")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
к = store._conn


def с_повтором(fn, *a, **kw):
    for п in range(20):
        try:
            return fn(*a, **kw)
        except sqlite3.OperationalError as ex:
            if "locked" not in str(ex): raise
            time.sleep(3 + п)
    return fn(*a, **kw)


def пиши(з):
    with io.open(ЖУР_К, "a", encoding="utf-8") as ф:
        ф.write(json.dumps(з, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())


цифры = lambda x: "".join(c for c in str(x or "") if c.isdigit())
# последняя запись по ключу
жур = {}
for с in io.open(ЖУР, encoding="utf-8"):
    if с.strip():
        з = json.loads(с); жур[з["kluch"]] = з
ок = [з for з in жур.values() if з.get("status") == "ок" and з.get("email")]

пауз = {r[0] for r in к.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1")}
ящ_м = sorted((m for m in cfg.mailboxes() if str(getattr(m, "division", "")) == "meyer" and m.mailbox_id not in пауз), key=lambda m: m.mailbox_id)
мейер_ящ = {m.mailbox_id for m in cfg.mailboxes() if str(getattr(m, "division", "")) == "meyer"}
круг = itertools.cycle(ящ_м)
имя_ящ = lambda m: (str(getattr(m, "from_name", "") or "").split(",")[0].split() or [""])[0]

порог = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()[:19]
мейер_15 = {e for e, mb in к.execute("SELECT lower(r.email), m.mailbox_id FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                      "WHERE m.status='sent' AND m.sent_at >= ?", (порог,)) if mb in мейер_ящ}
сейчас_с = datetime.now(timezone.utc).isoformat()
стоп = {(s, v.lower()) for s, v in к.execute("SELECT scope, value FROM suppression WHERE expires_at IS NULL OR expires_at > ?", (сейчас_с,))}

r = к.execute("SELECT id FROM campaigns WHERE name=?", (ИМЯ_КАМП,)).fetchone()
КАМП = r[0] if r else None
if not КАМП and ПРИМ:
    б = к.execute("SELECT status, legal_entity, legal_inn, provider_pool, config_json FROM campaigns WHERE id=?", (БАЗА,)).fetchone()

    def _завести():
        with store._lock:
            ид = к.execute("INSERT INTO campaigns (name, status, legal_entity, legal_inn, provider_pool, config_json, created_at, updated_at) "
                           "VALUES (?,?,?,?,?,?,?,?)", (ИМЯ_КАМП, б[0], б[1], б[2], б[3], б[4], сейчас_с, сейчас_с)).lastrowid
            шк = [x[1] for x in к.execute("PRAGMA table_info(sequence_steps)") if x[1] != "id"]
            for row in к.execute("SELECT %s FROM sequence_steps WHERE campaign_id=?" % ",".join(шк), (БАЗА,)).fetchall():
                д = dict(zip(шк, row)); д["campaign_id"] = ид
                к.execute("INSERT INTO sequence_steps (%s) VALUES (%s)" % (",".join(д), ",".join("?" * len(д))), list(д.values()))
            к.commit()
        return ид
    КАМП = с_повтором(_завести)
    print("заведена кампания", КАМП, ИМЯ_КАМП, flush=True)

в_камп = {e for (e,) in к.execute("SELECT lower(email) FROM confirm_reviews WHERE campaign_id=? AND status IN ('pending','approved','sent')", (КАМП or -1,))}
сч = Counter(); годные = []
for з in ок:
    em = з["email"].strip().lower(); дом = em.split("@")[-1]; и = цифры(з.get("inn"))
    if em in в_камп: сч["адрес уже в кампании / повтор в партии"] += 1; continue
    if ("email", em) in стоп or ("domain", дом) in стоп or (и and ("inn", и) in стоп): сч["стоп-лист"] += 1; continue
    if em in мейер_15: сч["Meyer писал < 15 дней"] += 1; continue
    try:
        мёртв = cs._nedostavimyy(em)
    except Exception as ex:  # noqa: BLE001
        мёртв = None; сч["заслон упал: %s" % type(ex).__name__] += 1
    if мёртв: сч["мёртвый адрес"] += 1; continue
    годные.append(з); в_камп.add(em)

# mail.ru равномерно по очереди
мр = [з for з in годные if МАИЛРУ.search(з["email"].lower())]; пр = [з for з in годные if not МАИЛРУ.search(з["email"].lower())]
порядок = [з for _, _, з in sorted([((i + .5) / len(мр), 0, з) for i, з in enumerate(мр)] + [((i + .5) / len(пр), 1, з) for i, з in enumerate(пр)],
                                      key=lambda t: (t[0], t[1]))]
print("журнал: «ок» %d | к заводу %d (mail.ru %d) | отсев %s | рабочих ящиков Meyer %d | кампания %s"
      % (len(ок), len(порядок), len(мр), dict(сч), len(ящ_м), КАМП or "(будет создана)"), flush=True)
if not ПРИМ:
    print("сухой прогон — ничего не записано"); sys.exit(0)

q = build_ai_quota(store, cfg)
заведено, пропущено, с_другой = 0, Counter(), 0
for з in порядок:
    em = з["email"].strip().lower(); и = цифры(з.get("inn"))
    mb = next(круг); менеджер = имя_ящ(mb)
    if менеджер and (з.get("obrashchenie") or "").split()[:1] == [менеджер]:
        mb = next(круг); менеджер = имя_ящ(mb)
    тело = з["pismo"].replace("ИМЯ_ОТПРАВИТЕЛЯ", менеджер)
    тема = з["tema"]
    сейчас = datetime.now(timezone.utc).isoformat()
    есть = к.execute("SELECT id FROM recipients WHERE lower(email)=?", (em,)).fetchone()
    if есть:
        rid = есть[0]
    else:
        def _получатель():
            with store._lock:
                ид = к.execute("INSERT INTO recipients (email, company_name, inn, segment, domain, tz, contact_name, source, extra_json, created_at, updated_at) "
                               "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (em, з.get("kompaniya") or "", и, "meyer", em.split("@")[-1], "Europe/Moscow", з.get("fio") or "",
                                                                   "meyer-provaly-1711", json.dumps({"target_division": "meyer", "shablon": з["shablon"]}, ensure_ascii=False),
                                                                   сейчас, сейчас)).lastrowid
                к.commit()
            return ид
        rid = с_повтором(_получатель)
    ключ = "%s|%s|%d" % (и or з["kluch"], em, КАМП)
    if к.execute("SELECT 1 FROM confirm_reviews WHERE dedup_key=?", (ключ,)).fetchone():
        пропущено["карточка уже есть"] += 1; continue
    другие = [x[0] for x in к.execute("SELECT id FROM confirm_reviews WHERE lower(email)=? AND campaign_id<>? AND status IN ('pending','approved')", (em, КАМП))]
    mid, _шаг, почему = с_повтором(q._ensure_message, КАМП, int(rid))
    if not mid:
        пиши({"kluch": з["kluch"], "email": em, "otsev": "сообщение не завелось: %s" % почему, "ts": сейчас}); пропущено["сообщение не завелось"] += 1; continue
    панель = json.dumps({"letter_division": "meyer", "mailbox_id": mb.mailbox_id, "vruchnuyu": ИМЯ_КАМП, "company": {"name": з.get("kompaniya") or ""},
                         "meyer_shablon": з["shablon"], **({"est_drugaya_kartochka": другие} if другие else {})}, ensure_ascii=False)

    def _карточка():
        with store._lock:
            к.execute("UPDATE messages SET mailbox_id=? WHERE id=?", (mb.mailbox_id, mid))
            ид = к.execute("INSERT INTO confirm_reviews (dedup_key, campaign_id, recipient_id, message_id, inn, email, subject, body, panel_json, status, kind, created_at, updated_at) "
                           "VALUES (?,?,?,?,?,?,?,?,?,'pending','outbound',?,?)", (ключ, КАМП, rid, mid, и, em, тема, тело, панель, сейчас, сейчас)).lastrowid
            к.commit()
        return ид
    кид = с_повтором(_карточка)
    заведено += 1; с_другой += bool(другие)
    пиши({"kluch": з["kluch"], "inn": и, "email": em, "karta": кид, "mailbox": mb.mailbox_id, "shablon": з["shablon"], "drugie": другие, "ts": сейчас})
    if заведено % 100 == 0: print("карточек: %d" % заведено, flush=True)
print("ИТОГ: кампания %d «%s», заведено %d, из них у адреса есть карточка в другой кампании %d, пропущено %s"
      % (КАМП, ИМЯ_КАМП, заведено, с_другой, dict(пропущено)), flush=True)
