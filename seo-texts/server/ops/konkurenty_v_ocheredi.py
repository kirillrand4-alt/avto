# -*- coding: utf-8 -*-
"""Конкуренты в очереди: компания сама делает то, что мы продаём.

Владелец 26.08: «уже второй раз конкурент проскакивает». ООО
«Энергоремкомплект» (erk-ekb.ru) ответило «мы тоже занимаемся поршневыми
компрессорами и производим запасные части к ним» — а письмо им написали
про подбор компрессоров. Причём модель ЗНАЛА: в самом письме стоит
«несколько направлений — блочно-модульные азотные станции, поршневые
компрессоры». Знала и всё равно писала: правила «не пиши конкуренту» в
цепочке просто нет.

ДВЕ СТУПЕНИ. Регулярка по паспорту сайта отбирает КАНДИДАТОВ — она дешёвая
и берёт с запасом. Решает модель, потому что regexp клиента от конкурента
не отличает: у «БК Урал» передвижные компрессорные станции в парке буровой
техники, у «Металлпрома» два винтовых компрессора в цеху — это покупатели,
а «СТК» с «официальный дистрибьютор винтовых компрессоров, генераторов
газов, осушителей» — конкурент.

    python konkurenty_v_ocheredi.py            # показать кандидатов
    python konkurenty_v_ocheredi.py sudit      # осудить моделью
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
СУДИТЬ = ДЕЛАТЬ or "sudit" in sys.argv[1:]
ЖУРНАЛ = r"C:\sender\_ops\konkurenty-sud.jsonl"

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

if not СУДИТЬ:
    print("\nвхолостую. Осудить моделью — sudit, снять — primenit")
    raise SystemExit(0)

# ---- суд модели -------------------------------------------------------- #
import io                                                     # noqa: E402
import json                                                   # noqa: E402
import os                                                     # noqa: E402
import threading                                              # noqa: E402
from collections import Counter                               # noqa: E402
from concurrent.futures import ThreadPoolExecutor             # noqa: E402

from sender.review_lenses import default_caller               # noqa: E402

МОДЕЛЬ = "claude-sonnet-4-6"
ГОЛОВА = """Ты отбираешь адресатов для поставщика промышленного оборудования.
Мы продаём: винтовые и поршневые компрессоры, осушители и фильтры сжатого
воздуха, генераторы азота и кислорода, воздуходувки, пневмооборудование
(направление КЦ); фотосепараторы и рентген-инспекцию продукции
(направление Meyer).

Реши по каждой компании: КОНКУРЕНТ она нам или нет.

КОНКУРЕНТ — компания, которая сама ПРОДАЁТ, ПРОИЗВОДИТ, ПОСТАВЛЯЕТ или
СЕРВИСНО ОБСЛУЖИВАЕТ это же оборудование для чужих предприятий: дилер,
дистрибьютор, завод-изготовитель, поставщик запчастей и комплектующих к
компрессорам, сервисный центр по их ремонту.

НЕ КОНКУРЕНТ — компания, у которой это оборудование стоит В СОБСТВЕННОМ
ЦЕХУ или в её технике. Компрессор в парке буровой установки, винтовой
компрессор в покрасочном цеху, компрессорная станция на своём производстве
— это ПОКУПАТЕЛЬ, а не конкурент. Смежный товар тоже не делает конкурентом:
насосно-компрессорные трубы для нефтедобычи, блок-контейнеры «под
компрессорную», муфты для насосов и компрессоров, сосуды под давлением —
это другой рынок, если компания не продаёт сами компрессоры.

Не уверен — «неясно», выдумывать нельзя."""
ХВОСТ = ('\nОТВЕТ - СТРОГО JSON без текста вокруг:\n'
         '{"verdicts":[{"idx":N,"verdict":"конкурент|не конкурент|неясно",'
         '"pochemu":"одной фразой, чем компания занимается"}]}')

осуждено = {}
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        try:
            з = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        if з.get("инн"):
            осуждено[str(з["инн"])] = з

работа = [(r, для, окно) for r, для, окно in подозрения
          if str(r["inn"]) not in осуждено]
print("")
print("к суду: %d (в журнале уже %d)" % (len(работа), len(осуждено)))
ф = io.open(ЖУРНАЛ, "a", encoding="utf-8")
замок = threading.Lock()
свод = Counter()


def партия(часть):
    блоки = []
    for i, (r, для, окно) in enumerate(часть):
        блоки.append("=== КОМПАНИЯ %d\nНазвание: %s\nОКВЭД: %s\n"
                     "ПАСПОРТ ИХ САЙТА: %s"
                     % (i, r["company_name"], "", окно))
    промпт = ГОЛОВА + "\n\nКомпании:\n\n" + "\n\n".join(блоки) + ХВОСТ
    try:
        текст, _м = default_caller(промпт, model=МОДЕЛЬ)
    except Exception as ex:                                   # noqa: BLE001
        with замок:
            свод["сбой вызова"] += len(часть)
        return
    данные = None
    for кусок in re.findall(r"\{.*\}", текст or "", re.S):
        try:
            данные = json.loads(кусок)
            break
        except Exception:                                     # noqa: BLE001
            continue
    if not isinstance(данные, dict):
        with замок:
            свод["ответ не разобрался"] += len(часть)
        return
    строки = []
    for в in данные.get("verdicts", []):
        try:
            i = int(в.get("idx"))
        except Exception:                                     # noqa: BLE001
            continue
        if not (0 <= i < len(часть)):
            continue
        r, для, _о = часть[i]
        вер = str(в.get("verdict") or "").strip().lower()
        if вер not in ("конкурент", "не конкурент", "неясно"):
            вер = "неясно"
        строки.append({"инн": str(r["inn"]), "crid": r["crid"],
                       "имя": r["company_name"], "вердикт": вер,
                       "почему": str(в.get("pochemu") or "")[:200],
                       "напр": для})
    with замок:
        for з in строки:
            осуждено[з["инн"]] = з
            свод[з["вердикт"]] += 1
            ф.write(json.dumps(з, ensure_ascii=False) + "\n")
        ф.flush()
        os.fsync(ф.fileno())


части = [работа[i:i + 6] for i in range(0, len(работа), 6)]
with ThreadPoolExecutor(max_workers=6) as пул:
    list(пул.map(партия, части))
ф.close()
print("суд: %s" % dict(свод))

конкуренты = [з for з in осуждено.values() if з.get("вердикт") == "конкурент"]
print("")
print("=== КОНКУРЕНТЫ: %d ===" % len(конкуренты))
for з in конкуренты:
    print("   #%-6s %-42s %s" % (з.get("crid"), str(з.get("имя"))[:42],
                                 str(з.get("почему"))[:80]))

if not ДЕЛАТЬ:
    print("\nсуд окончен. Снять письма — primenit")
    raise SystemExit(0)

from sender.ne_nash import НеНаш                              # noqa: E402
import time                                                   # noqa: E402

реестр = НеНаш(cfg.get("service.db_path", r"C:\sender\sender.db"),
               зеркало=r"C:\sender\enrich.db")
сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
по_инн = {str(r["inn"]): r for r, _д, _о in подозрения}
снято = 0
for з in конкуренты:
    r = по_инн.get(з["инн"])
    причина = "конкурент: %s" % з.get("почему", "")[:150]
    # Реестр — на всю компанию: конкурентом она останется и в другой партии.
    реестр.записать(з["инн"], причина, "суд конкурентов 26.08")
    c.execute("UPDATE confirm_reviews SET status='stoplist', reason=?, "
              "decided_at=?, decided_by='суд конкурентов', updated_at=? "
              " WHERE id=? AND status IN ('pending','approved','edited')",
              (причина, сейчас, сейчас, з["crid"]))
    if r is not None and r["message_id"]:
        c.execute("UPDATE messages SET status='skipped', last_error=?, "
                  "updated_at=? WHERE id=? AND status NOT IN ('sent','sending')",
                  (причина, сейчас, r["message_id"]))
    снято += 1
c.commit()
c.close()
print("\nснято писем и заведено в реестр: %d" % снято)
