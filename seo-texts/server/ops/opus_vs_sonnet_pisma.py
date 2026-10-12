# -*- coding: utf-8 -*-
"""Письма для сравнения: Meyer на opus, на которые ответили, и сегодняшние на sonnet.

Владелец 12.10: «дай штук 10 по которым ответили и были написаны на опусе и
рандомные 10 на соннет сегодня». Модель берём из журналов драйвера (там она
записана по каждому письму), текст — отправленный (messages.body_rendered),
а для неотправленных сегодняшних — из очереди подтверждения.

    opus_vs_sonnet_pisma.py sobrat        — собрать в _ops/sravnenie-pisem.json
    opus_vs_sonnet_pisma.py pokazat N S   — показать N писем начиная с S
"""
import io
import json
import random
import sqlite3
import sys

ВЫХОД = r"C:\sender\_ops\sravnenie-pisem.json"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

if "sobrat" in sys.argv:
    # кто ответил живым ответом (лента лидов без автоответов и отписок)
    кол = [р[1] for р in c.execute("PRAGMA table_info(leads)")]
    поле_вида = "reply_kind" if "reply_kind" in кол else None
    ответили = {}
    for р in c.execute("SELECT * FROM leads"):
        р = dict(р)
        вид = str(р.get(поле_вида) or "") if поле_вида else ""
        if вид in ("auto_reply", "unsub_request", "avtootvet"):
            continue
        for к in ("recipient_id",):
            if р.get(к):
                ответили[int(р[к])] = вид or "ответ"
    print("лидов с живым ответом (по recipient_id): %d" % len(ответили))

    opus = []
    for с in io.open(r"C:\sender\_ops\gen-partiya-935.jsonl", encoding="utf-8",
                     errors="replace"):
        try:
            z = json.loads(с)
        except Exception:  # noqa: BLE001
            continue
        if not z.get("тело") or "opus" not in str(z.get("модель") or ""):
            continue
        if str(z.get("направление") or "") != "meyer":
            continue
        rid = z.get("recipient_id")
        if rid not in ответили:
            continue
        отпр = c.execute(
            "SELECT m.body_rendered, m.subject, m.sent_at FROM confirm_reviews cr "
            "JOIN messages m ON m.id=cr.message_id WHERE cr.id=? "
            "AND m.status='sent'", (z.get("review_id"),)).fetchone()
        if not отпр:
            continue
        opus.append({"модель": z.get("модель"), "компания": z.get("имя"),
                     "ответ": ответили[rid], "отправлено": str(отпр[2])[:10],
                     "тема": отпр[1] or z.get("тема"),
                     "текст": отпр[0] or z.get("тело")})
    видели = set()
    opus = [x for x in opus if not (x["компания"] in видели or видели.add(x["компания"]))]
    print("Meyer на opus с живым ответом: %d" % len(opus))

    sonnet = []
    for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8",
                     errors="replace"):
        try:
            z = json.loads(с)
        except Exception:  # noqa: BLE001
            continue
        if not z.get("тело") or "sonnet" not in str(z.get("модель") or ""):
            continue
        sonnet.append({"модель": z.get("модель"), "компания": z.get("имя"),
                       "тема": z.get("тема"), "текст": z.get("тело")})
    видели = set()
    sonnet = [x for x in sonnet if not (x["компания"] in видели or видели.add(x["компания"]))]
    random.seed(12)
    выбор_s = random.sample(sonnet, min(10, len(sonnet)))
    выбор_o = opus[:10]
    json.dump({"opus": выбор_o, "sonnet": выбор_s},
              io.open(ВЫХОД, "w", encoding="utf-8"), ensure_ascii=False)
    print("sonnet сегодня, годных: %d; отобрано opus %d, sonnet %d"
          % (len(sonnet), len(выбор_o), len(выбор_s)))
    print("=== СОБРАНО ===")
    sys.exit(0)

if "pokazat" in sys.argv:
    i = sys.argv.index("pokazat")
    n, s = int(sys.argv[i + 1]), int(sys.argv[i + 2])
    д = json.load(io.open(ВЫХОД, encoding="utf-8"))
    все = [("OPUS", x) for x in д["opus"]] + [("SONNET", x) for x in д["sonnet"]]
    for метка, x in все[s:s + n]:
        print("##### %s | %s | %s" % (метка, x.get("компания"),
                                      x.get("отправлено") or "сегодня"))
        print("ТЕМА: %s" % x.get("тема"))
        print(str(x.get("текст") or "").split("С уважением")[0].strip())
        print()
    print("=== ПОКАЗАНО %d-%d из %d ===" % (s + 1, min(s + n, len(все)), len(все)))
