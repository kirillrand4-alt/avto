# -*- coding: utf-8 -*-
"""Извлечение ЛЮДЕЙ из собранных страниц через провайдерский API (claude-fable-5).

Работает В ПЕСОЧНИЦЕ: PROVIDER_API_KEY есть локально, а раннер — узкое место,
он делится с другими агентами. Кэш по (инн,url) — чтобы рестарт не стоил денег.

Вход:  lpr_batch_<тег>_<режим>.json.gz (скачан с дропа)
Выход: lpr_people_<тег>_<режим>.json  {'люди':[...], 'метрики':{}}

Главный рубеж — НЕ «есть ли на странице человек с должностью», а «сказано ли
прямо, что он работает В ЭТОЙ компании». Продуктивные страницы этого источника
почти все — СПИСКИ (награждённые, состав закупочной комиссии, реестр
аттестованных РТН, программа конференции), где рядом стоят десятки предприятий.

Запуск: python lpr_classify.py <файл.json.gz> <режим a|b>
"""
import gzip
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ВХОД = sys.argv[1] if len(sys.argv) > 1 else 'lpr_batch_m1_b.json.gz'
РЕЖИМ = sys.argv[2] if len(sys.argv) > 2 else 'b'
ДИР = os.path.dirname(os.path.abspath(ВХОД)) or '.'
ВЫХОД = os.path.join(ДИР, 'lpr_people_%s.json' % РЕЖИМ)
КЭШ = os.path.join(ДИР, 'lpr_cache_%s.jsonl' % РЕЖИМ)
ПОТОКОВ = int(os.environ.get('LPR_WORKERS', '10'))

_замок = threading.Lock()
_стат = {'вызовов': 0, 'сбоев': 0, 'из_кэша': 0, 'страниц': 0}


def провайдер(промпт, попыток=4):
    """Стриминг обязателен: шлюз рубит молчащее соединение примерно на 35-й
    секунде. Заголовки как в боевом клиенте — WAF шлюза отклоняет дефолтные
    заголовки anthropic-SDK."""
    key = os.environ.get('PROVIDER_API_KEY', '')
    base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    тело = json.dumps({'model': 'claude-fable-5', 'max_tokens': 1500, 'stream': True,
                       'messages': [{'role': 'user', 'content': промпт}]},
                      ensure_ascii=False).encode('utf-8')
    посл = ''
    for п in range(попыток):
        if п:
            time.sleep(3 * п)
        try:
            req = urllib.request.Request(
                base + '/v1/messages', data=тело, method='POST',
                headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                         'content-type': 'application/json',
                         'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
            куски = []
            with urllib.request.urlopen(req, timeout=180) as r:
                for сырая in r:
                    стр = сырая.decode('utf-8', 'replace').strip()
                    if not стр.startswith('data:'):
                        continue
                    try:
                        ev = json.loads(стр[5:].strip())
                    except Exception:  # noqa: BLE001
                        continue
                    if ev.get('type') == 'content_block_delta':
                        куски.append((ev.get('delta') or {}).get('text', ''))
            т = ''.join(куски)
            if т.strip():
                with _замок:
                    _стат['вызовов'] += 1
                return т
            посл = 'пустой ответ'
        except Exception as ex:  # noqa: BLE001
            посл = '%s: %s' % (type(ex).__name__, str(ex)[:90])
    with _замок:
        _стат['сбоев'] += 1
    sys.stderr.write('провайдер сдался: %s\n' % посл)
    return ''


ПРОМПТ = '''Страница найдена поиском «"<точное название компании>" "<должность>"».
Надо вытащить ЛЮДЕЙ ЭТОЙ КОМПАНИИ, у которых названа должность.

КОМПАНИЯ ИЗ ЕГРЮЛ:
  краткое имя: {krat}
  полное имя:  {poln}
  ИНН: {inn}   город: {city}   ОКВЭД: {okved}

СТРАНИЦА: {url}
Дата страницы (из разметки): {дата}
Заголовок: {title}

КУСКИ ТЕКСТА (каждый — окрестность слов-должностей; «[имя компании рядом]» значит,
что в этом же куске названа сама компания):
{текст}

ГЛАВНОЕ ПРАВИЛО. Такие страницы почти всегда СПИСКИ: награждённые, состав
закупочной комиссии, реестр аттестованных, программа конференции, выпускники.
Рядом стоят десятки разных предприятий. Человека берём ТОЛЬКО если в тексте
прямо сказано, что он работает ИМЕННО В ЭТОЙ компании (её название стоит рядом
с его фамилией и должностью). Если рядом с человеком стоит ДРУГОЕ предприятие —
не брать. Если принадлежность не сказана — не брать. Не угадывать.

ЕЩЁ ТРИ ПРАВИЛА:
1. Должность переписывать ЦЕЛИКОМ, как в тексте. «Заместитель главного инженера»
   НЕЛЬЗЯ сокращать до «главного инженера» — это разные люди, и в одной статье
   могут стоять оба.
2. Чиновников (глава района, министр, руководитель агентства), журналистов,
   сотрудников поставщиков и заказчиков — НЕ включать. Нужны сотрудники самого
   предприятия.
3. ФИО в именительном падеже. Если в тексте только инициалы — так и писать
   («Рябихин П.А.»), фамилию не выдумывать.

Верни СТРОГО один JSON без markdown:
{{"people":[{{"person":"Фамилия Имя Отчество","post":"должность целиком как в тексте",
  "quote":"фраза из текста, где сказано и должность, и принадлежность компании",
  "date":"YYYY-MM-DD если в тексте видна дата этого факта, иначе пусто",
  "confidence":"high|low"}}]}}
Пустой список — нормальный ответ.'''


def _кэш_читать():
    d = {}
    if os.path.exists(КЭШ):
        for line in open(КЭШ, encoding='utf-8'):
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            d[r['k']] = r['v']
    return d


def main():
    путь = ВХОД if os.path.exists(ВХОД) else os.path.join(ДИР, ВХОД)
    данные = json.loads(gzip.open(путь, 'rt', encoding='utf-8').read())
    кэш = _кэш_читать()
    кф = open(КЭШ, 'a', encoding='utf-8')
    задачи = []
    for c in данные:
        for p in (c.get('страницы') or []):
            if not (p.get('окна') or []):
                continue
            задачи.append((c, p))
    _стат['страниц'] = len(задачи)
    люди = []

    def одна(t):
        c, p = t
        k = '%s|%s' % (c['inn'], p['url'])
        if k in кэш:
            with _замок:
                _стат['из_кэша'] += 1
            return кэш[k]
        окна = p['окна'][:6]
        текст = '\n---\n'.join(
            ('[имя компании рядом] ' if o.get('имя_рядом') else '') + o['т'][:800]
            for o in окна)[:9000]
        пр = ПРОМПТ.format(krat=c.get('krat', ''), poln=c.get('poln', ''),
                           inn=c['inn'], city=c.get('город', ''),
                           okved=c.get('оквэд', ''), url=p['url'],
                           дата=p.get('дата') or 'не определена',
                           title=(p.get('title') or '')[:150], текст=текст)
        ответ = провайдер(пр)
        m = re.search(r'\{.*\}', ответ or '', re.S)
        рез = []
        if m:
            try:
                рез = (json.loads(m.group(0)) or {}).get('people') or []
            except Exception:  # noqa: BLE001
                рез = []
        with _замок:
            кф.write(json.dumps({'k': k, 'v': рез}, ensure_ascii=False) + '\n')
            кф.flush()
            os.fsync(кф.fileno())
        return рез

    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as ex:
        итоги = list(ex.map(одна, задачи))
    for (c, p), рез in zip(задачи, итоги):
        for ч in рез or []:
            фио = (ч.get('person') or '').strip()
            пост = (ч.get('post') or '').strip()
            if not (фио and пост):
                continue
            люди.append({
                'inn': c['inn'], 'company': c.get('krat', ''),
                'person': фио, 'post': пост,
                'quote': (ч.get('quote') or '')[:300],
                'url': p['url'], 'title': (p.get('title') or '')[:150],
                'date': ч.get('date') or p.get('дата') or '',
                'свежесть': p.get('свежесть') or '',
                'привязка': (p.get('привязка') or {}).get('уровень', ''),
                'роль_запроса': p.get('роль_запроса', ''),
                'confidence': ч.get('confidence') or '',
                'режим': РЕЖИМ, 'окон_с_именем': p.get('окон_с_именем', 0)})
    кф.close()
    # свежесть пересчитываем по дате, которую назвала модель (она точнее
    # разметки: в тексте бывает прямо «в 2019 году назначен»)
    import datetime as dt
    for l in люди:
        try:
            d = dt.date(*[int(x) for x in (l['date'] or '')[:10].split('-')])
            в = (dt.date.today() - d).days / 30.44
            l['возраст_мес'] = round(в, 1)
            l['свежесть'] = ('свежий' if в <= 24 else 'устаревший' if в <= 36
                             else 'старьё')
        except Exception:  # noqa: BLE001
            l['свежесть'] = 'дата?'
    out = {'люди': люди, 'метрики': dict(_стат, всего_людей=len(люди))}
    json.dump(out, open(ВЫХОД, 'w', encoding='utf-8'), ensure_ascii=False)
    print(json.dumps(out['метрики'], ensure_ascii=False))


if __name__ == '__main__':
    main()
