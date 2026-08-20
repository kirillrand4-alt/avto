# -*- coding: utf-8 -*-
r"""Сколько текста уйдёт провайдеру: меряем по самому кэшу, без вызовов."""
import gzip, json, os, random
KESH = r'C:\seostat\drop\pagecache'
имена = [n for n in os.listdir(KESH) if n.endswith('.json.gz')]
random.seed(7)
проба = random.sample(имена, min(120, len(имена)))
знаков, страниц, пустых = [], [], 0
for n in проба:
    try:
        with gzip.open(os.path.join(KESH, n), 'rb') as f:
            d = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:
        continue
    стр = d.get('pages') or []
    if not стр:
        пустых += 1
        continue
    # ровно то, что уходит в промпт: по 8000 знаков со страницы
    сумма = sum(len(str((p or {}).get('text') or (p or {}).get('html') or '')[:8000])
                for p in стр)
    знаков.append(сумма)
    страниц.append(len(стр))
знаков.sort()
n = len(знаков)
итог = {
    'осмотрено_карточек': len(проба), 'пустых': пустых,
    'страниц_на_компанию_средне': round(sum(страниц) / max(1, len(страниц)), 1),
    'знаков_на_компанию': {
        'медиана': знаков[n // 2] if n else 0,
        'среднее': round(sum(знаков) / max(1, n)),
        'верхние_10%': знаков[int(n * 0.9)] if n else 0,
    },
}
# токены грубо: 1 токен ~ 3 знака кириллицы
ср = итог['знаков_на_компанию']['среднее']
токенов = ср / 3.0
итог['токенов_вход_на_компанию'] = round(токенов)
# ставки gpt-5.6-luna: 0.11 / 0.67 долара за миллион
итог['доллара_на_компанию_вход'] = round(токенов / 1e6 * 0.11, 5)
итог['на_14457_без_паспорта_долларов'] = round(токенов * 14457 / 1e6 * 0.11, 1)
итог['плюс_выход_примерно_долларов'] = round(700 * 14457 / 1e6 * 0.67, 1)
print(json.dumps(итог, ensure_ascii=False, indent=1))
