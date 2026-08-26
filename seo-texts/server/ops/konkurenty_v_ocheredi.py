# -*- coding: utf-8 -*-
"""Конкуренты в очереди: компания сама делает то, что мы продаём.

Владелец 26.08: «уже второй раз конкурент проскакивает». ООО
«Энергоремкомплект» (erk-ekb.ru) ответило «мы тоже занимаемся поршневыми
компрессорами и производим запасные части к ним» — а письмо им написали
про подбор компрессоров. Причём модель ЗНАЛА: в самом письме стоит
«несколько направлений — блочно-модульные азотные станции, поршневые
компрессоры». Знала и всё равно писала: правила «не пиши конкуренту» в
цепочке просто нет.

Ищем по паспорту сайта и роду деятельности наши же товары.

    python konkurenty_v_ocheredi.py            # показать
    python konkurenty_v_ocheredi.py primenit   # снять письма и завести в реестр
"""
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]

# Наш товар. Слова берём такие, чтобы «купили компрессор» не попадало:
# ищем ПРОИЗВОДСТВО или ПРОДАЖУ этого, а не наличие в цеху.
ТОВАР = {
    "kc": re.compile(
        r"компрессор|винтов\w+ блок|азотн\w+ станц|генератор\w* азота|"
        r"генератор\w* кислорода|воздуходувк|осушител\w+ воздуха|"
        r"пневмооборудован|ресивер", re.I),
    "meyer": re.compile(
        r"фотосепаратор|фото-сепаратор|оптическ\w+ сортировк|"
        r"рентген\w*[- ]инспекц|рентгеновск\w+ инспекц|металлодетектор", re.I),
}
ПРОДАЁТ = re.compile(
    r"производ|изготовл|выпуска|поставля|продаж|продаём|продаем|"
    r"дистрибь|дилер|ремонт|запчаст|сервисн\w+ обслуживан|аренда", re.I)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
c = sqlite3.connect(cfg.get("service.db_path", r"C:\sender\sender.db"), timeout=60)
c.row_factory = sqlite3.Row

ряды = c.execute(
    "SELECT cr.id crid, cr.status, cr.message_id, r.id rid, r.inn, r.email, "
    "       r.company_name, substr(cr.subject,1,52) subj "
    "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.status IN ('pending','approved','edited') AND r.inn IS NOT NULL"
).fetchall()
print("писем в очереди: %d" % len(ряды))

подозрения = []
for r in ряды:
    инн = "".join(x for x in str(r["inn"]) if x.isdigit())
    try:
        паспорт = q._pasport_dlya_geyta(инн) or ""
    except Exception:                                         # noqa: BLE001
        паспорт = ""
    if not паспорт:
        continue
    для = "meyer" if re.search(r"сортиров|рентген|фотосепар", r["subj"] or "",
                               re.I) else "kc"
    м = ТОВАР[для].search(паспорт)
    if not м:
        continue
    # Рядом со словом товара должно стоять «производим/продаём/ремонтируем»:
    # компрессорная станция В ЦЕХУ — это клиент, а не конкурент.
    окно = паспорт[max(0, м.start() - 160):м.end() + 160]
    if not ПРОДАЁТ.search(окно):
        continue
    подозрения.append((r, для, " ".join(окно.split())[:200]))

print("похожи на конкурентов: %d" % len(подозрения))
for r, для, окно in подозрения[:20]:
    print("")
    print("   #%s %-9s %s (ИНН %s) → %s"
          % (r["crid"], r["status"], str(r["company_name"])[:44], r["inn"], для))
    print("      %s" % r["subj"])
    print("      %s" % окно)

if not ДЕЛАТЬ:
    print("\nвхолостую. Снять и завести в реестр — primenit")
    raise SystemExit(0)

from sender.ne_nash import НеНаш                              # noqa: E402
import time                                                   # noqa: E402

реестр = НеНаш(cfg.get("service.db_path", r"C:\sender\sender.db"),
               зеркало=r"C:\sender\enrich.db")
сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
снято = 0
for r, для, окно in подозрения:
    причина = "конкурент: сам работает с нашим товаром (%s)" % для
    реестр.записать(r["inn"], причина, "разбор 26.08")
    c.execute("UPDATE confirm_reviews SET status='stoplist', reason=?, "
              "decided_at=?, decided_by='разбор конкурентов', updated_at=? "
              " WHERE id=? AND status IN ('pending','approved','edited')",
              (причина, сейчас, сейчас, r["crid"]))
    if r["message_id"]:
        c.execute("UPDATE messages SET status='skipped', last_error=?, "
                  "updated_at=? WHERE id=? AND status NOT IN ('sent','sending')",
                  (причина, сейчас, r["message_id"]))
    снято += 1
c.commit()
c.close()
print("\nснято писем и заведено в реестр: %d" % снято)
