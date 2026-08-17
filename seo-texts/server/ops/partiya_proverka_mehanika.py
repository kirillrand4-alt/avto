# -*- coding: utf-8 -*-
"""Механическая часть сплошной проверки писем партии. Без провайдера.

Проверяем по каждому письму то, что можно доказать кодом:

  1. КОНТАКТ ДОКАЗАН. Берём source_url адреса из обогащения, открываем кеш
     страниц сервера по ИНН и ищем сам адрес в HTML той самой страницы.
     Итог - факт со ссылкой, а не оценка: «есть на странице» / «страница в
     кеше, адреса в ней нет» / «страницы нет в кеше» / «нет источника».
  2. БРЕНДЫ В ТЕЛЕ. Ни родных, ни дружественных, ни чужих - холодное письмо
     их не называет.
  3. ЧИСЛА. Каждое число письма должно быть в белом списке (паспорт сайта,
     факты направления, имя и город получателя).
  4. НАЗВАНИЕ ПОЛУЧАТЕЛЯ. Правило 19и: фирма названа в теме или теле.
  5. ГЕЙТ ЦЕЛИКОМ. Прогоняем штатный gate ещё раз: письмо могло попасть в
     очередь до правки правил.

Смысловое (правда ли компания этим занимается, верна ли роль контакта)
уходит отдельным прогоном через провайдера - здесь только доказуемое.

Результат: durable json-строки в журнал + сводка.
"""
import gzip
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import allowed_numbers, gate, load_facts  # noqa: E402
from sender.ai_quota import build_ai_quota                      # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

КАМПАНИИ = {10, 11}
КЕШ = r"C:\seostat\drop\pagecache"
ЖУРНАЛ = r"C:\sender\_ops\proverka-partii-mehanika.jsonl"
if os.path.exists(ЖУРНАЛ):
    os.remove(ЖУРНАЛ)   # проверка идёт целиком, а не дописывается

# Бренды: свои, дружественные и чужие. В холодном письме нет ни одного.
БРЕНДЫ = ("enger", "энгер", "berg", "берг", "cross air", "кросс эйр",
          "dali", "дали", "hansmann", "хансманн", "meyer", "мейер",
          "atlas copco", "атлас копко", "kaeser", "кайзер", "remeza",
          "ремеза", "ingersoll", "ингерсолл", "ceccato", "чеккато",
          "fini", "abac", "comaro", "комаро", "dalgakiran", "далгакиран")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
ФАКТЫ = {"kc": load_facts(division="kc"), "meyer": load_facts(division="meyer")}

ex = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True)
ex.row_factory = sqlite3.Row
источники = {}
for r in ex.execute(
        "SELECT inn, email, role, person, source_url, source FROM emails "
        "WHERE email IS NOT NULL AND email<>''"):
    источники[(str(r["inn"]), str(r["email"]).strip().lower())] = dict(r)

_кеш_памяти = {}


def страницы(inn):
    if inn in _кеш_памяти:
        return _кеш_памяти[inn]
    путь = os.path.join(КЕШ, f"{inn}.json.gz")
    стр = {}
    if os.path.exists(путь):
        try:
            with gzip.open(путь, "rt", encoding="utf-8") as f:
                blob = json.load(f)
            стр = {str(p.get("url") or ""): (p.get("html") or "")
                   for p in (blob.get("pages") or [])}
        except Exception:                                     # noqa: BLE001
            стр = {}
    if len(_кеш_памяти) > 300:
        _кеш_памяти.clear()
    _кеш_памяти[inn] = стр
    return стр


def доказан(inn, email):
    src = источники.get((inn, email)) or {}
    url = str(src.get("source_url") or "").strip()
    стр = страницы(inn)
    if not стр:
        return "страниц нет в кеше", url, src
    if not url:
        # источник не записан - ищем адрес по ВСЕМ страницам компании
        for u, h in стр.items():
            if email in (h or "").lower():
                return "есть на странице (источник найден перебором)", u, src
        return "нет источника, в кеше не найден", "", src
    if url in стр and email in (стр[url] or "").lower():
        return "есть на странице", url, src
    # Не нашёлся на странице-источнике - это ещё не приговор: обходчик
    # записывает ОДИН url, а адрес часто лежит и в подвале, и на «Контактах»,
    # и в карточке отдела. Сдаваться, не посмотрев остальные страницы
    # компании, значит объявлять недоказанным то, что доказано соседней
    # страницей того же сайта.
    for u, h in стр.items():
        if u != url and email in (h or "").lower():
            return "есть на другой странице кеша", u, src
    if url in стр:
        return "страница в кеше, адреса нет НИ НА ОДНОЙ", url, src
    return "страницы источника нет в кеше, адрес не найден", url, src


оч = [r for r in (store.confirm_list(status="pending", limit=100000) or [])
      if int(r.get("campaign_id") or 0) in КАМПАНИИ]
print(f"писем к проверке: {len(оч)}")

счёт, флаги = Counter(), Counter()
плохие = []
for r in оч:
    rid = int(r.get("recipient_id") or 0)
    rec = store.get_recipient(rid)
    inn = "".join(c for c in str(r.get("inn") or "") if c.isdigit())
    email = str(r.get("email") or "").strip().lower()
    тема = str(r.get("subject") or "")
    тело = str(r.get("body") or "")
    div = "meyer" if int(r.get("campaign_id") or 0) == 11 else "kc"

    вердикт, url, src = доказан(inn, email)
    счёт[вердикт] += 1

    свои = []
    низ = (тема + "\n" + тело).lower()
    бренды = sorted({б for б in БРЕНДЫ if б in низ})
    if бренды:
        свои.append(f"бренд в тексте: {', '.join(бренды)}")

    req = q._request(rec) if rec else {}
    extra = dict((req or {}).get("extra") or {})
    for k in ("company_name", "contact_name", "city", "domain"):
        if not extra.get(k) and rec is not None and getattr(rec, k, None):
            extra[k] = getattr(rec, k)
    бел = allowed_numbers(ФАКТЫ.get(div) or {}, extra, div)
    свои_числа = set()
    for k in ("company_name", "city", "contact_name"):
        свои_числа |= set(re.findall(r"\d+", str(extra.get(k) or "")))
    лишние = sorted(set(re.findall(
        r"\d+", re.sub(r"https?://\S+", " ", тело))) - бел - свои_числа)
    if лишние:
        свои.append(f"числа вне паспорта: {лишние}")

    имя = str(getattr(rec, "company_name", "") or "")
    if имя:
        корни = [w for w in re.findall(r"[^\W\d_]{4,}", имя, re.U)
                 if w.upper() not in ("ОБЩЕСТВО", "ОГРАНИЧЕННОЙ",
                                      "ОТВЕТСТВЕННОСТЬЮ", "АКЦИОНЕРНОЕ",
                                      "ПУБЛИЧНОЕ", "ЗАВОД", "КОМПАНИЯ",
                                      "ГРУППА", "ФИРМА", "ПРЕДПРИЯТИЕ")]
        if корни and not any(к[:5].lower() in низ for к in корни):
            свои.append("получатель не назван (19и)")

    # РЕЖИМ НАДО РАЗРЕШИТЬ ТАК ЖЕ, КАК ЭТО ДЕЛАЕТ ГЕНЕРАЦИЯ. _request отдаёт
    # 'auto', а AiLetterGen.generate превращает его в NEWS, когда в карточке
    # есть новость с объектом и городом. Гейт по неразрешённому 'auto' бьёт
    # правилом «псевдо-новость» законные новостные письма: на первых девяти
    # я так забраковал четыре, у которых новость настоящая и с числами.
    режим = str((req or {}).get("mode") or "auto")
    if режим == "auto":
        режим = ("NEWS" if (extra.get("news_object") and extra.get("city"))
                 else "GENERIC")
    try:
        gf = gate(тема, тело, mode=режим,
                  extra=extra, facts=ФАКТЫ.get(div) or {}, division=div)
    except Exception as e:                                    # noqa: BLE001
        gf = [f"гейт упал: {str(e)[:80]}"]
    if gf:
        свои.append("гейт: " + "; ".join(str(x)[:70] for x in gf[:3]))

    ДОКАЗАННЫЕ = ("есть на странице", "есть на другой странице кеша",
                  "есть на странице (источник найден перебором)")
    if вердикт not in ДОКАЗАННЫЕ:
        свои.append(f"контакт не доказан: {вердикт}")

    for f in свои:
        флаги[f.split(":")[0]] += 1
    зап = {"review_id": int(r["id"]), "inn": inn, "email": email,
           "компания": имя[:50], "направление": div, "режим": режим,
           "новость": str(extra.get("news_object") or "")[:90],
           "новость_url": str(extra.get("news_url") or "")[:160],
           "контакт": вердикт, "источник": url, "роль": str(src.get("role") or ""),
           "человек": str(src.get("person") or ""),
           "флаги": свои, "чисто": not свои, "ts": int(time.time())}
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
        f.write(json.dumps(зап, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    if свои:
        плохие.append(зап)

print("\n-- доказанность контакта --")
for k, n in счёт.most_common():
    print(f"  {k:<42} {n}")
print("\n-- флаги --")
for k, n in флаги.most_common():
    print(f"  {k:<42} {n}")
print(f"\nчистых писем: {len(оч) - len(плохие)} из {len(оч)}")
for z in плохие[:15]:
    print(f"  #{z['review_id']} {z['компания'][:32]:<34} {z['флаги']}")
