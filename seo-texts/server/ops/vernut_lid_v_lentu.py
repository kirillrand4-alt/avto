# -*- coding: utf-8 -*-
"""Вернуть лид 228 (ООО «ТЗК ИМСБ») в ленту: статус not_interested -> new.

Почему он выпал: лента прячет статусы из СКРЫТЫЕ_ИЗ_ЛЕНТЫ, куда входит
not_interested. Лид получил его 28.08 при разборе первого ответа, хотя
человек прямым текстом просит показать оборудование и цены. Второй ответ
02.09 (событие 325345, с rouk@imsb.ru на письмо, посланное на
secretar@imsb.ru) обновил тот же лид по ветке, но статус не поменял.

Меняем ЧЕРЕЗ МЕТОД ПАНЕЛИ, а не UPDATE по базе: там версия, журнал
переходов и время обновления.

По умолчанию СУХОЙ ПРОГОН. Запуск: python vernut_lid_v_lentu.py [--primenit]
"""
import inspect
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

ЛИД = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 228
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
путь = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(путь)

c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=90)
c.row_factory = sqlite3.Row
до = c.execute("SELECT * FROM leads WHERE id=?", (ЛИД,)).fetchone()
c.close()

методы = [и for и, _ in inspect.getmembers(store, inspect.ismethod)
          if "lead" in и.lower()]

шаги = []
if не_нашли := (до is None):
    шаги.append("лида %d нет" % ЛИД)
elif ПРИМЕНИТЬ:
    ф = getattr(store, "update_lead_cas", None)
    подпись = str(inspect.signature(ф)) if ф else "нет метода"
    шаги.append("подпись: update_lead_cas%s" % подпись[:140])
    сделано = False
    if ф:
        # expected_version и остальное — ТОЛЬКО именованные, метод берёт
        # один позиционный аргумент.
        try:
            ф(ЛИД, expected_version=int(до["version"]),
              action="status_changed", status="new")
            шаги.append("вызван update_lead_cas(%d, expected_version=%s, "
                        "status='new')" % (ЛИД, до["version"]))
            сделано = True
        except Exception as ex:                                # noqa: BLE001
            шаги.append("update_lead_cas упал: %s" % str(ex)[:140])
    if not сделано:
        шаги.append("штатный метод не подошёл — статус НЕ менял")
else:
    шаги.append("сухой прогон: статус не трогал")

c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=90)
c.row_factory = sqlite3.Row
после = c.execute("SELECT * FROM leads WHERE id=?", (ЛИД,)).fetchone()
скрытые = c.execute(
    "SELECT COUNT(*) FROM leads WHERE status IN "
    "('deleted','not_interested','in_bitrix','unqualified')").fetchone()[0]
видимых = c.execute(
    "SELECT COUNT(*) FROM leads WHERE status NOT IN "
    "('deleted','not_interested','in_bitrix','unqualified')").fetchone()[0]
c.close()

print("=" * 74)
print("=== СВОДКА: ВОЗВРАТ ЛИДА В ЛЕНТУ ===")
print("режим: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("методы стора про лиды: %s" % ", ".join(методы[:10]))
print("")
if до is not None:
    print("было:  статус %-16s вид %-14s версия %s"
          % (до["status"], до["reply_kind"], до["version"]))
if после is not None:
    print("стало: статус %-16s вид %-14s версия %s"
          % (после["status"], после["reply_kind"], после["version"]))
print("")
for с in шаги:
    print("   " + с)
print("")
print("в ленте видно лидов: %d; скрыто: %d" % (видимых, скрытые))
