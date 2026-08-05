# -*- coding: utf-8 -*-
"""Прицельный именной поиск по одному домену: Самсонов в ЭкоНиве.

Владелец дал контакт: Александр Самсонов, aleksandr.a.samsonov@ekoniva-apk.com, телефона
нет, общение только по почте. По базам его нет: ни почты, ни связки «Самсонов + ЭкоНива».
Обратный ход не берёт — он требует ПОЛНОЕ ФИО, а отчество и есть то, чего не хватает.

Зато домен известен, а это по замеру дешёвый случай: подтверждённый человек стоит ~21
запрос при известном домене против ~250 без него.

ЧТО СПРАШИВАЮ. Формы канала беру как есть (снимок выдачи следует за запросом, и форма
решает, что в снимке будет видно), но добавляю первой ФАМИЛИЮ — её мы знаем, и это самый
адресный запрос из возможных:

    site:ekoniva-apk.ru Самсонов          <- самый адресный, фамилия известна
    site:ekoniva-apk.com Самсонов
    "Самсонов" "ЭкоНива"                  <- без site:, вдруг он назван на стороннем ресурсе
    site:ekoniva-apk.ru "главный инженер"
    site:ekoniva-apk.ru руководство контакты

ЧТО ИЩУ В ОТВЕТАХ: отчество (третье слово рядом с «Самсонов Александр»), должность и
телефон. Печатаю ЦИТАТЫ, а не выводы: пусть видно, на чём основано.

ЗАСЛОН, КОТОРЫЙ ОБЯЗАН БЫТЬ. Документ с ЧУЖОГО домена при запросе `site:` значит, что
оператор не применён и выдаче верить нельзя — считаю такие отдельно и печатаю число.
Близость не доказывает принадлежность: «Самсонов» рядом со словом «ЭкоНива» на странице
агрегатора это ещё не наш человек.
"""
import collections
import importlib.util
import json
import os
import re
import sys

KANDIDATY_SERP = [r'C:\sender\_ops\3s_lpr_obratnyy.py',
                  r'C:\sender\server\lpr_obratnyy.py',
                  r'C:\sender\_ops\lpr_obratnyy.py']
DOMENY = ('ekoniva-apk.ru', 'ekoniva-apk.com')
FAMILIYA = 'Самсонов'
ZAPROSY = ['site:%s %s' % (DOMENY[0], FAMILIYA),
           'site:%s %s' % (DOMENY[1], FAMILIYA),
           '"%s" "ЭкоНива"' % FAMILIYA,
           'site:%s "главный инженер"' % DOMENY[0],
           'site:%s руководство контакты' % DOMENY[0]]

OTCHESTVO = re.compile(r'Самсонов\w*\s+Александр\w*\s+([А-ЯЁ][а-яё]+(?:ич|вич|евич|ович))')
FIO_LYUBOE = re.compile(r'Самсонов\w*\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?')
TELEFON = re.compile(r'(?:\+7|\b8)[\s\-(]{0,3}\d[\d\s\-()]{7,18}\d')
DOLZHNOST = re.compile(
    r'(?:главный|гл\.?)\s+(?:инженер|энергетик|механик|технолог)|технический директор|'
    r'директор[^,.;]{0,40}|начальник[^,.;]{0,40}|руководител[^,.;]{0,40}|'
    r'заместитель[^,.;]{0,40}', re.I)


def serp_fn():
    for put in KANDIDATY_SERP:
        if os.path.exists(put):
            spec = importlib.util.spec_from_file_location('lpr_obr', put)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            print('модуль поиска: %s' % put)
            return m.serp
    print('модуля поиска нет: %s' % (KANDIDATY_SERP,))
    return None


def host(u):
    return re.sub(r'^www\.', '', re.sub(r'^https?://', '', str(u or '')).split('/')[0].lower())


def main():
    serp = serp_fn()
    if not serp:
        print('ИТОГ ' + json.dumps({'поиск недоступен': True}, ensure_ascii=False))
        return
    sch = collections.Counter()
    nahodki = []
    for z in ZAPROSY:
        try:
            docs, err = serp(z)
        except Exception as e:  # noqa: BLE001
            print('\n### %s -> ОШИБКА %s' % (z, str(e)[:80]))
            sch['запрос упал'] += 1
            continue
        if err:
            print('\n### %s -> ошибка канала: %s' % (z, str(err)[:80]))
            sch['ошибка канала'] += 1
            continue
        docs = docs or []
        print('\n### %s -> документов %d' % (z, len(docs)))
        sch['запросов сделано'] += 1
        svoy = z.split('site:')[1].split()[0] if 'site:' in z else ''
        for d in docs[:10]:
            url = d.get('url') or ''
            tekst = d.get('tekst') or ''
            if svoy and host(url) and svoy not in host(url):
                sch['выдача вернула ЧУЖОЙ домен вопреки site:'] += 1
                continue
            est = FIO_LYUBOE.findall(tekst)
            otch = OTCHESTVO.findall(tekst)
            tel = [t for t in TELEFON.findall(tekst)]
            dol = DOLZHNOST.findall(tekst)
            if est or otch:
                sch['документов с фамилией'] += 1
                nahodki.append({'zapros': z, 'url': url, 'fio': est[:3],
                                'otchestvo': otch[:3], 'telefony': tel[:3],
                                'dolzhnosti': [x.strip()[:60] for x in dol[:3]],
                                'citata': re.sub(r'\s+', ' ', tekst)[:400]})
                print('  НАШЛОСЬ: %s' % url[:100])
                if otch:
                    print('     ОТЧЕСТВО: %s' % ', '.join(otch[:3]))
                if est:
                    print('     ФИО в тексте: %s' % '; '.join(est[:3]))
                if tel:
                    print('     телефоны рядом: %s' % ', '.join(tel[:3]))
                if dol:
                    print('     должности рядом: %s' % '; '.join(x.strip()[:40] for x in dol[:2]))
                print('     цитата: %s' % re.sub(r'\s+', ' ', tekst)[:260])
            else:
                sch['документ без фамилии'] += 1

    print()
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({
        'запросов': sch.get('запросов сделано', 0),
        'документов с фамилией': sch.get('документов с фамилией', 0),
        'отчество найдено': bool([n for n in nahodki if n['otchestvo']]),
        'находок': len(nahodki)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
