# -*- coding: utf-8 -*-
"""ВСТРЕЧНАЯ проверка вердиктов «НЕ НАША МАШИНА»: 8 686 фактов выведено из парка,
610 предприятий ушло целиком. Это слишком дорогое решение, чтобы принять его с одного
голоса — тем более что в образцах глазами видно ложные:

  «Котел вагон-цистерны, предназначенный для использования в качестве стационарного
   ресивера сжатого воздуха»                      — это РЕСИВЕР
  «Заключение ЭПБ на техническое устройство Ресивер РЦ…»   — это РЕСИВЕР
  «нанимает в компрессорное хозяйство: Слесарь по обслуживанию…» — вакансия ДОКАЗЫВАЕТ машину

Прибор: ДРУГАЯ модель (claude-fable-5, не gemini), и спрашиваем не «какой тип», а
«верно ли ИСКЛЮЧИЛИ» — то есть просим опровергнуть, а не подтвердить.
Результат в jsonl с fsync, резюмируемо по id.
"""
import sqlite3, json, os, re, sys, time, urllib.request, hashlib

sys.path.insert(0, '/home/user/avto/seo-texts')
from gen_provider import env

_E = env()
_BASE = (_E.get('PROVIDER_BASE_URL') or 'https://router.cheap').rstrip('/')
_KEY = _E['PROVIDER_API_KEY']
_NP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MODEL = os.environ.get('PARK_MODEL2', 'claude-fable-5')
D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, 'park_net_proverka_%d.jsonl')
SKOLKO = int(os.environ.get('PARK_SKOLKO', '300'))
# шардируем так же, как сверку типов: делим по id, файл у каждого свой
SHARD = int(sys.argv[1]) if len(sys.argv) > 1 else 0
SHARDS = int(sys.argv[2]) if len(sys.argv) > 2 else 1
PACHKA = 20

PROMPT = """Проверяешь РЕШЕНИЕ ОБ ИСКЛЮЧЕНИИ. Другая модель уже пометила эти факты как
«к нашей номенклатуре отношения не имеет», и по этой пометке они удаляются из базы.
Твоя задача — НАЙТИ ОШИБКУ в исключении, а не согласиться.

Наша номенклатура: промышленные компрессоры (винтовые, поршневые, центробежные,
безмасляные), МКС (модульные компрессорные станции), ПКС (передвижные дизельные),
генераторы азота и кислорода, ВРУ, промышленные воздуходувки, ресиверы сжатого воздуха,
осушители сжатого воздуха, турбокомпрессоры, нагнетатели, ГПА.

ИСКЛЮЧЕНИЕ ОШИБОЧНО, если текст говорит хоть об одном из:
* сама наша машина, даже названная необычно («котёл вагон-цистерны, используемый
  как стационарный ресивер сжатого воздуха» — это РЕСИВЕР);
* узел нашей машины: трубопровод обвязки, концевой холодильник, маслоохладитель,
  влагоотделитель, буферная ёмкость, корпус нагнетателя;
* расходник или сервис нашей машины: масло, фильтры, ЗИП, ремонт, экспертиза, поверка;
* ВАКАНСИЯ, доказывающая машину: машинист компрессорных установок, аппаратчик
  воздухоразделения, слесарь компрессорного хозяйства, оператор компрессорной;
* закупка или аренда азота/кислорода: баллоны, жидкий, криоцистерна, газификатор.

ИСКЛЮЧЕНИЕ ВЕРНО, если это: насосы, задвижки и арматура, фонтанная арматура скважин,
краны, дымососы и дутьевые вентиляторы котлов, садовые воздуходувки, медтехника,
автозапчасти, буровые станки, дизельные электростанции, металлургические конвертеры,
производство аммиака и удобрений, строительные и ремонтные работы без нашей машины.

По каждому входу верни:
  id
  isklyuchenie  ВЕРНО | ОШИБКА
  tip           если ОШИБКА — правильный тип из нашей номенклатуры, иначе пустая строка
  vid           если ОШИБКА — машина | узел | расходник | газ, иначе пустая строка
  pochemu       одно короткое предложение

Ответ — ТОЛЬКО массив JSON."""


def sprosit(s, popytok=5):
    posl = None
    for n in range(popytok):
        if n:
            time.sleep(min(90, 8 * 2 ** (n - 1)))
        try:
            body = json.dumps({'model': MODEL, 'stream': False, 'max_tokens': 4000,
                               'messages': [{'role': 'user', 'content': s}]}).encode()
            req = urllib.request.Request(_BASE + '/v1/chat/completions', data=body, headers={
                'Content-Type': 'application/json', 'Authorization': 'Bearer ' + _KEY,
                'User-Agent': 'curl/8.5.0'})
            return json.loads(_NP.open(req, timeout=300).read())['choices'][0]['message']['content']
        except Exception as e:
            posl = e
    raise posl


def main():
    p = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True)
    rows = p.execute("""select id, tip, kto, substr(chto_naydeno,1,500), pochemu
                        from fakt where vid_fakta='НЕТ'""").fetchall()
    p.close()
    # выборка воспроизводимая: порядок по хэшу id, а не случайная
    rows.sort(key=lambda r: hashlib.md5(str(r[0]).encode()).hexdigest())
    import glob as _g
    out = OUT % SHARD
    sdelano = set()
    for f in _g.glob(os.path.join(D, 'park_net_proverka*.jsonl')):
        for ln in open(f, encoding='utf-8'):
            try:
                sdelano.add(json.loads(ln)['id'])
            except Exception:
                pass
    ochered = [r for r in rows if r[0] % SHARDS == SHARD and r[0] not in sdelano]
    # второй набор процессов идёт по той же очереди С КОНЦА: так удваивается скорость
    # без перекрытия с уже работающими (они берут с начала). Встретятся в середине —
    # к тому времени sdelano уже покажет чужую работу.
    zad = ochered[-SKOLKO:][::-1] if os.environ.get('PARK_S_KONCA') else ochered[:SKOLKO]
    print('исключённых всего %d | к проверке %d | уже сделано %d'
          % (len(rows), len(zad), len(sdelano)), flush=True)
    for i in range(0, len(zad), PACHKA):
        pach = zad[i:i + PACHKA]
        vhod = json.dumps([{'id': r[0], 'tekst': r[3],
                            'pochemu_isklyuchili': (r[4] or '')[-160:]} for r in pach],
                          ensure_ascii=False)
        try:
            t = sprosit(PROMPT + '\n\nВХОД:\n' + vhod)
            m = re.search(r'\[.*\]', t, re.S)
            dan = json.loads(m.group(0)) if m else []
        except Exception as e:
            print('пачка %d СБОЙ %r' % (i, e), flush=True)
            continue
        kto = {r[0]: r[2] for r in pach}
        with open(out, 'a', encoding='utf-8') as f:
            for d in dan:
                if d.get('id') in kto:
                    d['kto'] = kto[d['id']]
                    f.write(json.dumps(d, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        print('пачка %d-%d: %d' % (i, i + len(pach), len(dan)), flush=True)
    print('ГОТОВО', flush=True)


if __name__ == '__main__':
    main()
