# -*- coding: utf-8 -*-
"""Номера из полного конвейера hz1 (20.10) -> общий формат телефонов базы прозвона (hz-telefony-h1.jsonl).

Сайт берётся, только если он свой: ИНН компании на сайте (аудит) либо проверка сайта «та же/группа» без опровержения,
либо совпадение по названию + проверка «та же/группа» или опровергатель «подтверждаю». Сайт «другая» или «опровергаю»
(без ИНН на сайте) — номера не берём. Номер — только «чей = эта». Плюс контактные лица из карточек закупок ЕИС.

    python3 hz_h1.py <папка hz1-*.jsonl> <out.jsonl>
"""
import collections
import io
import json
import os
import re
import sys


def посл(путь, ключ='inn'):
    d = {}
    for s in io.open(путь, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(s)
        except ValueError:
            continue
        if x.get(ключ):
            d[x[ключ]] = x
    return d


def main(папка, выход):
    кт = {}
    for s in io.open(os.path.join(папка, 'hz1-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        x = json.loads(s)
        if x.get('итог') == 'ok':
            кт[x['inn']] = x
    ау, пр, оп = (посл(os.path.join(папка, f)) for f in ('hz1-audit.jsonl', 'hz1-sayt-proverka.jsonl', 'hz1-oprov.jsonl'))
    сч = collections.Counter()
    with io.open(выход, 'w', encoding='utf-8') as f:
        for инн, x in кт.items():
            чей = str((ау.get(инн) or {}).get('сайт_чей') or '')
            п_ = (пр.get(инн) or {}).get('итог')
            о_ = (оп.get(инн) or {}).get('итог')
            if чей.startswith('свой'):
                годен = True
            elif п_ == 'другая' or о_ == 'опровергаю':
                годен = False
            elif п_ in ('та же', 'группа'):
                годен = True
            else:
                годен = чей.startswith('по названию') and о_ == 'подтверждаю'
            сч['сайт свой' if годен else 'сайт не подтверждён'] += 1
            if годен:
                for н in x.get('номера') or []:
                    if н.get('чей') != 'эта' or not н.get('номер'):
                        сч['номер чужой'] += 1
                        continue
                    стр = [u for u in н.get('страницы') or [] if str(u).startswith('http')]
                    if not стр:
                        continue
                    f.write(json.dumps({'inn': инн, 'телефон': н.get('номер'), 'доб': н.get('доб') or '', 'фио': н.get('фио') or '',
                                        'должность': н.get('должность') or '', 'роль': н.get('роль') or '',
                                        'источник': 'сайт компании', 'ссылка': стр[0], 'цитата': (н.get('контекст') or '')[:300],
                                        'источник_файл': 'hz1-kontakty.jsonl (полный обход 20.10)'}, ensure_ascii=False) + '\n')
                    сч['номеров'] += 1
            for з in x.get('закупки') or []:
                if not з.get('инн_на_странице'):
                    continue
                for ч in з.get('люди') or []:
                    # контакт карточки может быть сотрудником организатора закупки (Востокгазпром для Газпром метанола):
                    # берём, только если домен почты контакта = домен сайта компании
                    дом_п = str(ч.get('email') or '').lower().split('@')[-1]
                    дом_с = re.sub(r'^(https?://)?(www\.)?', '', str(x.get('сайт') or '').lower()).split('/')[0]
                    if not дом_п or not дом_с or not (дом_п == дом_с or дом_п.endswith('.' + дом_с) or дом_с.endswith('.' + дом_п)):
                        сч['контакт закупки чужого домена'] += 1
                        continue
                    for t in re.findall(r'\+?\d[\d\s()\-]{9,18}\d', str(ч.get('phone') or ч.get('телефон') or '')):
                        f.write(json.dumps({'inn': инн, 'телефон': t, 'доб': '', 'фио': ч.get('person') or ч.get('фио') or '',
                                            'должность': ч.get('post') or '', 'роль': 'контактное лицо закупки',
                                            'источник': 'ЕИС (карточка закупки)', 'ссылка': з.get('url') or '',
                                            'цитата': (з.get('предмет') or '')[:300], 'источник_файл': 'hz1-kontakty.jsonl (закупки)'},
                                           ensure_ascii=False) + '\n')
                        сч['номеров закупок'] += 1
    print(dict(сч))


if __name__ == '__main__':
    main(*sys.argv[1:3])
