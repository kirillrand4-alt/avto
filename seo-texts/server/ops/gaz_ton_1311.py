# -*- coding: utf-8 -*-
"""Перевод НЕОТПРАВЛЕННЫХ писем кампании 22 на новый тон канона (владелец 13.11: «не очевидно, что пишем про их процесс
и предлагаем азотные станции», «по-человечески», компрессоры — основное направление, ЦК только крупным).
Меняет: фразу охвата → новая (gaz_kanon.ОХВАТ / ОХВАТ_ОСОБ, тот же газ), перед фразой про процесс — «Увидел, что …»,
фразу про компрессоры → новая (крупным — с центробежными, если и было крупное). Остальное не трогаем.
Правит confirm_reviews (pending и approved) и messages.body_rendered (pending_review / scheduled / paused), строго
по совпадению старых строк канона; не нашли — не трогаем и считаем. Журнал _ops/gaz-ton-1311.jsonl.
    gaz_ton_1311.py [--primenit]"""
import io, json, os, random, sqlite3, sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gaz_kanon as K
СТАРЫЕ = {
 "ohvat_N2": [
  "Под такие задачи проектируем и поставляем азотные станции под ключ, в том числе модульные, сразу с компрессором и осушкой воздуха.",
  "Для этого ведём проекты по азоту: от станции под один участок до модульной системы на всё производство, в комплекте с компрессором и подготовкой воздуха.",
  "Под такие процессы поставляем азотные станции под ключ, в том числе модульные: станция идёт в комплекте с компрессором и осушкой."
 ],
 "ohvat_O2": [
  "Под такие задачи проектируем и поставляем кислородные станции под ключ, в том числе модульные, сразу с компрессором и осушкой воздуха.",
  "Для этого ведём проекты по кислороду: от станции под один участок до модульной системы на всё производство, в комплекте с компрессором и подготовкой воздуха.",
  "Под такие процессы поставляем кислородные станции под ключ, в том числе модульные: станция идёт в комплекте с компрессором и осушкой."
 ],
 "osob": [
  "Под резку проектируем и поставляем азотные станции с дожимом, в том числе модульные, сразу с компрессором и осушкой воздуха.",
  "Под такие процессы поставляем азотные станции под ключ с комплектом документов для GMP, в том числе модульные, в комплекте с компрессором и подготовкой воздуха.",
  "Для этого проектируем и поставляем азотные станции высокой чистоты для контакта с продуктом, в том числе модульные, сразу с компрессором и осушкой воздуха."
 ],
 "kompr": [
  "Компрессоры - наше основное направление. Подберём винтовой компрессор или спроектируем всю компрессорную.",
  "Сжатый воздух - наш основной профиль. Можем заменить один компрессор, а можем спроектировать всю компрессорную.",
  "Основное наше направление - компрессоры, есть и свой бренд Enger. Компрессорные проектируем целиком, от расчёта до пуска."
 ],
 "kompr_krupn": [
  "Компрессоры - наше основное направление, от винтовых до центробежных. Компрессорные проектируем целиком, от расчёта до пуска.",
  "Сжатый воздух - наш основной профиль. Подберём винтовой или центробежный компрессор или спроектируем всю компрессорную."
 ]
}
ОСОБ_КЛЮЧ = {0: "лазер", 1: "фарма", 2: "пиво"}
ПРИМ = "--primenit" in sys.argv
c = sqlite3.connect(r"C:\\sender\\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
random.seed(1311)
def переписать(т):
    """-> (новый текст, причина-неудачи)"""
    if not т: return т, "пусто"
    if "Увидел, что" in т: return т, "уже новый"
    ст = None
    for газ in ("N2", "O2"):
        for x in СТАРЫЕ["ohvat_" + газ]:
            if x in т: ст = (x, random.choice(K.ОХВАТ[газ]))
    for i, x in enumerate(СТАРЫЕ["osob"]):
        if x in т: ст = (x, K.ОХВАТ_ОСОБ[ОСОБ_КЛЮЧ.get(i, "лазер")])
    if not ст: return т, "станция не найдена"
    кп = None
    for x in СТАРЫЕ["kompr"]:
        if x in т: кп = (x, random.choice(K.КОМПР_ОТД))
    for x in СТАРЫЕ["kompr_krupn"]:
        if x in т: кп = (x, random.choice(K.КОМПР_ОТД_КРУПН))
    if not кп: return т, "компрессоры не найдены"
    абз = т.split("\n\n")
    i = next((k for k, a in enumerate(абз) if ст[0] in a), None)
    if i is None or not абз[i].endswith(ст[0]): return т, "станция не в конце абзаца"
    f = абз[i][: -len(ст[0])].strip()
    абз[i] = K.увидел(f) + " " + ст[1]
    н = "\n\n".join(абз).replace(кп[0], кп[1], 1)
    return н, ""
сч = Counter(); пример = None
т0 = datetime.now(timezone.utc).isoformat(timespec="seconds")
жур = io.open(r"C:\\sender\\_ops\\gaz-ton-1311.jsonl", "a", encoding="utf-8")
for кид, st, body, ed, mid in c.execute("SELECT id, status, body, edited_body, message_id FROM confirm_reviews WHERE campaign_id=22 AND status IN ('pending','approved')").fetchall():
    if ed and ed != body: сч["тронута оператором"] += 1; continue
    м = c.execute("SELECT status, body_rendered FROM messages WHERE id=?", (mid,)).fetchone() if mid else None
    if м and м[0] in ("sent", "sending", "failed", "skipped"): сч["письмо уже " + м[0]] += 1; continue
    н, беда = переписать(body)
    if беда: сч[беда] += 1; continue
    нм, бм = переписать(м[1]) if м and м[1] else (None, "")
    сч["переписано"] += 1
    if пример is None: пример = (кид, body, н)
    if ПРИМ:
        c.execute("UPDATE confirm_reviews SET body=?, edited_body=CASE WHEN edited_body IS NULL THEN NULL ELSE ? END, updated_at=? WHERE id=?", (н, н, т0, кид))
        if нм and not бм: c.execute("UPDATE messages SET body_rendered=? WHERE id=? AND status IN ('pending_review','scheduled','paused')", (нм, mid))
        elif м and м[1]: сч["в messages не совпало: " + бм] += 1
        жур.write(json.dumps({"karta": кид, "mid": mid, "bylo": body, "stalo": н, "ts": т0}, ensure_ascii=False) + "\n")
if ПРИМ: c.commit(); жур.flush(); os.fsync(жур.fileno())
print("%s: %s" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон", dict(сч)))
if пример: print("пример #%s\nБЫЛО:\n%s\n\nСТАЛО:\n%s" % пример)
