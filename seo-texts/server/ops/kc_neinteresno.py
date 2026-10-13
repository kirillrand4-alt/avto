# -*- coding: utf-8 -*-
"""Ответы по КЦ: кого владелец пометил «не интересно», хотя в ответе был интерес.

Владелец 13.10: «посмотри ответы по кц, сколько среди них тех, кто был
относительно заинтересован (пришлите прайс и т.д.), но я его скипнул в
неинтересно». Провайдер на нуле — поэтому без LLM: сырьё (текст ответа)
выкладываем в _ops/kc-neinteresno.json, признаки интереса — словарём.

    kc_neinteresno.py            — свод
    kc_neinteresno.py pokazat N S — тексты кандидатов
"""
import io
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402

LIM = 300
ФАЙЛ = r"C:\sender\_ops\kc-neinteresno.json"
ИНТЕРЕС = re.compile(
    r"(?i)прайс|цен[аыуе]|стоимост|коммерческ|\bкп\b|предложени|расч[её]т|"
    r"рассчита|каталог|пришлите|направьте|вышлите|отправьте|скиньте|"
    r"интерес|актуальн|рассмотр|перезвон|позвон|свяж|телефон|\+7|8 ?\(?9\d\d|"
    r"нужн|требует|потребност|ищем|подбер|тех\w* характеристик|опросн")
ОТКАЗ = re.compile(r"(?i)не интерес|не актуальн|не нужн|не требует|нет потребност|"
                   r"не рассматрива|не планиру|отпиш|удалит|не пишите|спам|откаж")

if "pokazat" in sys.argv:
    i = sys.argv.index("pokazat")
    n, s = int(sys.argv[i + 1]), int(sys.argv[i + 2])
    LIM = int(sys.argv[i + 3]) if len(sys.argv) > i + 3 else 300
    д = json.load(io.open(ФАЙЛ, encoding="utf-8"))
    for x in д[s:s + n]:
        print("## #%s %s | %s | %s" % (x["lead"], str(x["company"])[:30], x["kind"], x["date"]))
        print(x["text"][:LIM])
        print()
    print("=== ПОКАЗАНО %d-%d из %d ===" % (s + 1, min(s + n, len(д)), len(д)))
    sys.exit(0)

store = Store(r"C:\sender\sender.db")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
# Лиды в базе без campaign_id (все 340) — направление берём по письму,
# на которое ответили: последнее отправленное этому получателю → его
# кампания (КЦ: 1, 5, 6, 9, 10; Meyer: 7, 8, 11-14) и ящик (div ящика).
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
div_ящика = {}
for м in cfg.mailboxes():
    div_ящика[str(getattr(м, "mailbox_id", "") or getattr(м, "login", ""))] = str(
        getattr(м, "division", "") or "")
КЦ_КАМП, МЕЙЕР_КАМП = {1, 5, 6, 9, 10}, {7, 8, 11, 12, 13, 14}


def направление(л):
    rid = л.get("recipient_id")
    if not rid:
        return "?"
    р = c.execute("SELECT campaign_id, mailbox_id FROM messages WHERE recipient_id=? "
                  "AND status='sent' ORDER BY sent_at DESC LIMIT 1", (rid,)).fetchone()
    if not р:
        return "?"
    д = div_ящика.get(str(р["mailbox_id"] or ""))
    if д in ("kc", "meyer"):
        return д
    return "kc" if р["campaign_id"] in КЦ_КАМП else "meyer" if р["campaign_id"] in МЕЙЕР_КАМП else "?"


лиды = [dict(р) for р in c.execute("SELECT * FROM leads")]
for л in лиды:
    л["_напр"] = направление(л)
print("лиды по направлению: %s" % dict(Counter(л["_напр"] for л in лиды)))
лиды_кц = [л for л in лиды if л["_напр"] == "kc"]
print("ответов-лидов по КЦ: %d; статусы: %s" % (len(лиды_кц), dict(Counter(л["status"] for л in лиды_кц))))
print("виды (классификатор): %s" % dict(Counter(л["reply_kind"] for л in лиды_кц).most_common()))


def текст(л):
    куски = []
    if л.get("source_event_id"):
        р = c.execute("SELECT detail_json FROM events WHERE id=?", (л["source_event_id"],)).fetchone()
        if р and р[0]:
            try:
                d = json.loads(р[0])
            except Exception:  # noqa: BLE001
                d = {}
            for к in ("body", "text", "snippet", "reply_text", "summary"):
                if d.get(к):
                    куски.append(str(d[к]))
                    break
    if л.get("need"):
        куски.append("[нужда] " + str(л["need"]))
    return "\n".join(куски)


ЦИТАТА = re.compile(
    r"(?im)^\s*>|^-{2,}\s*Original Message|^\s*From:|^\s*От кого:|^\s*Отправлено из|"
    r"\d{4}\s*г\.,?\s*\d{1,2}:\d\d.*\sот\s|^\s*\d{1,2}\.\d{1,2}\.\d{4}.*пишет|wrote:|написал\(а\):|"
    r"^\s*--\s*$|^\s*С уважением|^\s*Настоящее сообщение")


def чистый(т):
    т = т.replace("[нужда] ", "")
    м = ЦИТАТА.search(т)
    т = т[:м.start()] if м else т
    return re.sub(r"\s+", " ", т).strip()


кандидаты = []
for л in лиды_кц:
    if л["status"] != "not_interested":
        continue
    т = чистый(текст(л))
    за = sorted({м.group(0).lower() for м in ИНТЕРЕС.finditer(т)})
    против = sorted({м.group(0).lower() for м in ОТКАЗ.finditer(т)})
    кандидаты.append({"lead": л["id"], "company": л.get("company_name") or л["email"],
                      "kind": л.get("reply_kind"), "date": str(л["created_at"])[:10],
                      "metki": "за: %s | против: %s" % (",".join(за[:6]), ",".join(против[:4])),
                      "za": len(за), "protiv": len(против), "text": т})
кандидаты.sort(key=lambda x: (-(x["za"] > 0 and x["protiv"] == 0), -x["za"], x["protiv"]))
json.dump(кандидаты, io.open(ФАЙЛ, "w", encoding="utf-8"), ensure_ascii=False)
print("помечено «не интересно»: %d" % len(кандидаты))
print("   с признаками интереса и без слов отказа: %d" % sum(1 for x in кандидаты if x["za"] and not x["protiv"]))
print("   с интересом И отказом (смешанные): %d" % sum(1 for x in кандидаты if x["za"] and x["protiv"]))
print("   без признаков интереса: %d" % sum(1 for x in кандидаты if not x["za"]))
print("   по виду классификатора: %s" % dict(Counter(x["kind"] for x in кандидаты).most_common()))
print("   без текста ответа: %d" % sum(1 for x in кандидаты if not x["text"].strip()))
print("=== КЦ НЕ ИНТЕРЕСНО ===")
