# -*- coding: utf-8 -*-
"""ЗАМЕР ИСТОЧНИКА №2: ОБЯЗАТЕЛЬНОЕ РАСКРЫТИЕ АО как поставщик ЛПР.

АО обязано публиковать годовой отчёт, отчёт об итогах голосования и список
аффилированных лиц — там органы управления названы ПОИМЁННО. Меряем:
  - у скольких АО раскрытие вообще нашлось и прочиталось;
  - сколько человек с должностями извлеклось;
  - сколько из них ТЕХНИЧЕСКИЕ (гл. инженер/энергетик/механик/технолог/
    конструктор/техдиректор), а сколько — администрация и совет директоров.

Разведка (_ops_pat_probe4/5/6.py, всё проверено сырьём):
  - e-disclosure.ru (Интерфакс) закрыт антиботом ServicePipe: любая страница
    отдаёт 1.6 КБ JS-заглушки, а Playwright получает «Мы хотим убедиться, что
    имеем дело именно с вами, а не с ботом». Это БЛОКИРОВКА, не пустота;
  - disclosure.1prime.ru (ПРАЙМ) и disclosure.skrin.ru (СКРИН) открыты прямым
    GET; документы 1prime лежат в .uif — это HTML в windows-1251, и читать их
    надо через EC._fetch_site (EC._раскодировать), иначе выходит крокозябра:
    через VC._fetch тот же файл дал нечитаемый мусор;
  - PDF годовых отчётов и отчётов об итогах голосования лежат прямо на сайтах
    эмитентов и читаются EC.doc_text (проверено: 24747 и 72856 символов).

Люди разбираются провайдерским API (claude-fable-5), как велит правило владельца.
Резюмируемо: C:\\sender\\_ops\\pat_disclosure.jsonl (fsync). В enrich.db не пишем.
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402
import enrich_db as EDB          # noqa: E402

ПОТОК = r'C:\sender\_ops\pat_disclosure.jsonl'
НАЧАЛО = time.time()
БЮДЖЕТ = float(os.environ.get('DIS_SEC', '200'))

# 15 АО/ПАО из sales_base (только акционерные общества — ООО ничего не раскрывает)
ВЫБОРКА = [
    ('4026007424', 'ПАО «Калужский турбинный завод»', 'paoktz.ru'),
    ('6664013880', 'АО «Уралхиммаш»', 'uralhimmash.ru'),
    ('5001000066', 'ПАО «Криогенмаш»', 'cryogenmash.ru'),
    ('1660004229', 'АО «Казанский оптико-механический завод»', 'komzrt.ru'),
    ('5919470019', 'ОАО «Соликамский магниевый завод»', 'smw.ru'),
    ('4718011856', 'АО «Сясьский целлюлозно-бумажный комбинат»', 'syas.ru'),
    ('5908007560', 'АО «ГалоПолимер Пермь»', 'halopolymer.ru'),
    ('0258005638', 'АО «ПОЛИЭФ»', 'polief.ru'),
    ('6679007712', 'НАО «НИПИГОРМАШ»', 'npgm.ru'),
    ('2128006240', 'АО «АБС ЗЭиМ Автоматизация»', 'zeim.ru'),
    ('7735007358', 'АО «Микрон»', 'mikron.ru'),
    ('3821008439', 'АО «Кремний»', 'group-kremny.ru'),
    ('4506004751', 'АО «Далур»', 'dalur.armz.ru'),
    ('4715022874', 'АО «Пикалёвская сода»', 'piksoda.ru'),
    ('4401008660', 'АО «Газпром трубинвест»', 'vrpp.ru'),
]

_ТЕХ = re.compile(
    r'главн\w+\s+(?:инженер|энергетик|механик|технолог|конструктор|металлург|'
    r'сварщик|геолог|маркшейдер)|технически\w+\s+директор|директор\w*\s+по\s+'
    r'(?:производств|техническ|развити|качеств|эксплуатац|энергет|ремонт)|'
    r'начальник\w*\s+(?:цеха|производств|отдела\s+главного|энергослужб|'
    r'ремонтн|котельн|компрессорн|службы\s+главного)|заместител\w+\s+'
    r'(?:генерального\s+директора\s+по\s+(?:производств|техническ|развити)|'
    r'директора\s+по\s+производств)|главный\s+специалист\s+по\s+'
    r'(?:техник|энерг|механ)', re.I)
_АДМ = re.compile(
    r'член\w*\s+совета\s+директоров|председател\w+\s+совета|генеральн\w+\s+'
    r'директор|президент|финансов\w+\s+директор|главн\w+\s+бухгалтер|'
    r'корпоративн\w+\s+секретар|ревизион|директор\w*\s+по\s+(?:экономик|'
    r'финанс|персонал|прав|безопасност|коммерч|продаж|закупк)', re.I)


def провайдер(промпт, максимум=2400):
    key = os.environ.get('PROVIDER_API_KEY', '')
    if not key:
        return '', 'нет PROVIDER_API_KEY'
    base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    тело = json.dumps({'model': 'claude-fable-5', 'max_tokens': максимум,
                       'stream': True,
                       'messages': [{'role': 'user', 'content': промпт}]},
                      ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        base + '/v1/messages', data=тело, method='POST',
        headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json',
                 'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
    куски = []
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            for сырая in r:
                с = сырая.decode('utf-8', 'replace').strip()
                if not с.startswith('data:'):
                    continue
                try:
                    ev = json.loads(с[5:].strip())
                except Exception:  # noqa: BLE001
                    continue
                if ev.get('type') == 'content_block_delta':
                    куски.append((ev.get('delta') or {}).get('text', ''))
    except Exception as ex:  # noqa: BLE001
        return '', '%s: %s' % (type(ex).__name__, str(ex)[:80])
    return ''.join(куски), ''


_ДОК = re.compile(r'\.pdf(?:\?|$)|\.uif(?:\?|$)|\.docx?(?:\?|$)|\.rtf(?:\?|$)',
                  re.I)
_ХЛАМ = ('checko', 'rusprofile', 'audit-it', 'list-org', 'zachestnyibiznes',
         'companies.rbc', 'sbis.ru', 'saby.ru', 'e-ecolog', 'synapsenet',
         'globalstat', 'licexpert', 'seldon', 'kontragent')


def ссылки_компании(имя, дом):
    """Кандидатные документы раскрытия: сайт эмитента, 1prime, skrin, azipi."""
    соб, отмечено = [], {}
    зпр = [f'{имя} годовой отчёт совет директоров правление',
           f'{имя} отчёт об итогах голосования общее собрание акционеров',
           f'{имя} список аффилированных лиц']
    for з in зпр:
        for u in EC._serp_urls(з, 10):
            d = EC._domain(u)
            if any(k in d for k in _ХЛАМ):
                continue
            if 'e-disclosure.ru' in d:
                отмечено['e-disclosure'] = отмечено.get('e-disclosure', 0) + 1
                continue          # закрыт антиботом, проверено сырьём
            if u not in соб:
                соб.append(u)
        time.sleep(0.3)
    # со страницы раскрытия эмитента дособираем PDF
    свои = [u for u in соб if дом and дом.split('.')[0] in EC._domain(u)
            and not _ДОК.search(u)]
    for u in свои[:2]:
        try:
            h, _m, _meta = EC._fetch_site(u)
        except Exception:  # noqa: BLE001
            continue
        for m in re.finditer(r'href="([^"]+\.pdf)"', h or '', re.I):
            п = urllib.parse.urljoin(u, m.group(1))
            if п not in соб:
                соб.append(п)
    док = [u for u in соб if _ДОК.search(u)]
    прочее = [u for u in соб if not _ДОК.search(u)]
    return док, прочее, отмечено


def текст_дока(u):
    try:
        if re.search(r'\.pdf(?:\?|$)|\.docx?(?:\?|$)|\.rtf(?:\?|$)', u, re.I):
            return u, EC.doc_text(u), 'doc_text'
        h, m, _meta = EC._fetch_site(u)      # .uif — HTML в cp1251
        return u, EC._текст(h or ''), m
    except Exception as ex:  # noqa: BLE001
        return u, '', 'ИСКЛ ' + type(ex).__name__


_РОЛЬ = re.compile(
    r'(главн\w+\s+(?:инженер\w*|энергетик\w*|механик\w*|технолог\w*|'
    r'конструктор\w*|металлург\w*|бухгалтер\w*)|техническ\w+\s+директор\w*|'
    r'генеральн\w+\s+директор\w*|директор\w*\s+по\s+[а-яё]+|'
    r'начальник\w*\s+[а-яё]+|заместител\w+\s+генерального|'
    r'член\w*\s+совета\s+директоров|председател\w+\s+(?:правления|совета)|'
    r'член\w*\s+правления|корпоративн\w+\s+секретар\w*|президент\w*)', re.I)


def окна(t, максимум=14):
    из = []
    for m in _РОЛЬ.finditer(t or ''):
        из.append(t[max(0, m.start() - 200):m.end() + 260])
        if len(из) >= максимум:
            break
    return из


def сделано():
    было = set()
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                было.add(str(json.loads(ln).get('inn')))
            except Exception:  # noqa: BLE001
                pass
    return было


def компания(inn, имя, дом):
    out = {'inn': inn, 'имя': имя, 'док_ссылок': 0, 'прочитано': 0,
           'символов': 0, 'люди': [], 'пустые': [], 'источники': []}
    док, прочее, отм = ссылки_компании(имя, дом)
    out['e_disclosure_отброшено'] = отм.get('e-disclosure', 0)
    out['док_ссылок'] = len(док)
    цели = док[:6] or прочее[:4]
    out['источники'] = [u[:100] for u in цели]
    тексты = []
    if цели:
        with ThreadPoolExecutor(max_workers=5) as п:
            тексты = list(п.map(текст_дока, цели))
    куски = []
    for u, t, как in тексты:
        if not t or len(t) < 300:
            out['пустые'].append({'url': u[:90], 'символов': len(t or ''),
                                  'как': как})
            continue
        out['прочитано'] += 1
        out['символов'] += len(t)
        ок = окна(t)
        if ок:
            куски.append('--- ' + u + '\n' + ' … '.join(ок))
    текст = '\n'.join(куски)[:26000]
    out['символов_модели'] = len(текст)
    if not текст.strip():
        out['почему_пусто'] = ('прочитано %d документов, но окон с должностями '
                               'не нашлось' % out['прочитано'])
        return out
    промпт = (
        f'Ниже куски документов обязательного раскрытия компании {имя} '
        f'(ИНН {inn}): годовой отчёт, отчёт об итогах голосования, список '
        'аффилированных лиц. Выпиши ВСЕХ названных ЛЮДЕЙ ЭТОЙ компании с '
        'должностью. Включай членов совета директоров и правления, '
        'генерального директора, главных специалистов. НЕ включай людей других '
        'организаций, аудиторов, регистраторов, нотариусов, представителей '
        'акционеров-юрлиц. ФИО в именительном падеже, должность — как в тексте. '
        'Верни СТРОГО JSON без markdown: {"people":[{"person":"Фамилия Имя '
        'Отчество","post":"должность","url":"адрес из строки --- над куском"}]}'
        '\n\n' + текст)
    ответ, беда = провайдер(промпт)
    if беда:
        out['ошибка_провайдера'] = беда
        return out
    m = re.search(r'\{.*\}', ответ or '', re.S)
    if not m:
        out['ошибка_разбора'] = 'модель не вернула JSON: ' + (ответ or '')[:120]
        return out
    try:
        люди = (json.loads(m.group(0)).get('people') or [])
    except Exception as ex:  # noqa: BLE001
        out['ошибка_разбора'] = '%s' % type(ex).__name__
        return out
    for ч in люди:
        фио = (ч.get('person') or '').strip()
        пост = (ч.get('post') or '').strip()
        if not (фио and пост):
            continue
        тех = bool(_ТЕХ.search(пост))
        адм = bool(_АДМ.search(пост)) and not тех
        out['люди'].append({'фио': фио, 'должность': пост,
                            'роль': EDB.EnrichDB._canon_role(пост),
                            'тех': тех, 'адм': адм,
                            'ссылка': (ч.get('url') or '')[:100]})
    out['людей'] = len(out['люди'])
    out['техЛПР'] = sum(1 for x in out['люди'] if x['тех'])
    out['админ'] = sum(1 for x in out['люди'] if x['адм'])
    return out


def main():
    if '--сброс' in sys.argv and os.path.exists(ПОТОК):
        os.remove(ПОТОК)
        print('поток сброшен')
    гот = сделано()
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    прошло = 0
    for inn, имя, дом in ВЫБОРКА:
        if inn in гот:
            continue
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        try:
            r = компания(inn, имя, дом)
        except Exception as ex:  # noqa: BLE001
            r = {'inn': inn, 'имя': имя,
                 'ошибка': '%s: %s' % (type(ex).__name__, str(ex)[:90])}
        ф.write(json.dumps(r, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
        прошло += 1
        print('OK %-38s док=%d прочит=%d людей=%d тех=%d адм=%d %s'
              % (имя[:38], r.get('док_ссылок', 0), r.get('прочитано', 0),
                 r.get('людей', 0), r.get('техЛПР', 0), r.get('админ', 0),
                 r.get('ошибка') or r.get('ошибка_провайдера')
                 or r.get('почему_пусто') or ''))
    ф.close()
    print('ПРОГРЕСС: за проход %d, всего %d из %d'
          % (прошло, len(сделано()), len(ВЫБОРКА)))


if __name__ == '__main__':
    main()
