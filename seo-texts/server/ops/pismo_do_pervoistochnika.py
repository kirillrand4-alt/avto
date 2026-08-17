# -*- coding: utf-8 -*-
"""Одно письмо целиком: текст, карточка, и ССЫЛКИ, по которым это проверяемо.

Владелец: «проверь каждое 50-ое глазами полностью до первоисточника». Читать
письмо и карточку мало: карточка сама может врать (её собирал обход), а
письмо ссылается на факты, которых в карточке может не быть вовсе. Поэтому
собираем в одном месте ВСЁ, что нужно для сверки руками:

  * тему и тело письма как они лежат в очереди;
  * карточку: направление, ОКВЭД с расшифровкой, деятельность, регион,
    выручку, контакт и роль ящика;
  * ИСТОЧНИКИ: сайт компании, ссылку, откуда взят контакт, ссылку новости -
    то есть адреса, которые надо открыть и сравнить с текстом письма;
  * все ЧИСЛА и ИМЕНА СОБСТВЕННЫЕ из письма отдельным списком - именно они
    бывают выдуманными, и именно их проверяют по первоисточнику;
  * механические проверки: длинное тире, <ul>, объём, байлайн, марки.

    python zapusk_svoego_skripta.py ops/pismo_do_pervoistochnika.py 1560
"""
import io
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ID = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ИМЯ = "PISMO-DO-ISTOCHNIKA.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ
МАРКИ = ("atlas copco", "kaeser", "ремеза", "enger", "remeza", "abac",
         "fini", "ceccato", "chicago pneumatic", "ingersoll", "boge",
         "alup", "берг", "dalgakiran", "далгакиран")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    if ID:
        row = store._conn.execute(
            "SELECT id, campaign_id, email, inn, subject, body, panel_json, "
            "status, recipient_id FROM confirm_reviews WHERE id=?",
            (ID,)).fetchone()
    else:
        row = store._conn.execute(
            "SELECT id, campaign_id, email, inn, subject, body, panel_json, "
            "status, recipient_id FROM confirm_reviews WHERE campaign_id=10 "
            "ORDER BY id DESC LIMIT 1").fetchone()
if not row:
    print("письма нет")
    raise SystemExit(0)

rid, camp, email, inn, subj, body, pj, статус, recip = row
try:
    panel = json.loads(pj or "{}")
except Exception:                                               # noqa: BLE001
    panel = {}
comp = panel.get("company") if isinstance(panel.get("company"), dict) else {}
full = panel.get("company_full") if isinstance(
    panel.get("company_full"), dict) else {}
cont = panel.get("contact") if isinstance(panel.get("contact"), dict) else {}
enr = (full.get("enrich") or {}) if isinstance(full.get("enrich"), dict) else {}
ecomp = (enr.get("company") or {}) if isinstance(enr.get("company"), dict) else {}

С = []


def п(s=""):
    С.append(s)


п(f"# Письмо #{rid} до первоисточника")
п()
п(f"кампания {camp} · статус {статус} · получатель {recip} · ИНН {inn}")
п(f"ящик: {email}")
п()
п("## Письмо")
п()
п(f"**Тема:** {subj}")
п()
п("```")
for s in str(body or "").splitlines():
    п(s)
п("```")
п()

п("## Карточка, из которой писали")
п()
п(f"- направление письма: **{panel.get('letter_division')}** "
  f"(причина {panel.get('letter_division_reason')})")
п(f"- направление карточки: **{comp.get('division')}**")
п(f"- название: {comp.get('name') or full.get('name')}")
п(f"- ОКВЭД: {comp.get('okved')} · {ecomp.get('okved_name') or ''}")
для_кодов = full.get("okved_decoded") or []
if isinstance(для_кодов, list) and для_кодов:
    п(f"- коды с расшифровкой: "
      f"{', '.join(str(d.get('name'))[:40] for d in для_кодов[:6] if isinstance(d, dict))}")
п(f"- деятельность (строка с сайта): {ecomp.get('activity') or 'нет'}")
п(f"- регион: {comp.get('region') or full.get('region') or 'нет'}")
п(f"- выручка: {ecomp.get('revenue') or 'нет'}")
п(f"- контакт: {cont.get('person') or 'нет имени'} · роль ящика: "
  f"{cont.get('role') or 'нет'}")
п()

п("## ЧТО ОТКРЫТЬ И СВЕРИТЬ (первоисточники)")
п()
источники = []
for ключ, подпись in (("site", "сайт компании"), ("domain", "домен"),
                      ("site_url", "сайт"), ("source_url", "источник строки")):
    v = ecomp.get(ключ) or comp.get(ключ) or full.get(ключ)
    if v:
        источники.append((подпись, str(v)))
if cont.get("source_url"):
    источники.append(("откуда взят контакт", str(cont["source_url"])))
if panel.get("news_url"):
    источники.append(("новость-повод", str(panel["news_url"])))
for подпись, url in источники:
    п(f"- {подпись}: {url}")
if not источники:
    п("- ССЫЛОК НЕТ ВОВСЕ - проверить письмо по первоисточнику нечем")
п()

п("## Что в письме подлежит проверке")
п()
числа = re.findall(r'\d[\d\s.,]*\s*(?:%|млн|млрд|тыс|шт|м3|м³|кВт|бар|литр\w*|'
                   r'год\w*|лет|бутыл\w*|тонн\w*)?', f"{subj}\n{body}")
числа = [ч.strip() for ч in числа if ч.strip() and len(ч.strip()) > 1]
п(f"- числа в письме: {числа or 'нет'}")
собственные = re.findall(r'«([^»]{2,40})»', f"{subj}\n{body}")
п(f"- названия в кавычках: {собственные or 'нет'}")
ссылки = re.findall(r'https?://\S+', str(body or ""))
п(f"- ссылки в теле: {ссылки or 'нет'}")
п()

п("## Механика")
п()
бяки = []
т = f"{subj}\n{body}"
if "—" in т or "–" in т:
    бяки.append("длинное тире")
if "<ul" in т.lower() or "<li" in т.lower():
    бяки.append("<ul>/<li>")
слов = len([w for w in re.split(r"\s+", str(body or "")) if w.strip()])
if not (45 <= слов <= 140):
    бяки.append(f"объём {слов} слов (норма 45-140)")
for м in МАРКИ:
    if м in т.lower():
        бяки.append(f"марка оборудования: {м}")
if "не отвлекать" not in т and str(panel.get("letter_division")) == "kc":
    бяки.append("нет канонной концовки КЦ")
п(f"- объём: {слов} слов")
п(f"- нарушений: {бяки or 'нет'}")
п()

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/" + ИМЯ,
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as rp:
        rp.read()
    print(f"отчёт на дропе: {ИМЯ}")
except Exception as ex:                                         # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])
print(f"письмо #{rid}, источников {len(источники)}, нарушений {len(бяки)}")
for подпись, url in источники:
    print(f"  {подпись}: {url}")
