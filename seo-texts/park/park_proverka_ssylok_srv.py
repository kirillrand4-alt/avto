# -*- coding: utf-8 -*-
"""Приёмка ссылок-доказательств ГЛАЗАМИ (пункт 5 владельца), но с сервера.

Из песочницы ЕИС и Портал Москвы дают Connection reset, а `browser_probe` отдаёт всего
600 знаков шапки — по ним нельзя сказать, есть ли на странице заявленный факт. Здесь
страница открывается целиком и в её ТЕКСТЕ ищется ровно то, что мы про неё утверждаем:
ИНН, модель, заводской номер, номер закупки, ФИО, телефон.

Вход:  C:\\sender\\park_proverka_zadanie.json = [{"id","url","ishchem":{"метка":"строка"}}]
Выход: C:\\sender\\park_proverka_ssylok.jsonl (fsync построчно, резюмируемо по id)
"""
import json, os, re, sys, time

BAZA = r'C:\sender'
ZAD = os.path.join(BAZA, 'park_proverka_zadanie.json')
OUT = os.path.join(BAZA, 'park_proverka_ssylok.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
KAPCHA = ('smartcaptcha', 'captcha-api.yandex', 'g-recaptcha', 'cf-turnstile',
          'подтвердите, что вы человек', 'вы не робот')


def _hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


def _norm(s):
    """Сравнение без учёта регистра, пробелов и типа дефиса — «ГА55 plus» и «GA-55 Plus»
    на странице пишут как угодно."""
    s = (s or '').lower().replace('ё', 'е')
    s = re.sub(r'[\u2010-\u2015\u2212]', '-', s)
    return re.sub(r'[\s\-_.,;:«»"\'()]+', '', s)


def main():
    zad = json.load(open(ZAD, encoding='utf-8'))
    sdelano = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding='utf-8'):
            try:
                sdelano.add(str(json.loads(ln)['id']))
            except Exception:
                pass
    zad = [z for z in zad if str(z['id']) not in sdelano]
    itog = {'k_proverke': len(zad), 'otkrylos': 0, 'kapcha': 0, 'oshibok': 0}
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
        for z in zad:
            r = {'id': z['id'], 'url': z['url'], 'kto': z.get('kto', ''),
                 'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
            try:
                otv = page.goto(z['url'], timeout=70000, wait_until='domcontentloaded')
                page.wait_for_timeout(int(z.get('wait_ms', 6000)))
                r['http'] = otv.status if otv else None
                html = page.content()
                tekst = page.inner_text('body')
                r['title'] = (page.title() or '')[:150]
                r['znakov'] = len(tekst)
                nz = html.lower()
                r['kapcha'] = next((k for k in KAPCHA if k in nz), None)
                if r['kapcha']:
                    itog['kapcha'] += 1
                nt = _norm(tekst)
                r['nashli'] = {m: (_norm(v) in nt) for m, v in (z.get('ishchem') or {}).items() if v}
                r['tekst_nachalo'] = re.sub(r'\s+', ' ', tekst)[:400]
                itog['otkrylos'] += 1
            except Exception as e:
                r['oshibka'] = str(e)[:200]
                itog['oshibok'] += 1
            with open(OUT, 'a', encoding='utf-8') as f:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
        br.close()
    print(json.dumps(itog, ensure_ascii=False))


if __name__ == '__main__':
    main()
