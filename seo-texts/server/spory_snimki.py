# -*- coding: utf-8 -*-
r"""Задание Зенке на снимки спорных мест и сбор готового.

Пара к кубику zenno/snimki_sporov.cs. Живой сайт снимает Зенка — браузер стоит
на сервере, и прокси у него те же, что у обхода; из песочницы Claude браузер
наружу не ходит вовсе (прокси рвёт CONNECT).

    python spory_snimki.py --zadanie [файл-споров.json] [сколько]
    python spory_snimki.py --stat
    python spory_snimki.py --sobrat            # снимки -> zip на дроп
"""
import json
import os
import re
import sys
import urllib.request
import zipfile

ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
ZADANIE = os.path.join(ZENNO, 'snimki_zadanie.txt')
SNIMKI = os.path.join(ZENNO, 'snimki')
ITOG = os.path.join(ZENNO, 'snimki_itog.txt')
DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')


def _stranicy_dlya(s):
    """Несколько адресов на попытку, через «|»: та страница, с которой адрес был
    снят, затем корень сайта и типовые контактные пути. Первый прогон дал 64
    задачи из 244 с ответом «адреса на странице нет» — сайт переверстали, и одной
    ссылки оказалось мало."""
    osnovnaya = (s.get('stranica') or s.get('url') or '').strip()
    if not osnovnaya.startswith('http'):
        return ''
    koren = re.match(r'^(https?://[^/]+)', osnovnaya)
    spisok = [osnovnaya]
    if koren:
        for hvost in ('/', '/contacts/', '/kontakty/', '/about/', '/o-kompanii/'):
            u = koren.group(1) + hvost
            if u not in spisok:
                spisok.append(u)
    return '|'.join(spisok[:5])


def _id(s, i):
    """Имя снимка = порядковый номер + ИНН: по нему отчёт находит картинку, а
    человек — компанию, не открывая json."""
    return '%04d-%s' % (i, str(s.get('inn') or 'bez-inn'))


def zadanie(put_sporov, skolko=250):
    spory = json.load(open(put_sporov, encoding='utf-8'))
    stroki, nomera = [], {}
    for i, s in enumerate(spory):
        url = (s.get('stranica') or s.get('url') or '').strip()
        adres = (s.get('email') or '').strip()
        if not (url.startswith('http') and adres):
            continue
        ident = _id(s, i)
        nomera[ident] = {'email': adres, 'inn': s.get('inn'), 'url': url}
        stroki.append('%s;%s;%s' % (ident, _stranicy_dlya(s) or url, adres))
        if len(stroki) >= skolko:
            break
    os.makedirs(ZENNO, exist_ok=True)
    with open(ZADANIE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(stroki) + '\n')
        f.flush()
        os.fsync(f.fileno())
    with open(os.path.join(ZENNO, 'snimki_karta.json'), 'w', encoding='utf-8') as f:
        json.dump(nomera, f, ensure_ascii=False)
    return {'в_задании': len(stroki), 'без_ссылки': len(spory) - len(stroki),
            'файл': ZADANIE}


def perespros(put_sporov, porog_kb=12):
    """Переснять то, что не вышло: снимка нет или он подозрительно лёгкий.

    Порог по весу — грубая мерка, и она уже подводила: белый лист на 4030 байт
    прошёл как годный. Но для ОТБОРА кандидатов её хватает — решает всё равно
    кубик, он теперь смотрит пиксели и белый кадр не сохраняет.
    """
    spory = json.load(open(put_sporov, encoding='utf-8'))
    est = {}
    if os.path.isdir(SNIMKI):
        for f in os.listdir(SNIMKI):
            if f.endswith('.png'):
                est[f[:-4]] = os.path.getsize(os.path.join(SNIMKI, f))
    # Кого переснимать НЕЗАВИСИМО от веса файла: те, где адрес не нашёлся. До
    # 14.08 поиск шёл XPath-ом и был слеп — адрес лежал в разметке во всех 18
    # проверенных случаях. Такие снимки сделаны «вслепую», по телу страницы.
    slepye = set()
    if os.path.exists(ITOG):
        for s in open(ITOG, encoding='utf-8', errors='replace'):
            ch = s.strip().split(';', 1)
            if len(ch) == 2 and ('адреса на странице нет' in ch[1]
                                 or ch[1].startswith('пустая страница')):
                slepye.add(ch[0])
            elif len(ch) == 2 and ch[1].strip() == 'ok':
                slepye.discard(ch[0])
    stroki, propushcheno = [], 0
    for i, s in enumerate(spory):
        url = (s.get('stranica') or s.get('url') or '').strip()
        adres = (s.get('email') or '').strip()
        if not (url.startswith('http') and adres):
            continue
        ident = _id(s, i)
        if est.get(ident, 0) >= porog_kb * 1024 and ident not in slepye:
            propushcheno += 1
            continue
        stroki.append('%s;%s;%s' % (ident, _stranicy_dlya(s) or url, adres))
    with open(ZADANIE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(stroki) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return {'в_задании': len(stroki), 'уже_годных': propushcheno, 'файл': ZADANIE}


def stat():
    zadano = sum(1 for _ in open(ZADANIE, encoding='utf-8', errors='replace')) \
        if os.path.exists(ZADANIE) else 0
    png = [f for f in os.listdir(SNIMKI) if f.endswith('.png')] if os.path.isdir(SNIMKI) else []
    prichiny = {}
    if os.path.exists(ITOG):
        for s in open(ITOG, encoding='utf-8', errors='replace'):
            ch = s.strip().split(';', 1)
            if len(ch) == 2:
                k = ch[1][:40]
                prichiny[k] = prichiny.get(k, 0) + 1
    return {'осталось_в_задании': zadano, 'снимков': len(png),
            'итоги': sorted(prichiny.items(), key=lambda x: -x[1])[:6],
            'мб': round(sum(os.path.getsize(os.path.join(SNIMKI, f)) for f in png) / 1048576, 1)}


def sobrat(imya='SPORY-SNIMKI.zip', predel_mb=40):
    if not os.path.isdir(SNIMKI):
        return {'снимков нет': SNIMKI}
    put = os.path.join(ZENNO, imya)
    n, bajt = 0, 0
    with zipfile.ZipFile(put, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(SNIMKI)):
            if not f.endswith('.png'):
                continue
            p = os.path.join(SNIMKI, f)
            if bajt + os.path.getsize(p) > predel_mb * 1048576:
                break
            z.write(p, f)
            bajt += os.path.getsize(p)
            n += 1
    with open(put, 'rb') as f:
        blob = f.read()
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    op.open(urllib.request.Request(DROP + '/' + imya, data=blob, method='PUT',
                                   headers={'X-Drop-Token': TOKEN}), timeout=300)
    return {'в_архиве': n, 'мб': round(len(blob) / 1048576, 1), 'файл': imya}


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == '--zadanie':
        put = a[1] if len(a) > 1 else r'C:\sender\_tmp\SPORY-SUDI-KUSKI.json'
        print(json.dumps(zadanie(put, int(a[2]) if len(a) > 2 else 250), ensure_ascii=False))
    elif a[0] == '--perespros':
        put = a[1] if len(a) > 1 else r'C:\sender\_tmp\SPORY-SUDI-KUSKI.json'
        print(json.dumps(perespros(put), ensure_ascii=False))
    elif a[0] == '--stat':
        print(json.dumps(stat(), ensure_ascii=False))
    elif a[0] == '--sobrat':
        print(json.dumps(sobrat(predel_mb=int(a[1]) if len(a) > 1 else 40),
                         ensure_ascii=False))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
