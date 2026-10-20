# -*- coding: utf-8 -*-
# 20.10: проба классификации Sol — 20 крупнейших + 20 случайных, синхронно; файл пробы стирается (полный прогон — заново).
import io, json, os, random, sys
sys.path.insert(0, r'C:\sender\server')
import fsa_klass3 as F  # noqa: E402
import kc_kontakty as KK  # noqa: E402
if os.path.exists(F.ВЫХ):
    os.remove(F.ВЫХ)
вход = json.load(io.open(F.ВХОД, encoding='utf-8'))
кк = list(вход)
random.seed(7)
выб = кк[:20] + random.sample(кк[20:], 20)
F.пачка(KK, выб[:20], вход)
F.пачка(KK, выб[20:], вход)
г = F.готовые()
print('===ИТОГ===')
for i in выб:
    y = г.get(i) or {}
    print(y.get('класс', '?'), y.get('уверенность', ''), '|', y.get('почему', ''), '|', вход[i][:120])
os.remove(F.ВЫХ)
