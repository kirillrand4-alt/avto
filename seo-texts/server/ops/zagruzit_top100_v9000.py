# -*- coding: utf-8 -*-
"""Загрузить top100 в панель группой 9000 — штатным путём импорта.

Собираем CSV с теми именами колонок, которые панель узнаёт, и отдаём его
в sender.import_bazy: разобрать → свод (показ до записи) → применить.

ИНН: только настоящий российский, 10 или 12 цифр. Белорусский УНП и
строки «САЙТ:домен» оставляем ПУСТЫМИ: импорт срезал бы буквы и записал
огрызок вроде «100058367» — фальшивый номер хуже отсутствующего, он
притворяется настоящим и ломает сверки со стоп-листом и дедуп.

argv: --primenit чтобы записать.
"""
import csv
import io
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.import_bazy import применить, разобрать, свод        # noqa: E402

ГРУППА = "9000"
ФАЙЛ = r"C:\sender\server\ops\top100_v2.json"
ПРИМЕНИТЬ = "--primenit" in sys.argv

строки = json.load(io.open(ФАЙЛ, encoding="utf-8"))
буф = io.StringIO()
перо = csv.writer(буф, delimiter=";", lineterminator="\n")
перо.writerow(["инн", "почта", "компания", "контакт", "должность",
               "регион", "сайт"])
без_почты = без_инн = 0
for р in строки:
    if not р["почта"]:
        без_почты += 1
        continue
    инн = р["inn"]            # уже отфильтрован: только 10/12 цифр
    if not инн:
        без_инн += 1
    перо.writerow([инн, р["почта"], р["название"], р["фио"], р["роль"],
                   р["регион"], р["сайт"]])
текст = буф.getvalue()
print("строк в файле: %d; в CSV ушло: %d; без адреса пропущено: %d; "
      "из загружаемых без ИНН: %d"
      % (len(строки), len(текст.splitlines()) - 1, без_почты, без_инн))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
контакты, замечания = разобрать(текст, "MEYER-7 top100 паспорт")
print("")
print("--- замечания разбора ---")
for з in замечания:
    print("   " + str(з)[:160])
итог = свод(контакты, store)
print("")
print("--- что получится ---")
for к, в in итог.items():
    if к == "kontakty":
        continue
    print("   %-24s %s" % (к, в))

if not ПРИМЕНИТЬ:
    print("")
    print("=" * 74)
    print("=== ПОКАЗ БЕЗ ЗАПИСИ (нужен --primenit) ===")
    raise SystemExit(0)

записано = применить(store, итог["kontakty"], группа=ГРУППА,
                     источник="ручная загрузка: MEYER-7 top100 паспорт 12.10")
print("")
print("--- записано ---")
for к, в in записано.items():
    print("   %-24s %s" % (к, в))

with store._lock:
    n = store._conn.execute("SELECT COUNT(*) FROM recipients WHERE segment=?",
                            (ГРУППА,)).fetchone()[0]
    пусто = store._conn.execute(
        "SELECT COUNT(*) FROM recipients WHERE segment=? "
        "  AND COALESCE(inn,'')=''", (ГРУППА,)).fetchone()[0]
print("")
print("=" * 74)
print("=== ГРУППА %s ===" % ГРУППА)
print("   получателей в группе: %d, из них без ИНН: %d" % (n, пусто))
