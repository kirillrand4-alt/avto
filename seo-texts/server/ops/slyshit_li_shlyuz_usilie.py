# -*- coding: utf-8 -*-
"""Слышит ли шлюз наш effort — или гонит рассуждение на high по умолчанию.

В журнале шлюза у всех опусовых вызовов стоит «Рассуждение: high по
умолчанию», хотя генерация отправляет effort='low'. Если настройка не
доходит, мы платим за рассуждение, которого не просили: выход у таких
вызовов 2.5-7 тысяч токенов по $25/M — это и есть основная цена письма.

Гоняем ОДИН и тот же промпт четырьмя способами и смотрим ВЫХОД. Если
цифры не отличаются — шлюз наш effort игнорирует.
"""
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402

ЦЕНА = (5.0, 25.0)
# РАЗНЫЕ КОМПАНИИ НА КАЖДЫЙ ВАРИАНТ. Первый заход этой пробы дал четыре
# одинаковых строки (731/539/1020 знаков), причём со второго раза ответ
# приходил за секунду вместо одиннадцати: шлюз отдал КЭШ ОТВЕТА на тот же
# промпт. Сравнивать усилие на одинаковом тексте бессмысленно.
ФИРМЫ = [("ООО «Четвёртый Прокатный»", "прокат цветных металлов", "24.42"),
         ("ООО «Пятый Литейный»", "литьё стали", "24.52"),
         ("ООО «Шестой Кузнечный»", "ковка и штамповка", "25.50"),
         ("ООО «Седьмой Механический»", "мехобработка", "25.62")]
факты = load_facts(division="kc")

ВАРИАНТЫ = [("effort=low", {"effort": "low"}),
            ("effort не шлём", {}),
            ("thinking=False, effort=low", {"effort": "low",
                                            "thinking": False}),
            ("effort=high (для сверки)", {"effort": "high"})]

print(f"{'вариант':<28} {'вход':>7} {'выход':>7} {'сек':>6} {'$':>9} знаков")
for (имя, kw), (фирма, вид, оквэд) in zip(ВАРИАНТЫ, ФИРМЫ):
    пол = {"mode": "GENERIC", "company_name": фирма, "activity": вид,
           "okved": оквэд, "extra": {}}
    сис, тело = GP.razrezat_promt(
        gen_prompt([пол], факты, "kc", angle_base=7))
    т0 = time.time()
    try:
        m = GP._raw_stream([{"role": "user", "content": тело}],
                           "claude-opus-4-8", 4000,
                           thinking=kw.get("thinking", False),
                           effort=kw.get("effort"), system=сис)
    except Exception as ex:                                      # noqa: BLE001
        print(f"{имя:<28} упал: {str(ex)[:60]}")
        continue
    u = getattr(m, "usage", None)
    вх = int(getattr(u, "input_tokens", 0) or 0)
    вых = int(getattr(u, "output_tokens", 0) or 0)
    зап = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    чт = int(getattr(u, "cache_read_input_tokens", 0) or 0)
    текст = "".join(b.text for b in m.content
                    if getattr(b, "type", "") == "text")
    цена = ((вх + 1.25 * зап + 0.10 * чт) / 1e6 * ЦЕНА[0]
            + вых / 1e6 * ЦЕНА[1])
    print(f"{имя:<28} {вх:>7} {вых:>7} {time.time()-т0:>6.0f} "
          f"{цена:>9.4f} {len(текст)}")
