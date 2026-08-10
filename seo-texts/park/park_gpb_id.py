# -*- coding: utf-8 -*-
"""Ищем внутренний id лота на ЭТП ГПБ, чтобы починить 4 351 факт.

Сейчас у этих фактов ссылка вида `etpgpb.ru/procedures/?search=ГП415801`. Проверено:
страница отдаёт 200 и общую ленту («146 предложений»), номера лота на ней нет — то есть
доказательства она не открывает. В адресе карточки у площадки стоит ВНУТРЕННИЙ id,
а у нас в базе реестровый номер площадки.

Пробуем по порядку, каждый шаг с замером:
  1. применяет ли площадка параметр поиска вообще (есть ли номер в HTML);
  2. какие ссылки /procedures/<id> есть на странице и сколько их;
  3. работают ли другие имена параметра (number, q, text, registryNumber);
  4. отдаёт ли что-то внутренний поиск площадки по api.

Ничего не вписываем в базу — только отчёт. Вписывать буду, когда форма подтвердится.
"""
import json, os, re, sys, time, urllib.parse

BAZA = r'C:\sender'
OUT = os.path.join(BAZA, 'park_gpb_id.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
NOMERA = ['ГП415801', 'ГП339353', 'ГП026024', 'АП007945']
PARAMY = ['search', 'number', 'q', 'text', 'registryNumber', 'procedureNumber']
_PROC = re.compile(r'/procedures/(\d{4,})')


def _hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


def main():
    itog = []
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
        for nom in NOMERA[:2]:
            for par in PARAMY:
                u = 'https://etpgpb.ru/procedures/?%s=%s' % (par, urllib.parse.quote(nom))
                r = {'nomer': nom, 'parametr': par, 'url': u}
                try:
                    otv = page.goto(u, timeout=60000, wait_until='domcontentloaded')
                    page.wait_for_timeout(4500)
                    r['http'] = otv.status if otv else None
                    html = page.content()
                    t = re.sub(r'\s+', ' ', page.inner_text('body'))
                    ids = list(dict.fromkeys(_PROC.findall(html)))
                    r['nomer_v_html'] = nom in html
                    r['nomer_v_tekste'] = nom in t
                    r['ssylok_na_procedury'] = len(ids)
                    r['id_pervye'] = ids[:5]
                    m = re.search(r'(\d[\d\s]{0,6})\s*предложени', t)
                    r['skolko_predlozheniy'] = m.group(1).strip() if m else None
                except Exception as e:
                    r['oshibka'] = str(e)[:160]
                itog.append(r)
                with open(OUT, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
                    f.flush()
                    os.fsync(f.fileno())
        # если номер где-то нашёлся — открываем найденный id и смотрим, тот ли это лот
        nashli = [r for r in itog if r.get('nomer_v_html') and r.get('id_pervye')]
        for r in nashli[:2]:
            u = 'https://etpgpb.ru/procedures/%s' % r['id_pervye'][0]
            pr = {'proverka_kartochki': u, 'nomer': r['nomer']}
            try:
                otv = page.goto(u, timeout=60000, wait_until='domcontentloaded')
                page.wait_for_timeout(4000)
                t = re.sub(r'\s+', ' ', page.inner_text('body'))
                pr['http'] = otv.status if otv else None
                pr['nomer_na_kartochke'] = r['nomer'] in t
                pr['nachalo'] = t[:300]
            except Exception as e:
                pr['oshibka'] = str(e)[:160]
            itog.append(pr)
            with open(OUT, 'a', encoding='utf-8') as f:
                f.write(json.dumps(pr, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
        br.close()
    print(json.dumps(itog, ensure_ascii=False)[:5500])


if __name__ == '__main__':
    main()
