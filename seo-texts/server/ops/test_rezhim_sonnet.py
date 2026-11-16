# -*- coding: utf-8 -*-
"""Замер режима вызова на канале (владелец 16.11: «дороговато… посмотри, как кеш лечили»): промпт линз Meyer в system
(кэш), три режима по 2 повтора: без поля thinking и без effort / без thinking + effort=low / thinking disabled.
Печатает токены: вход, кэш запись/чтение, выход, знаков рассуждения.   test_rezhim_sonnet.py [модель]"""
import os, sys, time
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402
import sender.ai_letter as AL  # noqa: E402
М = sys.argv[1] if len(sys.argv) > 1 else "claude-sonnet-5-5"
СИС = ("Ты проверяешь письмо поставщика Meyer тремя взглядами.\n1) " + AL._TEH_LENS_TEHNOLOG_MEYER + "\n2) " + AL._TEH_LENS_SKEPTIK_MEYER +
       '\nОтвет СТРОГО JSON: {"tehnolog": {"verdict": "...", "pochemu": "кратко"}, "skeptik": {"verdict": "...", "pochemu": "кратко"}}') * 2
ПИС = "Профиль: зерновое хозяйство, продукт: зерно.\nПисьмо: Для зерна фотосепараторы Meyer до фасовки отделяют сорную примесь и дефектные зёрна по цвету и форме."
for имя, поле, eff in (("omit, без effort", "omit", None), ("omit, effort=low", "omit", "low"), ("disabled, без effort", "disabled", None)):
    os.environ["PROVIDER_THINKING_FIELD"] = поле
    for п in range(2):
        t = time.time()
        try:
            м = GP._raw_stream([{"role": "user", "content": ПИС}], М, 600, thinking=False, effort=eff, system=СИС, cache_system=True)
            у = м.usage; дум = sum(len(b.text) for b in м.content if b.type == "thinking")
            print("%-22s #%d вход %5d кэш-запись %5d кэш-чтение %5d выход %4d рассуждение %5d зн %.1fс" % (
                имя, п + 1, у.input_tokens, у.cache_creation_input_tokens, у.cache_read_input_tokens, у.output_tokens, дум, time.time() - t), flush=True)
        except Exception as ex:  # noqa: BLE001
            print(имя, "ошибка", str(ex)[:150], flush=True)
