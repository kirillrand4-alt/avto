# -*- coding: utf-8 -*-
"""Выборочная проверка писем партии вторых адресов судьёй на провайдере.

Владелец 28.08: «посмотри выборочно письма которые стоят на отправку, там
всё верно написано? … выборочно штук 50».

Тяжёлое — через провайдерский API (правило владельца), пачками по 5 писем.
Вердикты пишем строкой в _ops\\sud-vtoryh.jsonl с fsync: прогон резюмируемый.
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "50"))
МОДЕЛЬ = next((a.split("=", 1)[1] for a in sys.argv[1:]
               if a.startswith("модель=")), "claude-sonnet-4-6")
ПАЧКА = 5
# Партия задаётся аргументом: partiya=2 читает второй список адресов и пишет
# вердикты в свой файл, чтобы прогоны не смешивались.
ПАРТИЯ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("partiya=")), "1")
_ХВОСТ = "" if ПАРТИЯ == "1" else "-%s" % ПАРТИЯ
АДРЕСА = r"C:\sender\_ops\vtorye-adresa%s.jsonl" % _ХВОСТ
СЛЕД = r"C:\sender\_ops\sud-vtoryh%s.jsonl" % _ХВОСТ

СИСТЕМА = """Ты придирчивый редактор холодных B2B-писем. Тебе дают карточку
компании (название, ОКВЭД, паспорт сайта — то, что о ней реально известно) и
письмо, которое ей собираются отправить.

Отправитель — ООО «Руспром», два направления:
· «Компрессор Центр» — компрессоры, осушители, генераторы азота и кислорода,
  пневмоинструмент, системы подготовки сжатого воздуха.
· «Руспром Meyer» — рентген-инспекция упакованной продукции и фотосепараторы
  (очистка сыпучего/овощного сырья от посторонних включений).

Проверь КАЖДОЕ письмо по пунктам и ответь строго JSON:
{"pisma":[{"id":<id>,
  "fakty_verny": true/false,      // всё сказанное о компании подтверждается карточкой
  "vydumka": "" или что именно выдумано (продукт, цех, цифра, которых в карточке нет),
  "napravlenie_verno": true/false,// компании вообще может пригодиться ЭТО направление
  "napravlenie_pochemu": "коротко",
  "reklama": true/false,          // рекламные обороты, обещания, самовосхваление
  "vopros_est": true/false,       // есть конкретный вопрос адресату, а не монолог
  "obrashchenie_ok": true/false,  // приветствие уместно и не к чужому человеку
  "yazyk_ok": true/false,         // русский чистый, без корявых склонений названия
  "verdikt": "годно"|"поправить"|"не отправлять",
  "chto_ne_tak": "одной фразой, пусто если годно"}]}

Строгость: «не отправлять» — если письмо о том, чего компания не делает, или
направление ей заведомо не нужно. «Поправить» — мелочи: корявое склонение,
слабый вопрос. Не придирайся к отсутствию подписи: её движок дописывает при
отправке. Метка ИМЯ_ОТПРАВИТЕЛЯ — так и задумано, это не ошибка."""

партия = {}
for с in io.open(АДРЕСА, encoding="utf-8"):
    d = json.loads(с)
    партия[int(d["review"])] = (str(d["inn"]), d["email"].lower())

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(партия))
строки = c.execute(
    "SELECT cr.id, cr.email, cr.subject, cr.body, cr.inn, cr.panel_json, "
    "       r.company_name, r.okved "
    "  FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.id IN (%s) AND cr.status='pending' ORDER BY cr.id" % зн,
    list(партия)).fetchall()
c.close()
шаг = max(1, len(строки) // СКОЛЬКО)
проба = [строки[i] for i in range(0, len(строки), шаг)][:СКОЛЬКО]
print("в очереди %d, беру каждое %d-е -> %d писем, модель %s"
      % (len(строки), шаг, len(проба), МОДЕЛЬ))

уже = set()
if os.path.exists(СЛЕД):
    for с in io.open(СЛЕД, encoding="utf-8", errors="replace"):
        try:
            уже.add(int(json.loads(с)["id"]))
        except Exception:                                        # noqa: BLE001
            pass
проба = [r for r in проба if int(r["id"]) not in уже]
print("осталось судить: %d (ранее %d)" % (len(проба), len(уже)))
if not проба:
    raise SystemExit(0)

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
инны = sorted({str(r["inn"]) for r in проба})
паспорта = {}
зн2 = ",".join("?" * len(инны))
for r in e.execute("SELECT inn, facts_json FROM site_facts WHERE inn IN (%s)" % зн2, инны):
    т = str(r["facts_json"] or "")
    if len(т) > len(паспорта.get(str(r["inn"]), "")):
        паспорта[str(r["inn"])] = т
e.close()


def блок(r):
    п = паспорта.get(str(r["inn"]), "")
    if len(п) > 1400:
        п = п[:1400] + "…"
    роль = ""
    try:
        роль = ((json.loads(r["panel_json"] or "{}") or {})
                .get("vtoroy_adres") or {}).get("rol") or ""
    except Exception:                                            # noqa: BLE001
        pass
    return ("id: %s\nКОМПАНИЯ: %s\nОКВЭД: %s\nПАСПОРТ САЙТА: %s\n"
            "АДРЕСАТ: %s (роль: %s)\nТЕМА: %s\nПИСЬМО:\n%s"
            % (r["id"], r["company_name"], str(r["okved"] or "—")[:90],
               п or "нет", r["email"], роль or "—", r["subject"],
               str(r["body"] or "")[:2600]))


def судить(пачка):
    текст = "\n\n" + ("=" * 40) + "\n\n"
    зов = текст.join(блок(r) for r in пачка)
    for попытка in range(3):
        try:
            m = GP._raw_stream([{"role": "user", "content": зов}], МОДЕЛЬ, 3000,
                               thinking=False, system=СИСТЕМА)
            т = "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
            мм = re.search(r"\{.*\}", т, re.S)
            if not мм:
                continue
            d = json.loads(мм.group(0))
            u = getattr(m, "usage", None)
            return (d.get("pisma") or [],
                    int(getattr(u, "input_tokens", 0) or 0),
                    int(getattr(u, "output_tokens", 0) or 0))
        except Exception as ex:                                  # noqa: BLE001
            print("   пачка сбойнула (%s), повтор %d" % (str(ex)[:70], попытка + 1),
                  flush=True)
            time.sleep(3 * (попытка + 1))
    return [], 0, 0


пачки = [проба[i:i + ПАЧКА] for i in range(0, len(проба), ПАЧКА)]
t0 = time.time()
вх = вых = 0
поток = io.open(СЛЕД, "a", encoding="utf-8")
готово = []
with ThreadPoolExecutor(max_workers=4) as ex:
    for вердикты, i, o in ex.map(судить, пачки):
        вх += i
        вых += o
        for в in вердикты:
            готово.append(в)
            поток.write(json.dumps(в, ensure_ascii=False) + "\n")
        поток.flush()
        os.fsync(поток.fileno())
поток.close()
цена = вх / 1e6 * 3.0 + вых / 1e6 * 15.0
print("судил %d писем за %.0f с, вход %d, выход %d, ~$%.3f"
      % (len(готово), time.time() - t0, вх, вых, цена))
print("")
print("=== вердикты ===")
for к, n in Counter(str(в.get("verdikt")) for в in готово).most_common():
    print("   %-16s %4d" % (к, n))
print("")
print("=== по признакам (сколько ПЛОХО) ===")
for поле, имя in (("fakty_verny", "факты неверны"),
                  ("napravlenie_verno", "направление не то"),
                  ("vopros_est", "нет вопроса"),
                  ("obrashchenie_ok", "обращение не то"),
                  ("yazyk_ok", "язык корявый")):
    print("   %-22s %4d" % (имя, sum(1 for в in готово if в.get(поле) is False)))
print("   %-22s %4d" % ("реклама", sum(1 for в in готово if в.get("reklama") is True)))
print("   %-22s %4d" % ("выдумки", sum(1 for в in готово if (в.get("vydumka") or "").strip())))
