# -*- coding: utf-8 -*-
"""Что внутри файла-протокола и почему из него не извлеклось ни одного имени.

Прогон нашёл девять протоколов, прочитал их и вернул ноль людей. Разница
важная: либо в тексте правда нет состава комиссии, либо не срабатывает вырезка
окон, либо молчит модель. Печатаем всё три состояния по одной компании.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC  # noqa: E402
import eis_protocols as EP    # noqa: E402


def main():
    inn = next((a for a in sys.argv[1:] if a.isdigit()), '')
    z = EC.find_zakupki_contacts(inn, max_cards=3)
    out = {'инн': inn, 'карточек': len((z or {}).get('cards') or []), 'файлы': []}
    for c in ((z or {}).get('cards') or [])[:3]:
        файлы = EC.eis_documents(c.get('url') or '')
        for имя_ф, у in файлы[:6]:
            зап = {'имя': (имя_ф or '')[:70],
                   'протокол_в_имени': bool(EP._ПРОТОКОЛ.search(имя_ф or ''))}
            txt = EC.doc_text(у)
            зап['символов'] = len(txt or '')
            if txt:
                зап['есть_слово_комиссия'] = bool(EP._КОМИССИЯ.search(txt))
                окна = EP.куски_комиссии(txt)
                зап['окон_вырезано'] = len(окна)
                зап['первое_окно'] = (окна[0][:400] if окна else '')
                зап['начало_текста'] = re.sub(r'\s+', ' ', txt)[:250]
            out['файлы'].append(зап)
            if len(out['файлы']) >= 5:
                break
        if len(out['файлы']) >= 5:
            break
    # и проверим саму модель на первом окне
    for ф in out['файлы']:
        if ф.get('окон_вырезано'):
            люди = EP.разобрать(ф.get('первое_окно', '') * 1, 'проба', inn, 'x')
            out['модель_вернула'] = люди[:4]
            break
    print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])


if __name__ == '__main__':
    main()
