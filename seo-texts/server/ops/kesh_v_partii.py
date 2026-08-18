# -*- coding: utf-8 -*-
"""Работает ли кэш промпта на пути массовой генерации (partiya_gen).

Владелец спросил прямо: «ты опросы без кэша делаешь?». Отвечать по памяти
нельзя - меряем токенами, которые вернул сам шлюз.

Два пути ходят к модели по-разному:
  * панель (ai_quota -> review_lenses.default_caller) режет промпт и кладёт
    статику в поле system с cache_control - кэш читается;
  * ops/partiya_gen.py зовёт _raw_stream ОДНИМ куском в messages, без
    system - кэшу неоткуда взяться.

Замер: один и тот же статический префикс, два РАЗНЫХ получателя.
  A. одним куском (как в partiya_gen сейчас);
  B. с разрезом (как в панели).
Смотрим cache_read_input_tokens: если у B на втором вызове он ненулевой -
кэш живой, и partiya_gen переплачивает.
"""
import sys

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402

МОДЕЛЬ = "claude-fable-5"
факты = load_facts()

ПОЛУЧАТЕЛИ = [
    {"mode": "GENERIC", "company_name": "ООО «Первый Механический»",
     "activity": "механическая обработка металлов", "okved": "25.62",
     "extra": {}},
    {"mode": "GENERIC", "company_name": "ООО «Второй Литейный»",
     "activity": "литьё чугуна", "okved": "24.51", "extra": {}},
]


def _замер(prompt, режим):
    системный, тело = (GP.razrezat_promt(prompt) if режим == "разрез"
                       else (None, prompt))
    m = GP._raw_stream([{"role": "user", "content": тело}], МОДЕЛЬ, 2000,
                       thinking=False, effort="low", system=системный)
    u = getattr(m, "usage", None)
    вход = int(getattr(u, "input_tokens", 0) or 0)
    чт = int(getattr(u, "cache_read_input_tokens", 0) or 0)
    зп = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    вых = int(getattr(u, "output_tokens", 0) or 0)
    print(f"  {режим:<10} system={len(системный or ''):>6} знаков  "
          f"вход={вход:>6}  кэш_чтение={чт:>6}  кэш_запись={зп:>6}  "
          f"выход={вых:>5}")
    return вход, чт, зп, вых


for режим in ("одним куском", "разрез"):
    print(f"{режим}:")
    for i, r in enumerate(ПОЛУЧАТЕЛИ):
        _замер(gen_prompt([r], факты, "kc", angle_base=i), режим)

print("\nЕсли у «разрез» на втором вызове кэш_чтение > 0, а у «одним куском»\n"
      "ноль оба раза - partiya_gen ходит без кэша и переплачивает за вход.")
