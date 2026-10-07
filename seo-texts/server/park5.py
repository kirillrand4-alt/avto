# -*- coding: utf-8 -*-
r"""Пятый файл базы Meyer: 76 компаний из «Парка компрессорного оборудования» (park_panel.db),
целевых для Meyer по основному ОКВЭД, которых нет в файлах 1–4, без сделок/запретов и
ликвидированных (владелец 07.10).

На каждый телефон из kontakt: проверка по живой странице-источнику (ssylka):
  * checko.ru — через прокси владельца с браузерными заголовками (cc_checko_proxy.Прокси);
  * площадки закупок — если номера на карточке нет, номер НЕ выкидывается: владелец 07.10 —
    «карточки закупок не всегда значило именно номер на странице, иногда он был в приложенных
    файлах» -> пометка «номер в документах закупки»;
  * прочие сайты — живая страница, иначе кэш обхода.
Где у номера есть ФИО/должность и номер найден — модель по фрагменту подтверждает, чей он.
Доход 2025 — открытые данные ФНС (revexp). Выход: C:\sender\server\park5.jsonl (+ дроп).
"""
import csv
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_proverka as MP  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import cc_checko_proxy as CP  # noqa: E402
import verify_company as VC  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ВЫХОД = os.path.join(DIR, 'park5.jsonl')
ЗАКУПКИ = re.compile(r'zakupki\.gov|tender\.pro|roseltorg|b2b-center|etpgpb|fabrikant|zakupki360|rts-tender|'
                     r'sberbank-ast|tektorg|lot-online|zakazrf|otc\.ru|onlinecontract|bicotender|etp-ets', re.I)
КЛАССЫ = ('директор', 'главный инженер', 'технический директор', 'производство', 'главный технолог', 'технолог',
          'качество', 'закупки', 'агроном', 'семеноводство', 'элеватор', 'коммерческий директор', 'продажи',
          'бухгалтерия', 'кадры', 'инженер', 'приёмная', 'общий', 'другое')
ПРОМПТ = (
    'Компания «{имя}» (ИНН {инн}). Страница: {url}\nТекст вокруг номеров:\n«««{текст}»»»\n\nНомера:\n{номера}\n\n'
    'Для КАЖДОГО номера: кому он принадлежит по тексту рядом (подпись обычно ПЕРЕД номером; номер соседа '
    'не приписывай; нет подписи — пусто). Класс строго одно из: ' + '|'.join(КЛАССЫ) + '. «директор» — только '
    'первое лицо или его заместитель. «общий» — номер без подписи/общий/приём заказов.\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер_в_списке,"фио":"","должность":"","класс":"…"}}]')


def записать(з):
    with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
        f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def норм(t):
    ц = re.sub(r'\D', '', t or '')
    if len(ц) == 11 and ц[0] in '78':
        ц = '7' + ц[1:]
    elif len(ц) == 10:
        ц = '7' + ц
    return ц if len(ц) == 11 else ''


def main():
    r = list(csv.DictReader(io.open(os.path.join(ДРОП, 'park-meyer-kandidaty.csv'), encoding='utf-8-sig'), delimiter=';'))
    канд = {x['ИНН']: x for x in r if x['Сегмент по осн. ОКВЭД'] and not x['Где у нас'].startswith('в наших')
            and not x['Запрет панели'] and (x['Статус ЕГРЮЛ'] or '').upper() not in ('LIQUIDATED', 'LIQUIDATING', 'BANKRUPT')
            and 'ликвид' not in (x['Статус ЕГРЮЛ'] or '').lower()}
    c = sqlite3.connect('file:%s?mode=ro' % os.path.join(ДРОП, 'park_panel.db'), uri=True)
    кол = [x[1] for x in c.execute('pragma table_info(kontakt)')]
    тел = [dict(zip(кол, x)) for x in c.execute("select * from kontakt where vid='telefon'") if str(x[0]) in канд]
    пкол = [x[1] for x in c.execute('pragma table_info(predpriyatie)')]
    пр = {str(x[0]): dict(zip(пкол, x)) for x in c.execute('select * from predpriyatie') if str(x[0]) in канд}
    c.close()
    # доход 2025 — ФНС revexp
    доход = {}
    z = zipfile.ZipFile(r'C:\sender\_ops\ak\fns\revexp.zip')
    for zi in z.infolist():
        with z.open(zi) as fh:
            for ev, el in ET.iterparse(fh, events=('end',)):
                if not el.tag.endswith('Документ'):
                    continue
                inn = д = None
                for ch in el:
                    if 'СведНП' in ch.tag:
                        inn = ch.get('ИННЮЛ') or ch.get('ИННФЛ')
                    elif 'ДохРасх' in ch.tag:
                        д = ch.get('СумДоход')
                if inn in канд and д:
                    доход[inn] = float(д)
                el.clear()
    прокси = [CP.Прокси(п) for п in json.load(open(os.path.join(DIR, 'checko-proxies.json')))]
    прокси = [п for п in прокси if п.get('https://checko.ru/')[0] == 200]
    if os.path.exists(ВЫХОД):
        os.remove(ВЫХОД)
    записать({'тип': 'компании', 'данные': {i: dict(пр.get(i, {}), **{'доход_2025': доход.get(i), 'кандидат': канд[i]})
                                            for i in канд}})
    по_стр = {}
    for к in тел:
        по_стр.setdefault((str(к['inn']), к['ssylka'] or ''), []).append(к)
    k = 0
    for (инн, url), кк in по_стр.items():
        хост = urllib.parse.urlsplit(url).hostname or ''
        if 'checko.ru' in хост and прокси:
            код, html = прокси[k % len(прокси)].get(url)
            k += 1
            статус, текст = ('ok' if код == 200 else 'ошибка: %s' % код), (CP.текст(html) if код == 200 else '')
        elif url:
            ст, html, _ = MN.скачать(url)
            статус, текст = ст, (MP.в_текст(html) if ст == 'ok' else '')
        else:
            статус, текст = 'нет ссылки', ''
        найденные, с_подписью = [], []
        for к in кк:
            ц = норм(к['znachenie'])
            з = {'тип': 'номер', 'inn': инн, 'номер': ц, 'url': url, 'страница': статус, 'person': к.get('person'),
                 'dolzhnost': к.get('dolzhnost'), 'rol': к.get('rol'), 'lichnyy': к.get('lichnyy'), 'mobilnyy': к.get('mobilnyy')}
            поз = MP.найти(текст, ц[-10:]) if текст and ц else []
            if поз:
                з['итог'] = 'на странице'
                з['контекст'] = re.sub(r'\s+', ' ', текст[max(0, поз[0] - 200):поз[0] + 60])
                if (к.get('person') or '').strip() not in ('', 'None') or (к.get('dolzhnost') or '') not in ('', 'должность не названа'):
                    с_подписью.append((з, поз[0]))
            elif ЗАКУПКИ.search(хост):
                з['итог'] = 'закупка: номер в документах закупки (на карточке нет)'
            else:
                кэш = MP.из_кэша_обхода(инн, ц[-10:]) if ц else None
                з['итог'] = ('был на странице при обходе %s' % кэш[2][:10]) if кэш else 'не подтверждён'
            найденные.append(з)
        if с_подписью:
            окна = '\n…\n'.join(текст[max(0, п - 400):п + 150] for _, п in с_подписью)[:6500]
            промпт = ПРОМПТ.format(имя=канд[инн]['Название'], инн=инн, url=url, текст=окна,
                                   номера='\n'.join('%d. %s' % (i + 1, з['номер']) for i, (з, _) in enumerate(с_подписью)))
            ответ = {}
            for попытка in range(3):
                try:
                    out = VC._provider_call_stdlib(промпт)
                    ответ = {int(x.get('n', 0)): x for x in json.loads(re.search(r'\[.*\]', out, re.S).group(0)) if isinstance(x, dict)}
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(5)
            for i, (з, _) in enumerate(с_подписью):
                x = ответ.get(i + 1) or {}
                з.update({'стр_фио': x.get('фио', ''), 'стр_должность': x.get('должность', ''),
                          'стр_класс': x.get('класс') if x.get('класс') in КЛАССЫ else ''})
        for з in найденные:
            записать(з)
    shutil.copyfile(ВЫХОД, os.path.join(ДРОП, 'park5.jsonl'))
    print('===ИТОГ===')
    print(json.dumps({'компаний': len(канд), 'телефонов': len(тел), 'страниц': len(по_стр), 'доход_2025': len(доход),
                      'прокси_живых': len(прокси)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
