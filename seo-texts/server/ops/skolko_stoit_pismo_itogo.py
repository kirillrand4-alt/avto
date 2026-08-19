# -*- coding: utf-8 -*-
"""Сколько в итоге стоит одно письмо: с браком, дописыванием и рецензией.

Владелец: «сколько у нас в итоге стоит 1 письмо? с учётом дописываний,
отбраковок». Считаем по durable-журналам, за окно последних суток - там
живёт нынешний конвейер (текст сайта в промпте, проверки на модели попроще,
кэш промпта, сохранение черновиков брака).

Три цены, и путать их нельзя:
  за попытку  - сколько стоит подойти к компании (брак включён);
  за вышедшее - сколько стоит письмо, прошедшее гейт и линзы;
  ЗА ГОДНОЕ   - сколько стоит письмо, которое рецензент по сайту разрешил
                отправлять. Это единственная честная цена: остальные не
                учитывают, что часть писем всё равно снимут.

Дописывание считаем отдельной строкой: это спасение уже оплаченного брака,
и оно меняет знаменатель, а не числитель.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ГЕН = r"C:\sender\_ops\gen-partiya-935.jsonl"
ДОП = r"C:\sender\_ops\dopisannye-zachiny.jsonl"
РЕЦ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
СЧЁТ = r"C:\sender\_ops\schyotchik-shlyuza.jsonl"
# ПОЛЯ «день» в записи генерации НЕТ - первый заход этого замера отфильтровал
# по нему и получил ноль попыток. Берём хвост журнала: ночные волны это
# последние записи, и именно они шли нынешним конвейером.
ХВОСТ = int(next((a for a in sys.argv[1:] if a.isdigit()), "620"))

верд = {}
for s in io.open(РЕЦ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
# review_id по получателю - чтобы связать письмо с вердиктом
по_получателю = {}
with store._lock:
    for rid, rcid in store._conn.execute(
            "SELECT id, recipient_id FROM confirm_reviews "
            "WHERE campaign_id IN (10,11)").fetchall():
        if rcid:
            по_получателю.setdefault(int(rcid), []).append(int(rid))


def вердикт(rcid):
    в = [верд.get(r) for r in по_получателю.get(int(rcid), [])]
    в = [x for x in в if x]
    for предпочтение in ("годно", "не годно", "нечем проверить"):
        if предпочтение in в:
            return предпочтение
    return "нет вердикта"


# --- генерация -----------------------------------------------------------
попыток = вышло = 0
деньги = 0.0
исходы = Counter()
_строки_ген = io.open(ГЕН, encoding="utf-8", errors="replace").readlines()
for s in _строки_ген[-ХВОСТ:]:
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") == "итог":
        continue
    попыток += 1
    деньги += float(z.get("цена_$") or 0)
    if z.get("ок") or z.get("тело"):
        вышло += 1
        исходы[вердикт(z.get("recipient_id"))] += 1

# --- дописывание ---------------------------------------------------------
доп_в_очереди = доп_брак = 0
доп_исходы = Counter()
for s in io.open(ДОП, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("гейт"):
        доп_брак += 1
        continue
    if not z.get("review_id"):
        continue
    доп_в_очереди += 1
    доп_исходы[верд.get(int(z["review_id"])) or "нет вердикта"] += 1

# деньги дописывания - по счётчику шлюза (своих токенов оно не считает)
доп_деньги = 0.0
замеры = []
for s in io.open(СЧЁТ, encoding="utf-8", errors="replace"):
    try:
        замеры.append(json.loads(s))
    except Exception:                                            # noqa: BLE001
        pass
for a, b in zip(замеры, замеры[1:]):
    if "дописыван" in str(b.get("метка") or ""):
        доп_деньги += (b["total_usage"] - a["total_usage"]) / 100.0

годных = исходы.get("годно", 0)
доп_годных = доп_исходы.get("годно", 0)

print(f"== генерация: последние {ХВОСТ} записей журнала ==")
print(f"  попыток:        {попыток}")
print(f"  вышло писем:    {вышло}")
print(f"  денег:          ${деньги:.2f}")
print("  вердикт рецензента у вышедших:")
for k, n in исходы.most_common():
    print(f"    {n:>4}  {k}")

print("\n== дописывание зачинов (спасение оплаченного брака) ==")
print(f"  в очереди:      {доп_в_очереди}, гейт снова забраковал: {доп_брак}")
print(f"  денег:          ${доп_деньги:.2f}")
for k, n in доп_исходы.most_common():
    print(f"    {n:>4}  {k}")

print("\n== ИТОГОВАЯ ЦЕНА ==")
if попыток:
    print(f"  за попытку:            ${деньги / попыток:.4f}")
if вышло:
    print(f"  за вышедшее письмо:    ${деньги / вышло:.4f}")
if годных:
    print(f"  за годное (без дописки): ${деньги / годных:.4f}")
всего_годных = годных + доп_годных
всего_денег = деньги + доп_деньги
if всего_годных:
    print(f"  ЗА ГОДНОЕ С ДОПИСКОЙ:  ${всего_денег / всего_годных:.4f}  "
          f"({всего_годных} годных за ${всего_денег:.2f})")
