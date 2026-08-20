# -*- coding: utf-8 -*-
"""Вебинар 28.08: письма людям с ролями из мейеровской базы.

Владелец 20.08: «отбери для карточек мейера вот эти роли и поставь такие
вариации писем в очередь от мейеровских почт (даже если писали этим
компаниям)», и следом: «только тем кто нам ответил не надо».

Отбор:
  * компания с мейеровской меткой в базе обзвона;
  * есть человек с целевой ролью (качество, технолог, инженер,
    производство, ЛПР, снабжение) и ЖИВОЙ личной почтой;
  * компания нам не отвечала (событие reply или карточка лида);
  * адрес не в стоп-листе и без приговора пробы.

Четыре варианта текста владельца идут по кругу. Тексты его, я их не
переписываю - только подставляю обращение по имени, где имя известно.

Карточку заводим НАПРЯМУЮ, минуя confirm.submit: у него на входе заслон
«писали <90 дней», а владелец прямо разрешил писать и тем, кому писали.
Пометка в reason нужна и заслону отправки - он тоже считает по ИНН.
"""
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.dtos import RecipientIn                              # noqa: E402
from sender.store import Store                                   # noqa: E402

КАТИТЬ = "--katit" in sys.argv
ПРЕДЕЛ = int(next((a for a in sys.argv[1:] if a.isdigit()), "0"))
КАМПАНИЯ = 11                       # мейеровская: пул ящиков берётся по ней
ПОМЕТКА = ("вебинар 28.08 · повтор разрешён владельцем "
           "(писать и тем, кому уже писали)")
ТЕКСТЫ = r"C:\sender\_ops\vebinar-teksty.json"
# РОЛИ РОВНО ТЕ, ЧТО НАЗВАЛ ВЛАДЕЛЕЦ: «специалистам по кач-ву, технологам,
# инженерам, ЛПР». Снабжение и закупки я добавил сам, и это дало мусор: три
# четверти выборки оказались закупщиками из госзакупок, включая «Мосгаз» и
# семь человек из одного «Кубань-Вино». Убрано.
# «главный» и «гл.» как отдельные слова ловили чиновников: «общий главный
# специалист отдела растениеводства» на домене минсельхоза. Оставляем
# только сильные признаки - гл.инженер и гл.технолог проходят по «инженер»
# и «технолог».
ЦЕЛЕВЫЕ = ("качеств", "технолог", "инженер", "производств", "директор",
           "начальник цеха", "руководител")
# Госдомены - не наши адресаты: приглашение на вебинар им не по адресу.
ГОСДОМЕНЫ = ("cap.ru", "gov.ru", ".gov.", "adm.", "admin.", "mcx", "minsel")
# Вебинар про пищевое производство - и база отбирается по делу, а не по
# мейеровской метке: она стоит и у металлообработки, и у стройки.
ПИЩЕВЫЕ = ("10", "11")
# Больше двух человек из одной компании - это уже веер, а не приглашение.
НА_КОМПАНИЮ = 2

варианты = json.load(io.open(ТЕКСТЫ, encoding="utf-8"))
print(f"вариантов текста: {len(варианты)}")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
сейчас = datetime.now(timezone.utc)


def ро(п):
    return sqlite3.connect("file:%s?mode=ro" % п.replace("\\", "/"), uri=True)


o, e = ро(r"C:\sender\obzvon-index.db"), ро(r"C:\sender\enrich.db")
o.row_factory = sqlite3.Row
p = ро(r"C:\sender\sender.db")

приговор = {str(r[0]).lower() for r in p.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
стоп = {str(r[0]).lower() for r in p.execute("SELECT value FROM suppression")}
# Ответившие: живое событие ответа или заведённый лид.
ответили = {str(r[0]) for r in p.execute(
    "SELECT DISTINCT COALESCE(rc.inn,'') FROM events ev "
    "JOIN recipients rc ON rc.id=ev.recipient_id "
    "WHERE ev.event_type IN ('reply','complaint')")}
ответили |= {str(r[0]) for r in p.execute(
    "SELECT DISTINCT COALESCE(inn,'') FROM leads")}
ответили.discard("")
print(f"компаний, которые нам отвечали: {len(ответили)}")

мейер = {}
for r in o.execute("SELECT inn, name_short, name_full, COALESCE(division,'') d, "
                   "COALESCE(base_label,'') b, COALESCE(okved_main,'') ok, "
                   "COALESCE(region,'') reg FROM obzvon"):
    метка = (str(r["d"]) + " " + str(r["b"])).lower()
    if not ("meyer" in метка or "мейер" in метка):
        continue
    if str(r["ok"] or "")[:2] not in ПИЩЕВЫЕ:
        continue
    мейер[str(r["inn"])] = dict(r)

кандидаты = []
счёт = Counter()
видели = set()
сколько_у = Counter()
for таб in ("imena", "people"):
    try:
        кол = [x[1] for x in e.execute(f"PRAGMA table_info([{таб}])")]
    except Exception:                                            # noqa: BLE001
        continue
    for r in e.execute(f"SELECT * FROM [{таб}]"):
        д = dict(zip(кол, r))
        инн = str(д.get("inn") or "")
        компания = мейер.get(инн)
        if not компания:
            continue
        роль = (str(д.get("role") or "") + " "
                + str(д.get("post") or "")).lower().strip()
        if not any(ц in роль for ц in ЦЕЛЕВЫЕ):
            continue
        почта = str(д.get("email") or "").strip().lower()
        if "@" not in почта:
            счёт["роль есть, личной почты нет"] += 1
            continue
        if any(г in почта for г in ГОСДОМЕНЫ):
            счёт["госдомен - не пишем"] += 1
            continue
        if почта in приговор or почта in стоп:
            счёт["адрес мёртв или в стоп-листе"] += 1
            continue
        if инн in ответили:
            счёт["компания нам отвечала - пропуск"] += 1
            continue
        if почта in видели:
            continue
        if сколько_у[инн] >= НА_КОМПАНИЮ:
            счёт["больше двух человек из компании - хватит"] += 1
            continue
        видели.add(почта)
        сколько_у[инн] += 1
        кандидаты.append({
            "inn": инн, "email": почта, "role": роль,
            "person": str(д.get("person") or ""),
            "name": str(компания.get("name_short")
                        or компания.get("name_full") or ""),
            "okved": str(компания.get("ok") or ""),
            "region": str(компания.get("reg") or ""),
        })
        счёт["ОТОБРАН"] += 1

print(f"\nмейеровских компаний в базе: {len(мейер)}")
for k, n in счёт.most_common():
    print(f"  {n:>5}  {k}")
if ПРЕДЕЛ:
    кандидаты = кандидаты[:ПРЕДЕЛ]
print(f"\nк постановке в очередь: {len(кандидаты)}")
for к in кандидаты[:12]:
    print(f"  {к['email']:<34} {к['person'][:24]:<24} {к['role'][:22]:<22} "
          f"{к['name'][:26]}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить - --katit")
    raise SystemExit(0)


def имя_из(person: str) -> str:
    """Имя из «Фамилия Имя Отчество» или «Имя Фамилия». Пусто - без имени."""
    части = [ч for ч in re.split(r"\s+", str(person or "").strip()) if ч]
    if len(части) >= 3:
        return части[1]
    if len(части) == 2:
        # «Иванов Иван» или «Иван Иванов» - берём то, что не похоже на фамилию.
        а, б = части
        return б if а.lower().endswith(("ов", "ев", "ин", "ко", "ий", "ая")) else а
    return ""


поставлено = 0
for i, к in enumerate(кандидаты):
    в = варианты[i % len(варианты)]
    имя = имя_из(к["person"])
    тело = в["body"]
    if имя:
        тело = тело.replace("Добрый день!", f"Добрый день, {имя}!", 1)
    try:
        rid = store.upsert_recipient(RecipientIn(
            email=к["email"], domain=к["email"].split("@")[-1],
            inn=к["inn"], company_name=к["name"], okved=к["okved"],
            contact_name=к["person"], source="вебинар 28.08",
            region=к["region"], extra={"вебинар": "28.08"}))
        пара = q._ensure_message(КАМПАНИЯ, int(rid))
        mid = пара[0] if пара else None
        ключ = f"vebinar28:{к['inn']}:{к['email']}"
        with store._lock:
            store._conn.execute(
                "INSERT OR IGNORE INTO confirm_reviews "
                "(dedup_key, campaign_id, recipient_id, message_id, inn, "
                " email, subject, body, status, reason, kind, created_at, "
                " updated_at) VALUES (?,?,?,?,?,?,?,?,'pending',?, "
                "'outbound',?,?)",
                (ключ, КАМПАНИЯ, int(rid), mid and int(mid), к["inn"],
                 к["email"], в["subject"], тело, ПОМЕТКА,
                 сейчас.isoformat(), сейчас.isoformat()))
            store._conn.commit()
        поставлено += 1
    except Exception as ex:                                      # noqa: BLE001
        print(f"  {к['email']}: {type(ex).__name__} {str(ex)[:90]}")
print(f"\nпоставлено в очередь: {поставлено}")
