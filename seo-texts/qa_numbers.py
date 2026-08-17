# -*- coding: utf-8 -*-
"""Механическая сверка КАЖДОГО числа текста с payload страницы и базой знаний.

Зачем. Мех-гейт qa_text проверяет форму (тире, стоп-слова, объём, ссылки), но не
проверяет, откуда взялось число. Семантические линзы стоят денег и до 17.08 звались
на каждой 6-й странице. В зазоре между ними корпус набрал выдуманную фактуру:
замер 17.08 по 759 страницам дал 277 страниц (37%) минимум с одним числом, которого
нет в payload - сроки поставки на 142 страницах, экономика в процентах на 176,
децибелы на 21.

Проверка бесплатная (регулярки, без API) и ставится в цикл генерации рядом с
qa_text.check, то есть на КАЖДУЮ страницу, а не на каждую шестую.

Использование:
    from qa_numbers import check_numbers
    issues = check_numbers(text_html, payload, brand_facts=kb_record)

Идея простая: собрать все числа, которые страница имеет право называть (payload +
запись бренда из базы знаний + узаконенные стайлгайдом правила-константы), и
показать те, которых в этом множестве нет.
"""
import json
import re

# Числа, которые стайлгайд и REFINEMENT разрешают называть без payload:
# это правила подбора, а не факты о товаре.
SANCTIONED_RULES = {
    '15', '20',      # запас 15-20% к расходу (пул FAQ стайлгайда)
    '10',            # ресивер 10-20% минутной производительности (REFINEMENT п.4)
    '30', '50',      # до 30-50% при резких пиках (REFINEMENT п.4)
    '3',             # PDP рефрижераторного около +3 C (REFINEMENT п.5)
    '40',            # адсорбционный до -40 C (REFINEMENT п.5)
    '380', '220',    # напряжение сети (пул FAQ)
    '7', '8',        # типовое давление пескоструя (пул FAQ)
    '12',            # до 10-12 бар для толстых покрытий (пул FAQ)
}

# Классы утверждений, которых в payload обычно нет вовсе. Это те самые классы,
# что дали 277 страниц брака на замере 17.08.
#
# Проверяются НЕ по цифрам, а по НАЛИЧИЮ КЛАССА ДАННЫХ в payload: «под заказ 2-4
# недели» нельзя обосновать тем, что двойка и четвёрка где-то в payload встречаются.
# Если в исходных данных страницы нет ни слова про сроки, то любой срок в тексте
# взят из воздуха. Второй элемент пары - признак наличия класса в payload.
RISKY = [
    ('срок поставки',  r'\d{1,2}\s?[-–]\s?\d{1,2}\s?(?:недел|рабочих дн|дн[ейя]|мес)',
     r'недел|срок[и]? постав|рабочих дн|отгруз[а-я]* за'),
    ('экономика в %',  r'(?:дешевл|дороже|экономи|окупа|переплат|снижа)[а-я]*[^.!?]{0,60}?\d{1,2}\s?[-–]\s?\d{1,2}\s?%',
     r'экономи|окупаем|дешевл|дороже на'),
    ('уровень шума',   r'\d{2,3}(?:\s?[-–]\s?\d{2,3})?\s?дБ',
     r'дБ|шум'),
    ('зазор в метрах', r'\d(?:[,.]\d)?\s?[-–]\s?\d(?:[,.]\d)?\s?метр',
     r'зазор|расстояни|метр'),
]

_NUM = re.compile(r'\d+(?:[.,]\d+)?')


def _norm(s: str) -> str:
    """Числа к общему виду: запятая как точка, без пробелов-разделителей разрядов."""
    return re.sub(r'(?<=\d)[  ](?=\d)', '', str(s)).replace(',', '.')


def allowed_numbers(payload: dict, brand_facts=None) -> set:
    """Множество чисел, которые страница имеет право называть."""
    src = _norm(json.dumps(payload, ensure_ascii=False))
    if brand_facts:
        src += ' ' + _norm(json.dumps(brand_facts, ensure_ascii=False))
    out = set(_NUM.findall(src))
    # округления вниз «до красивого», разрешённые стайлгайдом: 320 -> 300, 2268 -> 2250
    for n in list(out):
        try:
            v = float(n)
        except ValueError:
            continue
        if v >= 100:
            for step in (10, 50, 100, 250):
                out.add(str(int(v // step * step)))
        # л/мин -> м3/мин (стайлгайд требует перевода свыше 1000 л/мин)
        if v >= 1000:
            out.add(_norm(f'{v / 1000:g}'))
    return out | SANCTIONED_RULES


def check_numbers(html: str, payload: dict, brand_facts=None, all_numbers=False) -> list:
    """-> список претензий (пусто = все числа обоснованы)."""
    text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()
    allow = allowed_numbers(payload, brand_facts)
    issues = []

    if all_numbers:
        # сплошной режим: шумит на единицах измерения (0,1 мкм; 60 Гц), включать вручную
        unknown = [m.group(0).rstrip('.') for m in _NUM.finditer(_norm(text))
                   if m.group(0).rstrip('.') not in allow and len(m.group(0)) > 1]
        if unknown:
            issues.append('числа не из payload/базы знаний: '
                          + ', '.join(sorted(set(unknown), key=lambda x: -len(x))[:8]))

    src = json.dumps(payload, ensure_ascii=False)
    if brand_facts:
        src += ' ' + json.dumps(brand_facts, ensure_ascii=False)
    for name, rx, has_class in RISKY:
        if re.search(has_class, src, re.I):
            continue                      # класс данных в исходниках есть, цифру можно обосновать
        seen = set()
        for hit in re.findall(rx, text):
            frag = (hit if isinstance(hit, str) else hit[0]).strip()
            if frag in seen:
                continue
            seen.add(frag)
            issues.append(f'{name}: «{frag[:60]}» - данных этого класса в payload нет вовсе')

    return issues


def check_self_consistency(html: str) -> list:
    """Одно и то же свойство названо в тексте двумя разными наборами чисел.

    Ловит случай, найденный 17.08 на пробе Remeza: объёмы ресиверов «270, 500 и 660»
    в одном разделе и «270, 500 и 900» в FAQ. Источник расхождения был в самой базе
    знаний (marking_logic против ready_facts), мех-гейт его не видел, а три
    семантические линзы указали независимо.
    """
    text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()
    issues = []
    # только ЯВНЫЕ перечисления одного свойства: «объёмом 270, 500 и 900 литров»
    ENUM = re.compile(r'(объёмом|объемом|на)\s+((?:\d{2,4}\s*,\s*)+\d{2,4}\s+и\s+\d{2,4})\s*литр')
    sets = {tuple(sorted(set(_NUM.findall(m.group(2))), key=int)) for m in ENUM.finditer(text)}
    if len(sets) > 1:
        issues.append(f'объёмы ресиверов названы двумя разными наборами {sorted(sets)} - '
                      f'сверь слои базы знаний, они могут расходиться')
    return issues


if __name__ == '__main__':
    import glob
    import sys
    kb = json.load(open('kb/brand-facts-clean.json', encoding='utf-8'))
    only = sys.argv[1:] or None
    bad = tot = 0
    for pf in sorted(glob.glob('gen/payload-*.json')):
        slug = pf[len('gen/payload-'):-len('.json')]
        if only and slug not in only:
            continue
        try:
            p = json.load(open(pf, encoding='utf-8'))
            d = json.load(open(f'gen/result-{slug}.json', encoding='utf-8'))
        except OSError:
            continue
        tot += 1
        iss = check_numbers(d['text_html'], p, kb.get(p.get('page_brand')))
        iss += check_self_consistency(d['text_html'])
        if iss:
            bad += 1
            if only or bad <= 5:
                print(f'\n{slug}')
                for i in iss:
                    print('   ', i[:150])
    print(f'\nстраниц с претензиями по числам: {bad} из {tot}')
