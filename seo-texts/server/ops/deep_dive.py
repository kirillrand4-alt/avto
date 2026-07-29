# -*- coding: utf-8 -*-
"""Глубокий пробой одной компании по источникам, которых нет в конвейере.

Владелец разрешил работать по АО «Криогенмаш» и проверить гипотезы вручную.
Обычные источники по нему пусты: сайт — каталог без раздела о людях, в ЕИС
компания не заказчик, на hh страница чужая. Значит нужны те источники, где
инженера называют по другому поводу:

  1. РАСКРЫТИЕ АО. Акционерное общество обязано публиковать годовой отчёт и
     список аффилированных лиц, а там перечислен совет директоров и правление
     ПОИМЁННО. Для завода это единственный источник, который обязан быть.
  2. ПАТЕНТЫ. У машиностроительного завода авторы изобретений — его же
     конструкторы и главные специалисты. Фамилия автора плюс «Криогенмаш» в
     патентообладателях — это готовый технарь.
  3. КОНФЕРЕНЦИИ И ОТРАСЛЕВАЯ ПРЕССА: доклад делает главный инженер или
     технический директор, и его должность пишут рядом с фамилией.
  4. АРБИТРАЖ: в актах названы представители по доверенности.
  5. КАРТОЧКИ СПРАВОЧНИКОВ (2ГИС, Яндекс.Карты) — телефоны ОТДЕЛОВ.
  6. ГРУППА ВК — контакты в описании.

И проверка гипотезы про почту: если у компании видна схема адресов, найденная
фамилия превращается в адрес и проверяется SMTP-пробой RCPT TO без отправки
письма. Пишем только то, что сервер подтвердил.

Запуск: python deep_dive.py ИНН [--apply] [--снять-конкурента]
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402
import email_schema as ES        # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
СНЯТЬ = '--снять-конкурента' in sys.argv
# ИНН — РОВНО 10 или 12 цифр. Без этой проверки бюджет «1800» в пакетном
# режиме прочитался бы как ИНН и прогон молча свёлся бы к одной компании.
ИНН = next((a for a in sys.argv[1:]
            if a.isdigit() and len(a) in (10, 12)), '')

db = EDB.EnrichDB()
e = db.cx

БЮДЖЕТ = float(next((a for a in sys.argv[1:]
                     if a.replace('.', '').isdigit() and len(a) < 6
                     and len(a) not in (10, 12)), 1800))
ПОТОК = r'C:\seostat\drop\deep_dive_stream.jsonl'
НАЧАЛО = time.time()


def цели_базы():
    """ИНН базы продажников в порядке файла (сверху — те, кого дали продажники)."""
    из, было = [], set()
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    for строки in БАЗА.values():
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in было:
                было.add(i)
                из.append(i)
    return из


def сделано():
    было = set()
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not x.get('err'):
                было.add(str(x.get('inn')))
    return было


_СПРАВОЧНИКИ = ('checko', 'rusprofile', 'list-org', 'audit-it', 'kontur',
                'zachestnyibiznes', 'companies.rbc', 'sbis.ru', 'seldon')


def провайдер(промпт, максимум=1800):
    key = os.environ.get('PROVIDER_API_KEY', '')
    if not key:
        return ''
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
    with urllib.request.urlopen(req, timeout=300) as r:
        for сырая in r:
            стр = сырая.decode('utf-8', 'replace').strip()
            if not стр.startswith('data:'):
                continue
            try:
                ev = json.loads(стр[5:].strip())
            except Exception:  # noqa: BLE001
                continue
            if ev.get('type') == 'content_block_delta':
                куски.append((ev.get('delta') or {}).get('text', ''))
    return ''.join(куски)


def пробой(ИНН, ПРИМЕНИТЬ=False, СНЯТЬ=False):
    c = e.execute('SELECT name, site, is_competitor FROM companies WHERE inn=?',
                  (ИНН,)).fetchone()
    if not c:
        return {'инн': ИНН, 'ошибка': 'нет такой компании'}
    имя, сайт, конкурент = c[0] or '', c[1] or '', c[2]
    бренд = EC.бренд_компании(имя, сайт)
    дом = EC.site_domain(сайт)
    out = {'инн': ИНН, 'компания': имя, 'бренд': бренд, 'домен': дом,
           'был_конкурентом': конкурент, 'источники': {}, 'люди': [],
           'телефоны': [], 'почты_подтверждённые': [],
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)'}

    if СНЯТЬ and ПРИМЕНИТЬ and конкурент:
        # флаг снимаем ЯВНО и по прямому слову владельца; в stage_log остаётся
        # след, чтобы через месяц было понятно, почему конкурент попал в работу
        e.execute('UPDATE companies SET is_competitor=0 WHERE inn=?', (ИНН,))
        e.execute('INSERT OR REPLACE INTO stage_log(inn, stage, detail, ts) '
                  'VALUES(?,?,?,datetime("now"))',
                  (ИНН, 'competitor_off',
                   'снят по прямому указанию владельца 2026-07-29'))
        e.commit()
        out['флаг_конкурента'] = 'снят'

    # --- сбор адресов по гипотезам
    группы = {
        'раскрытие': [f'{бренд} годовой отчёт совет директоров',
                      f'{бренд} список аффилированных лиц e-disclosure',
                      f'{бренд} правление генеральный директор отчёт эмитента'],
        'патенты': [f'{бренд} патент авторы изобретения',
                    f'{бренд} патентообладатель изобретение findpatent'],
        'конференции': [f'{бренд} доклад конференция главный инженер',
                        f'{бренд} технический директор выступил'],
        'арбитраж': [f'{бренд} представитель по доверенности решение суда'],
        'справочники_карт': [f'{бренд} 2гис телефон отдел',
                             f'{бренд} яндекс карты организация телефон'],
        'вк': [f'{бренд} vk.com группа контакты'],
    }
    адреса = {}
    for группа, запросы in группы.items():
        собрано = []
        for з in запросы:
            if time.time() - НАЧАЛО > БЮДЖЕТ:
                break
            for u in EC._serp_urls(з, 8):
                d = EC._domain(u)
                if any(k in d for k in _СПРАВОЧНИКИ):
                    continue
                if u not in собрано:
                    собрано.append(u)
            time.sleep(0.4)
        адреса[группа] = собрано[:6]
        out['источники'][группа] = [u[:95] for u in собрано[:6]]

    # --- чтение и вырезка окрестностей должностей
    _ДОЛЖН = re.compile(
        r'(главн\w+\s+(?:инженер\w*|энергетик\w*|механик\w*|технолог\w*|'
        r'конструктор\w*|металлург\w*)|техническ\w+\s+директор\w*|'
        r'начальник\w*\s+[а-яё]+|директор\w*\s+по\s+[а-яё]+|заместител\w+\s+'
        r'генерального|член\w*\s+совета\s+директоров|председател\w+\s+правления|'
        r'автор\w*\s+изобретени|представител\w+)', re.I)
    куски, прочитано = [], 0
    # Потолок на ОДНУ компанию. Бюджет проверялся только МЕЖДУ компаниями, а
    # внутри пробой делает шесть запросов в выдачу и до трёх десятков закачек
    # страниц — одна компания могла занять столько, что пакетный прогон
    # переставал укладываться в отведённое раннеру время и уходил в тишину.
    ПОТОЛОК = float(os.environ.get('DEEP_ONE_SEC', '150'))
    начало_компании = time.time()
    for группа, список in адреса.items():
        for u in список:
            if time.time() - начало_компании > ПОТОЛОК:
                out['оборвано_по_времени'] = True
                break
            t = ''
            try:
                if re.search(r'\.pdf(?:\?|$)', u, re.I) or 'files.aspx' in u.lower():
                    # раскрытие АО почти всегда PDF: годовой отчёт, отчёт об
                    # итогах голосования, список аффилированных лиц
                    t = EC.doc_text(u)
                    if t:
                        прочитано += 1
                else:
                    h, _m, mt = EC._fetch_site(u)
                    if not h or mt.get('captcha_type'):
                        continue
                    прочитано += 1
                    t = EC._текст(h)
            except Exception:  # noqa: BLE001
                continue
            if not t:
                continue
            окна = [t[max(0, m.start() - 240):m.end() + 280]
                    for m in _ДОЛЖН.finditer(t)][:6]
            # телефоны с карточек справочников берём отдельно: там они лежат
            # рядом с названием отдела, а не рядом с должностью человека
            if группа == 'справочники_карт':
                for мт in list(EC.phones_in(t))[:12]:
                    тел = мт.group(0).strip()
                    окно = t[max(0, мт.start() - 90):мт.end() + 40]
                    if not any(x['тел'] == тел for x in out['телефоны']):
                        out['телефоны'].append({'тел': тел, 'контекст': окно[:110],
                                                'ссылка': u[:90]})
            if окна:
                куски.append(f'--- {u}\n' + ' … '.join(окна))
            time.sleep(0.4)
    out['страниц_прочитано'] = прочитано

    текст = '\n'.join(куски)[:24000]
    out['символов_модели'] = len(текст)
    if текст.strip():
        промпт = (
            f'Ниже куски страниц про компанию «{имя}» (бренд «{бренд}», ИНН {ИНН}). '
            'Найди ЛЮДЕЙ ЭТОЙ КОМПАНИИ с НАЗВАННОЙ ДОЛЖНОСТЬЮ. Авторов патентов '
            'включай, если патентообладатель — эта компания, и помечай их '
            'должностью "автор изобретения", если другой должности не названо. '
            'Людей других организаций, чиновников, судей и журналистов НЕ включай. '
            'Если принадлежность к компании не сказана прямо — пропусти. ФИО в '
            'именительном падеже. Верни СТРОГО JSON без markdown: '
            '{"people":[{"person":"Фамилия Имя Отчество","post":"должность",'
            '"quote":"фраза-основание","url":"адрес из строки --- над куском"}]}'
            '\n\n' + текст)
        try:
            ответ = провайдер(промпт)
        except Exception as ex:  # noqa: BLE001
            out['ошибка_провайдера'] = f'{type(ex).__name__}: {str(ex)[:90]}'
            ответ = ''
        m = re.search(r'\{.*\}', ответ or '', re.S)
        if m:
            try:
                for ч in (json.loads(m.group(0)).get('people') or []):
                    фио = (ч.get('person') or '').strip()
                    пост = (ч.get('post') or '').strip()
                    if not (фио and пост):
                        continue
                    роль = EDB.EnrichDB._canon_role(пост)
                    out['люди'].append({'фио': фио, 'должность': пост,
                                        'роль': роль,
                                        'цитата': (ч.get('quote') or '')[:150],
                                        'ссылка': (ч.get('url') or '')[:95]})
                    if ПРИМЕНИТЬ:
                        db.add_person(ИНН, фио, post=пост, source='глубокий пробой',
                                      source_url=ч.get('url') or '')
            except Exception as ex:  # noqa: BLE001
                out['разбор_ответа'] = f'{type(ex).__name__}: {str(ex)[:70]}'

    # --- гипотеза про схему почты: фамилия -> адрес -> SMTP-проба
    if дом:
        схема, голосов, примеры = ES.вывести_схему(ИНН, дом)
        out['схема_почты'] = {'правило': схема or '(не выведена)',
                              'подтверждений': голосов, 'примеры': примеры[:3]}
        # даже без выведенной схемы пробуем самую частую форму «фамилия@»,
        # если известные адреса компании выглядят именно так
        известные = [r[0].split('@')[0] for r in e.execute(
            'SELECT email FROM emails WHERE inn=? AND email LIKE ?',
            (ИНН, f'%@{дом}'))]
        похоже_фамилия = sum(1 for x in известные
                             if x.isalpha() and len(x) > 4 and '.' not in x)
        out['схема_почты']['адресов_вида_фамилия'] = похоже_фамилия
        проба_домена = EC.smtp_verify(f'zz-net-takogo-{ИНН}@{дом}')
        out['схема_почты']['домен'] = проба_домена
        if проба_домена != 'catch-all':
            кандидаты = []
            for ч in out['люди']:
                части = ES.части(ч['фио'])
                if not части:
                    continue
                правила = схема or ('фамилия' if похоже_фамилия >= 2 else '')
                if not правила:
                    continue
                лок = ES.по_схеме(ч['фио'], правила)
                if лок:
                    кандидаты.append((f'{лок}@{дом}', ч))
            for адрес, ч in кандидаты[:12]:
                итог = EC.smtp_verify(адрес)
                зап = {'адрес': адрес, 'кто': ч['фио'],
                       'должность': ч['должность'], 'ответ': итог}
                out['почты_подтверждённые'].append(зап)
                if итог == 'smtp_ok' and ПРИМЕНИТЬ:
                    db.add_email(ИНН, адрес, role=ч['роль'] or '',
                                 person=ч['фио'], mx_ok=1, source='схема+smtp',
                                 source_url=f'схема {схема or "фамилия"}')
                time.sleep(1.2)

    if ПРИМЕНИТЬ:
        for т in out['телефоны']:
            e.execute('INSERT OR IGNORE INTO phone_contacts(inn, phone, person,'
                      ' role, source, source_url, updated_at) '
                      'VALUES(?,?,?,?,?,?,datetime("now"))',
                      (ИНН, т['тел'], '', 'справочник', 'справочник карт',
                       т['ссылка']))
        e.commit()
    out['итого'] = {'людей': len(out['люди']),
                    'техЛПР': sum(1 for x in out['люди']
                                  if x['роль'] in EDB.EnrichDB.TECH_ROLES),
                    'телефонов': len(out['телефоны']),
                    'почт_ok': sum(1 for x in out['почты_подтверждённые']
                                   if x['ответ'] == 'smtp_ok')}
    return out


def main():
    if ИНН:
        out = пробой(ИНН, ПРИМЕНИТЬ, СНЯТЬ)
        print(json.dumps(out, ensure_ascii=False, indent=1)[:11000])
        print(json.dumps({'итого': out.get('итого'),
                          'схема': out.get('схема_почты')}, ensure_ascii=False))
        return
    # ПАКЕТ: по всей базе продажников, резюмируемо. Способ разведан на одной
    # компании и дал там шесть человек там, где обычные источники дали ноль, —
    # но вывод по одной компании ничего не стоит, поэтому меряем на всех.
    todo = [i for i in цели_базы() if i not in сделано()]
    свод = {'целей': len(todo), 'пройдено': 0, 'людей': 0, 'техЛПР': 0,
            'телефонов': 0, 'почт_ok': 0, 'ошибок': 0, 'примеры': []}
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    for inn in todo:
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        try:
            r = пробой(inn, ПРИМЕНИТЬ, False)
            и = r.get('итого') or {}
            свод['пройдено'] += 1
            свод['людей'] += и.get('людей', 0)
            свод['техЛПР'] += и.get('техЛПР', 0)
            свод['телефонов'] += и.get('телефонов', 0)
            свод['почт_ok'] += и.get('почт_ok', 0)
            for ч in (r.get('люди') or []):
                if ч.get('роль') in EDB.EnrichDB.TECH_ROLES and len(свод['примеры']) < 20:
                    свод['примеры'].append({'инн': inn, 'фио': ч['фио'],
                                            'должность': ч['должность'],
                                            'ссылка': ч.get('ссылка')})
            ф.write(json.dumps({'inn': inn, 'итого': и}, ensure_ascii=False) + '\n')
        except Exception as ex:  # noqa: BLE001
            свод['ошибок'] += 1
            ф.write(json.dumps({'inn': inn, 'err': f'{type(ex).__name__}: '
                                                   f'{str(ex)[:70]}'},
                               ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
    ф.close()
    print(json.dumps(свод, ensure_ascii=False, indent=1)[:6000])
    print(json.dumps({k: v for k, v in свод.items() if k != 'примеры'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
