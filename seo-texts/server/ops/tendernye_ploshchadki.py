# -*- coding: utf-8 -*-
"""Тендерные площадки из входящих писем (владелец 18.10: «в некоторых писали адреса
тендерных площадок, вытащи»). Источники: тексты лидов и события reply/reply_auto.
Ищет ссылки и упоминания ЭТП. Только чтение; итог — _ops/tendernye-ploshchadki.tsv."""
import io, json, re, sqlite3
from collections import defaultdict
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
ЭТП = re.compile(r"(?i)(?<![\w.@-])(zakupki\.gov|b2b-center|b2b-cent|sberbank-ast|roseltorg|fabrikant|rts-tender|"
                 r"tektorg|etpgpb|etp-?\w*|gazneftetorg|lot-online|onlinecontract|otc\.ru|uralbidin|setonline|"
                 r"regtorg|bicotender|tenderpro|tender\.\w+|torgi\.\w+|zakupki\.\w+|"
                 r"торгов\w+ площадк|тендерн\w+ площадк|электронн\w+ площадк|закупочн\w+ площадк|"
                 r"портал\w* (поставщик|закуп)|аккредит\w+|через (наш )?тендер|участ\w+ в (тендер|закупк|конкурс)|"
                 r"\bЭТП\b|площадк\w+ (для|по) (закуп|тендер|поставщик))")
URL = re.compile(r"(?i)(https?://[^\s<>\"')]+|www\.[^\s<>\"')]+|\b[\w-]+(?:\.[\w-]+)*\.(?:ru|com|рф|su|net|org|by|kz)(?:/[^\s<>\"')]*)?)")
находки = defaultdict(lambda: {"источники": set(), "контекст": ""})
def разбор(текст, кто):
    т = str(текст or "")
    for м in ЭТП.finditer(т):
        окно = т[max(0, м.start() - 400): м.end() + 600].replace("\n", " ")
        ссылки = [u.rstrip(".,;") for u in URL.findall(окно) if re.search(r"(?i)zakup|tender|torg|etp|b2b|ast\.ru|fabrikant|otc|lot-online|contract|bidin|supplier|postav|purchas|procure|snab", u) and "@" not in u]
        for u in ссылки or ["(без ссылки) " + м.group(0)]:
            ключ = u.lower()
            находки[ключ]["источники"].add(кто)
            if not находки[ключ]["контекст"]:
                находки[ключ]["контекст"] = re.sub(r"\s+", " ", окно)[:900]
for lid, name, email, need in c.execute("SELECT id, company_name, email, need FROM leads"):
    разбор(need, "лид #%s %s <%s>" % (lid, name or "", email or ""))
for rid, dj, em, name in c.execute("SELECT e.recipient_id, e.detail_json, r.email, r.company_name FROM events e "
                                   "LEFT JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','reply_auto')"):
    try: d = json.loads(dj or "{}")
    except ValueError: d = {}
    разбор(" ".join(str(d.get(k) or "") for k in ("snippet", "text", "body", "subject")), "%s <%s>" % (name or "", em or ""))
с_ссылкой = {k: v for k, v in находки.items() if not k.startswith("(без ссылки)")}
без = {k: v for k, v in находки.items() if k.startswith("(без ссылки)")}
with io.open(r"C:\sender\_ops\tendernye-ploshchadki.tsv", "w", encoding="utf-8") as f:
    for k, v in sorted(находки.items()):
        f.write("%s\t%s\t%s\n" % (k, "; ".join(sorted(v["источники"]))[:400], v["контекст"]))
print("ССЫЛОК:", len(с_ссылкой), "| упоминаний без ссылки:", len(без))
for k, v in sorted(находки.items()):
    print("\n*", k, "\n   от:", "; ".join(sorted(v["источники"]))[:200], "\n   текст:", v["контекст"][:900])
