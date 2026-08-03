# -*- coding: utf-8 -*-
"""Кто покупает компрессоры на Тендер.Про, но в нашу базу не попал.

ОТКУДА ВОПРОС. Из 2 387 человек в сборе 3-й сессии 1 290 строк относятся к
компаниям, которых в панели нет вовсе. Это не мусор: площадка отбирала карточки
по компрессорной тематике, значит перед нами предприятия, которые ЗАКУПАЮТ
компрессорное оборудование и при этом мимо нашей базы центробежников прошли.

ЧТО ЗДЕСЬ РЕШАЕТСЯ, А ЧТО НЕТ. Здесь не решается, наши они или нет — для этого
есть суд моделей. Здесь готовится список с доказательством: что за компания,
что именно закупала, сколько раз, есть ли у неё живые контакты, и похож ли
предмет закупки на воздушную центробежную машину. Решение принимает владелец,
а не регулярка.

РАЗДЕЛЕНИЕ ПО ПРЕДМЕТУ, ЧЕСТНОЕ. Предмет закупки делится на три корзины:
  * `похоже на нашу` — назван центробежный, турбокомпрессор, воздуходувка ТВ,
    семейство К-250/ЦК/ВЦ;
  * `компрессор, принцип не назван` — просто «компрессор»: может оказаться и
    поршневым, и винтовым, и нашим;
  * `не наше` — насос, кондиционер, ЗИП, услуги ремонта.
Молчаливо схлопывать вторую корзину в первую нельзя: именно так в панель
попадают поршневые машины, и именно это пришлось вычищать из реестра ЭПБ.

Ничего не пишет в базы. Кладёт CSV на дроп.

Запуск: python tenderpro_vne_bazy.py
"""
import csv
import json
import os
import re
import sqlite3
import sys
import urllib.request
from collections import defaultdict

БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ДРОП = r'C:\seostat\drop\drop-storage'
ФАЙЛ = 'VAZHNOE-3s-TENDERPRO-lica.csv'
ИМЯ = 'TENDERPRO-kompanii-vne-bazy.csv'

_ОПФ = re.compile(
    r'\b(ооо|оао|зао|ао|пао|муп|гуп|фгуп|нао|ано|фгбу|фку|гк)\b|'
    r'общество\s+с\s+ограниченной\s+ответственностью|'
    r'акционерное\s+общество|публичное|непубличное', re.I)

# Наша машина названа прямо.
_НАША = re.compile(
    r'центробежн|турбокомпрессор|турбовоздуходувк|нагнетател|'
    r'\bцк[\s-]?\d|\bк-?\d{3}-\d{2}|\b\d{2}вц[\s-]?\d|\bтв-?\d{2}|'
    r'centac|turbo\s?max|turbowin|hibon|neuros|aerzen\s?tb', re.I)
# Явно не наше: другой принцип или вовсе не машина.
_ЧУЖОЕ = re.compile(
    r'насос|кондиционер|сплит|холодильн|вентилятор|дымосос|котёл|котел|'
    r'поршнев|винтов|\bвк-?\d|\bпкс\b|\bзиф\b|ремонт\s+|техническ\w+\s+'
    r'обслуживани|запасн\w+\s+част|\bзип\b|фильтр|масло|прокладк', re.I)
_КОМПРЕССОР = re.compile(r'компрессор|воздуходувк|воздушн\w+\s+станц', re.I)


def норм(т):
    т = re.sub(r'["«»\']', '', str(т or '').lower())
    т = _ОПФ.sub(' ', т)
    return re.sub(r'\s+', ' ', т).strip()


def корзина(текст):
    т = str(текст or '')
    if _НАША.search(т):
        return 'похоже на нашу'
    if _ЧУЖОЕ.search(т) and not _КОМПРЕССОР.search(т):
        return 'не наше'
    if _КОМПРЕССОР.search(т):
        return 'компрессор, принцип не назван'
    return 'предмет не про машины'


def main():
    csv.field_size_limit(10 ** 7)
    путь = os.path.join(ДРОП, ФАЙЛ)
    if not os.path.exists(путь):
        raise SystemExit(f'нет {ФАЙЛ} на дропе сервера')

    цб = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    в_базе = set()
    # ПОХОЖИЕ ИМЕНА — ОТДЕЛЬНО. Сверка идёт по точному совпадению после
    # нормализации, и первый же прогон поставил на первое место «Химпром
    # (Новочебоксарск)» как компанию вне базы: в панели он записан без города,
    # строки не совпали. Назвать его новым клиентом значит соврать владельцу.
    #
    # Но и склеивать по первому слову НЕЛЬЗЯ: Химпромов в стране несколько
    # (Новочебоксарск, Волгоград, Кемерово), и это разные юрлица. Поэтому не
    # решаем за владельца, а показываем кандидатов из базы рядом со строкой:
    # «возможно, это вот эти ИНН, проверьте».
    по_слову = defaultdict(list)
    for и, н, рег in цб.execute(
            "SELECT inn, predpriyatie, COALESCE(region,'') FROM company"):
        к = норм(н)
        if not к or len(к) < 5:
            continue
        в_базе.add(к)
        for сл in к.split():
            if len(сл) >= 5:
                по_слову[сл].append((и, н, рег))
    цб.close()

    комп = defaultdict(lambda: {
        'company_id': '', 'название': '', 'закупок': 0, 'людей': 0,
        'с_телефоном': 0, 'технических': 0, 'корзины': defaultdict(int),
        'предметы': [], 'люди': [], 'тендеры': set()})
    прочитано = 0
    строк_в_базе = 0
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            прочитано += 1
            имя = (r.get('company') or '').strip()
            к = норм(имя)
            if not к:
                continue
            if к in в_базе:
                строк_в_базе += 1
                continue
            з = комп[к]
            з['company_id'] = (r.get('company_id') or '').strip()
            з['название'] = з['название'] or имя
            пред = (r.get('predmet') or '').strip()
            тид = (r.get('tender_id') or '').strip()
            if тид not in з['тендеры']:
                з['тендеры'].add(тид)
                з['закупок'] += 1
                з['корзины'][корзина(пред)] += 1
                if пред and len(з['предметы']) < 4:
                    з['предметы'].append(пред[:150])
            чел = (r.get('imya') or '').strip()
            тел = (r.get('telefon') or '').strip()
            роль = (r.get('rol') or '').strip()
            if чел:
                з['людей'] += 1
                if тел:
                    з['с_телефоном'] += 1
                if роль.startswith('техн'):
                    з['технических'] += 1
                if len(з['люди']) < 3:
                    з['люди'].append(
                        f'{чел} ({(r.get("dolzhnost") or роль)[:30]}) '
                        f'{тел or (r.get("pochta") or "")}')

    ряды = []
    for _к, з in комп.items():
        похожие = []
        видел_и = set()
        for сл in _к.split():
            if len(сл) < 5:
                continue
            for и, н, рег in по_слову.get(сл, [])[:4]:
                if и in видел_и:
                    continue
                видел_и.add(и)
                похожие.append(f'{и} {н[:34]}{" / " + рег[:18] if рег else ""}')
            if len(похожие) >= 3:
                break
        главн = max(з['корзины'].items(), key=lambda x: x[1])[0] if з['корзины'] \
            else 'предмет не про машины'
        ряды.append({
            'company_id': з['company_id'],
            'kompaniya': з['название'],
            'zakupok': з['закупок'],
            'chto_zakupala': главн,
            'nashih_predmetov': з['корзины'].get('похоже на нашу', 0),
            'kompressor_bez_principa': з['корзины'].get(
                'компрессор, принцип не назван', 0),
            'lyudey': з['людей'],
            's_telefonom': з['с_телефоном'],
            'tehnicheskih': з['технических'],
            'primery_predmetov': ' | '.join(з['предметы']),
            'kontakty': ' | '.join(з['люди']),
            'vozmozhno_uzhe_v_baze': ' | '.join(похожие[:3]),
        })
    ряды.sort(key=lambda x: (-x['nashih_predmetov'], -x['zakupok']))

    итог = {
        'строк_прочитано': прочитано,
        'строк_по_компаниям_из_базы': строк_в_базе,
        'КОМПАНИЙ_ВНЕ_БАЗЫ': len(ряды),
        'из_них_с_нашим_предметом': sum(1 for р in ряды if р['nashih_predmetov']),
        'из_них_только_компрессор_без_принципа': sum(
            1 for р in ряды if not р['nashih_predmetov']
            and р['kompressor_bez_principa']),
        'ПОХОЖЕЕ_ИМЯ_УЖЕ_В_БАЗЕ_проверить': sum(
            1 for р in ряды if р['vozmozhno_uzhe_v_baze']),
        'точно_новых_имён': sum(
            1 for р in ряды if not р['vozmozhno_uzhe_v_baze']),
        'людей_у_них_всего': sum(р['lyudey'] for р in ряды),
        'из_них_с_телефоном': sum(р['s_telefonom'] for р in ряды),
    }
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    for р in ряды[:15]:
        print(f'  {р["kompaniya"][:40]:<40} закупок {р["zakupok"]:>3} '
              f'наших {р["nashih_predmetov"]:>2} людей {р["lyudey"]:>3} '
              f'с тел {р["s_telefonom"]:>3}  {р["primery_predmetov"][:70]}')

    if not ряды:
        return
    п = os.path.join(r'C:\sender\server', ИМЯ)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.DictWriter(ф, fieldnames=list(ряды[0].keys()), delimiter=';')
        в.writeheader()
        в.writerows(ряды)
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    urllib.request.urlopen(urllib.request.Request(
        урл.rstrip('/') + '/' + ИМЯ, data=open(п, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
        timeout=300).read()
    print(f'файл на дропе: {ИМЯ} ({len(ряды)} компаний)')


if __name__ == '__main__':
    main()
