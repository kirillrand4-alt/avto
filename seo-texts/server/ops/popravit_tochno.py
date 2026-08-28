# -*- coding: utf-8 -*-
import io, json, re, sqlite3
from collections import Counter
всё = {}
for ф, п in ((r"C:\sender\_ops\sud-vtoryh.jsonl", 1),
             (r"C:\sender\_ops\sud-vtoryh-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с); d["_p"] = п
            всё[(п, int(d["id"]))] = d
    except FileNotFoundError:
        pass
поправ = {k: d for k, d in всё.items()
          if str(d.get("verdikt") or "").replace("o", "о").replace("p", "р") == "поправить"}
КРИТ = re.compile(r"(?i)(выдум|придума|не подтвержд|нет в карточке|нет данных|"
                  r"перепута|не производ|не занимается|которых нет|которой нет|"
                  r"ошибочн|неверн[оыа]|не соответству|приписан)")
СРЕДН = re.compile(r"(?i)(реклам|обеща|навязчив|обращени|не тому|чужому|роль|адресат)")
КОСМ = re.compile(r"(?i)(склонени|падеж|формулиров|коряв|стилист|опечат|запят|громоздк)")
разряд = Counter()
крит_ids = []
for (п, i), d in поправ.items():
    т = str(d.get("chto_ne_tak") or "")
    if str(d.get("vydumka") or "").strip() or d.get("fakty_verny") is False or КРИТ.search(т):
        разряд["критично"] += 1; крит_ids.append((п, i))
    elif d.get("obrashchenie_ok") is False or d.get("reklama") is True or СРЕДН.search(т):
        разряд["среднее"] += 1
    elif d.get("yazyk_ok") is False or КОСМ.search(т):
        разряд["косметика"] += 1
    else:
        разряд["неясно"] += 1
print("«поправить» всего: %d" % len(поправ))
for к, n in разряд.most_common():
    print("   %-12s %4d  (%.0f%%)" % (к, n, 100.0 * n / len(поправ)))

# ложная тревога: судья не видел имени контакта — он его в карточку не получал
об = [(п, i) for (п, i), d in поправ.items() if d.get("obrashchenie_ok") is False]
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
ids = [i for _п, i in об] or [0]
зн = ",".join("?" * len(ids))
есть_имя = 0
for r in c.execute("SELECT cr.id, r.contact_name FROM confirm_reviews cr "
                   "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
                   " WHERE cr.id IN (%s)" % зн, ids):
    if str(r["contact_name"] or "").strip():
        есть_имя += 1
c.close()
print("")
print("претензий к обращению: %d, из них имя контакта у нас ЕСТЬ: %d"
      % (len(об), есть_имя))
print("(судья имени в карточке не видел — эти претензии ложные)")
