# -*- coding: utf-8 -*-
"""Какие дешёвые модели шлюза отвечают ПРЯМО СЕЙЧАС и почём.

Предклассификатор ходит на gpt-5.6-luna, и 20.08 она замолчала: стрим
шлёт только ping, 90 с — и таймаут. _predklass ловит сбой и НИКОГО не
режет, то есть прогон «с предклассификатором» идёт без него.

Спрашиваем каждую кандидатку тем же способом, что и предклассификатор
(_raw_stream, thinking=False, system), на живом куске работы — чтобы
видеть и ответ, и токены.
"""
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                     # noqa: E402

СИСТЕМА = ("Ты классификатор. Ответь ТОЛЬКО json "
           '{"firmy":[{"inn":"...","napravlenie":"кц|мейер|оба|никакое"}]}')
ЗАДАЧА = ("Компании:\n\nИНН 1111111111 · ООО «Дорстрой»\nАсфальтирование "
          "дорог, аренда спецтехники, свой парк катков.\n\n"
          "ИНН 2222222222 · ООО «Зерно-Юг»\nПереработка и очистка зерна, "
          "элеватор, фасовка круп.")

МОДЕЛИ = sys.argv[1:] or [
    "claude-haiku-4-5", "gpt-5.6-luna", "gpt-5.4-mini",
    "gemini-3.6-flash", "deepseek-v4-flash"]
for м in МОДЕЛИ:
    t0 = time.time()
    try:
        m = GP._raw_stream([{"role": "user", "content": ЗАДАЧА}], м, 600,
                           thinking=False, system=СИСТЕМА)
        сек = time.time() - t0
        т = "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
        u = getattr(m, "usage", None)
        вх = getattr(u, "input_tokens", None) if u else None
        вых = getattr(u, "output_tokens", None) if u else None
        print(f"  {м:<20} за {сек:5.1f} с  вход={вх} выход={вых}\n"
              f"      {т.strip()[:160]!r}")
    except Exception as ex:                                   # noqa: BLE001
        print(f"  {м:<20} СБОЙ за {time.time() - t0:5.1f} с: "
              f"{type(ex).__name__}: {str(ex)[:130]}")
