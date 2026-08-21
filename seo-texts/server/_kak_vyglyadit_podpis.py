# -*- coding: utf-8 -*-
r"""Живые примеры: что именно моё правило берёт со страницы и во что это ложится.

Владелец 21.08: «не понял, как ты вытащишь роли из html, если их определяет
провайдер». Показываем на настоящих страницах кэша: слева от номера печатаем
сырой кусок текста, рядом — что взяло правило и во что это превращает наша же
каноническая таблица ролей (_ROLE_CANON), которой пользуется провайдерский путь.
"""
import json
import os
import random
import re
import sys

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
sys.path.insert(0, r'C:\sender\server')
import lid_ssylka as LS  # noqa: E402
from enrich_db import EnrichDB  # noqa: E402

КЕШ = r'C:\seostat\drop\pagecache'
файлы = [n for n in os.listdir(КЕШ) if n.endswith('.json.gz')]
random.seed(11)
random.shuffle(файлы)

примеры, без_подписи = [], []
for имя in файлы[:900]:
    if len(примеры) >= 8 and len(без_подписи) >= 4:
        break
    инн = имя.split('.')[0]
    страницы = LS._stranicy_kesha(инн)
    if not страницы:
        continue
    for url, html in страницы[:6]:
        текст = LS._tekst_stranicy(html)
        for m in LS._ТЕЛ_В_ТЕКСТЕ.finditer(текст):
            ц = LS._цифры(m.group(0))
            if not LS._pohozh_na_telefon(ц) or LS._fiktivnyy(ц[-10:]):
                continue
            слева = re.sub(r'\s+', ' ', текст[max(0, m.start() - 70):m.start()])
            подпись = LS._podpis_pered(текст, m.start())
            низ = подпись.lower().strip(' .:')
            if any(б in низ for б in LS._НЕ_ТЕЛЕФОН):
                continue
            если_пустая = низ in LS._ПУСТАЯ_ПОДПИСЬ
            строка = {'инн': инн, 'страница': url[:52],
                      'слева_на_странице': '…' + слева[-58:],
                      'номер': m.group(0).strip()[:24],
                      'правило_взяло': ('' if если_пустая else подпись),
                      'канон_роль': (EnrichDB._canon_role(подпись)
                                     if подпись and not если_пустая else '')}
            # берём в базу ТОЛЬКО то, что наша каноническая таблица опознала
            # как настоящую роль: «Единый телефон» она честно кладёт в «общий»,
            # а «общий» писать незачем — это то же самое, что не писать ничего
            if (строка['канон_роль'] and строка['канон_роль'] != 'общий'
                    and len(примеры) < 8):
                примеры.append(строка)
            elif not строка['правило_взяло'] and len(без_подписи) < 3:
                без_подписи.append(строка)
            break
print(json.dumps({'ПОДПИСИ НЕТ — роль остаётся пустой': без_подписи},
                 ensure_ascii=False, indent=1)[:1200])
print(json.dumps({'ПОДПИСЬ ОПОЗНАНА КАНОНОМ — её и пишем': примеры},
                 ensure_ascii=False, indent=1)[:2600])
