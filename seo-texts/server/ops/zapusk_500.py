# -*- coding: utf-8 -*-
"""Запустить генерацию 500 писем: кампания, отрасли → Meyer, фон.

1. Кампания «Россия 9000 — Meyer» — копия настроек №11 «Партия 935 —
   Meyer» (юрлицо, ИНН, пул, конфиг, шаг-письмо); сегмент — группа.
2. Настройка segment_division: 15 отраслей книг → meyer. Сегмент теперь
   отрасль, и без этого направление новых компаний (их нет в базе обзвона)
   выводилось бы цепочкой с дефолтом КЦ.
3. generaciya_500.py — отсоединённым процессом (генерация идёт часами,
   а задание раннера живёт 15 минут).

Запуск: zapusk_500.py [--primenit]
"""
import io
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.dtos import CampaignIn, SequenceStepIn                # noqa: E402
from sender.store import Store                                   # noqa: E402

ПРИМЕНИТЬ = "--primenit" in sys.argv
ИМЯ = "Россия 9000 — Meyer"
ОТРАСЛИ = ["Пластик и полимеры", "Мясо, птица, молоко",
           "Зерно, мука, элеваторы, семена", "Горнодобыча, нерудные",
           "Хлеб, кондитерка, макароны", "Вторсырьё и лом",
           "Лес и деревообработка", "Овощи, фрукты, орехи, ягоды",
           "Прочая пищевка, корма, фасовка", "Кофе, чай, специи",
           "Опт продуктами", "Стекло", "Масложир (МЭЗ)", "Химия, удобрения",
           "Металлургия"]

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    обр = dict(store._conn.execute(
        "SELECT * FROM campaigns WHERE id=11").fetchone())
    есть = store._conn.execute(
        "SELECT id FROM campaigns WHERE name=?", (ИМЯ,)).fetchone()
шаги = store.get_steps(11)
print("образец №11: %s | юрлицо %s %s | пул %s | шагов %d"
      % (обр["name"], обр["legal_entity"], обр["legal_inn"],
         обр["provider_pool"], len(шаги)))
конф = json.loads(обр["config_json"] or "{}") or {}
конф["segment"] = "Россия 9000 — Meyer"
print("конфиг образца: %s" % json.dumps(конф, ensure_ascii=False)[:300])

карта = store.get_setting("segment_division", None) or {}
карта = dict(карта) if isinstance(карта, dict) else {}
нов_карта = dict(карта)
for о in ОТРАСЛИ:
    нов_карта[о.lower()] = "meyer"
print("segment_division: было %d правил, станет %d" % (len(карта), len(нов_карта)))

if not ПРИМЕНИТЬ:
    print("=== ЗАПУСК 500: СУХОЙ ПРОГОН (кампания %s) ===" %
          ("есть #%s" % есть[0] if есть else "будет создана"))
    sys.exit(0)

store.set_setting("segment_division", нов_карта)
if есть:
    камп = int(есть[0])
else:
    камп = store.create_campaign(CampaignIn(
        name=ИМЯ, legal_entity=обр["legal_entity"], legal_inn=обр["legal_inn"],
        provider_pool=обр["provider_pool"], config=конф))
    ш = шаги[0]
    store.add_step(SequenceStepIn(
        campaign_id=камп, step_index=0, delay_hours=int(ш.delay_hours or 0),
        subject_tmpl=ш.subject_tmpl, body_tmpl=ш.body_tmpl,
        engagement_gate=getattr(ш, "engagement_gate", "all") or "all",
        include_legal=bool(getattr(ш, "include_legal", False))))
print("кампания: #%d «%s»" % (камп, ИМЯ))

лог = io.open(r"C:\sender\_ops\gen500.log", "a", encoding="utf-8")
п = subprocess.Popen(
    [sys.executable, r"C:\sender\server\ops\generaciya_500.py", str(камп)],
    cwd=r"C:\sender", stdout=лог, stderr=лог,
    creationflags=0x00000008 | 0x00000200)   # DETACHED | NEW_PROCESS_GROUP
io.open(r"C:\sender\_ops\gen500.pid", "w").write(str(п.pid))
time.sleep(8)
print("работник запущен, pid %d, жив: %s" % (п.pid, п.poll() is None))
try:
    print("прогресс: %s" % io.open(r"C:\sender\_ops\gen500-progress.json",
                                   encoding="utf-8").read()[:300])
except Exception:  # noqa: BLE001
    print("прогресс: файла ещё нет")
print("=== ЗАПУСК 500: ПРИМЕНЕНО, кампания #%d ===" % камп)
