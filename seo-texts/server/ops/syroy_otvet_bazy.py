# -*- coding: utf-8 -*-
"""Что именно возвращает gen_provider через baza-ai: сырой текст ответа."""
import io
import os
import sys

os.environ["PROVIDER_API_KEY"] = io.open(r"C:\sender\baza.key",
                                         encoding="utf-8").read().strip()
os.environ["PROVIDER_BASE_URL"] = "https://api.baza-ai.org"
sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402

СИСТЕМА = ('Ты классификатор. Ответь СТРОГО JSON без текста вокруг: '
           '{"firmy":[{"inn":"...","napravlenie":"кц|мейер|оба|никакое"}]}')
ЗАДАЧА = ("Компании:\n\nИНН 1111111111 · ООО «Дорстрой»\nАсфальтирование "
          "дорог, аренда спецтехники.\n\nИНН 2222222222 · ООО «Зерно-Юг»\n"
          "Переработка и очистка зерна, элеватор, фасовка круп.")

for м in ("gpt-5.4-mini", "gpt-5.6-luna"):
    print(f"=== {м} ===")
    try:
        m = GP._raw_stream([{"role": "user", "content": ЗАДАЧА}], м, 600,
                           thinking=False, system=СИСТЕМА)
        блоки = getattr(m, "content", None)
        print("  тип ответа:", type(m).__name__, "| блоков:",
              len(блоки) if блоки else 0)
        т = "".join(getattr(b, "text", "") for b in (блоки or []))
        print("  текст:", repr(т[:400]))
        u = getattr(m, "usage", None)
        print("  usage:", getattr(u, "input_tokens", None),
              getattr(u, "output_tokens", None))
    except Exception as ex:                                      # noqa: BLE001
        print(f"  СБОЙ {type(ex).__name__}: {str(ex)[:200]}")
