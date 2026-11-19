# -*- coding: utf-8 -*-
"""Письма-уточнения 19.11 (владелец: «1» — короткое уточнение с ящика того же менеджера): в копиях на адреса, которые
дали сами клиенты (Термотроник — гл. технолог, Эластомерик — гл. инженер), ушли чужое обращение и две подписи
(ошибка kopiya_na_adres.py, исправлена). Тексты одобрены владельцем 19.11. Новое письмо (свой ключ идемпотентности),
карточка, ящик менеджера из исходного письма, ручная отправка approve(force=True) — заслон «компания ответила».
    utochnenie_1911.py [--primenit]"""
import sqlite3, sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.wiring import build_deps
from sender.dtos import MessageIn

ПИСЬМА = [
    {"email": "i.andreev@termotronic.ru", "mailbox": "p.novoseltsev@kompressor-air-trade.ru", "tema": "Вопрос по азоту на следующий год",
     "telo": "Иван Сергеевич, добрый день!\n\n"
             "Прошу прощения: в письме, которое вы сегодня получили от нас, перепутались обращение и подпись. Пишу вам, потому что "
             "Эдуард Рыбко подсказал обратиться именно к вам как к главному технологу.\n\n"
             "Коротко о сути: мы поставляем азотные станции под ключ, в том числе для монтажа электронных модулей, где нужна "
             "инертная среда, а также компрессорное оборудование с собственным сервисом.\n\n"
             "Скажите, есть ли в планах на ближайшие 4 месяца модернизация азотной станции, новый проект или обновление компрессорной?"},
    {"email": "e.chernyshov@elastomeric.ru", "mailbox": "v.prokhorov@compressor-air-expert.ru", "tema": "Модернизация компрессорной: планы",
     "telo": "Добрый день!\n\n"
             "Прошу прощения: во вчерашнем письме от нас перепутались обращение и подпись. Ваш адрес подсказала Виктория из "
             "бухгалтерии: посоветовала обратиться к вам как к главному инженеру.\n\n"
             "Коротко: в 2022 году ваша компания обращалась в наш сервисный центр. Мы ведём проекты по сжатому воздуху на "
             "производствах, от отдельного компрессора до модульной станции с осушкой и генерацией азота, и обслуживаем "
             "оборудование своим сервисным центром.\n\n"
             "Подскажите, планируете ли в ближайшие месяцы модернизацию или расширение компрессорной?"},
]
ПРИМ = "--primenit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, st, dry_run=False).confirm
к = sqlite3.connect(r"C:\sender\sender.db", timeout=60); к.row_factory = sqlite3.Row
ящ = {m.mailbox_id for m in cfg.mailboxes()}
пауз = {r[0] for r in к.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1")}
if ПРИМ:   # пустая копия с ошибочным текстом от повтора kopiya_na_adres 18-19.11
    with к: к.execute("UPDATE confirm_reviews SET status='skipped', reason='дубль копии с ошибочным текстом (19.11)' WHERE id=56915 AND status='pending'")
for п in ПИСЬМА:
    р = к.execute("SELECT * FROM recipients WHERE lower(email)=?", (п["email"],)).fetchone()
    м = к.execute("SELECT * FROM messages WHERE recipient_id=? AND status='sent' ORDER BY sent_at DESC LIMIT 1", (р["id"],)).fetchone()
    print("==", п["email"], "| ящик", п["mailbox"], "есть" if п["mailbox"] in ящ else "НЕТ ТАКОГО", "| пауза" if п["mailbox"] in пауз else "",
          "| исходное m%s камп %s" % (м["id"], м["campaign_id"]))
    print(п["telo"])
    if not ПРИМ or п["mailbox"] not in ящ: continue
    шаг = st.get_steps(int(м["campaign_id"]))[0]
    mid, _ = st.enqueue_message(MessageIn(idempotency_key="utochnenie-1911-%s" % п["email"], campaign_id=int(м["campaign_id"]),
                                          recipient_id=int(р["id"]), sequence_step_id=int(шаг.id), scheduled_at=datetime.now(timezone.utc)))
    with к: к.execute("UPDATE messages SET mailbox_id=?, status='pending_review' WHERE id=? AND status NOT IN ('sent','sending')", (п["mailbox"], mid))
    # cs.submit склеивает с уже отправленной карточкой того же адреса и кампании (19.11: вернул старую, ничего не ушло) —
    # карточку уточнения заводим напрямую со своим ключом
    import json as _j
    ключ = "utochnenie-1911|%s" % п["email"]
    ст = к.execute("SELECT id, status FROM confirm_reviews WHERE dedup_key=?", (ключ,)).fetchone()
    if ст and ст["status"] == "sent": print("уточнение уже отправлено, карточка", ст["id"]); continue
    if ст:
        rid = ст["id"]
    else:
        т = datetime.now(timezone.utc).isoformat()
        with к:
            rid = к.execute("INSERT INTO confirm_reviews (dedup_key, campaign_id, recipient_id, message_id, inn, email, subject, body, panel_json, status, kind, created_at, updated_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,'pending','outbound',?,?)", (ключ, int(м["campaign_id"]), int(р["id"]), mid, р["inn"], п["email"], п["tema"], п["telo"],
                            _j.dumps({"utochnenie_k": int(м["id"]), "mailbox_id": п["mailbox"], "letter_division": "kc"}, ensure_ascii=False), т, т)).lastrowid
    print("карточка %s, отправка: %s" % (rid, cs.approve(rid, operator="владелец 19.11: уточнение после ошибки в копии", force=True)))
    print("после:", dict(к.execute("SELECT status, sent_at, mailbox_id FROM messages WHERE id=?", (mid,)).fetchone()))
