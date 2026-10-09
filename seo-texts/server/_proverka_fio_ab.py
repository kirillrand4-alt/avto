# -*- coding: utf-8 -*-
"""Верны ли ФИО и должности у номеров агентов (Luna vs Sol): страница-источник скачивается заново, рядом с номером
(±400 символов) ищутся фамилия из ФИО и слово должности. Только общие компании обеих моделей."""
import html
import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

D = r'C:\sender\server'
sys.path.insert(0, D)
sys.path.insert(0, r'C:\sender')
os.chdir(D)
import meyer_proverka as MP  # noqa: E402

ЛПР = {'директор', 'технический директор', 'главный инженер', 'главный механик', 'главный энергетик', 'инженер',
       'производство', 'закупки', 'главный технолог', 'технолог', 'качество'}
СЛОВА = {'директор': 'директор|руководител|генеральн', 'технический директор': 'техническ', 'главный инженер': 'инженер',
         'главный механик': 'механик', 'главный энергетик': 'энергетик', 'инженер': 'инженер',
         'производство': 'производств|цех', 'закупки': 'закуп|снабж|мто', 'главный технолог': 'технолог',
         'технолог': 'технолог', 'качество': 'качеств|лаборатор|отк'}


def читать(м):
    п = os.path.join(D, 'pilot-ab-%s.jsonl' % м)
    return {з['inn']: з for з in (json.loads(s) for s in io.open(п, encoding='utf-8')) if з.get('итог') == 'ok'}


_кэш = {}


def текст(u):
    if u not in _кэш:
        try:
            _кэш[u] = MP.скачать(u)
        except Exception:  # noqa: BLE001
            _кэш[u] = ''
    return _кэш[u]


def проверить(н):
    т = текст(н['url'])
    т = т[1] if isinstance(т, tuple) else т
    т = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', т or '', flags=re.S | re.I)
    т = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', т))).lower().replace('ё', 'е')
    if not т:
        return 'страница не скачалась'
    ц = н['номер'][-10:]
    м = None
    for x in re.finditer(r'[\d][\d\s\-\(\)]{8,20}\d', т):
        if re.sub(r'\D', '', x.group(0))[-10:] == ц:
            м = x
            break
    if not м:
        return 'номер не найден при повторном скачивании'
    окно = т[max(0, м.start() - 400):м.end() + 200]
    фам = [w for w in re.findall(r'[а-я]{3,}', (н.get('фио') or '').lower().replace('ё', 'е'))][:1]
    фио_ок = bool(фам) and фам[0][:-1] in окно
    дол_ок = bool(re.search(СЛОВА.get(н.get('класс'), '^$'), окно))
    return ('ФИО ' + ('верно' if фио_ок else 'НЕ рядом') if фам else 'без ФИО') + '; должность ' + ('верно' if дол_ок else 'НЕ рядом')


def main():
    л, с = читать('gpt-6-luna'), читать('gpt-6-sol')
    общие = sorted(set(л) & set(с))
    задачи = [(м, i, н) for м, зз in (('luna', л), ('sol', с)) for i in общие for н in зз[i].get('номера') or []
              if н.get('класс') in ЛПР]
    with ThreadPoolExecutor(12) as ex:
        вердикты = list(ex.map(lambda t: проверить(t[2]), задачи))
    итог = {}
    примеры = {'luna': [], 'sol': []}
    for (м, i, н), в in zip(задачи, вердикты):
        итог.setdefault(м, {}).setdefault(в, 0)
        итог[м][в] += 1
        примеры[м].append('%s | %s | %s | %s | %s' % ((л if м == 'luna' else с)[i]['имя'][:30], н['номер'], н.get('фио', ''),
                                                       н.get('должность', '')[:40], в))
    print('===ИТОГ===')
    print(json.dumps({'общих компаний': len(общие), 'номеров ЛПР': {м: sum(v.values()) for м, v in итог.items()},
                      'вердикты': итог, 'примеры': примеры}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
