# -*- coding: utf-8 -*-
"""Технические люди с hh по предприятиям без техЛПР — мой участок раздачи.

Владелец распорядился обогащать контактами 1486 предприятий, где технического
ЛПР нет. Мне достался hh: токен приложения поднял я, 403 снят.

Что hh даёт и чего НЕ даёт, честно до начала работы. Имён hh не публикует
почти никогда — значит «найти ФИО главного энергетика» здесь не выйдет.
Зато даёт другое, и это самостоятельная ценность:

  * САМ ФАКТ найма в техслужбу — «ищут главного энергетика» означает, что
    место или пустует, или человек только пришёл. И то и другое повод звонить;
  * НАЗВАНИЕ подразделения и подчинённость из текста вакансии — по ним видно,
    кому技 звонить: «в подчинении главного инженера», «отдел главного механика»;
  * иногда контактное лицо и телефон в тексте описания.

Поэтому мера успеха здесь не «сколько ФИО», а «скольким предприятиям добавлен
проверяемый повод и адрес обращения». Меру назначаю ДО прогона, чтобы потом не
подгонять её под результат.

Ходим строго по ИНН из общего файла `BEZ-TEHLPR-1486.csv`, чтобы не пересечься
с соседями: у них сайты, ЕИС, Тендер.Про и реестр ЭПБ.

Запуск: python hh_bez_tehlpr.py [--n 200] [--apply]
"""
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ИМЯ = 'HH-po-bez-tehlpr.csv'
УА = 'prokompressor-enrich/1.0 (kirillrand4@gmail.com)'
ПРИМЕНИТЬ = '--apply' in sys.argv


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


# должности, ради которых всё и делается
_ТЕХ_СЛОВА = re.compile(
    r'(?:главн\w*\s+(?:энергетик|механик|инженер|технолог|конструктор)|'
    r'начальн\w*\s+(?:цеха|участка|производств\w*|отдела\s+главн\w*)|'
    r'энергетик|механик|теплотехник|КИПиА|АСУ ?ТП|'
    r'компрессорн\w*|энергослужб\w*|энергохозяйств\w*)', re.I)
# подчинённость: кому подчиняется вакансия — это и есть адрес обращения
_ПОДЧИН = re.compile(
    r'подчин\w*\s+(?:непосредственно\s+)?([А-Яа-яёЁ\s]{6,45}?)(?:[.,;)]|$)', re.I)
_ТЕЛ = re.compile(r'(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}')

# ИМЯ ДЛЯ ПОИСКА. Первый прогон дал 5% и вывод «работодателя нет на hh» — это
# была не правда про hh, а моя строка запроса: в базе имя лежит как
# «ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "БЕЛЕБЕЕВСКИЙ ВОДОКАНАЛ"», а hh
# знает бренд. Замер на 14 целях: полным именем нашлось 3, ядром — 9.
_ОПФ = re.compile(
    r'^\s*(?:ПУБЛИЧНОЕ\s+|ОТКРЫТОЕ\s+|ЗАКРЫТОЕ\s+|АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|'
    r'ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s+ОТВЕТСТВЕННОСТЬЮ|МУНИЦИПАЛЬНОЕ\s+\w+|'
    r'ГОСУДАРСТВЕННОЕ\s+\w+|ФЕДЕРАЛЬНОЕ\s+\w+|УНИТАРНОЕ\s+ПРЕДПРИЯТИЕ|'
    r'ООО|ОАО|ЗАО|ПАО|АО|МУП|ГУП|ФГУП|НАО)\s*', re.I)


def ядро_имени(имя):
    s = (имя or '').strip()
    м = re.search(r'[«"]([^»"]{2,60})[»"]', s)
    if м:
        return м.group(1).strip()
    for _ in range(3):
        s = _ОПФ.sub('', s).strip()
    return re.sub(r'\s+', ' ', re.sub(r'\(ИНН[^)]*\)', '', s)).strip(' "«»')


def чужой_rabotodatel(ядро, назв_hh, найдено):
    """Гейт против тёзок. «АО БМК» по ядру «БМК» даёт found=69, и первым
    стоит «Автотранспортное предприятие БМК» — чужая контора. Взять её вслепую
    значит приписать заводу чужие вакансии: ровно то, за что сегодня чистили
    рассыльщик от тёзок, только здесь я бы сделал это сам.

    Правило: короткое ядро (аббревиатура) при большом числе совпадений — не
    берём. И название на hh должно содержать ядро целиком."""
    я = (ядро or '').strip().lower()
    н = (назв_hh or '').strip().lower()
    if not я or not н:
        return 'пусто'
    if я not in н:
        return f'ядро «{ядро}» не входит в «{назв_hh}»'
    if len(я) <= 4 and найдено > 3:
        return f'аббревиатура «{ядро}», совпадений {найдено} — слишком много тёзок'
    return ''


def токен():
    t = os.environ.get('HH_APP_TOKEN', '')
    if t:
        return t
    cid, sec = os.environ.get('HH_CLIENT_ID'), os.environ.get('HH_CLIENT_SECRET')
    if not (cid and sec):
        return ''
    тело = urllib.parse.urlencode({'grant_type': 'client_credentials',
                                   'client_id': cid,
                                   'client_secret': sec}).encode()
    r = urllib.request.Request('https://hh.ru/oauth/token', data=тело,
                               headers={'User-Agent': УА,
                                        'Content-Type':
                                        'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(r, timeout=60) as о:
        return json.loads(о.read().decode()).get('access_token', '')


def зпр(url, tok):
    r = urllib.request.Request(url, headers={'User-Agent': УА,
                                             'Authorization': 'Bearer ' + tok})
    with urllib.request.urlopen(r, timeout=45) as о:
        return json.loads(о.read().decode('utf-8', 'replace'))


def main():
    tok = токен()
    if not tok:
        print('НЕТ токена hh — без него api.hh.ru отдаёт 403, идти некуда')
        return
    print(f'токен получен ({len(tok)} символов)')

    csv.field_size_limit(10 ** 7)
    п = os.path.join(ДРОП, 'BEZ-TEHLPR-1486.csv')
    цели = list(csv.DictReader(io.StringIO(
        open(п, encoding='utf-8-sig', errors='replace').read()), delimiter=';'))
    n = int(арг('--n', '200'))
    цели = цели[:n]
    print(f'целей в работе: {len(цели)} (из файла {os.path.basename(п)})')

    db = EDB.EnrichDB()
    строки = []
    итог = Counter()
    for i, ц in enumerate(цели, 1):
        инн = (ц.get('inn') or '').strip()
        имя = (ц.get('predpriyatie') or '').strip()
        if not (инн and имя):
            итог['без имени или ИНН'] += 1
            continue
        # 1) работодатель по названию — hh ищет по имени, ИНН он не хранит
        я = ядро_имени(имя) or имя
        try:
            наш = зпр('https://api.hh.ru/employers?text='
                      + urllib.parse.quote(я[:60]) + '&per_page=3', tok)
        except urllib.error.HTTPError as e:
            итог[f'employers HTTP {e.code}'] += 1
            continue
        except Exception as e:  # noqa: BLE001
            итог['employers ошибка'] += 1
            continue
        раб = (наш.get('items') or [])
        if не_нашли(раб):
            итог['работодатель на hh не найден'] += 1
            continue
        назв_hh = раб[0].get('name', '')
        отказ = чужой_rabotodatel(я, назв_hh, наш.get('found', 0))
        if отказ:
            итог[f'отклонён как тёзка ({отказ.split(chr(171))[0].strip()})'] += 1
            continue
        eid = раб[0]['id']

        # 2) вакансии этого работодателя с техническими словами
        try:
            вак = зпр(f'https://api.hh.ru/vacancies?employer_id={eid}'
                      '&per_page=50', tok)
        except Exception as e:  # noqa: BLE001
            итог['vacancies ошибка'] += 1
            continue
        техн = [v for v in (вак.get('items') or [])
                if _ТЕХ_СЛОВА.search(v.get('name') or '')]
        if not техн:
            итог['вакансий техслужбы нет'] += 1
            continue
        итог['предприятий с наймом в техслужбу'] += 1

        for v in техн[:6]:
            # 3) описание — оттуда подчинённость и иногда телефон
            подч = телефон = ''
            try:
                полн = зпр(f'https://api.hh.ru/vacancies/{v["id"]}', tok)
                оп = re.sub(r'<[^>]+>', ' ', полн.get('description') or '')
                м = _ПОДЧИН.search(оп)
                подч = re.sub(r'\s+', ' ', м.group(1)).strip() if м else ''
                мт = _ТЕЛ.search(оп)
                телефон = мт.group(0) if мт else ''
            except Exception:  # noqa: BLE001
                pass
            строки.append({
                'inn': инн, 'predpriyatie': имя,
                'rabotodatel_na_hh': назв_hh,
                'vakansiya': v.get('name', ''),
                'podchinyaetsya': подч,
                'telefon_iz_opisaniya': телефон,
                'gorod': ((v.get('area') or {}).get('name') or ''),
                'data': (v.get('published_at') or '')[:10],
                'ssylka': v.get('alternate_url', ''),
                'chto_eto_znachit':
                    'место в техслужбе открыто: либо вакантно, либо человек '
                    'только пришёл — повод для звонка и вопрос «кто сейчас за '
                    'это отвечает»',
            })
            if телефон:
                итог['телефон в описании вакансии'] += 1
            if подч:
                итог['названа подчинённость'] += 1
        if i % 25 == 0:
            print(f'  {i}/{len(цели)}, строк {len(строки)}')
        time.sleep(0.35)          # hh не любит частых обращений

    путь = os.path.join(r'C:\sender\server', ИМЯ)
    поля = ['inn', 'predpriyatie', 'rabotodatel_na_hh', 'vakansiya',
            'podchinyaetsya', 'telefon_iz_opisaniya', 'gorod', 'data',
            'ssylka', 'chto_eto_znachit']
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        w = csv.DictWriter(ф, fieldnames=поля, delimiter=';')
        w.writeheader()
        w.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())

    # числа перечитыванием файла
    вс = сп = ст = 0
    предпр = set()
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            вс += 1
            предпр.add(r['inn'])
            if r['podchinyaetsya'].strip():
                сп += 1
            if r['telefon_iz_opisaniya'].strip():
                ст += 1
    print()
    print('=== ЧИСЛА ПЕРЕЧИТЫВАНИЕМ ФАЙЛА ===')
    print(f'  строк: {вс}, предприятий: {len(предпр)} из {len(цели)} '
          f'({round(100 * len(предпр) / max(1, len(цели)))}%)')
    print(f'  с названной подчинённостью: {сп}')
    print(f'  с телефоном в описании: {ст}')
    print('  что происходило:')
    for к, v in итог.most_common():
        print(f'    {v:>5}  {к}')

    if ПРИМЕНИТЬ and строки:
        for с in строки:
            db.add_signal(с['inn'], source='вакансии hh',
                          event_type='наём в техслужбу',
                          what=с['vakansiya'][:120],
                          source_url=с['ssylka'], hotness=3)
        db.cx.commit()
        print('  сигналы записаны в enrich.db')

    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ИМЯ, data=open(путь, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:110]}')


def не_нашли(раб):
    return not раб


if __name__ == '__main__':
    main()
