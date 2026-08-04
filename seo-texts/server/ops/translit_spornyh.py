# -*- coding: utf-8 -*-
"""Сколько «спорных» привязок 3-й сессии на деле верны: фамилия в адресе латиницей.

Её проверка ищет фамилию нашего человека в адресе и, не найдя, метит строку
спорной. Но `pakhomova_ev@interrao.ru` — это Пахомова, просто транслитом. Если
таких много, заслон метит спорными часть ВЕРНЫХ привязок, и это стоит сказать
числом, а не впечатлением.
"""
import csv, io, os, re
from collections import Counter
ОБМЕН = r'C:\seostat\drop\drop-storage'
ФАЙЛ = 'P25-OBRATNYY-3S-spornaya-privyazka-009.csv'
ТАБЛ = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
        'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
        'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
        'щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
def транслит(с):
    return ''.join(ТАБЛ.get(б, б) for б in с.lower())
def варианты(ф):
    т = транслит(ф)
    из = {т}
    из.add(т.replace('kh','h')); из.add(т.replace('y','i'))
    из.add(т.replace('ya','ia').replace('yu','iu'))
    из.add(т.replace('ts','c')); из.add(т.replace('zh','j'))
    return {в for в in из if len(в) >= 4}
строки = list(csv.DictReader(
    io.open(os.path.join(ОБМЕН, ФАЙЛ), encoding='utf-8-sig'), delimiter=';'))
стат = Counter(); примеры = []
for р in строки:
    чел = ' '.join(str(р.get('chelovek') or '').split())
    адрес = str(р.get('pochta') or '').strip().lower()
    if not чел or not адрес:
        continue
    фамилия = чел.split()[0]
    локальная = адрес.split('@')[0]
    попал = any(в in локальная for в in варианты(фамилия))
    стат['ФАМИЛИЯ В АДРЕСЕ ЕСТЬ (транслитом) — помечено спорным зря' if попал
         else 'фамилии в адресе нет — спорная по делу'] += 1
    if попал and len(примеры) < 8:
        примеры.append(f'{фамилия:22} ← {адрес}')
print('ПОМЕЧЕНЫ СПОРНЫМИ, НО ФАМИЛИЯ В АДРЕСЕ ЕСТЬ:')
for п in примеры or ['   ни одной']:
    print('   ', п)
print()
for к, v in sorted(стат.items()):
    print(f'{к:60} {v:5}')
print(f'{"строк в файле спорных":60} {len(строки):5}')
