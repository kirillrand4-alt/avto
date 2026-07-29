# -*- coding: utf-8 -*-
"""СВОД по обоим замерам: охват, находки, доля технических ЛПР, примеры."""
import io
import json
import os

ПАТ = r'C:\sender\_ops\pat_patents.jsonl'
ДОБ = r'C:\sender\_ops\pat_dobor.jsonl'
РАС = r'C:\sender\_ops\pat_disclosure.jsonl'


def читать(п):
    из = []
    if not os.path.exists(п):
        return из
    for ln in io.open(п, encoding='utf-8', errors='replace'):
        try:
            из.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            pass
    return из


пат = {str(x['inn']): x for x in читать(ПАТ)}
for x in читать(ДОБ):                      # добор дополняет основной проход
    i = str(x['inn'])
    if x.get('свои_патенты'):
        y = пат.get(i) or x
        было = {a.lower().replace('.', '').replace(' ', '')
                for a in (y.get('авторы') or [])}
        y['свои_патенты'] = list(dict.fromkeys((y.get('свои_патенты') or [])
                                               + x['свои_патенты']))
        for a in x.get('авторы') or []:
            if a.lower().replace('.', '').replace(' ', '') not in было:
                y.setdefault('авторы', []).append(a)
        y['примеры'] = (y.get('примеры') or []) + (x.get('примеры') or [])
        y['добор'] = True
        пат[i] = y

print('=' * 30, 'ИСТОЧНИК 1: ПАТЕНТЫ')
скомп = сумавт = 0
for i, x in пат.items():
    n = len(x.get('свои_патенты') or [])
    a = len(x.get('авторы') or [])
    скомп += 1 if n else 0
    сумавт += a
    print('  %-38s патентов=%-2d авторов=%-3d отсеяно_чужих=%-2d %s'
          % (x['имя'][:38], n, a, x.get('чужих_отсеяно', 0),
             'ДОБОР' if x.get('добор') else ''))
print('  ИТОГ: компаний %d, с патентами %d, авторов всего %d'
      % (len(пат), скомп, сумавт))
print('  ПРИМЕРЫ:')
к = 0
for i, x in пат.items():
    for p in (x.get('примеры') or [])[:2]:
        if к >= 8:
            break
        print('    %s | %s | %s | %s' % (p['фио'], x['имя'][:28],
                                         p['обладатель'][:60], p['ссылка']))
        к += 1

print('=' * 30, 'ИСТОЧНИК 2: РАСКРЫТИЕ АО')
рас = читать(РАС)
скр = сумлюд = сумтех = сумадм = 0
for x in рас:
    л = x.get('людей', 0) or 0
    скр += 1 if л else 0
    сумлюд += л
    сумтех += x.get('техЛПР', 0) or 0
    сумадм += x.get('админ', 0) or 0
    print('  %-40s док=%-2d прочит=%-2d людей=%-3d тех=%-2d адм=%-2d %s'
          % (x['имя'][:40], x.get('док_ссылок', 0), x.get('прочитано', 0), л,
             x.get('техЛПР', 0) or 0, x.get('админ', 0) or 0,
             (x.get('ошибка') or x.get('ошибка_провайдера')
              or x.get('почему_пусто') or '')[:40]))
print('  ИТОГ: компаний %d, с раскрытием %d, людей %d, техЛПР %d, админ %d'
      % (len(рас), скр, сумлюд, сумтех, сумадм))
print('  ТЕХНИЧЕСКИЕ ПРИМЕРЫ:')
к = 0
for x in рас:
    for ч in (x.get('люди') or []):
        if ч.get('тех') and к < 10:
            print('    %s | %s | %s | %s' % (ч['фио'], ч['должность'][:45],
                                             x['имя'][:26], ч.get('ссылка', '')[:70]))
            к += 1
print('  ПРОЧИЕ ПРИМЕРЫ (для сверки состава):')
к = 0
for x in рас:
    for ч in (x.get('люди') or []):
        if not ч.get('тех') and к < 6:
            print('    %s | %s | %s' % (ч['фио'], ч['должность'][:45], x['имя'][:26]))
            к += 1
print('СВОД: патенты %d/%d компаний %d авторов | раскрытие %d/%d компаний '
      '%d людей %d тех %d адм'
      % (скомп, len(пат), сумавт, скр, len(рас), сумлюд, сумтех, сумадм))
