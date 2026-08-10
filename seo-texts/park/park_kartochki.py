# -*- coding: utf-8 -*-
"""Второй этап оси РАСХОДА ГАЗА: с карточки закупки снимаем ИНН заказчика.

Почему не по справочнику: замерено — из 1 621 закупки по имени заказчика сопоставилось
3%. Покупатели газа это больницы, водоканалы, институты; базы владельца (компрессорные,
162 440 юрлиц) их не содержат. ИНН есть на самой карточке ЕИС — берём оттуда.

Формы адреса проверены на сервере пробами:
  11 цифр -> /223/purchase/public/purchase/info/common-info.html?regNumber=  (7 из 8 ок)
  19 цифр -> /epz/order/notice/ea44/view/common-info.html?regNumber=         (3 из 3 ок)
Форма /epz/order/notice/notice-info/... даёт 404 — её не используем.

Долговечность: C:\\sender\\park_gaz_inn.jsonl построчно с fsync, резюмируемо по номеру.
"""
import json, os, re, sys, time

BAZA = r'C:\sender'
# panel_py окружение не передаёт (проверено: пришло 0 к снятию), поэтому пути — аргументами
VHOD = os.path.join(BAZA, sys.argv[2] if len(sys.argv) > 2 else 'park_gaz.jsonl')
OUT = os.path.join(BAZA, sys.argv[3] if len(sys.argv) > 3 else 'park_gaz_inn.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
_INN = re.compile(r'ИНН\s*[:№]?\s*(\d{10}|\d{12})')
# у 44-ФЗ ИНН на карточке НЕ печатают (замер: 0 из 7), но есть ссылка на организацию.
# Код организации переиспользуется между лотами — держим кэш, больницы повторяются.
_ORGKOD = re.compile(r'organizationCode=(\d{6,})')
ORG_STRANICA = 'https://zakupki.gov.ru/epz/organization/view/info.html?organizationCode=%s'
_KPP = re.compile(r'КПП\s*[:№]?\s*(\d{9})')
# Контактный блок карточки/организации. У газового сегмента (587 предприятий) контакт
# сейчас есть у 43 — а он лежит прямо здесь, на той же странице, что и ИНН.
_FIO = re.compile(r'(?:Контактное лицо|Ответственное должностное лицо|Ф\.?И\.?О\.?)\s*'
                  r'([А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+)?)')
# Замер на 304 карточках: прежний шаблон склеивал ДВА номера подряд
# («79149511774 45095010652»), потому что пробел входил в класс символов.
# Теперь номер — непрерывная группа, а пробел допускаем только внутри скобок/разделителей
# и проверяем длину цифрами уже после.
_TEL = re.compile(r'(?:Телефон|Контактный телефон)\s*:?\s*'
                  r'([+\d][\d\s()\-]{9,24}\d)')
_FIO2 = re.compile(r'([А-ЯЁ][а-яё-]{2,}\s+[А-ЯЁ][а-яё-]{2,}(?:\s+[А-ЯЁ][а-яё-]{2,})?)')


def _telefon(t):
    m = _TEL.search(t or '')
    if not m:
        return ''
    c = re.sub(r'\D', '', m.group(1))
    if len(c) > 11:
        c = c[:11]
    return c if len(c) >= 10 else ''


def _fio(t):
    m = _FIO.search(t or '')
    if m:
        return m.group(1)
    # запасной ход: имя стоит СРАЗУ ПОСЛЕ слова «лицо» без двоеточия
    m = re.search(r'лицо\s+' + _FIO2.pattern, t or '')
    return m.group(1) if m else ''
_MAIL = re.compile(r'[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'.replace('%%', '%'))


def _hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


def adres(nomer):
    if len(nomer) == 11:
        return ('https://zakupki.gov.ru/223/purchase/public/purchase/info/'
                'common-info.html?regNumber=' + nomer)
    return ('https://zakupki.gov.ru/epz/order/notice/ea44/view/'
            'common-info.html?regNumber=' + nomer)


def main():
    predel = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    zad = []
    vidennye = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding='utf-8'):
            try:
                vidennye.add(json.loads(ln)['nomer'])
            except Exception:
                pass
    for ln in open(VHOD, encoding='utf-8'):
        if not ln.strip():
            continue
        r = json.loads(ln)
        n = r.get('nomer') or ''
        if n and n not in vidennye and len(n) in (11, 19):
            vidennye.add(n)
            zad.append(r)
        if len(zad) >= predel:
            break
    itog = {'k_snyatiyu': len(zad), 'otkrylos': 0, 'inn_snyat': 0, 'bez_inn': 0, 'oshibok': 0}
    if not zad:
        print(json.dumps(itog, ensure_ascii=False))
        return
    from playwright.sync_api import sync_playwright
    exe = _hrom()
    with sync_playwright() as p:
        kw = {'headless': True, 'args': ['--no-sandbox',
                                         '--disable-blink-features=AutomationControlled']}
        if exe:
            kw['executable_path'] = exe
        br = p.chromium.launch(**kw)
        ctx = br.new_context(user_agent=UA, locale='ru-RU',
                             viewport={'width': 1366, 'height': 900},
                             ignore_https_errors=True)
        page = ctx.new_page()
        kesh_org = {}
        for r in zad:
            n = r['nomer']
            u = adres(n)
            out = {'nomer': n, 'url_kartochki': u, 'zakazchik_iz_lenty': r.get('zakazchik'),
                   'predmet': r.get('predmet'), 'zapros': r.get('zapros'),
                   'os': 'расход газа', 'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'kto': '1-я сессия, карточка ЕИС через серверный браузер'}
            try:
                otv = page.goto(u, timeout=60000, wait_until='domcontentloaded')
                page.wait_for_timeout(2200)
                out['http'] = otv.status if otv else None
                t = page.inner_text('body')
                itog['otkrylos'] += 1
                inn = _INN.findall(t)
                out['inn_vse'] = list(dict.fromkeys(inn))[:5]
                out['inn'] = inn[0] if inn else ''
                kpp = _KPP.findall(t)
                out['kpp'] = kpp[0] if kpp else ''
                out['nomer_na_stranice'] = n in t.replace(' ', '')
                t1 = re.sub(r'\s+', ' ', t)
                out['tekst'] = t1[:4000]
                mm = _MAIL.search(t1)
                out['kontakt_fio'] = _fio(t1)
                out['kontakt_tel'] = _telefon(t1)
                out['kontakt_email'] = mm.group(0) if mm else ''
                if not out['inn']:
                    # 44-ФЗ: идём на страницу организации-заказчика
                    kod = _ORGKOD.search(page.content() or '')
                    if kod:
                        k = kod.group(1)
                        out['org_kod'] = k
                        if k in kesh_org:
                            out['inn'], out['org_imya'] = kesh_org[k]
                            out['inn_otkuda'] = 'страница организации (из кэша)'
                        else:
                            try:
                                page.goto(ORG_STRANICA % k, timeout=60000,
                                          wait_until='domcontentloaded')
                                page.wait_for_timeout(1800)
                                to = page.inner_text('body')
                                ii = _INN.findall(to)
                                imya = ''
                                mi = re.search(r'Полное наименование\s*(.{5,180}?)\s{2,}', to)
                                if mi:
                                    imya = mi.group(1).strip()
                                t1o = re.sub(r'\s+', ' ', to)
                                mm = _MAIL.search(t1o)
                                if not out.get('kontakt_fio'): out['kontakt_fio'] = _fio(t1o)
                                if not out.get('kontakt_tel'): out['kontakt_tel'] = _telefon(t1o)
                                if not out.get('kontakt_email') and mm: out['kontakt_email'] = mm.group(0)
                                kesh_org[k] = (ii[0] if ii else '', imya)
                                out['inn'], out['org_imya'] = kesh_org[k]
                                out['inn_otkuda'] = 'страница организации ЕИС'
                            except Exception as e:
                                out['org_oshibka'] = str(e)[:120]
                else:
                    out['inn_otkuda'] = 'карточка закупки'
                if out['inn']:
                    itog['inn_snyat'] += 1
                else:
                    itog['bez_inn'] += 1
            except Exception as e:
                out['oshibka'] = str(e)[:180]
                itog['oshibok'] += 1
            with open(OUT, 'a', encoding='utf-8') as f:
                f.write(json.dumps(out, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
        br.close()
    print(json.dumps(itog, ensure_ascii=False))


if __name__ == '__main__':
    main()
