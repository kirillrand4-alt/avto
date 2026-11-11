# -*- coding: utf-8 -*-
"""Правка текста pending-карточек кампании 22 «КЦ газ 11.11»: замены «было → стало» из JSON (список пар).
Владелец 11.11: «обоснован ли повтор» («в том числе модульные» в станции и в компрессорах). Правит body и
edited_body, если он есть; карточки, тронутые оператором (edited_body отличается от body), не трогаем.
Плюс сравнение panel_json карточек кампании 21 и 22 (блок комплаенса).
    gaz_pravka_tekstov_22.py <замены.json на дропе> [--primenit]"""
import io, json, os, sqlite3, sys
from datetime import datetime, timezone
ЗАМ = json.load(io.open(os.path.join(r"C:\seostat\drop\drop-storage", sys.argv[1]), encoding="utf-8"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
ряды = c.execute("SELECT id, body, edited_body FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchall()
правок, тронуты = [], 0
for кид, body, ed in ряды:
    if ed and ed != body:
        тронуты += 1; continue
    н = body or ""
    for a, b in ЗАМ: н = н.replace(a, b)
    if н != body: правок.append((кид, н))
print("pending: %d, к правке: %d, тронуты оператором (пропуск): %d" % (len(ряды), len(правок), тронуты))
ТЕМЫ = None
if "--temy" in sys.argv:   # 11.11: темы из канона gaz_kanon.ТЕМЫ (7 на газ), случайно, по газу письма
    import random
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gaz_kanon as K
    ТЕМЫ = K.ТЕМЫ
if "--primenit" in sys.argv:
    т = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if ТЕМЫ:
        n = 0
        with c:
            for кид, body, ed in c.execute("SELECT id, body, edited_body FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchall():
                if ed and ed != body: continue
                газ = "O2" if "кислородн" in (body or "").split("\n\n")[1 if (body or "").count("\n\n") else 0] else "N2"
                c.execute("UPDATE confirm_reviews SET subject=?, updated_at=? WHERE id=?", (random.choice(ТЕМЫ[газ]), т, кид)); n += 1
        print("темы переразложены:", n)
    with c:
        for кид, н in правок:
            c.execute("UPDATE confirm_reviews SET body=?, edited_body=CASE WHEN edited_body IS NULL THEN NULL ELSE ? END, updated_at=? WHERE id=? AND status='pending'", (н, н, т, кид))
    print("исправлено:", len(правок))
for кмп in (21, 22):
    р = c.execute("SELECT panel_json FROM confirm_reviews WHERE campaign_id=? ORDER BY id DESC LIMIT 1", (кмп,)).fetchone()
    print("кампания %d panel_json ключи: %s" % (кмп, sorted(json.loads(р[0] or "{}").keys()) if р else "нет карточек"))
