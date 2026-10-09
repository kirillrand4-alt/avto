# -*- coding: utf-8 -*-
r"""Луна 6.0 против Луны 5.6 на разметке контактов (владелец 09.10: «посмотри луну 6.1 и 5.6 — может меньше тупить
будут»; 6.1 шлюз не отдаёт). Компании из обхода набора (последние записи), до 8 подписанных контактов на компанию:
один и тот же промпт разметки (kc_kontakty.ПРОМПТ_НОМЕРА, текст — фрагменты вокруг контактов) — обеим моделям.
Сравнение по контактам: класс, роль, ЛПР, ФИО. Где роль или ЛПР разошлись — судья Sol вслепую. Итог — время, сбои,
согласие, победы у судьи. Строки — в <набор>-luna-ab.jsonl (fsync).

    KC_NABOR=meyer7t python kc_luna_ab.py [компаний=25]
"""
import collections
import io
import json
import os
import random
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402
import verify_company as VC  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'meyer7t')
ВЫХОД = os.path.join(DIR, НАБОР + '-luna-ab.jsonl')
МОДЕЛИ = ('gpt-6-luna', 'gpt-5.6-luna')
СУДЬЯ = os.environ.get('KC_AB_SUDYA', 'gpt-6-sol')
_лок = threading.Lock()


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def вызов(промпт, модель):
    t = time.time()
    try:
        out = VC._provider_call_stdlib(промпт, model=модель) or ''
        arr = {int(x.get('n', 0)): x for x in json.loads(re.search(r'\[.*\]', out, re.S).group(0)) if isinstance(x, dict)}
        return arr, round(time.time() - t, 1), ''
    except Exception as e:  # noqa: BLE001
        return {}, round(time.time() - t, 1), repr(e)[:80]


СУД = ('Фрагмент страницы сайта компании «{имя}» вокруг контакта {контакт}:\n«{фрагмент}»\n\nДве разметки контакта:\n'
       'Вариант 1: роль «{р1}», ЛПР по оборудованию «{л1}», ФИО «{ф1}»\nВариант 2: роль «{р2}», ЛПР «{л2}», ФИО «{ф2}»\n'
       'Справочник ролей: {роли}. ЛПР «да» — руководитель, техдиректор/главный инженер, механик/энергетик, производство, '
       'технолог, качество, закупки; продажи, финансы, кадры, общий номер — «нет».\n'
       'Какой вариант точнее по фрагменту? Ответ — JSON: {{"лучше": "1"|"2"|"равны", "почему": "до 12 слов"}}')


def компания(з):
    конт = [н for н in з.get('номера') or [] if н.get('контекст') and (н.get('фио') or н.get('должность') or н.get('класс') not in ('', 'общий', None))][:8]
    if len(конт) < 2:
        return None
    текст = '\n…\n'.join(н['контекст'][-400:] for н in конт)
    промпт = KK.ПРОМПТ_НОМЕРА.format(домен=MN.домен(з.get('сайт') or ''), название=з.get('имя') or з['inn'], url=з.get('сайт') or '',
                                     текст=текст[:6500], номера='\n'.join('%d. %s' % (j + 1, н.get('номер') or н.get('почта'))
                                                                     for j, н in enumerate(конт)))
    рез = {м: вызов(промпт, м) for м in МОДЕЛИ}
    строки = []
    for j, н in enumerate(конт):
        a, b = рез[МОДЕЛИ[0]][0].get(j + 1) or {}, рез[МОДЕЛИ[1]][0].get(j + 1) or {}
        x = {'inn': з['inn'], 'контакт': н.get('номер') or н.get('почта'), 'фрагмент': н['контекст'][-500:],
             МОДЕЛИ[0]: {k: a.get(k) for k in ('класс', 'роль', 'лпр', 'фио')},
             МОДЕЛИ[1]: {k: b.get(k) for k in ('класс', 'роль', 'лпр', 'фио')}}
        x['совпало'] = (a.get('роль'), a.get('лпр')) == (b.get('роль'), b.get('лпр'))
        if a and b and not x['совпало']:
            порядок = list(МОДЕЛИ) if random.Random(x['контакт']).random() < 0.5 else list(reversed(МОДЕЛИ))
            v1, v2 = x[порядок[0]], x[порядок[1]]
            отв = KK.модель(СУД.format(имя=з.get('имя') or '', контакт=x['контакт'], фрагмент=x['фрагмент'], р1=v1.get('роль'),
                                       л1=v1.get('лпр'), ф1=v1.get('фио') or '', р2=v2.get('роль'), л2=v2.get('лпр'),
                                       ф2=v2.get('фио') or '', роли=', '.join(KK.РОЛИ)), False) or {}
            л = str(отв.get('лучше') or '')
            x['судья'] = 'равны' if л == 'равны' else (порядок[int(л) - 1] if л in ('1', '2') else '')
            x['почему'] = (отв.get('почему') or '')[:100]
        строки.append(x)
    итог = {'inn': з['inn'], 'вид': 'компания', 'время': {м: рез[м][1] for м in МОДЕЛИ}, 'сбой': {м: рез[м][2] for м in МОДЕЛИ},
            'контактов': len(конт), 'строки': строки}
    записать(итог)
    return итог


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    посл = {}
    for s in io.open(os.path.join(DIR, НАБОР + '-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('итог') == 'ok':
            посл[з['inn']] = з
    сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
    for i, з in посл.items():
        з['имя'] = (сп.get(i) or {}).get('имя') or ''
    кандидаты = [з for з in посл.values() if з['inn'] in сп]
    random.Random(910).shuffle(кандидаты)
    VC._PROVIDER_MODEL = СУДЬЯ  # KK.модель (судья) берёт модель по умолчанию
    with ThreadPoolExecutor(6) as ex:
        рез = [r for r in ex.map(компания, кандидаты[:n * 2]) if r][:n]
    вр = {м: [r['время'][м] for r in рез if not r['сбой'][м]] for м in МОДЕЛИ}
    стр = [x for r in рез for x in r['строки']]
    суд = collections.Counter(x.get('судья') for x in стр if 'судья' in x)
    o = {'компаний': len(рез), 'контактов': len(стр), 'совпало роль+ЛПР': sum(x['совпало'] for x in стр),
         'медиана с': {м: statistics.median(v) if v else None for м, v in вр.items()},
         'сбоев': {м: sum(1 for r in рез if r['сбой'][м]) for м in МОДЕЛИ},
         'судья: лучше': dict(суд),
         'ФИО найдено': {м: sum(1 for x in стр if (x[м].get('фио') or '').strip()) for м in МОДЕЛИ},
         'примеры расхождений': ['%s | 6.0: %s/%s | 5.6: %s/%s | судья: %s — %s' % (
             x['контакт'], x[МОДЕЛИ[0]].get('роль'), x[МОДЕЛИ[0]].get('лпр'), x[МОДЕЛИ[1]].get('роль'), x[МОДЕЛИ[1]].get('лпр'),
             x.get('судья'), x.get('почему')) for x in стр if 'судья' in x][:12]}
    print('===ИТОГ===')
    print(json.dumps(o, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
