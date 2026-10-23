# -*- coding: utf-8 -*-
"""Проверка кэша шлюза провайдера: два одинаковых запроса подряд с длинной
системной частью (кэшируемой) — сколько записано/прочитано кэша во втором.
Если чтение ~0 и запись снова большая — кэш шлюза не работает.
    test_kesh.py [модель]"""
import sys

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402

М = sys.argv[1] if len(sys.argv) > 1 else "claude-sonnet-4-6"
СИС = ("Ты помощник. " + "Справочный текст для кэша. " * 900)[:20000]
for i in (1, 2):
    m = GP._raw_stream([{"role": "user", "content": "Ответь одним словом: ок"}], М, 20, thinking=False,
                       effort="low", system=СИС)
    u = getattr(m, "usage", None)
    print("вызов %d: usage=%s" % (i, {k: getattr(u, k, None) for k in ("input_tokens", "cache_creation_input_tokens",
                                                                     "cache_read_input_tokens", "output_tokens")}
                                     if u is not None else m if isinstance(m, dict) else "нет"))
