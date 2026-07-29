# -*- coding: utf-8 -*-
r"""ВЫБОРОЧНАЯ ПЕРЕПРОВЕРКА записанного (владелец просил прямо).

Берём записи из базы, заново открываем ИХ ЖЕ страницу-источник и сверяем
построчно: стоит ли на странице этот человек, этот телефон, эта почта и ИНН
нашей компании. Проверяем то, что записали, а не то, что думали, что записали, —
привычка, поймавшая за день четыре подделки.

Выборка НЕ случайная в смысле удобства: берём и свежие, и stale, и горячие,
и записи с большим числом схлопнутых закупок — то есть ровно те места, где
дедуп мог склеить двух разных людей.
"""
import json
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402


def цифры(s):
    return re.sub(r'\D', '', s or '')


def main():
    db = EDB.EnrichDB()
    e = db.cx
    выбор = []
    for усл, метка in (("freshness='stale'", 'stale'),
                       ('hot=1', 'горячая'),
                       ('n_procs>=3', 'много_закупок'),
                       ("freshness='fresh'", 'fresh')):
        for r in e.execute(
                'SELECT inn,person,post,phone,email,proc_date,freshness,hot,'
                'n_procs,source_url,alt_url,subject FROM eis_arch WHERE ' + усл
                + ' ORDER BY proc_date DESC LIMIT 3'):
            if r[9] and not any(x['url'] == r[9] and x['inn'] == r[0] for x in выбор):
                выбор.append({'inn': r[0], 'person': r[1], 'post': r[2],
                              'phone': r[3], 'email': r[4], 'дата': r[5],
                              'свежесть': r[6], 'горяч': r[7], 'закупок': r[8],
                              'url': r[9], 'alt_url': r[10], 'предмет': r[11],
                              'почему_взят': метка})
    выбор = выбор[:8]
    print('ПРОВЕРЯЕМ %d записей' % len(выбор), flush=True)
    итог = {'проверено': 0, 'всё_совпало': 0, 'расхождений': 0, 'строки': []}
    for з in выбор:
        o = dict(з)
        try:
            h = EC._eis_get(з['url'])
            t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
        except Exception as ex:  # noqa: BLE001
            o['ошибка'] = f'{type(ex).__name__}: {str(ex)[:50]}'
            итог['строки'].append(o)
            continue
        тц = цифры(t)
        o['инн_на_странице'] = з['inn'] in t
        # фамилия человека (без инициалов) — её и ищем на странице
        фам = (з['person'] or '').split()[0] if з['person'] else ''
        o['фамилия_на_странице'] = bool(фам) and фам in t
        баз = цифры((з['phone'] or '').split(' доб.')[0])
        o['телефон_на_странице'] = bool(баз) and (baz10 := баз[-10:]) and baz10 in тц
        o['почта_на_странице'] = bool(з['email']) and з['email'].lower() in t.lower()
        # дата размещения на самой странице — сверка возраста контакта
        дм = re.search(r'(?:Дата\s+размещен\w*[^0-9]{0,40})(\d{2}\.\d{2}\.\d{4})', t, re.I)
        o['дата_на_странице'] = (дм.group(1) if дм else '')
        совпало = (o['инн_на_странице']
                   and (o['фамилия_на_странице'] or not фам)
                   and (o['телефон_на_странице'] or not баз)
                   and (o['почта_на_странице'] or not з['email']))
        o['ВЕРДИКТ'] = 'совпало' if совпало else 'РАСХОЖДЕНИЕ'
        итог['проверено'] += 1
        итог['всё_совпало' if совпало else 'расхождений'] += 1
        итог['строки'].append(o)
        print('… ' + json.dumps(o, ensure_ascii=False)[:400], flush=True)
        time.sleep(0.8)
    print('СВОДКА ' + json.dumps(
        {k: итог[k] for k in ('проверено', 'всё_совпало', 'расхождений')},
        ensure_ascii=False), flush=True)
    print('ПОДРОБНО ' + json.dumps(итог['строки'], ensure_ascii=False,
                                   indent=1)[:5000], flush=True)

    # ------------------------------------------------------------------
    # АУДИТ ПРЕЖНЕГО ИСТОЧНИКА. find_zakupki_contacts не проверяет привязку
    # ВООБЩЕ: берёт контакты с любой карточки, которую вернул свободный поиск.
    # Проба 8 показала, чем это грозит — по названию компании ЕИС отдаёт чужие
    # закупки, где наша фирма лишь упомянута. Смотрим, не лежат ли в базе уже
    # записанные чужие контакты.
    стар = list(e.execute(
        "SELECT inn, phone, person, source_url FROM phone_contacts "
        "WHERE source LIKE 'zakupki:eis' AND source_url<>'' "
        "ORDER BY RANDOM() LIMIT 10"))
    ауд = {'проверено': 0, 'инн_на_странице': 0, 'ЧУЖАЯ_КАРТОЧКА': 0, 'ошибок': 0,
           'подозрительные': []}
    for inn, тел, чел, url in стар:
        try:
            h = EC._eis_get(url)
            t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
        except Exception:  # noqa: BLE001
            ауд['ошибок'] += 1
            continue
        ауд['проверено'] += 1
        if inn in t:
            ауд['инн_на_странице'] += 1
        else:
            ауд['ЧУЖАЯ_КАРТОЧКА'] += 1
            зм = re.search(r'Заказчик\s*[:\-]?\s*([^,;]{6,70})', t)
            ауд['подозрительные'].append(
                {'инн': inn, 'кто': чел, 'тел': тел,
                 'чей_на_деле': (зм.group(1).strip() if зм else '?')[:60],
                 'url': url[-50:]})
        time.sleep(0.7)
    print('АУДИТ_ПРЕЖНЕГО ' + json.dumps(ауд, ensure_ascii=False, indent=1)[:2500],
          flush=True)


if __name__ == '__main__':
    main()
