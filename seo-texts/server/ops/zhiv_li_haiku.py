# -*- coding: utf-8 -*-
"""Жив ли haiku на шлюзе — он держит линзы идей и валит прогоны тайм-аутами.

В прогоне deepseek каждый вызов линзы висел по 90 секунд («шлюз шлёт только
ping») и уходил в запасную модель. Тридцать минут ушли на ожидание, письмо
вышло одно. Проверяем коротким вызовом, а не по логам.
"""
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402

for м in ("claude-haiku-4-5", "gpt-5.6-luna", "claude-sonnet-4-6"):
    т0 = time.time()
    try:
        msg = GP._raw_stream(
            [{"role": "user", "content": "Назови три причины, зачем заводу "
                                         "нужен компрессор. По строке."}],
            м, 300, thinking=False, effort="low")
        т = "".join(b.text for b in msg.content
                    if getattr(b, "type", "") == "text")
        print(f"{м:<22} ОТВЕТИЛ за {time.time()-т0:.0f}с, {len(т)} знаков")
    except Exception as ex:                                      # noqa: BLE001
        print(f"{м:<22} УПАЛ за {time.time()-т0:.0f}с: "
              f"{type(ex).__name__}: {str(ex)[:90]}")
