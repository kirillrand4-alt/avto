# -*- coding: utf-8 -*-
"""Видит ли панель пометки привязки. Вопрос не про базу, а про то, что доходит до глаз.

Перепроверка записала в базу три вещи: снятое сомнение у 43 человек, найденного чужого
работодателя у 39 и итог проверки у всех 543. Всё это ценно ровно настолько, насколько
доходит до того, кто звонит. Если панель про колонки не знает, чистка сделана в стол.

ПЕРВЫЙ ЗАХОД ЭТОГО ПРИБОРА СОВРАЛ, и соврал ровно тем способом, который я весь день ловлю
в чужих данных. Он искал упоминания колонок во всех файлах сервера и нашёл их — в трёх,
двух и двух файлах. Итоговая строка объявила «колонок, которых панель не знает: 0». Но
все найденные файлы назывались `3s_*` — это МОИ ЖЕ скрипты, которые раннер туда и положил.
Прибор нашёл собственное эхо и принял его за чужое знание.

Поэтому теперь: свои файлы (`3s_*` и всё в `_ops`) из счёта исключены явно, а рядом с
колонками ищется то, чем панель ЖИВЁТ — как она отбирает людей и чем скрывает. Пометка,
которой панель не знает, не чистит витрину; чистит её тот же рычаг, которым панель
скрывает уже сейчас.
"""
import collections
import io
import json
import os
import re

KORNI = (r'C:\sender', r'C:\seostat')
ISKAT = ('privyazka_somnitelna', 'privyazka_proverena', 'vid_nomera_po_lyudyam')
# Чем панель живёт: отбор людей и рычаг скрытия.
RYCHAGI = ('skryt', 'hidden', 'is_hidden', 'скрыт', 'hide', 'visible', 'pokazyvat')
RASSHIRENIYA = ('.py', '.js', '.html', '.htm', '.jsx', '.ts', '.tsx', '.sql', '.json')
PROPUSK = re.compile(r'[\\/](?:node_modules|\.git|__pycache__|venv|env|dist|build)[\\/]', re.I)
# МОЁ СОБСТВЕННОЕ ЭХО: раннер кладёт мои скрипты на сервер, и они не есть панель.
MOYO = re.compile(r'[\\/](?:_ops)[\\/]|[\\/]3s_|[\\/]2s_|[\\/]1s_', re.I)


def prochest(p):
    try:
        if os.path.getsize(p) > 4 * 1024 * 1024:
            return ''
        return io.open(p, encoding='utf-8', errors='replace').read()
    except Exception:  # noqa: BLE001
        return ''


sch = collections.Counter()
nashli = collections.defaultdict(list)
rychagi_gde = collections.defaultdict(list)
prosmotreno = 0
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if PROPUSK.search(put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith(RASSHIRENIYA):
                continue
            p = os.path.join(put, f)
            svoy = bool(MOYO.search(p))
            t = prochest(p)
            if not t:
                continue
            prosmotreno += 1
            if svoy:
                sch['мои же файлы на сервере (в счёт не идут)'] += 1
            for slovo in ISKAT:
                if slovo in t and not svoy:
                    n = t[:t.index(slovo)].count('\n') + 1
                    nashli[slovo].append((p[-70:], n, t.split('\n')[n - 1].strip()[:110]))
            # Рычаг скрытия ищем только там, где рядом есть таблица людей.
            if not svoy and re.search(r'\bperson\b|\bcontact\b', t):
                for r in RYCHAGI:
                    for m in re.finditer(re.escape(r), t, re.I):
                        n = t[:m.start()].count('\n') + 1
                        stroka = t.split('\n')[n - 1].strip()[:110]
                        if len(rychagi_gde[p[-60:]]) < 4:
                            rychagi_gde[p[-60:]].append((n, stroka))
                        break

ne_znaet = [s for s in ISKAT if not nashli.get(s)]
for slovo in ISKAT:
    sp = nashli.get(slovo) or []
    print('\n=== %s — в файлах панели: %d' % (slovo, len(sp)))
    for p, n, s in sp[:6]:
        print('    %s:%d  %s' % (p, n, s))
    if not sp:
        print('    НЕ УПОМИНАЕТСЯ — панель этого не показывает')

print('\n=== чем панель скрывает людей (файлы, где есть person/contact)')
for p, sp in list(rychagi_gde.items())[:12]:
    print('  %s' % p)
    for n, s in sp:
        print('      :%-5d %s' % (n, s))

for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('REC колонок, которых панель не знает\t%d' % len(ne_znaet))
print('ИТОГ ' + json.dumps({
    'файлов просмотрено': prosmotreno,
    'колонок, которых панель не знает': len(ne_znaet),
    'какие': ne_znaet}, ensure_ascii=False))
