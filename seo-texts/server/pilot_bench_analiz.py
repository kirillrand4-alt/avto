# -*- coding: utf-8 -*-
"""Разбор сравнения моделей (pilot_bench_modeli.py): ответы -> решения по элементам, согласие с эталоном, цена.

Эталон по элементу — большинство сильных моделей (claude-opus-5-5, claude-fable-5, claude-sonnet-4-6, gpt-6-sol);
при равенстве — opus. Для двух лучших недорогих моделей все ответы проверяются вручную (владелец 09.10) —
выгрузка `bench-ruchnaya-<модель>.jsonl` (вход-фрагмент + решение модели + эталон) для ручной разметки.

    python3 pilot_bench_analiz.py <папка с pilot-bench-nabor.json и pilot-bench-otvety.jsonl> [out.json]
"""
import collections
import json
import os
import re
import sys

# цена «с учётом типа баланса и источника», $ за 1M токенов (вход, выход) — скриншот прайса router.cheap 09.10
ЦЕНЫ = {'claude-fable-5': (10, 50), 'claude-opus-5-5': (4, 20), 'claude-sonnet-4-6': (3, 15), 'claude-sonnet-5-5': (2, 10),
        'claude-haiku-4-5': (1, 5), 'gpt-6-sol': (1.11, 5.56), 'gpt-6-luna': (0.06, 0.28), 'gpt-5.6-luna': (0.11, 0.67),
        'deepseek-v4-flash': (0.42, 1.67), 'deepseek-v4-pro': (1.83, 5.5), 'gemini-3.8-flash': (2.6, 13.02),
        'glm-5.3-flash': (0.52, 1.74), 'qwen3.8-flash': (0.21, 0.65), 'grok-4.7': (0.93, 2.78), 'minimax-m3': (0.42, 1.67),
        'mimo-v2.5-pro': (0.6, 1.21), 'kimi-k3': (1.04, 5.21)}
СИЛЬНЫЕ = ['claude-opus-5-5', 'claude-fable-5', 'claude-sonnet-4-6', 'gpt-6-sol']


def json_из(текст, массив):
    try:
        м = re.search(r'\[.*\]' if массив else r'\{.*\}', текст or '', re.S)
        return json.loads(м.group(0)) if м else None
    except ValueError:
        return None


def решения(тип, ответ):
    """-> {элемент: решение} или None (не разобран)."""
    if тип in ('T1', 'T2', 'T4'):
        д = json_из(ответ, True)
        if not isinstance(д, list):
            return None
        out = {}
        for x in д:
            if not isinstance(x, dict):
                continue
            n = str(x.get('n', ''))
            if тип == 'T1':
                out[n + ':роль'] = (x.get('роль') or '').strip()
                out[n + ':лпр'] = (x.get('лпр') or '').strip()
                out[n + ':фио?'] = 'есть' if (x.get('фио') or '').strip() else 'нет'
                out[n + ':чей'] = (x.get('чей') or '').strip()
            elif тип == 'T2':
                out[n] = (x.get('чей') or '').strip()
            else:
                out[n] = (x.get('решение') or '').strip()
        return out
    д = json_из(ответ, False)
    if not isinstance(д, dict):
        return None
    return {'вердикт': (д.get('вердикт') or '').strip()}


def main(п, out=None):
    набор = {з['id']: з for з in json.load(open(os.path.join(п, 'pilot-bench-nabor.json'), encoding='utf-8'))}
    отв = collections.defaultdict(dict)
    стат = collections.defaultdict(lambda: {'вызовов': 0, 'ошибок': 0, 'не_разобран': 0, 'вх': 0, 'вых': 0, 'сек': 0.0})
    for s in open(os.path.join(п, 'pilot-bench-otvety.jsonl'), encoding='utf-8'):
        з = json.loads(s)
        м, i = з['модель'], з['id']
        с = стат[м]
        if з.get('ошибка'):
            if i not in отв[м]:
                с['ошибок'] += 1
            continue
        с['вызовов'] += 1
        с['вх'] += з.get('вх') or 0
        с['вых'] += з.get('вых') or 0
        с['сек'] += з.get('сек') or 0
        р = решения(з['тип'], з['ответ'])
        if р is None:
            с['не_разобран'] += 1
        отв[м][i] = {'тип': з['тип'], 'р': р or {}, 'ответ': з['ответ']}
    # эталон по элементу
    эталон = {}
    for i, з in набор.items():
        элементы = set()
        for м in СИЛЬНЫЕ:
            элементы |= set((отв[м].get(i) or {}).get('р', {}))
        for э in элементы:
            голоса = collections.Counter((отв[м].get(i) or {}).get('р', {}).get(э) for м in СИЛЬНЫЕ if (отв[м].get(i) or {}).get('р'))
            голоса.pop(None, None)
            голоса.pop('', None)
            if not голоса:
                continue
            лучшие = голоса.most_common()
            if len(лучшие) > 1 and лучшие[0][1] == лучшие[1][1]:
                в = (отв['claude-opus-5-5'].get(i) or {}).get('р', {}).get(э) or лучшие[0][0]
            else:
                в = лучшие[0][0]
            эталон[(i, э)] = (в, лучшие[0][1], sum(голоса.values()))
    итог = []
    for м in ЦЕНЫ:
        if м not in стат:
            continue
        по_типу = collections.defaultdict(lambda: [0, 0])
        for (i, э), (в, _, _) in эталон.items():
            т = набор[i]['тип']
            кл = т + (':' + э.split(':')[1] if т == 'T1' else '')
            р = (отв[м].get(i) or {}).get('р')
            по_типу[кл][1] += 1
            if р and р.get(э) == в:
                по_типу[кл][0] += 1
        с = стат[м]
        цв, цо = ЦЕНЫ[м]
        цена = (с['вх'] * цв + с['вых'] * цо) / 1e6
        итог.append({'модель': м, 'вызовов': с['вызовов'], 'ошибок': с['ошибок'], 'не разобран': с['не_разобран'],
                     'цена набора, $': round(цена, 3), '$ на вызов': round(цена / max(1, с['вызовов']), 5),
                     'вх ток/вызов': round(с['вх'] / max(1, с['вызовов'])), 'вых ток/вызов': round(с['вых'] / max(1, с['вызовов'])),
                     'сек/вызов': round(с['сек'] / max(1, с['вызовов']), 1),
                     'совпадение с эталоном': {к: '%d%% (%d/%d)' % (100 * a // max(1, b), a, b) for к, (a, b) in sorted(по_типу.items())},
                     'совпадение, всего %': round(100 * sum(a for a, b in по_типу.values()) / max(1, sum(b for a, b in по_типу.values())), 1)})
    итог.sort(key=lambda x: -x['совпадение, всего %'])
    рез = {'модели': итог, 'элементов эталона': len(эталон)}
    # выгрузка для ручной проверки
    for м in sys.argv[3:]:
        with open(os.path.join(п, 'bench-ruchnaya-%s.jsonl' % м), 'w', encoding='utf-8') as f:
            for i, з in набор.items():
                о = отв[м].get(i) or {}
                f.write(json.dumps({'id': i, 'тип': з['тип'], 'вход': з['вход'][-7000:], 'ответ модели': о.get('ответ', ''),
                                    'решения модели': о.get('р', {}),
                                    'эталон': {э: эталон[(i, э)][0] for (ii, э) in эталон if ii == i}}, ensure_ascii=False) + '\n')
    txt = json.dumps(рез, ensure_ascii=False, indent=1)
    if out:
        open(out, 'w', encoding='utf-8').write(txt)
    print(txt)


if __name__ == '__main__':
    main(*sys.argv[1:3])
