# -*- coding: utf-8 -*-
r"""База КЦ: повторная проверка «чей сайт» для сайтов, не подтверждённых kc_audit (ни ИНН, ни ядра
названия). Причины ложных «нет»: вложенные кавычки в названии (ОАО "АПФ "ФАНАГОРИЯ"" -> ядро «апф»),
страница не открылась при проверке. Здесь: все открывшиеся страницы обхода (до 8) + /contacts,
/kontakty, /about, /o-kompanii, /rekvizity; отличительные слова названия (>= 5 букв, не общие слова
вроде «молочный», «завод») и ИНН. Подтверждение — ИНН или отличительное слово на сайте.
Выход: C:\sender\server\kc-audit2.jsonl -> копия на дроп.
"""
import io
import json
import os
import re
import shutil
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_nalichie as MN  # noqa: E402
import meyer_proverka as MP  # noqa: E402

ВЫХОД = os.path.join(DIR, 'kc-audit2.jsonl')
ОБЩИЕ = {'общество', 'ограниченной', 'ответственностью', 'акционерное', 'открытое', 'закрытое', 'публичное',
         'молочный', 'молочная', 'молочное', 'молочные', 'комбинат', 'завод', 'заводы', 'частная', 'пивоварня',
         'винодельня', 'винодельческое', 'предприятие', 'компания', 'группа', 'холдинг', 'производственная',
         'производственное', 'мясокомбинат', 'птицефабрика', 'агропромышленная', 'фирма', 'торговый', 'продукты',
         'классических', 'шампанских', 'игристых', 'имени', 'россия', 'русский', 'русская', 'продукт'}
ДОП = ('contacts', 'kontakty', 'contact', 'about', 'o-kompanii', 'rekvizity', 'company')


def слова(имя):
    т = re.sub(r'[«»"\'()]', ' ', имя or '').lower().replace('ё', 'е')
    return {w for w in re.findall(r'[а-яa-z][а-яa-z\-]{4,}', т) if w not in ОБЩИЕ}


def одна(i, к, з):
    страницы = [u for u, ст in з.get('страницы', []) if ст == 'ok'][:8]
    корень = 'https://' + MN.домен(з['сайт'])
    for п in ДОП:
        страницы.append(urllib.parse.urljoin(корень + '/', п))
    текст = ''
    for u in страницы:
        ст, html, _ = MN.скачать(u)
        if ст == 'ok':
            текст += ' ' + MP.в_текст(html).lower().replace('ё', 'е')
    сл = слова(к['имя'])
    найдено = sorted(w for w in сл if w in текст)
    if i in текст:
        вердикт = 'свой: ИНН компании на сайте'
    elif найдено:
        вердикт = 'по названию: %s' % ', '.join(найдено[:3])
    elif not текст:
        вердикт = 'не подтверждён: сайт не открылся'
    else:
        вердикт = 'не подтверждён: ни ИНН, ни названия (%s) на сайте' % ', '.join(sorted(сл)[:3])
    return {'inn': i, 'сайт': з['сайт'], 'сайт_чей': вердикт, 'слова': sorted(сл), 'символов': len(текст)}


def main():
    сп = json.load(io.open(os.path.join(DIR, 'kc-spisok.json'), encoding='utf-8'))['компании']
    конт = {}
    for s in io.open(os.path.join(DIR, 'kc-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        з = json.loads(s)
        if з.get('итог') == 'ok':
            конт[з['inn']] = з
    задачи = []
    for s in io.open(os.path.join(DIR, 'kc-audit.jsonl'), encoding='utf-8'):
        a = json.loads(s)
        if a['сайт_чей'].startswith('не подтверждён'):
            задачи.append((a['inn'], сп[a['inn']], конт[a['inn']]))
    with ThreadPoolExecutor(8) as ex:
        рез = list(ex.map(lambda x: одна(*x), задачи))
    with io.open(ВЫХОД, 'w', encoding='utf-8') as f:
        for r in рез:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(ВЫХОД, r'C:\seostat\drop\drop-storage\kc-audit2.jsonl')
    print('===ИТОГ===')
    print('\n'.join('%s | %s | %s' % (r['inn'], r['сайт'][:40], r['сайт_чей'][:80]) for r in рез))


if __name__ == '__main__':
    main()
