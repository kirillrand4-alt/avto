# -*- coding: utf-8 -*-
r"""Есть ли след ПРЕЖНЕЙ пробы этих адресов: отбивка перезаписывает вердикт."""
import json, os
АДРЕСА = ['sales@premfire.ru','snab@taimyr-fish.ru','neapol.sklad@mail.ru',
          'hr@sibach.store','pastarellab@mail.ru','snab@konex.ru',
          'okna_sklad@alkona.net','office@dscavtostrada.com','shop@zavodsota.ru']
итог = {'файлы': {}}
корни = [r'C:\sender', r'C:\sender\server', r'C:\seostat\drop']
кандидаты = []
for к in корни:
    if not os.path.isdir(к):
        continue
    for и in os.listdir(к):
        н = и.lower()
        if ('probe' in н or 'proba' in н) and н.endswith(('.jsonl', '.json', '.txt')):
            кандидаты.append(os.path.join(к, и))
for п in кандидаты:
    try:
        разм = os.path.getsize(п)
        т = open(п, encoding='utf-8', errors='replace').read()
        найдены = {a: (a in т) for a in АДРЕСА}
        итог['файлы'][п] = {'байт': разм, 'изменён': round(os.path.getmtime(п)),
                            'нашлись': [a for a, e in найдены.items() if e]}
    except Exception as e:
        итог['файлы'][п] = str(e)[:80]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2600])
