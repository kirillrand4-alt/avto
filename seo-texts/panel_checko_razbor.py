# -*- coding: utf-8 -*-
"""Разбор скачанных страниц checko.ru (panel_checko_sbor.py) в поля карточки панели Meyer.

Вход: архив checko-meyer-html.zip (gzip-HTML: <ИНН>.html.gz и <ИНН>-kontakty.html.gz).
Выход: JSON {ИНН: поля} – адрес, руководитель, статус ЕГРЮЛ, ССЧ с годом, выручка и чистая
прибыль за последний год отчётности (точные числа из данных графика страницы), телефоны,
почты и сайты из блока контактов. Только то, что есть на странице; ИНН страницы обязан
совпасть с запрошенным (иначе запись помечается и не заливается).
Запуск: python3 panel_checko_razbor.py <архив.zip> <выход.json>
"""
import gzip
import html as H
import io
import json
import re
import sys
import zipfile

MES = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
       'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}


def chist(s):
    s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s or '')
    return re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def sekciya(h, imya):
    m = re.search(r'<section id="%s"' % imya, h)
    if not m:
        return ''
    k = h.find('<section id="', m.end())
    return h[m.start():k if k > 0 else len(h)]


def data_ru(s):
    m = re.search(r'(\d{1,2}) ([а-я]+) (\d{4})', s or '')
    if m and m.group(2) in MES:
        return '%02d.%02d.%s' % (int(m.group(1)), MES[m.group(2)], m.group(3))
    return ''


def finansy(h):
    m = re.search(r'window\.FS_HUGE=\{years:(\[[^\]]*\]),last_year:"(\d{4})",rows:', h)
    if not m:
        return {}
    gody = json.loads(m.group(1))
    i, glub = m.end(), 0
    for j in range(i, min(len(h), i + 200000)):
        if h[j] == '[':
            glub += 1
        elif h[j] == ']':
            glub -= 1
            if glub == 0:
                break
    stroki = json.loads(h[i:j + 1])
    if len(stroki) != len(gody):
        return {'fin_oshibka': 'годов %d, строк %d' % (len(gody), len(stroki))}
    out = {}
    # последний год, где есть выручка или прибыль
    for god, r in sorted(zip(gody, stroki), key=lambda x: x[0], reverse=True):
        v, p = (r[0] if len(r) > 0 else None), (r[3] if len(r) > 3 else None)
        if v is not None or p is not None:
            out = {'fin_god': god, 'vyruchka': v, 'pribyl': p}
            break
    out['fin_gody'] = {g: [r[0] if len(r) > 0 else None, r[3] if len(r) > 3 else None] for g, r in zip(gody, stroki)}
    return out


def rukovoditel(h):
    s = sekciya(h, 'management') or h
    m = re.search(r'<div class="fw-700">([^<]{3,120})(?:<a [^>]*></a>)?</div>\s*<a class="link" href="/(person|company|entrepreneur)/([^"]+)">([^<]+)</a>'
                  r'(.{0,1200}?)</div>\s*</div>', s, re.S)
    if not m:
        # управляющая организация вместо руководителя-человека
        zag = re.search(r'<h2 class="header[^"]*"><a [^>]*>([^<]+)</a></h2>', s)
        u = re.search(r'<a class="link" href="/company/([^"]+)">([^<]+)</a>(.{0,1500}?)</div>\s*<div class="col-12', s, re.S)
        if zag and 'Управляющ' in zag.group(1) and u:
            hvost = chist(u.group(3))
            inn = re.search(r'ИНН (\d{10,12})', hvost)
            s_daty = re.search(r'с (\d{1,2} [а-я]+ \d{4})', hvost)
            return {'ruk_fio': chist(u.group(2)), 'ruk_dolzhnost': 'управляющая организация', 'ruk_inn': inn.group(1) if inn else '',
                    'ruk_s': data_ru(s_daty.group(1)) if s_daty else '', 'ruk_vid': 'company', 'rukovoditeley': 1}
        return {}
    dolzh = chist(m.group(1))
    imya = chist(m.group(4))
    hvost = chist(m.group(5))
    inn = re.search(r'ИНН (\d{10,12})', hvost)
    s_daty = re.search(r'с (\d{1,2} [а-я]+ \d{4})', hvost)
    vse = len(re.findall(r'<div class="fw-700">[^<]{3,120}(?:<a [^>]*></a>)?</div>\s*<a class="link" href="/(?:person|company|entrepreneur)/', s))
    return {'ruk_fio': imya, 'ruk_dolzhnost': dolzh, 'ruk_inn': inn.group(1) if inn else '',
            'ruk_s': data_ru(s_daty.group(1)) if s_daty else '', 'ruk_vid': m.group(2), 'rukovoditeley': vse}


def kontakty(blok):
    tel, poch, sayty = [], [], []
    for m in re.finditer(r'href="tel:([^"]+)"[^>]*>([^<]+)</a>(\s*<span[^>]*>([^<]*)</span>)?', blok):
        t = chist(m.group(2))
        if t and t not in [x[0] for x in tel]:
            tel.append([t, chist(m.group(4) or '')])
    for m in re.finditer(r'href="mailto:([^"]+)"[^>]*>([^<]+)</a>(\s*<span[^>]*>([^<]*)</span>)?', blok):
        e = chist(m.group(2)).lower()
        if e and e not in [x[0] for x in poch]:
            poch.append([e, chist(m.group(4) or '')])
    for m in re.finditer(r'<a [^>]*class="link"[^>]*href="(https?://[^"]+)"[^>]*>([^<]+)</a>', blok):
        u = chist(m.group(2))
        if re.match(r'^[\w.\-]+\.[a-zа-я]{2,}$', u, re.I) and 'checko' not in u and u not in sayty:
            sayty.append(u)
    return tel, poch, sayty


def odna(h, inn, h_kont=None):
    z = {}
    m = re.search(r'id="copy-inn"[^>]*>(\d{10,12})<', h)
    z['inn_stranicy'] = m.group(1) if m else ''
    if z['inn_stranicy'] != inn:
        z['oshibka'] = 'на странице ИНН %s' % (z['inn_stranicy'] or 'не найден (не карточка компании)')
        return z
    m = re.search(r'id="copy-ogrn"[^>]*>(\d{13,15})<', h)
    z['ogrn'] = m.group(1) if m else ''
    i = h.find('id="copy-ogrn"')
    shapka = h[max(0, i - 3000):i]
    shapka = shapka[shapka.rfind('<div class="bs-row gy-2 gx-4">'):] if '<div class="bs-row gy-2 gx-4">' in shapka else shapka
    st = re.search(r'<div class="([^"]*fw-600[^"]*)"([^>]*)>(.*?)</div>(\s*<div class="text-secondary">([^<]+)</div>)?', shapka, re.S)
    z['status'] = (chist(st.group(3)) + ((' ' + chist(st.group(5))) if st.group(5) else '')) if st else ''
    z['status_cvet'] = (re.search(r'text-([a-z]+)', st.group(1)).group(1) if st and 'text-' in st.group(1)
                        else (re.search(r'color:([^;"]+)', st.group(2)).group(1) if st and 'color:' in st.group(2) else '')) if st else ''
    m = re.search(r'Правопреемник</div>\s*<div><a class="link" href="/company/(\d+)">([^<]+)</a>', shapka)
    if m:
        z['pravopreemnik'] = chist(m.group(2))
        z['pravopreemnik_ogrn'] = m.group(1)
    m = re.search(r'<span id="copy-address"[^>]*>(.*?)</span>', h, re.S)
    z['adres'] = chist(m.group(1)) if m else ''
    m = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
    z['naim'] = chist(m.group(1)) if m else ''
    m = re.search(r'Дата регистрации</div>\s*<div>([^<]+)', h)
    z['data_reg'] = data_ru(m.group(1)) if m else ''
    m = re.search(r'Среднесписочная численность работников</div>\s*<div>([\d\s ]+)человек(.{0,600}?)'
                  r'Согласно данным ФНС за (\d{4}) год', h, re.S)
    if m:
        z['ssch'] = int(re.sub(r'\D', '', m.group(1)))
        z['ssch_god'] = m.group(3)
    z.update(rukovoditel(h))
    z.update(finansy(h))
    blok = sekciya(h, 'contacts')
    if not blok:
        r = h.find('<section id="rating"')
        blok = h[:r] if r > 0 else ''
        z['kontakty_iz'] = 'шапка страницы'
    tel, poch, sayty = kontakty(blok)
    if h_kont:
        t2, p2, s2 = kontakty(re.sub(r'(?s)^.*?<main', '<main', h_kont))
        for a, b in ((tel, t2), (poch, p2)):
            for x in b:
                if x[0] not in [y[0] for y in a]:
                    a.append(x)
        sayty += [x for x in s2 if x not in sayty]
        z['kontakty_stranica'] = True
    z['telefony'], z['pochty'], z['sayty'] = tel, poch, sayty
    m = re.search(r'href="(/company/\d{13}/contacts)">Еще (\d+)', h)
    z['eshche_na_kontaktah'] = int(m.group(2)) if m else 0
    return z


def main(arh, vyhod):
    z = zipfile.ZipFile(arh)
    imena = set(z.namelist())
    out = {}
    for f in sorted(imena):
        if not f.endswith('.html.gz') or '-kontakty' in f:
            continue
        inn = f.split('.')[0]
        h = gzip.decompress(z.read(f)).decode('utf-8', 'replace')
        hk = None
        if inn + '-kontakty.html.gz' in imena:
            hk = gzip.decompress(z.read(inn + '-kontakty.html.gz')).decode('utf-8', 'replace')
        try:
            out[inn] = odna(h, inn, hk)
        except Exception as e:  # noqa: BLE001
            out[inn] = {'oshibka': 'разбор: ' + repr(e)[:200]}
    io.open(vyhod, 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=0))
    return out


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
