# -*- coding: utf-8 -*-
"""Разбор страниц, скачанных probe.py (приёмы 2 и 3).

Считаем по каждому пути: сколько доменов ответили страницей, на скольких есть телефон,
почта, техническая должность. Телефон и почта — регуляркой (правило 6), связка
«имя-должность-чей номер» уходит провайдеру отдельным шагом.
"""
import json
import os
import re
import collections

D = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad/pr3'
LENS = '/home/user/avto/seo-texts/engineers-lens'
PH = re.compile(r'(?:\+7|\b8|\b7)[\s\-‐-―().]{0,3}\(?\d{3,5}\)?[\s\-‐-―().]{0,3}'
                r'\d{2,3}[\s\-‐-―().]{0,3}\d{2}[\s\-‐-―().]{0,3}\d{2}\b')
EM = re.compile(r'[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
TAG = re.compile(r'<[^>]+>')
SCRIPT = re.compile(r'<(script|style)\b.*?</\1>', re.S | re.I)
# должности: полные словоформы (ловушка В16 — обрезанная основа даёт ноль)
ROLE = re.compile(r'(?i)главн\w*\s+инженер\w*|главн\w*\s+механик\w*|главн\w*\s+энергетик\w*|'
                  r'技', re.U)
ROLES = [('главный инженер', r'главн\w{0,3}\s+инженер\w{0,3}'),
         ('главный механик', r'главн\w{0,3}\s+механик\w{0,3}'),
         ('главный энергетик', r'главн\w{0,3}\s+энергетик\w{0,3}'),
         ('технический директор', r'техническ\w{0,3}\s+директор\w{0,3}'),
         ('начальник цеха', r'начальник\w{0,3}\s+\w*\s*цеха'),
         ('начальник компрессорной', r'начальник\w{0,3}\s+компрессорн\w{0,3}'),
         ('ОГМ/ОГЭ', r'\bОГМ\b|\bОГЭ\b|отдел\w{0,3}\s+главного\s+механика|'
                     r'отдел\w{0,3}\s+главного\s+энергетика'),
         ('КИПиА', r'КИПиА|КИП\s?и\s?А'),
         ('энергетик', r'\bэнергетик\w{0,3}\b'),
         ('механик', r'\bмеханик\w{0,3}\b'),
         ('заместитель главного', r'заместител\w{0,3}\s+главного'),
         ('отдел кадров/HR', r'отдел\w{0,3}\s+кадров|кадров\w{0,3}\s+служб|HR[- ]|рекрут')]
ROLES = [(n, re.compile(rx, re.I | re.U)) for n, rx in ROLES]
FIO = re.compile(r'\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}(?:вич|вна|чна|ична)\b|'
                 r'\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.')


def norm(s):
    d = re.sub(r'\D', '', s)
    if len(d) == 11 and d[0] == '8':
        d = '7' + d[1:]
    if len(d) == 10:
        d = '7' + d
    return d if len(d) == 11 and d[0] == '7' else None


def plohoy(d):
    t = d[1:]
    return len(set(t)) <= 2 or t in '01234567890123456789'


def read(p):
    b = open(p, 'rb').read()
    for e in ('utf-8', 'cp1251'):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode('utf-8', 'replace')


def phones(s):
    o = set()
    for m in PH.finditer(s):
        d = norm(m.group(0))
        if d and not plohoy(d):
            o.add(d)
    return o


def nash_korpus():
    ours = set()
    for dp, dn, fn in os.walk(LENS):
        for f in fn:
            if f.lower().endswith(('.csv', '.md', '.json', '.txt')):
                try:
                    ours |= phones(read(os.path.join(dp, f)))
                except Exception:
                    pass
    return ours


def main():
    ours = nash_korpus()
    probe = json.load(open(D + '/probe.json'))
    kk = json.load(open(D + '/kontrol.json'))
    myagkiy = {o['domain'] for o in kk if o['kontrol_code'] == '200' and o['kontrol_size'] > 1500}
    probe = [r for r in probe if r['domain'] not in myagkiy]
    print('исключено доменов с мягким 404:', len(myagkiy))
    by = collections.defaultdict(lambda: {'otvet': 0, 'tel': 0, 'mail': 0, 'rol': 0,
                                          'fio': 0, 'novyh_tel': 0})
    rows = []
    for r in probe:
        if not r['file']:
            continue
        p = os.path.join(D, 'pages', r['file'])
        if not os.path.exists(p):
            continue
        h = read(p)
        txt = TAG.sub(' ', SCRIPT.sub(' ', h))
        txt = re.sub(r'&nbsp;?', ' ', txt)
        txt = re.sub(r'[ \t ]+', ' ', txt)
        # телефоны берём и из склеенного (строчные теги рвут номер) и из tel:
        glue = TAG.sub(' ', SCRIPT.sub(' ', re.sub(
            r'</?(span|b|strong|em|i|a|font|wbr|nobr|sup|sub|u|small)\b[^>]*>', '', h)))
        tel = phones(txt) | phones(glue)
        for m in re.finditer(r'href\s*=\s*["\']tel:([^"\']{5,40})["\']', h, re.I):
            d = norm(m.group(1))
            if d and not plohoy(d):
                tel.add(d)
        mails = set(x.lower() for x in EM.findall(h)
                    if not x.lower().endswith(('.png', '.jpg', '.gif', '.js', '.css')))
        roli = [n for n, rx in ROLES if rx.search(txt)]
        fios = set(FIO.findall(txt))
        novye = tel - ours
        k = by[r['path']]
        k['otvet'] += 1
        k['tel'] += 1 if tel else 0
        k['mail'] += 1 if mails else 0
        k['rol'] += 1 if [x for x in roli if x != 'отдел кадров/HR'] else 0
        k['fio'] += 1 if fios else 0
        k['novyh_tel'] += len(novye)
        rows.append({'domain': r['domain'], 'path': r['path'], 'size': r['size'],
                     'tel': sorted(tel), 'novye_tel': sorted(novye),
                     'mail': sorted(mails)[:12], 'roli': roli,
                     'fio': sorted(fios)[:12], 'file': r['file']})
    json.dump(rows, open(D + '/razbor.json', 'w'), ensure_ascii=False, indent=1)
    print('страниц разобрано:', len(rows), '| корпус наших телефонов:', len(ours))
    print(f'{"путь":28} {"ответ":>5} {"тел":>5} {"почта":>6} {"роль":>5} {"ФИО":>5} {"новых тел":>9}')
    for p, k in sorted(by.items(), key=lambda x: -x[1]['otvet']):
        print(f'{p:28} {k["otvet"]:5} {k["tel"]:5} {k["mail"]:6} {k["rol"]:5} {k["fio"]:5} {k["novyh_tel"]:9}')
    vs = set()
    for r in rows:
        vs |= set(r['novye_tel'])
    print('ВСЕГО новых телефонов (нет ни в одном файле engineers-lens):', len(vs))


main()
