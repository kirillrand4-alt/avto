# -*- coding: utf-8 -*-
"""Разные ли модели отвечают на разные имена у шлюза.

Замер кэша дал у opus-4-8, opus-4-6, fable-5 и sonnet-5 одинаковые числа
usage ДО ТОКЕНА, включая случайные на вид чтения (28, потом 84). Один
токенизатор такого не объясняет. Спрашиваем сами модели: кто отвечает и
чем отличается ответ.

Вопрос выбран так, чтобы ответ зависел от модели, а не от промпта.
"""
import sys

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402

МОДЕЛИ = ["claude-opus-4-8", "claude-opus-4-6", "claude-fable-5",
          "claude-sonnet-5", "claude-sonnet-4-6"]
ВОПРОС = ("Назови точное имя своей модели и дату обучения одной строкой, "
          "без пояснений. Формат: имя | дата.")

for м in МОДЕЛИ:
    try:
        msg = GP._raw_stream([{"role": "user", "content": ВОПРОС}], м, 120,
                             thinking=False)
        т = "".join(b.text for b in msg.content
                    if getattr(b, "type", "") == "text").strip()
        u = getattr(msg, "usage", None)
        print(f"{м:<20} вход {int(getattr(u, 'input_tokens', 0) or 0):>4} "
              f"выход {int(getattr(u, 'output_tokens', 0) or 0):>4}  "
              f"{т[:90]}")
    except Exception as ex:                                      # noqa: BLE001
        print(f"{м:<20} сбой: {type(ex).__name__} {str(ex)[:70]}")
