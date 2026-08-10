# -*- coding: utf-8 -*-
"""Открывает карточку организации ЕИС и записывает ссылку ТОЛЬКО при совпадении ИНН.

Разрыв, который это закрывает: машина доказана у 95 % фактов выдачи, а машина вместе с ИНН —
у 63 %. Причина не в данных: извещение 44-ФЗ печатает название заказчика, но не ИНН. ИНН
лежит на карточке организации, и её адрес выводится из реестрового номера (первые 11 цифр —
код организации).

Записывать вслепую нельзя: код принадлежит тому, кто РАЗМЕЩАЕТ закупку, а это часто
уполномоченный орган (75 администраций и центров закупок уже пришлось убрать из выдачи).
Поэтому здесь страница ОТКРЫВАЕТСЯ, с неё снимаются все ИНН, и наружу идёт вердикт:
совпал ИНН факта или нет. Ссылку в базу пишет уже приёмник, и только по совпадению.

Заодно проверяется форма 3-й сессии — поиск организации по ИНН
(`epz/organization/search/results.html?searchString=<ИНН>`): она утверждает, что там видны и
ИНН, и название. У меня к поисковым страницам ЕИС доверия нет (выдача закупок рисуется
скриптом и пуста в теле), так что это надо увидеть, а не принять на слово.

Задание: C:\\sender\\_kartaorg.json — список {fakt_id, inn, kod, url}.
Результат целиком: PARK-1S-KARTAORG-RAZBOR.json на дропе; в stdout — сводка.
"""
import io, json, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_kartaorg.json'
# РАБОЧАЯ запись идёт в C:\sender, на дроп кладётся ОДИН раз в конце. Прямая запись в
# хранилище дропа на каждой карточке уронила прогон на 51-й: я в этот момент скачивал файл
# клиентом, и os.replace получил «file is being used by another process».
RABOCHIY = r'C:\sender\park_kartaorg.json'
DROP = r'C:\seostat\drop\drop-storage\PARK-1S-KARTAORG-RAZBOR.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
INN = re.compile(r'(?<!\d)(\d{10}|\d{12})(?!\d)')
# ИНН СЧИТАЕМ ТОЛЬКО ТОТ, ЧТО СТОИТ ПОСЛЕ СЛОВА «ИНН». Поиск ЕИС сверяет строку не только с
# ИНН, но и с ОГРН: выдуманный 9999999999 «находит» тестовую организацию, потому что эти
# цифры входят в её ОГРН 9999999999986. Простое вхождение цифр в текст — негодный признак,
# это показала 3-я сессия снимками, и мой замер её подтвердил.
POSLE_INN = re.compile(r'ИНН\s*[:№]?\s*(\d{10,12})')
SKOLKO = int(sys.argv[1]) if len(sys.argv) > 1 else 120


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


def sdelano():
    if not os.path.exists(RABOCHIY):
        return {}
    try:
        return {r['fakt_id']: r for r in json.load(open(RABOCHIY, encoding='utf-8'))}
    except Exception:  # noqa: BLE001
        return {}


zad = json.load(open(ZAD, encoding='utf-8'))
gotovo = sdelano()
ochered = [z for z in zad if z['fakt_id'] not in gotovo][:SKOLKO]
from playwright.sync_api import sync_playwright

out = list(gotovo.values())
itog = {'проверено': 0, 'ИНН совпал': 0, 'чужой ИНН': 0, 'ИНН на странице нет': 0, 'ошибок': 0}
exe = hrom()
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    if exe:
        kw['executable_path'] = exe
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for z in ochered:
        r = {'fakt_id': z['fakt_id'], 'inn': z['inn'], 'url': z['url']}
        try:
            for popytka in range(3):
                try:
                    otv = pg.goto(z['url'], timeout=90000, wait_until='domcontentloaded')
                    break
                except Exception:
                    if popytka == 2:
                        raise
                    pg.wait_for_timeout(4000 * (popytka + 1))
            pg.wait_for_timeout(2000)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            nayd = sorted(set(INN.findall(t)))
            posle = POSLE_INN.findall(t)
            r['inn_na_stranice'] = nayd[:5]
            r['posle_slova_inn'] = posle[:5]
            # строгий признак: наш ИНН напечатан именно как реквизит
            r['sovpal'] = z['inn'] in posle
            imya = re.search(r'(?:Полное наименование|Наименование)\s+(.{0,110}?)(?:\s+ИНН|\s+Сокращ|$)', t)
            r['imya'] = imya.group(1).strip() if imya else t[:80]
            itog['проверено'] += 1
            if r['sovpal']:
                itog['ИНН совпал'] += 1
            elif nayd:
                itog['чужой ИНН'] += 1
            else:
                itog['ИНН на странице нет'] += 1
        except Exception as e:  # noqa: BLE001
            r['oshibka'] = str(e)[:140]
            itog['ошибок'] += 1
        out.append(r)
        with open(RABOCHIY + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(RABOCHIY + '.tmp', RABOCHIY)
    # ПРОБА ФОРМЫ 3-й СЕССИИ: поиск организации по ИНН
    proba = []
    for z in ochered[:3]:
        u = ('https://zakupki.gov.ru/epz/organization/search/results.html?searchString='
             + z['inn'])
        try:
            otv = pg.goto(u, timeout=90000, wait_until='domcontentloaded')
            pg.wait_for_timeout(2500)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            proba.append({'inn': z['inn'], 'http': otv.status if otv else None,
                          'знаков': len(t), 'ИНН в теле': z['inn'] in t,
                          'кусок': t[:160]})
        except Exception as e:  # noqa: BLE001
            proba.append({'inn': z['inn'], 'ошибка': str(e)[:120]})
    br.close()

import shutil
shutil.copyfile(RABOCHIY, DROP + '.tmp')
os.replace(DROP + '.tmp', DROP)
print(json.dumps(itog, ensure_ascii=False))
print('всего в разборе: %d' % len(out))
print('=== проба формы 3-й сессии (поиск организации по ИНН) ===')
for x in proba:
    print('  ' + json.dumps(x, ensure_ascii=False)[:300])
print('полный разбор: PARK-1S-KARTAORG-RAZBOR.json на дропе')
