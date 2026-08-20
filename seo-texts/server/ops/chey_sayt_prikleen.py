# -*- coding: utf-8 -*-
"""Свой ли сайт приклеен к карточке: ищем имя компании в тексте её сайта.

Тот случай, ради которого это писалось. Карточка #1010: ИНН 3607005541,
ОКВЭД 10.61 «мукомольное и крупяное производство», компания ООО «Старт»,
письмо про очистку крупы — а почта info@business-gazeta.ru и сайт
казанского издания «Бизнес Online». Почта и сайт друг другу не
противоречат: чужая тут КОМПАНИЯ. Значит и проверять надо не почту с
сайтом, а имя компании с текстом её же сайта.

Проверка бесплатная и механическая: берём значимое слово из названия
(без «ООО», «завод», «торговый дом» и прочих общих) и смотрим, есть ли
оно в тексте сайта или в паспорте. Нет ни разу — сайт, скорее всего,
чужой, и письмо построено на чужих фактах.

Ложные срабатывания будут: фирма «Старт» с сайтом под брендом «Витязь»
— обычное дело. Поэтому это не приговор, а список на глаза.
"""
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ОБЩИЕ = {"ооо", "оао", "зао", "ао", "пао", "нао", "спк", "мбу", "муп", "гуп",
         "общество", "с", "ограниченной", "ответственностью", "акционерное",
         "завод", "фабрика", "комбинат", "торговый", "дом", "тд", "пк", "нпо",
         "нпп", "группа", "компаний", "компания", "фирма", "производственная",
         "производственный", "агро", "гк", "им", "имени", "по", "и"}

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
enr = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True, timeout=15)

with store._lock:
    ряды = store._conn.execute(
        "SELECT c.id, c.campaign_id, c.email, r.inn, r.company_name "
        "FROM confirm_reviews c "
        "LEFT JOIN messages m ON m.id = c.message_id "
        "LEFT JOIN recipients r ON r.id = c.recipient_id "
        "WHERE (c.status='pending') "
        "   OR (c.status IN ('approved','edited') "
        "       AND m.status IN ('scheduled','sending'))").fetchall()


def слова(имя):
    ч = re.findall(r"[а-яёa-z0-9]{3,}", str(имя or "").lower())
    return [w for w in ч if w not in ОБЩИЕ]


подозрительные = []
проверено = без_текста = 0
for r in ряды:
    инн = str(r["inn"] or "").strip()
    ключи = слова(r["company_name"])
    if not ключи or not инн:
        continue
    try:
        т = enr.execute("SELECT text FROM site_text WHERE inn=?",
                        (инн,)).fetchone()
        текст = (т[0] if т else "") or ""
    except Exception:                                            # noqa: BLE001
        текст = ""
    try:
        д = q._site_facts(инн) or {}
    except Exception:                                            # noqa: BLE001
        д = {}
    паспорт = " ".join(str(v) for v in д.values())
    if len(текст) < 300 and len(паспорт) < 200:
        без_текста += 1
        continue
    проверено += 1
    поле = (текст + " " + паспорт).lower()
    # Достаточно, чтобы нашлось начало слова: склонения и «-ий/-ая».
    если_есть = any(w[:max(4, len(w) - 2)] in поле for w in ключи)
    if не_нашлось := not если_есть:
        подозрительные.append((int(r["id"]), int(r["campaign_id"]),
                               str(r["company_name"] or "")[:44],
                               str(r["email"] or "")[:34], ключи[:3]))

print(f"писем в работе: {len(ряды)} | проверено: {проверено} | "
      f"без текста и паспорта: {без_текста}")
print(f"\nИМЯ КОМПАНИИ НЕ НАЙДЕНО НА ЕЁ САЙТЕ: {len(подозрительные)}")
for rid, k, имя, почта, кл in подозрительные[:70]:
    print(f"  #{rid} к{k} {имя:<44} {почта:<34} искал {кл}")
