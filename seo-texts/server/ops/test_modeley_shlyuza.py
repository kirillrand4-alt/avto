# -*- coding: utf-8 -*-
"""Короткий тест: какие модели шлюз отдаёт прямо сейчас (по одному маленькому вызову, без ретраев).
    test_modeley_shlyuza.py [модель1,модель2,...]"""
import sys, time
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402
М = (sys.argv[1] if len(sys.argv) > 1 else
     "claude-sonnet-4-6,claude-sonnet-5,claude-sonnet-5-5,claude-opus-4-6,claude-opus-4-7,claude-opus-4-8,claude-opus-5,claude-opus-5-5,claude-fable-5").split(",")
for м in М:
    t = time.time()
    try:
        о = GP._raw_stream([{"role": "user", "content": "Ответь одним словом: ок"}], м, 20, thinking=False, effort="low")
        т = о if isinstance(о, str) else "".join(getattr(b, "text", "") for b in getattr(о, "content", []) or [])
        print("%-20s OK   %4.1fс  %r" % (м, time.time() - t, т.strip()[:20]), flush=True)
    except Exception as ex:  # noqa: BLE001
        print("%-20s FAIL %4.1fс  %s" % (м, time.time() - t, str(ex)[:110]), flush=True)
