# -*- coding: utf-8 -*-
r"""Замер: опознаёт ли роль ПО СНИМКУ лучше, чем по тексту, и сколько это стоит.

Вопрос владельца 14.08: «насколько удобнее будет делать опознавание через скрины
или дороже сильно выйдет». Отвечаем не мнением, а прогоном на одних и тех же
адресах: текстовому судье уже сдан кусок страницы, зрению отдаём снимок того же
места, дальше сверяем ответы и берём цену из счётчиков самого шлюза.

Модели сравниваем по паре: дешёвая рабочая и дорогая — чтобы видеть, покупается
ли точность деньгами.

    python roli_zrenie_zamer.py [папка_с_jpg] [модели через запятую]
"""
import base64
import json
import os
import re
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

ROLI = ('гл.инженер', 'гл.энергетик', 'гл.механик', 'техдиректор', 'нач.производства',
        'нач.цеха', 'инженер (не главный)', 'техконтакт', 'снабжение/закупки',
        'директор', 'продажи', 'приёмная', 'бухгалтерия', 'кадры', 'общий')

PROMPT = """На снимке — фрагмент сайта предприятия «%(name)s». Найди на нём адрес
%(email)s и определи, ЧЕЙ это ящик, по тому, что напечатано рядом.

Ответь ОДНОЙ ролью из списка: %(roli)s.

Правила, без которых ответ бесполезен:
1. Смотри на подпись РЯДОМ с адресом — в той же строке таблицы, в той же
   карточке, под тем же заголовком. Подпись из соседнего блока не считается.
2. Если рядом ничего нет или адрес стоит в общем блоке контактов — роль «общий».
   Пустое честнее правдоподобного.
3. Приёмная и секретариат — это «приёмная», отдел сбыта и коммерческий отдел —
   «продажи», снабжение, закупки, МТО — «снабжение/закупки».

Верни строго JSON: {"rol": "...", "dovod": "что написано рядом с адресом, дословно"}
"""


def _kartinka(put):
    with open(put, 'rb') as f:
        return base64.b64encode(f.read()).decode()


def sprosit(klient, model, put, karta):
    import gen_provider as GP
    soobshchenie = [{'role': 'user', 'content': [
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                     'data': _kartinka(put)}},
        {'type': 'text', 'text': PROMPT % {'name': karta.get('name', '')[:60],
                                           'email': karta['email'],
                                           'roli': ', '.join(ROLI)}},
    ]}]
    msg = GP.call(klient, soobshchenie, model=model, attempts=3)
    tekst = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    tekst = re.sub(r'```(?:json)?', '', tekst).strip()
    m = re.search(r'\{.*\}', tekst, re.S)
    otvet = {}
    if m:
        try:
            otvet = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            otvet = {}
    u = getattr(msg, 'usage', None)
    return {'rol': (otvet.get('rol') or '').strip(),
            'dovod': (otvet.get('dovod') or '')[:160],
            'vhod': getattr(u, 'input_tokens', 0) or 0,
            'vyhod': getattr(u, 'output_tokens', 0) or 0}


def progon(papka, modeli):
    import gen_provider as GP
    karty = {k['id']: k for k in json.load(open(os.path.join(papka, 'meta.json'),
                                                encoding='utf-8'))}
    klient = GP.make_client()
    itog = {'адресов': 0, 'модели': {}}
    stroki = []
    for ident in sorted(karty):
        put = os.path.join(papka, ident + '.jpg')
        if not os.path.exists(put):
            continue
        karta = karty[ident]
        itog['адресов'] += 1
        stroka = {'id': ident, 'email': karta['email'], 'nasha': karta['nasha'],
                  'sudya_tekst': karta['sudya'], 'klass': karta['klass'],
                  'url': karta['url'], 'zrenie': {}}
        for model in modeli:
            try:
                r = sprosit(klient, model, put, karta)
            except Exception as e:  # noqa: BLE001
                r = {'rol': '', 'dovod': 'сбой: %s' % str(e)[:90], 'vhod': 0, 'vyhod': 0}
            stroka['zrenie'][model] = r
            m = itog['модели'].setdefault(model, {'вход': 0, 'выход': 0, 'сбоев': 0,
                                                  'совпало_с_нами': 0, 'совпало_с_судьёй': 0})
            m['вход'] += r['vhod']
            m['выход'] += r['vyhod']
            if not r['rol']:
                m['сбоев'] += 1
            if r['rol'] == karta['nasha']:
                m['совпало_с_нами'] += 1
            if r['rol'] == karta['sudya']:
                m['совпало_с_судьёй'] += 1
        stroki.append(stroka)
    itog['строки'] = stroki
    return itog


def main():
    papka = sys.argv[1] if len(sys.argv) > 1 else r'C:\sender\_tmp\zamer_zrenie'
    modeli = (sys.argv[2].split(',') if len(sys.argv) > 2
              else ['claude-haiku-4-5', 'claude-opus-4-8'])
    itog = progon(papka, modeli)
    put = r'C:\sender\zamer_zrenie.json'
    with open(put, 'w', encoding='utf-8') as f:
        json.dump(itog, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    kratko = {'адресов': itog['адресов'], 'модели': itog['модели'], 'файл': put}
    print(json.dumps(kratko, ensure_ascii=False))


if __name__ == '__main__':
    main()
