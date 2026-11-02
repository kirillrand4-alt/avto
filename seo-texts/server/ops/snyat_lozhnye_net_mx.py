# -*- coding: utf-8 -*-
"""Снять ложные приговоры «нет MX» 02.11 (DNS сервера перестал отдавать MX — даже
у mail.ru и 8.8.8.8 NoAnswer, — и проба второго касания записала 44 «нет MX»
реальным доменам: primatek.ru, tatrmilk.ru…). Берём адреса с verdict='нет MX'
и ts за указанный день; строки до правки — в _ops/lozhnye-net-mx.jsonl (возврат).
Во всех трёх базах вердикт стирается: адрес снова «без проверки».
    snyat_lozhnye_net_mx.py <YYYY-MM-DD> [--primenit]"""
import io, json, os, sqlite3, sys
день = sys.argv[1]
ПРИМ = "--primenit" in sys.argv
s = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
s.row_factory = sqlite3.Row
# и «неясно» с ответом «MX не найден…» — тот же сбой DNS (VPN на сервере, 02.11)
ряды = [dict(r) for r in s.execute("SELECT * FROM addr_probe WHERE substr(ts,1,10)=? AND (verdict='нет MX' "
                                   "OR (verdict='неясно' AND answer LIKE 'MX не найден%'))", (день,))]
print("ложных вердиктов (сбой DNS) за %s: %d" % (день, len(ряды)))
ст = s.execute("SELECT count(*) FROM suppression WHERE value IN (%s)" % ",".join("?" * len(ряды)),
               [r["email"].lower() for r in ряды]).fetchone()[0] if ряды else 0
print("из них в стоп-листе:", ст)
if ПРИМ and ряды:
    with io.open(r"C:\sender\_ops\lozhnye-net-mx.jsonl", "a", encoding="utf-8") as ж:
        for r in ряды:
            ж.write(json.dumps(r, ensure_ascii=False) + "\n")
        ж.flush(); os.fsync(ж.fileno())
    адреса = [r["email"].lower() for r in ряды]
    зн = ",".join("?" * len(адреса))
    with s:
        n1 = s.execute("DELETE FROM addr_probe WHERE verdict IN ('нет MX','неясно') AND lower(email) IN (%s)" % зн, адреса).rowcount
    e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
    with e:
        n2 = e.execute("UPDATE emails SET probe_verdict=NULL, probe_ts=NULL, probe_answer=NULL "
                       "WHERE probe_verdict IN ('нет MX','неясно') AND lower(email) IN (%s)" % зн, адреса).rowcount
    o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
    with o:
        n3 = o.execute("DELETE FROM email_probe WHERE verdict IN ('нет MX','неясно') AND lower(email) IN (%s)" % зн, адреса).rowcount
    print("снято: sender.db %d, enrich.db %d, obzvon %d" % (n1, n2, n3))
