#!/usr/bin/env python3
"""Критика плана отбора доноров (ноябрь 2026) шестью моделями: по две от Anthropic, OpenAI и Google.

    python3 kritika_plana.py brief     # только собрать бриф -> kritika-1110/BRIEF.md
    python3 kritika_plana.py run       # бриф + опрос моделей (готовые ответы пропускаются)

Бриф собирается из файлов репозитория и выгрузки: план (DONOR-OTBOR-2026-11.md),
стайлгайд, акцепторы, журнал размещений, итог проверки эффекта 05.10 и статистика
по 1 290 площадкам после фильтра. Секретов (cookie, ключи) в бриф не попадает.
Каждый ответ пишется на диск сразу, с fsync.
"""
import collections
import json
import os
import statistics as st
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(DIR, '..'))
OUT = os.path.join(DIR, 'kritika-1110')

# По две модели от Anthropic, OpenAI и Google (владелец 10.11).
MODELS = ['claude-fable-5', 'claude-opus-5-5',
          'openai:gpt-6.1-sol', 'openai:gpt-6-astra',
          'openai:gemini-4-argon', 'openai:gemini-3.8-flash']

VERDIKT_10_05 = """Проверка эффекта прошлой кампании (05.10.2026, 9 агентов, две волны: искали рост и опровергали):
- куплено 22 статьи на Miralinks (июнь-сентябрь 2026), 37 ссылок на 27 страниц 6 наших сайтов;
- каждая страница сравнивалась с 30 похожими страницами того же сайта без ссылок + плацебо;
- Google: показы -3,2% (плацебо -2,3%, 95%: -20...+17%), p=0,54; Яндекс: -16,6%;
- верхняя граница эффекта: не больше +20% показов, не больше 55 кликов Google в месяц на 21 страницу;
- живой трафик с доноров: 4 человеческих визита с 20 доноров за 4 месяца, заявок 0;
- страницы со ссылками росли ХУЖЕ страниц без ссылок внутри тех же типов разделов;
- рост prokompressor объяснён другим: перенос поддоменов в основной домен, карточки товаров,
  раздел осушителей без ссылок, спрос (Вордстат) x1,25-1,33;
- 11 из 37 ссылок вели на редирект (переезд сайта, смена адреса раздела, адреса без слеша);
- накрутка поведенческих в Яндексе мешает аналитике (Вебмастер после конца июля не использовать).
Перепроверка запланирована на середину ноября (12+ недель у августовских ссылок) - ещё не сделана:
нужны свежие выгрузки GSC/Вебмастера/Метрики с сервера владельца."""

ZADANIE = """Ты - независимый эксперт по SEO (Яндекс и Google) и по GEO (видимость бренда в ответах
ИИ-ассистентов: Алиса, ChatGPT, Perplexity, AI Overviews), работаешь на рынке РФ, B2B, промышленное
оборудование. Ниже исходные данные и план отбора доноров для гостевых статей на бирже Miralinks.

Твоя задача - найти СЛАБЫЕ МЕСТА плана и предложить УЛУЧШЕНИЯ. Будь конкретен и честен:
если план в целом бесполезен с учётом проверки 05.10 - так и скажи и предложи, куда тот же бюджет
тратить лучше. Не пересказывай план, не хвали.

Ответ строго по разделам (markdown):

## 1. Главный вывод (3-5 предложений)
## 2. Слабые места (по убыванию важности)
Для каждого: что не так, почему (со ссылкой на цифры из данных), чем грозит, как исправить,
как проверить, что исправление сработало. Минимум 6 пунктов.
## 3. Чего в плане нет, а должно быть
## 4. Критерии отбора: что убрать, что добавить, какие пороги поменять (таблица: критерий | сейчас | предлагаю | почему)
## 5. SEO против GEO: правильно ли разделены доноры, как мерить GEO-эффект на практике
## 6. Как измерять эффект новой волны, чтобы через 3 месяца получить однозначный ответ
(дизайн эксперимента: контроль, размер, сроки, метрики)
## 7. Бюджет: на что тратить, если весь бюджет на ссылки и размещения - до 40 тыс. руб в месяц
(конкретная раскладка по статьям расходов и по типам доноров; при медиане цены живого донора 15 450 руб
это 2-3 размещения в месяц - учти это в дизайне замера)
## 8. Пять самых важных изменений плана (нумерованный список, по одной строке)

Цифры бери только из данных ниже. Если делаешь допущение - помечай «допущение».
Пиши по-русски, без длинных тире."""


def _read(name, limit=None):
    p = os.path.join(DIR, name)
    s = open(p, encoding='utf-8').read()
    return s[:limit] if limit else s


def statistika():
    ahr = {}
    for l in open(os.path.join(DIR, 'otbor-1110-ahrefs.jsonl'), encoding='utf-8'):
        if l.strip():
            d = json.loads(l)
            ahr[d['domain']] = d
    kand = [json.loads(l) for l in open(os.path.join(DIR, 'otbor-1110-kandidaty.jsonl'), encoding='utf-8')
            if l.strip()]

    def a(h):
        return max((ahr.get(h, {}), ahr.get('www.' + h, {})), key=lambda x: x.get('org_traffic') or 0)

    for k in kand:
        x = a(k['host'])
        k['tr'] = x.get('org_traffic') or 0
        k['kw'] = int(x.get('org_keywords') or 0)
        k['rd'] = int(x.get('refdomains') or 0)
        k['ru'] = x.get('ru_share') or 0
    zhiv = [k for k in kand if k['tr'] >= 1000]
    L = []
    L.append('Воронка: выгрузка Miralinks 18 526 площадок (10.11.2026) -> жёсткий фильтр (спам Я <5%, '
             'индекс Я >=70%, язык ru, «Ahrefs трафик» из выгрузки >=1000, доля проданных через биржу '
             f'статей от страниц в индексе Я <=5%) -> {len(kand)} -> органика САМОГО места размещения по '
             f'Ahrefs (хост и www.хост, берётся больший) >=1000/мес -> {len(zhiv)}; из них с нашими '
             f'тематиками (промышленность/строительство/техника/сельское хоз./бизнес/производство/авто): '
             f'{sum(k["nash_temy"] for k in zhiv)}.')
    infl = sum(1 for k in kand if k['tr'] < 0.3 * (k.get('Ahrefs трафик') or 0))
    L.append(f'Цифра «Ahrefs трафик» в выгрузке Miralinks завышена: у {infl} из {len(kand)} реальная органика '
             'места по Ahrefs меньше 30% от неё (пример: kam.business-gazeta.ru 1592 в выгрузке, 179 по Ahrefs).')
    pr = sorted(k['Цена ₽'] for k in zhiv if k.get('Цена ₽'))
    L.append(f'Цены живых ({len(zhiv)}): медиана {st.median(pr):.0f} руб, квартили '
             f'{pr[len(pr)//4]:.0f}/{pr[3*len(pr)//4]:.0f}, мин {pr[0]:.0f}, макс {pr[-1]:.0f}.')
    for nm, lo, hi in (('1-5 тыс', 1000, 5000), ('5-20 тыс', 5000, 20000), ('20-100 тыс', 20000, 100000),
                       ('100 тыс+', 100000, 10**12)):
        g = [k for k in zhiv if lo <= k['tr'] < hi]
        if g:
            L.append(f'  органика места {nm}: {len(g)} площадок, медиана цены '
                     f'{st.median([k["Цена ₽"] for k in g]):.0f} руб')
    tem = collections.Counter()
    for k in zhiv:
        for t in (k.get('Тематика') or '').split(';'):
            if t.strip():
                tem[t.strip()] += 1
    L.append('Тематики живых (метка биржи, у площадки их несколько): ' +
             '; '.join(f'{t} {n}' for t, n in tem.most_common(22)))
    reg = collections.Counter((k.get('Регион') or '?') for k in zhiv)
    L.append('Регионы: ' + '; '.join(f'{r} {n}' for r, n in reg.most_common(12)))
    sub = sum(1 for k in zhiv if k['host'] != k['Домен'].lower().removeprefix('www.'))
    L.append(f'Размещение на поддомене, а не на главном домене: {sub} из {len(zhiv)}.')
    L.append('')
    L.append('Топ-60 живых по органике места, из них с нашими тематиками (host | цена руб | органика места/мес | '
             'доля РФ в органике | ключей | ссылающихся доменов | ИКС домена | продано статей | тематика биржи):')
    for k in sorted([k for k in zhiv if k['nash_temy']], key=lambda k: -k['tr'])[:60]:
        L.append(f"{k['host']} | {k['Цена ₽']:.0f} | {k['tr']} | {k['ru']} | {k['kw']} | {k['rd']} | "
                 f"{k.get('ИКС')} | {k.get('Статей')} | {(k.get('Тематика') or '')[:70]}")
    L.append('')
    L.append('Дешёвые живые с нашими тематиками (цена <=5000 руб, по органике места):')
    for k in sorted([k for k in zhiv if k['nash_temy'] and (k.get('Цена ₽') or 0) <= 5000],
                    key=lambda k: -k['tr'])[:30]:
        L.append(f"{k['host']} | {k['Цена ₽']:.0f} | {k['tr']} | {k['kw']} | {(k.get('Тематика') or '')[:70]}")
    return '\n'.join(L)


def brief():
    akc = _read('FINAL-ACCEPTORS.md', 9000)
    log = _read('PLACEMENTS-LOG.md', 5000)
    parts = [
        '# Исходные данные\n',
        '## Бизнес\nООО «Руспром»: направление «Компрессор Центр» (prokompressor.ru - каталог, enger-air.ru - '
        'собственный бренд-производитель Enger, 16 дилерских сайтов брендов Berg, Dali, Cross Air и др.) и '
        'направление Meyer (фотосепараторы и рентген-инспекция: meyer-corp.ru, usort.ru, vsefotoseparatory.ru). '
        'B2B, средний чек сотни тысяч - миллионы руб. Бюджет на ссылки и размещения: до 40 тыс. руб в месяц. Цель кампании: SEO (позиции и трафик в Яндексе и Google '
        'на коммерческие страницы каталога) и GEO (бренды Enger и Meyer упоминаются и рекомендуются в ответах '
        'ИИ-ассистентов).',
        '## Итог прошлой кампании\n' + VERDIKT_10_05,
        '## Инструменты\nДоступны: выгрузка Miralinks, Ahrefs (пакетная проверка органики хоста), Semrush '
        '(органика РФ по домену), Majestic. Similarweb - только данные по Великобритании (бесполезен). '
        'Генерация и проверка статей - свой конвейер: 18 автоматических проверок (инженерные, SEO Яндекс/Google, '
        'анти-ИИ, нейтральность, ссылки, ответ первым).',
        '## Акцепторы (страницы, на которые ставим ссылки) и правило раскладки\n' + akc,
        '## Журнал размещений (начало)\n' + log,
        '## Статистика по донорам (выгрузка 10.11.2026)\n' + statistika(),
        '# План\n',
        '## План отбора доноров\n' + _read('DONOR-OTBOR-2026-11.md'),
        '## Стайлгайд статей (действующий, с правками 09.11.2026)\n' + _read('STYLE-GUIDE-GUEST.md'),
    ]
    os.makedirs(OUT, exist_ok=True)
    text = '\n\n'.join(parts)
    with open(os.path.join(OUT, 'BRIEF.md'), 'w', encoding='utf-8') as f:
        f.write(text)
    return text


def ask(model, prompt):
    import gen_provider as gp
    from gen_wave import _openai_stream
    path = os.path.join(OUT, 'otvet-' + model.replace('openai:', '').replace('/', '_') + '.md')
    if os.path.exists(path) and os.path.getsize(path) > 500:
        return model, 'уже есть'
    last = None
    for a in range(3):
        if a:
            time.sleep(20 * a)
        try:
            t0 = time.time()
            if model.startswith('openai:'):
                text, _ = _openai_stream([{'role': 'user', 'content': prompt}], model[7:], 16000)
            else:
                msg = gp._raw_stream([{'role': 'user', 'content': prompt}], model, 16000,
                                     thinking=False, effort=None)
                text = ''.join(b.text for b in msg.content if b.type == 'text')
            if len(text.strip()) > 500:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(f'<!-- {model}, {round(time.time() - t0)} с -->\n' + text)
                    f.flush()
                    os.fsync(f.fileno())
                return model, f'{len(text)} знаков'
            last = f'короткий ответ ({len(text)})'
        except Exception as e:
            last = repr(e)[:150]
    return model, 'ОШИБКА: ' + str(last)


def main():
    text = brief()
    print(f'бриф: {len(text)} знаков -> {OUT}/BRIEF.md', flush=True)
    if sys.argv[1:2] != ['run']:
        return
    prompt = ZADANIE + '\n\n' + text
    os.environ.setdefault('PROVIDER_FIRST_TOKEN_SEC', '300')
    os.environ.setdefault('PROVIDER_STREAM_DEADLINE_SEC', '900')
    with ThreadPoolExecutor(len(MODELS)) as ex:
        for model, res in ex.map(lambda m: ask(m, prompt), MODELS):
            print(f'{model}: {res}', flush=True)


if __name__ == '__main__':
    main()
