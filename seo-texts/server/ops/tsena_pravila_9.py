# -*- coding: utf-8 -*-
"""Чего стоит устаревшее правило 9: замер по отправленным и по браку гейта."""
import io
import re
import sqlite3
import statistics

ФАЙЛ = r"C:\sender\sender\ai_letter.py"
т = io.open(ФАЙЛ, encoding="utf-8", errors="replace").read()
for н, с in enumerate(т.splitlines(), 1):
    if "главнее" in с or "при конфликте" in с:
        print("отмена: ai_letter.py:%d  %s" % (н, с.strip()[:130]))

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
столбцы = [r[1] for r in c.execute("PRAGMA table_info(messages)")]
print("колонки messages: %s" % ", ".join(столбцы))

print("\n=== ОТПРАВЛЕННЫЕ: ДЛИНА ТЕЛА В СЛОВАХ ===")
for камп, имя in ((10, "КЦ"), (11, "Meyer")):
    длины = []
    for r in c.execute("SELECT body_rendered AS body FROM messages WHERE campaign_id=? "
                       "  AND sent_at IS NOT NULL AND body IS NOT NULL", (камп,)):
        т_ = str(r["body"] or "")
        # подпись движка отрезаем: считаем до «С уважением,»
        т_ = т_.split("С уважением,")[0]
        длины.append(len(т_.split()))
    if not длины:
        print("  кампания %d (%s): отправленных нет" % (камп, имя))
        continue
    длины.sort()
    выше140 = sum(1 for д in длины if д > 140)
    в_каноне = sum(1 for д in длины if 140 <= д <= 190)
    print("  кампания %d (%s): %d писем; медиана %d, среднее %.0f, "
          "10%%–90%% %d–%d, максимум %d"
          % (камп, имя, len(длины), statistics.median(длины),
             sum(длины) / float(len(длины)), длины[len(длины) // 10],
             длины[len(длины) * 9 // 10], длины[-1]))
    print("        выше 140 слов: %d (%.1f%%); в «каноне» 140–190: %d (%.1f%%)"
          % (выше140, 100.0 * выше140 / len(длины),
             в_каноне, 100.0 * в_каноне / len(длины)))

print("\n=== ВОПРОСИТЕЛЬНЫЕ ЗНАКИ В ОТПРАВЛЕННЫХ ===")
for камп, имя in ((10, "КЦ"), (11, "Meyer")):
    счёт = {}
    for r in c.execute("SELECT body_rendered AS body FROM messages WHERE campaign_id=? "
                       "  AND sent_at IS NOT NULL AND body IS NOT NULL", (камп,)):
        n = str(r["body"] or "").count("?")
        счёт[n] = счёт.get(n, 0) + 1
    всего = sum(счёт.values())
    if всего:
        print("  %s: %s (всего %d)"
              % (имя, ", ".join("%d знак(ов) — %d писем (%.0f%%)"
                                % (k, v, 100.0 * v / всего)
                                for k, v in sorted(счёт.items())), всего))

print("\n=== ГДЕ КОД ПИШЕТ БРАК ГЕЙТА ===")
for n, с in enumerate(т.splitlines(), 1):
    if re.search(r"объ[её]м \{?words|f'объ[её]м|\"объ[её]м", с):
        print("  ai_letter.py:%d  %s" % (n, с.strip()[:110]))
c.close()

print("\n=== ИТОГ ===")
print("Живой промпт содержит и правило 9 (140-190), и правило 19, которое его")
print("отменяет. Гейт кода режет КЦ выше 140 слов. Отправленная практика —")
print("медиана около сотни. Значит боевой канон = плотность правила 19,")
print("а число 140-190 в правиле 9 — мёртвая строка, оставшаяся от 13.08.")
