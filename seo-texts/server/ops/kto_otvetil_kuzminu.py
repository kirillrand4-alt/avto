# -*- coding: utf-8 -*-
"""Кто написал «Прошу предложения присылать мне» на y.kuzmin@optic-sort.ru.

Ищем по тексту во входящих событиях: разбор почты кладёт в detail_json и
заголовки, и кусок тела. Показываем отправителя, кому адресовано, тему,
время и связанную компанию - чтобы ответить было куда и от кого.
"""
import json
import sqlite3

ЯЩИК = "y.kuzmin@optic-sort.ru"
ИСКОМОЕ = ("прошу предложения присылать", "предложения присылать мне",
           "прошу предложения")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT e.id, e.event_type, e.mailbox_id, e.recipient_id, e.campaign_id, "
    "       substr(COALESCE(e.event_ts,e.created_at),1,19) когда, "
    "       COALESCE(e.detail_json,'') dj, r.email, r.company_name, r.inn "
    "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
    " ORDER BY e.id DESC").fetchall()

нашли = []
for р in ряды:
    dj = str(р["dj"] or "")
    низ = dj.lower()
    if any(и in низ for и in ИСКОМОЕ) or (
            str(р["mailbox_id"] or "") == ЯЩИК and р["event_type"] in
            ("reply", "reply_auto", "other")):
        нашли.append(р)

print(f"событий, похожих на искомое: {len(нашли)}")
for р in нашли[:12]:
    try:
        д = json.loads(р["dj"] or "{}")
    except Exception:                                              # noqa: BLE001
        д = {}
    заг = д.get("headers") if isinstance(д.get("headers"), dict) else {}
    тело = str(д.get("snippet") or д.get("body") or "")
    совпало = any(и in тело.lower() for и in ИСКОМОЕ)
    print(f"\n#{р['id']} {р['event_type']} {р['когда']}"
          f"{'   <-- ТЕКСТ СОВПАЛ' if совпало else ''}")
    print(f"   наш ящик : {р['mailbox_id']}")
    print(f"   ОТ       : {заг.get('From') or д.get('from_addr') or '?'}")
    print(f"   КОМУ     : {заг.get('To') or '?'}")
    if заг.get("Reply-To"):
        print(f"   Reply-To : {заг.get('Reply-To')}")
    print(f"   тема     : {str(заг.get('Subject') or д.get('subject') or '')[:80]}")
    print(f"   компания : {р['company_name'] or '?'} / {р['email'] or '?'} "
          f"/ ИНН {р['inn'] or '?'}")
    if тело:
        print(f"   текст    : {тело[:200].strip()}")
