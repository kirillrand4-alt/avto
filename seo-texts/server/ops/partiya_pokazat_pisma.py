# -*- coding: utf-8 -*-
"""Свежие письма партии 935 целиком - чтобы владелец их прочитал и оценил.

Отличие от ops/partiya_sverka_pisem.py: тот сверяет форму с эталоном по
диапазону id, а здесь нужно просто «покажи последние N писем очереди, как
они есть». Диапазон id владелец не знает и знать не обязан.

Рядом с каждым письмом печатаем то, из чего оно сделано: направление
карточки, ОКВЭД, контакт и роль ящика, признаки надёжности имени. Без этого
письмо нечем оценивать: «почему обратились по имени» и «почему нет просьбы
перенаправить» видно только из карточки.

Отчёт целиком уходит на дроп: письма в стандартный вывод задания не влезают,
его к тому же режет с начала.

    python zapusk_svoego_skripta.py ops/partiya_pokazat_pisma.py 6
"""
import io
import json
import os
import re
import sqlite3
import sys
import urllib.request

БАЗА = r"C:\sender\sender.db"
ИМЯ = "PISMA-SVEZHIE.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ
СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 else 6
КАМПАНИИ = (10, 11)

conn = sqlite3.connect(f"file:{БАЗА}?mode=ro", uri=True, timeout=30)
conn.row_factory = sqlite3.Row

С = []


def п(s=""):
    С.append(s)


def слов(т):
    return len([w for w in re.split(r"\s+", т or "") if w.strip()])


строки = list(conn.execute(
    "SELECT * FROM confirm_reviews WHERE campaign_id IN (?,?) "
    "ORDER BY id DESC LIMIT ?", (*КАМПАНИИ, СКОЛЬКО)))
строки.reverse()

п(f"# Свежие письма партии 935 - последние {len(строки)} из очереди")
п()
if not строки:
    п("В очереди по кампаниям 10/11 писем нет.")

for r in строки:
    d = dict(r)
    panel = {}
    try:
        panel = json.loads(d.get("panel_json") or "{}")
    except Exception:                                          # noqa: BLE001
        panel = {}
    comp = (panel.get("company") or {}) if isinstance(
        panel.get("company"), dict) else {}
    напр = (str(panel.get("letter_division") or "").strip()
            or str(comp.get("division") or "").strip() or "?")
    кампания = d.get("campaign_id")
    п(f"## review #{d.get('id')} | кампания {кампания} "
      f"({'КЦ' if кампания == 10 else 'Meyer'}) | направление письма {напр}")
    п()
    п("**Карточка, из которой писали**")
    п()
    п(f"- компания: {comp.get('name') or d.get('company_name') or '?'} "
      f"(ИНН {comp.get('inn') or d.get('inn') or '?'})")
    п(f"- ОКВЭД/профиль: {comp.get('okved') or '?'} "
      f"{comp.get('activity') or ''}".rstrip())
    п(f"- ящик: {d.get('email') or '?'} | роль ящика: "
      f"{comp.get('role') or panel.get('role') or 'не указана'}")
    п(f"- контакт в карточке: {comp.get('contact_name') or 'нет имени'}")
    п(f"- источник имени: {comp.get('contact_source') or 'нет'} "
      f"{comp.get('contact_source_url') or ''}".rstrip())
    п(f"- статус в очереди: {d.get('status')}")
    п()
    п(f"**Тема:** {d.get('subject') or ''}")
    п()
    п("```")
    for s in str(d.get("body") or "").splitlines():
        п(s)
    п("```")
    п()
    п(f"объём тела: {слов(d.get('body'))} слов")
    п()

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
except Exception as ex:                                        # noqa: BLE001
    print("на диск не легло:", str(ex)[:200])
try:
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/" + ИМЯ,
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as rp:
        rp.read()
    print(f"отчёт на дропе: {ИМЯ}")
except Exception as ex:                                        # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])

print(f"писем в отчёте: {len(строки)}")
for r in строки:
    print(f"  #{r['id']} камп.{r['campaign_id']} {r['status']} "
          f"{str(r['email'])[:40]}")
