# -*- coding: utf-8 -*-
"""Снять с компаний попытки, сгоревшие на пустом кошельке провайдера.

17.08, ~19:20: у провайдера кончился баланс ($0.0254), и КАЖДЫЙ вызов стал
отдавать HTTP 403. Конвейер честно записал это в журнал как неудачу
генерации - и тем самым израсходовал компаниям попытки: резюм считает
попыткой любую строку «сгенерировано», а на четвёртой ИНН выбывает
насовсем («исчерпал 3 попытки»).

Урон не в деньгах - вызовы 403 бесплатны, - а в том, что компании
выбрасываются из партии по причине, к ним не относящейся. Молча это
оставлять нельзя.

Чиним честно: дописываем в журнал строку-отмену на каждую сгоревшую
попытку. Резюм читает журнал целиком, поэтому отменённые попытки перестают
считаться. Ничего не удаляем - журнал остаётся тем, что было.

Без аргумента - только считает. Пишет при `--снять`.

    python zapusk_svoego_skripta.py ops/otkatit_403_popytki.py
    python zapusk_svoego_skripta.py ops/otkatit_403_popytki.py --снять
"""
import io
import json
import os
import sys
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ПРИЗНАК = "credit wallet quota insufficient"
СНИМАТЬ = "--снять" in sys.argv

счёт = Counter()
сгоревшие = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                       # noqa: BLE001
            continue
        текст = json.dumps(z.get("брак") or [], ensure_ascii=False)
        if ПРИЗНАК not in текст and "HTTP 403" not in текст:
            continue
        счёт["строк с 403"] += 1
        if z.get("этап") == "сгенерировано":
            счёт["из них попыток (этап «сгенерировано»)"] += 1
            сгоревшие.append(z)

инн = {str(z.get("inn") or "") for z in сгоревшие}
print(f"строк журнала, убитых пустым кошельком: {счёт['строк с 403']}")
print(f"из них сгоревших попыток: {len(сгоревшие)} у {len(инн)} компаний")

# сколько компаний из-за этого уже на грани выбывания
попыток = Counter()
for s in io.open(ЖУРНАЛ, encoding="utf-8") if os.path.exists(ЖУРНАЛ) else []:
    try:
        z = json.loads(s)
    except Exception:                                           # noqa: BLE001
        continue
    if z.get("этап") != "итог" and str(z.get("inn") or ""):
        попыток[str(z["inn"])] += 1
на_грани = [i for i in инн if попыток[i] >= 3]
print(f"компаний, которым 403 добил счётчик до 3 и выше: {len(на_грани)}")

if not СНИМАТЬ:
    print("\nсухой прогон: журнал не тронут. Снять - аргумент --снять")
    raise SystemExit(0)

if not сгоревшие:
    print("снимать нечего")
    raise SystemExit(0)

with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
    for z in сгоревшие:
        f.write(json.dumps({
            "inn": z.get("inn"), "recipient_id": z.get("recipient_id"),
            "имя": z.get("имя"), "этап": "отмена_попытки",
            "почему": "провайдер вернул 403: кончился баланс кошелька, "
                      "к компании претензий нет",
            "ок": False}, ensure_ascii=False) + "\n")
    f.flush()
    os.fsync(f.fileno())
print(f"дописано отмен: {len(сгоревшие)}")
print("ВАЖНО: резюм в ops/partiya_gen.py обязан вычитать «отмена_попытки» "
      "из счётчика попыток - без этого запись бесполезна.")
