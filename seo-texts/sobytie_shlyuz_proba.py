# -*- coding: utf-8 -*-
"""Почему одиночный вызов стадии падает на сервере: дело в РАЗМЕРЕ тела или вообще в связи?

Замер 16.09: на сервере `stadiya_odnogo` вернул sboy_provaydera с
ConnectionResetError(10054). В docstring `verify_company._provider_call_stdlib` прямо
записано, что маршрут сервера душит большие однокусковые POST. Промпт классификатора
стадии ~3,8 КБ против ~1,5 КБ у `extract_event`, который работает годами. Значит версий
две, и они чинятся по-разному:
    1) виноват размер тела - тогда надо сокращать промпт для серверного пути;
    2) шлюз сейчас недоступен вообще - тогда сокращать нечего, надо ждать.
Прибор различает их: шлёт короткий промпт и длинный, по три раза каждый.
"""
import sys
import time

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import verify_company as VC  # noqa: E402

import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location('sobytie_stadiya',
                                              r'C:\sender\_ops\3s_sobytie_stadiya.py')
SS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SS)

KOROTKIY = 'Ответь одним словом: работает'
DLINNYY = SS.PROMPT + '[{"id":1,"tekst":"строительство завода по выпуску полимеров"}]'
SREDNIY = ('Определи стадию проекта одним словом из списка: намерение, планирование, '
           'проектирование, финансирование, стройка, оснащение, ввод, эксплуатация. '
           'Текст: "подписано соглашение о строительстве завода полимеров". '
           'Ответь только словом.')

for imya, prompt in (('короткий', KOROTKIY), ('средний', SREDNIY), ('полный промпт стадии', DLINNYY)):
    print('\n### %s: %d байт' % (imya, len(prompt.encode('utf-8'))))
    for n in range(3):
        t = time.time()
        try:
            out = VC._provider_call_stdlib(prompt, model='claude-fable-5')
            print('  попытка %d: ОТВЕТ %d знаков за %.1f с: %r'
                  % (n + 1, len(out or ''), time.time() - t, (out or '')[:80]))
        except Exception as ex:  # noqa: BLE001
            print('  попытка %d: СБОЙ за %.1f с: %r' % (n + 1, time.time() - t, ex))
        time.sleep(1)
print('\n=== ИТОГ пробы шлюза ===')
