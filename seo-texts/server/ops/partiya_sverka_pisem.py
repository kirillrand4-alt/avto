# -*- coding: utf-8 -*-
"""Свежие письма против отправленных вручную: то же ли это письмо по форме.

Вопрос владельца: письма после правки написаны так же, как те, что он
отправлял руками? Единственным отличием должно быть, что факты берутся из
карточки, а не выдумываются из ОКВЭДа.

Поэтому берём три вещи разом:
  * тела писем, ОТПРАВЛЕННЫХ вручную (status='sent' и строки send_log) -
    это эталон;
  * тела писем, сделанных после правки (по списку review_id в аргументах);
  * карточку каждого письма (panel_json) - чтобы видеть, откуда взяты числа
    и факты: из карточки или из воздуха.

Механические проверки по правилам владельца: длинных тире нет, <ul> нет,
предприятие названо в теме и в теле, байлайн «ООО «Руспром»», объём
45-140 слов, марок оборудования нет.

Отчёт целиком уходит на дроп: в стандартный вывод письма не влезают.

    python zapusk_svoego_skripta.py ops/partiya_sverka_pisem.py 1268 1276
"""
import io
import json
import os
import re
import sqlite3
import sys
import urllib.request

БАЗА = r"C:\sender\sender.db"
ОТЧЁТ = r"C:\sender\_ops\SVERKA-PISEM.md"
ОТ = int(sys.argv[1]) if len(sys.argv) > 1 else 1268
ДО = int(sys.argv[2]) if len(sys.argv) > 2 else 1276

# Марки оборудования в теле холодного письма - брак (правило владельца).
МАРКИ = ("atlas copco", "kaeser", "ремеза", "enger", "remeza", "abac",
         "fini", "ceccato", "chicago pneumatic", "ingersoll", "boge",
         "alup", "берг", "dalgakiran", "далгакиран")

conn = sqlite3.connect(f"file:{БАЗА}?mode=ro", uri=True, timeout=30)
conn.row_factory = sqlite3.Row

С = []


def п(s=""):
    С.append(s)


def слов(т):
    return len([w for w in re.split(r"\s+", т or "") if w.strip()])


def проверки(subject, body, имя_фирмы):
    """Механический гейт по правилам владельца. Возвращает список нарушений."""
    бяки = []
    т = f"{subject}\n{body}"
    if "—" in т or "–" in т:
        бяки.append("длинное тире")
    if "<ul" in т.lower() or "<li" in т.lower():
        бяки.append("<ul>/<li>")
    n = слов(body)
    if not (45 <= n <= 140):
        бяки.append(f"объём {n} слов (норма 45-140)")
    if "руспром" not in т.lower():
        бяки.append("нет байлайна «Руспром»")
    ядро = re.sub(r'^(ООО|АО|ПАО|ОАО|ЗАО|НПФ|ГК)\s+', '', str(имя_фирмы or ''),
                  flags=re.I).strip(' "«»')
    ядро = ядро.split()[0].strip(' "«».,') if ядро else ""
    if ядро and len(ядро) > 3:
        if ядро.lower() not in subject.lower():
            бяки.append(f"«{ядро}» нет в теме")
        if ядро.lower() not in body.lower():
            бяки.append(f"«{ядро}» нет в теле")
    for м in МАРКИ:
        if м in т.lower():
            бяки.append(f"марка оборудования: {м}")
    return бяки


def карточка_фактов(panel_json):
    """Что панель дала модели как факты компании."""
    try:
        d = json.loads(panel_json or "{}")
    except Exception:                                          # noqa: BLE001
        return {}
    из = {}
    for ключ in ("facts", "факты", "company", "kartochka", "карточка",
                 "recipient", "profile", "site_facts", "idea"):
        if isinstance(d.get(ключ), (dict, list, str)):
            из[ключ] = d[ключ]
    return из


def числа(т):
    """Числа из текста - их и надо сверять с карточкой."""
    return sorted(set(re.findall(r"\b\d[\d\s]{1,8}\b", т or "")))


def показать(r, метка):
    subject = r["edited_subject"] or r["subject"] or ""
    body = r["edited_body"] or r["body"] or ""
    имя = ""
    rec = conn.execute("SELECT company_name FROM recipients WHERE id=?",
                       (r["recipient_id"],)).fetchone()
    if rec:
        имя = rec["company_name"] or ""
    бяки = проверки(subject, body, имя)
    п(f"### {метка} #{r['id']} — {имя[:52]}")
    п()
    п(f"кампания {r['campaign_id']} | статус **{r['status']}** | "
      f"создана {r['created_at'][:19]}"
      + (f" | решил {r['decided_by']}" if r["decided_by"] else ""))
    п()
    п(f"**Тема:** {subject}")
    п()
    п("```")
    п(body.strip())
    п("```")
    п()
    п(f"слов {слов(body)} | числа в тексте: {числа(body) or 'нет'}")
    п(f"механика: {'ЧИСТО' if not бяки else '; '.join(бяки)}")
    факты = карточка_фактов(r["panel_json"])
    if факты:
        сжато = json.dumps(факты, ensure_ascii=False)
        п(f"карточка дала: {сжато[:900]}")
    else:
        п("карточка: фактов в panel_json не найдено")
    п()
    return бяки


п("# Свежие письма против отправленных вручную")
п()

# --- эталон: то, что ушло руками ----------------------------------------
п("## Эталон — письма, отправленные вручную")
п()
эталон = list(conn.execute(
    "SELECT * FROM confirm_reviews WHERE status='sent' "
    "ORDER BY id DESC LIMIT 4"))
if not эталон:
    п("писем со статусом sent в очереди нет — беру из send_log")
    for s in conn.execute("SELECT * FROM send_log ORDER BY id DESC LIMIT 4"):
        п(f"* send_log #{s['id']}: {s['email']} — «{s['subject']}» "
          f"({s['created_at'][:19]})")
    п()
    п("(тела в send_log не хранятся, только тема)")
бяки_эталона = []
for r in эталон:
    бяки_эталона += показать(r, "ОТПРАВЛЕНО ВРУЧНУЮ")

# --- свежие --------------------------------------------------------------
п("## Свежие письма после правки")
п()
свежие = list(conn.execute(
    "SELECT * FROM confirm_reviews WHERE id BETWEEN ? AND ? ORDER BY id",
    (ОТ, ДО)))
бяки_свежих = []
for r in свежие:
    бяки_свежих += показать(r, "ПОСЛЕ ПРАВКИ")

п("## Итог механики")
п()
п(f"эталонных писем {len(эталон)}, нарушений {len(бяки_эталона)}: "
  f"{бяки_эталона or 'нет'}")
п(f"свежих писем {len(свежие)}, нарушений {len(бяки_свежих)}: "
  f"{бяки_свежих or 'нет'}")

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/SVERKA-PISEM.md",
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as r:
        r.read()
    print("отчёт на дропе: SVERKA-PISEM.md")
except Exception as ex:                                        # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])

print(f"эталонных {len(эталон)}, нарушений {len(бяки_эталона)}")
print(f"свежих {len(свежие)}, нарушений {len(бяки_свежих)}")
