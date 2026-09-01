# -*- coding: utf-8 -*-
"""Живая проба линзы: отдаёт ли шлюз текст или одно рассуждение.

Зовём _raw_stream ровно так, как зовёт линза (thinking=False, effort из
LETTER_EFFORT), на коротком промпте формы гейта, и печатаем токены выхода
против длины текста. Несколько моделей подряд — чтобы понять, шлюз это
целиком или одна модель.
"""
import os
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider                                            # noqa: E402

ПРОМПТ = (
    "Ты отборщик адресатов. Компания: ООО «Агрокомплекс», производство "
    "круп и зернопродуктов, своя линия фасовки, элеватор, 120 сотрудников. "
    "Мы продаём рентген-инспекцию и фотосепараторы для пищевого сырья.\n"
    "Ответь СТРОГО одним JSON без пояснений: "
    '{"подходит": true|false, "почему": "одна короткая фраза"}'
)

МОДЕЛИ = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"]
УСИЛИЯ = ["medium", "low"]

print("=== ПРОБА ЛИНЗЫ ЧЕРЕЗ ШЛЮЗ ===")
print("порог срыва: выход >= 2000 токенов И знаков текста < токенов выхода")
print("")
for м in МОДЕЛИ:
    for у in УСИЛИЯ:
        t = time.time()
        try:
            msg = gen_provider._raw_stream(
                [{"role": "user", "content": ПРОМПТ}], м, 2000,
                thinking=False, effort=у, system=None)
            текст = "".join(b.text for b in msg.content
                            if getattr(b, "type", "") == "text")
            u = getattr(msg, "usage", None)
            вых = int(getattr(u, "output_tokens", 0) or 0)
            вх = int(getattr(u, "input_tokens", 0) or 0)
            срыв = вых >= 2000 and len(текст) < вых
            print("%-28s %-7s %5.1fс  вход %5d  выход %5d  знаков %5d  %s"
                  % (м, у, time.time() - t, вх, вых, len(текст),
                     "СРЫВ" if срыв else "ок"))
            if текст:
                print("      ответ: %s" % текст.replace("\n", " ")[:150])
            else:
                типы = [getattr(b, "type", "?") for b in msg.content]
                print("      текста нет; блоки ответа: %s" % типы[:8])
        except Exception as ex:  # noqa: BLE001
            print("%-28s %-7s %5.1fс  ОШИБКА: %s"
                  % (м, у, time.time() - t, str(ex)[:110]))
        time.sleep(1)
