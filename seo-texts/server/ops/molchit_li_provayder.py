# -*- coding: utf-8 -*-
"""Отвечает ли шлюз прямо сейчас: короткий вызов с секундомером.

Владелец 20.08: «провайдер молчит». Проверяем не догадкой, а вызовом:
одна фраза, минимум токенов, засекаем время до первого байта и до
конца. Заодно — mtime журнала партии, чтобы отличить «шлюз молчит» от
«прогон не дошёл до генерации».
"""
import os
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                     # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
try:
    st = os.stat(ЖУРНАЛ)
    print(f"журнал партии: изменён {int(time.time() - st.st_mtime)} с назад")
except Exception as ex:                                       # noqa: BLE001
    print("журнал не прочесть:", str(ex)[:90])

КЛИЕНТ = GP.make_client()
МОДЕЛИ = sys.argv[1:] or ["claude-opus-4-8", "gpt-5.6-luna"]
for м in МОДЕЛИ:
    t0 = time.time()
    try:
        ответ = GP.call(КЛИЕНТ,
                        [{"role": "user", "content": "Ответь одним словом: да"}],
                        model=м, attempts=1, thinking=False)
        сек = time.time() - t0
        текст = (ответ if isinstance(ответ, str) else str(ответ))[:60]
        print(f"  {м:<18} ОТВЕТИЛ за {сек:5.1f} с: {текст!r}")
    except Exception as ex:                                   # noqa: BLE001
        сек = time.time() - t0
        print(f"  {м:<18} СБОЙ через {сек:5.1f} с: {type(ex).__name__}: "
              f"{str(ex)[:200]}")
