# -*- coding: utf-8 -*-
"""Сводка _ops/otvety-v-yashchikah.json без шума (рассылки сервисов): сначала привязанные к нашим
компаниям, потом прочие ответы (Re:/In-Reply-To). Только чтение."""
import io, json, re
from collections import Counter
н = json.load(io.open(r"C:\sender\_ops\otvety-v-yashchikah.json", encoding="utf-8"))
ШУМ = re.compile(r"(?i)360\.yandex|yandex\.ru$|@id\.yandex|mail\.ru$.*news|robot|newsletter|rassylka|news@|info@.*(beget|reg\.ru|nic\.ru)|unisender|sendsay|dashamail")
сч = Counter(x["от"] for x in н)
print("всего не в ленте: %d; топ отправителей:" % len(н), сч.most_common(6))
чист = [x for x in н if not ШУМ.search(x["от"]) and not x["от"].endswith("@360.yandex.ru")]
прив = [x for x in чист if x.get("rid")]
отв = [x for x in чист if not x.get("rid") and (x.get("ответ_на") or re.match(r"(?i)\s*(re|ответ|отв)\s*:", x["тема"] or ""))]
for заг, сп in (("ПРИВЯЗАНЫ К НАШЕЙ КОМПАНИИ", прив), ("ОТВЕТЫ (Re/In-Reply-To), компания не найдена", отв)):
    print("== %s: %d" % (заг, len(сп)))
    for x in сп[:80]:
        print("  %s | %-30s %-5s | от %-30s | %-24s | ИНН %s | %s" % (x["дата"][5:22], x["ящик"][:30], "спам" if x["папка"] != "INBOX" else "вход",
              x["от"][:30], str(x.get("компания") or "—")[:24], x.get("inn"), x["тема"][:70]))
