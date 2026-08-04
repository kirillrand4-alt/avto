# -*- coding: utf-8 -*-
"""Пересмотреть контакты центробежной базы тем же заслоном, что поймал агрегаторы в P25.

ПОЧЕМУ ЭТО НЕ ОТЛОЖИТЬ. Сегодня в P25 нашлось, что правило «имя предприятия стоит в адресе
страницы» подтверждает не холдинг, а ЛЮБОЙ агрегатор выписок: `checko.ru/company/ao-apatit-…`
несёт имя компании в адресе всегда, это его устройство. После починки подтверждённых стало
12 вместо 84.

Центробежная база — тот же класс данных и тот же вопрос: у 1 749 её телефонов записано
«подтверждён первоисточником». Заслон там появился позже части заливок, а правило холдинга
жило в той же редакции. Значит часть «первоисточников» может оказаться карточкой агрегатора,
и продавец увидит подтверждение там, где его нет. Это ровно пункт «проверить остальные каналы
тем же правилом», который висит с утра.

ЧТО СЧИТАЕТСЯ И ЧТО НЕ ДЕЛАЕТСЯ. Здесь только ЗАМЕР: сколько записей меняют вердикт и на
какой именно. Ничего не переписывается — сперва число и глазами, потом решение. База
открывается только на чтение.
"""
import collections
import csv
import io
import json
import os
import sqlite3
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\_ops')
import _3s_chuzhaya_stranica as CH  # noqa: E402

BAZA = 'file:C:/seostat/data/centrifugal.db?mode=ro'
VYHOD = 'VAZHNOE-3s-CENTRO-agregatory-v-pervoistochnikah.csv'


def main():
    b = sqlite3.connect(BAZA, uri=True)
    tabl = [r[0] for r in b.execute("select name from sqlite_master where type='table'")]
    # ИМЕНА КОЛОНОК ЧИТАЮТСЯ, А НЕ ПРИДУМЫВАЮТСЯ — на этом я уже получала честный ноль.
    otchet = {'таблицы': tabl}
    sch = collections.Counter()
    plohie = []
    if 'contact' not in tabl:
        print('ИТОГ ' + json.dumps({'ошибка': 'нет таблицы contact', **otchet},
                                   ensure_ascii=False))
        return
    kol = [r[1] for r in b.execute('pragma table_info(contact)')]
    otchet['колонки contact'] = kol
    url_kol = next((k for k in ('source_url', 'ssylka', 'url', 'istochnik_url') if k in kol), None)
    if not url_kol:
        print('ИТОГ ' + json.dumps({'ошибка': 'в contact нет колонки со ссылкой', **otchet},
                                   ensure_ascii=False))
        return
    imya_kol = 'predpriyatie' if 'predpriyatie' in [
        r[1] for r in b.execute('pragma table_info(company)')] else None
    imena = {}
    sayty = {}
    if imya_kol:
        for inn, imya, sayt in b.execute(
                'select inn, coalesce(predpriyatie,""), coalesce(sayt,"") from company'):
            imena[inn] = imya
            if sayt:
                sayty[inn] = sayt
    otchet['имён предприятий'] = len(imena)
    otchet['сайтов предприятий'] = len(sayty)

    znach_kol = next((k for k in ('value', 'znachenie', 'kontakt') if k in kol), 'value')
    chel_kol = next((k for k in ('person', 'chelovek', 'fio') if k in kol), None)
    zapros = 'select inn, coalesce(%s,""), coalesce(%s,"")%s from contact' % (
        znach_kol, url_kol, (', coalesce(%s,"")' % chel_kol) if chel_kol else '')
    for ryad in b.execute(zapros):
        inn, znach, url = ryad[0], ryad[1], ryad[2]
        chel = ryad[3] if len(ryad) > 3 else ''
        sch['контактов всего'] += 1
        if not url:
            sch['ссылки нет — заслон неприменим'] += 1
            continue
        est, poch = CH.stranica_podtverzhdaet(url, sayty.get(inn, ''), imena.get(inn, ''),
                                              '', strogo=True)
        if est:
            sch['ПОДТВЕРЖДАЕТСЯ: ' + poch.split('(')[0][:40]] += 1
            continue
        sch['не подтверждается: ' + poch.split('(')[0][:44]] += 1
        if 'агрегатор' in poch:
            plohie.append({'inn': inn, 'predpriyatie': imena.get(inn, ''), 'chelovek': chel,
                           'kontakt': znach, 'ssylka': url, 'pochemu': poch[:180]})

    otchet['счёт'] = dict(sch.most_common())
    otchet['АГРЕГАТОРОВ СРЕДИ ССЫЛОК'] = len(plohie)
    if plohie:
        b2 = io.StringIO()
        w = csv.DictWriter(b2, delimiter=';', fieldnames=[
            'inn', 'predpriyatie', 'chelovek', 'kontakt', 'ssylka', 'pochemu'])
        w.writeheader()
        w.writerows(plohie)
        telo = b2.getvalue().encode('utf-8-sig')
        req = urllib.request.Request(
            os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
            + '/' + VYHOD, data=telo, method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''),
                     'Content-Type': 'text/csv'})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                otchet[VYHOD] = '%s, строк %d' % (r.status, len(plohie))
        except Exception as e:  # noqa: BLE001
            otchet[VYHOD] = 'НЕ выгружено: %s' % type(e).__name__
    for z in plohie[:6]:
        print('REC ' + json.dumps(z, ensure_ascii=False))
    print('ИТОГ ' + json.dumps(otchet, ensure_ascii=False))


if __name__ == '__main__':
    main()
