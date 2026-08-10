# -*- coding: utf-8 -*-
"""Достаём контактное лицо из УЖЕ СНЯТЫХ карточек закупок.

Дефект, который это чинит: мой съёмщик искал на карточке блок «Контактное лицо», а в
44-ФЗ он называется «Ответственное должностное лицо». Замер на 844 карточках общих
запросов: блок с ФИО есть у **747**, а снялось **21**. То же самое было в оси расхода
газа («ФИО снимается плохо: 15 из 304») — причина одна и та же.

Заново обходить ЕИС не нужно: полный текст карточки сохранён в поле `tekst`.

Формы, которые встречаются (проверено на живых карточках):
    «Ответственное должностное лицо Ляхович Т. В. Адрес электронной почты …»
    «Контактное лицо Молодык Д.В. Адрес электронной почты … Контактный телефон …»
    «Ответственное должностное лицо Сальникова А. С. … Номер контактного телефона …»

Пишем в contact_source: у каждого контакта ссылка на карточку и цитата — то, что
требует владелец. Свод (kontakt) пересобирается отдельным скриптом.
"""
import sqlite3, json, os, re, sys, importlib.util, collections

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()

FAYLY = sys.argv[1:] or ['park_obshchie_inn.jsonl', 'park_gaz_inn.jsonl',
                         'park_brendy_inn.jsonl']

_LICO = re.compile(
    r'(?:Ответственн\w+\s+должностн\w+\s+лиц\w+|Контактн\w+\s+лиц\w+|'
    r'Фамилия,?\s*имя,?\s*отчество)\s*'
    r'([А-ЯЁ][а-яё\-]{2,24}(?:\s+[А-ЯЁ][а-яё\-]{2,24}\s+[А-ЯЁ][а-яё\-]{2,24}|'
    r'\s+[А-ЯЁ]\.\s*[А-ЯЁ]?\.?))')
_POCHTA = re.compile(r'(?:Адрес\s+электронн\w+\s+почты|E-?mail)\s*([^\s;,]+@[^\s;,]+)', re.I)
_TEL = re.compile(r'(?:Номер\s+контактн\w+\s+телефона|Контактн\w+\s+телефон)\s*'
                  r'([\d\s\-\(\)\+]{7,28})')
_DOLZH = re.compile(r'(?:Должность)\s*([А-ЯЁа-яё][^\n]{3,60})')


def cifry10(s):
    c = re.sub(r'\D', '', s or '')
    if len(c) >= 11 and c[0] in '78':
        c = c[1:]
    return c[-10:] if len(c) >= 10 else ''


vs = s_fio = s_tel = s_mail = 0
pri = collections.Counter()
inny = set()
for imya in FAYLY:
    put = os.path.join(D, imya)
    if not os.path.exists(put):
        pri['файла нет: ' + imya] += 1
        continue
    for ln in open(put, encoding='utf-8', errors='replace'):
        if not ln.strip():
            continue
        try:
            x = json.loads(ln)
        except Exception:
            continue
        vs += 1
        inn = (x.get('inn') or '').strip()
        url = (x.get('url_kartochki') or '').strip()
        if not re.fullmatch(r'\d{10}|\d{12}', inn) or not url:
            pri['нет ИНН или адреса карточки'] += 1
            continue
        t = re.sub(r'\s+', ' ', x.get('tekst') or '')
        if not t:
            pri['текст карточки не сохранён'] += 1
            continue
        m_l = _LICO.search(t)
        fio = (m_l.group(1).strip() if m_l else '')
        # цитата — окно вокруг блока, чтобы принадлежность номера человеку была видна
        citata = ''
        if m_l:
            i = m_l.start()
            citata = t[max(0, i - 40):i + 260]
        m_p = _POCHTA.search(t)
        m_t = _TEL.search(t)
        m_d = _DOLZH.search(t)
        dolzh = (m_d.group(1).strip()[:80] if m_d else '')
        raz = pb.razbor_url(url)
        if not raz:
            pri['ссылка не разбирается'] += 1
            continue
        if fio:
            s_fio += 1
        tel = cifry10(m_t.group(1) if m_t else '')
        if tel:
            cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,'
                        'dolzhnost,istochnik,source_url,domen,pervoistochnik,'
                        'data_nablyudeniya,quote,kto) values (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (inn, 'telefon', tel, fio[:200],
                         dolzh or 'контактное лицо закупки', raz[1], url, raz[0], raz[2],
                         '', citata[:300],
                         '1-я сессия, контактное лицо с карточки ЕИС (перепарсинг текста)'))
            s_tel += 1
        if m_p:
            adres = m_p.group(1).strip().strip('.,;')
            if '@' in adres:
                cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,'
                            'dolzhnost,istochnik,source_url,domen,pervoistochnik,'
                            'data_nablyudeniya,quote,kto) values (?,?,?,?,?,?,?,?,?,?,?,?)',
                            (inn, 'email', adres, fio[:200],
                             dolzh or 'контактное лицо закупки', raz[1], url, raz[0],
                             raz[2], '', citata[:300],
                             '1-я сессия, контактное лицо с карточки ЕИС (перепарсинг текста)'))
                s_mail += 1
        if fio:
            cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,'
                        'dolzhnost,istochnik,source_url,domen,pervoistochnik,'
                        'data_nablyudeniya,quote,kto) values (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (inn, 'chelovek', fio[:200], fio[:200],
                         dolzh or 'контактное лицо закупки', raz[1], url, raz[0], raz[2],
                         '', citata[:300],
                         '1-я сессия, контактное лицо с карточки ЕИС (перепарсинг текста)'))
        inny.add(inn)

p.commit()
print('карточек просмотрено %d | предприятий %d' % (vs, len(inny)))
print('  ФИО найдено ....... %d' % s_fio)
print('  телефонов ......... %d' % s_tel)
print('  почт .............. %d' % s_mail)
print('  пропуски:', dict(pri))
q = lambda s: cur.execute(s).fetchone()[0]
print('\nв contact_source теперь наблюдений с ФИО:',
      q("select count(*) from contact_source where coalesce(person,'')<>''"))
p.close()
