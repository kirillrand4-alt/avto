# -*- coding: utf-8 -*-
"""Классификация типа машины провайдером вместо регэкспа по подстроке.
Правило владельца: вся тяжёлая работа — через провайдерский API, не токенами сессии.
Долговечность: результат пишется в jsonl построчно с fsync + сразу в park.db.
Резюмируемость: уже размеченные id пропускаются."""
import sqlite3, json, os, sys, re, time, urllib.request
sys.path.insert(0, '/home/user/avto/seo-texts')
from gen_provider import env

_E = env()
_BASE = (_E.get('PROVIDER_BASE_URL') or 'https://router.cheap').rstrip('/')
_KEY = _E['PROVIDER_API_KEY']
_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MODEL = os.environ.get('PARK_MODEL', 'gemini-3.5-flash')


def sprosit(soobshchenie, popytok=4):
    """НЕ стриминг: замер показал, что рвётся именно стрим, а не модель.
    Короткие пачки отвечают за 3-30 с, в потолок Cloudflare (120 с) не упираются."""
    posl = None
    for n in range(popytok):
        if n:
            time.sleep(min(60, 8 * 2 ** (n - 1)))
        try:
            body = json.dumps({'model': MODEL, 'stream': False, 'max_tokens': 4000,
                               'messages': [{'role': 'user', 'content': soobshchenie}]}).encode()
            req = urllib.request.Request(_BASE + '/v1/chat/completions', data=body, headers={
                'Content-Type': 'application/json', 'Authorization': 'Bearer ' + _KEY,
                'User-Agent': 'curl/8.5.0'})
            d = json.loads(_NOPROXY.open(req, timeout=240).read())
            return d['choices'][0]['message']['content']
        except Exception as e:
            posl = e
    raise posl

D = os.path.dirname(os.path.abspath(__file__))
PARK = os.path.join(D, 'park.db')
OUT = os.path.join(D, 'park_klass.jsonl')
PACHKA = 15

PROMPT = """Ты классифицируешь ЗАКУПКИ, ВАКАНСИИ и НОВОСТИ российских предприятий для базы
парка компрессорного оборудования.

Компания продаёт: промышленные компрессоры (винтовые, поршневые, центробежные, безмасляные),
МКС (МОДУЛЬНЫЕ компрессорные станции), ПКС (ПЕРЕДВИЖНЫЕ компрессорные станции),
генераторы азота и генераторы кислорода (мембранные и адсорбционные, PSA),
воздухоразделительные установки.

По каждому тексту верни:
  tip        компрессор | воздуходувка | турбокомпрессор | нагнетатель | ВРУ |
             генератор азота | генератор кислорода | МКС | ПКС | НЕ НАША МАШИНА
  sostoyanie эксплуатирует | покупает машину | арендует | покупает ГАЗ | планирует |
             продаёт (дилер) | неясно
  sreda      воздух | азот | кислород | иное | неясно
  pochemu    одно короткое предложение: по какому признаку решил

ВАЖНЫЕ РАЗЛИЧЕНИЯ, на них чаще всего ошибаются:
* «кислородно-конвертерный цех», «конвертер», «донная продувка» — это МЕТАЛЛУРГИЯ,
  а не кислородная станция -> НЕ НАША МАШИНА;
* «завод по производству аммиака/карбамида», «азотная кислота», «азотные удобрения» —
  ХИМИЯ, а не генератор азота -> НЕ НАША МАШИНА;
* название предприятия («Псковский азотно-кислородный завод») само по себе не факт о машине;
* закупка ЖИДКОГО или ГАЗООБРАЗНОГО азота/кислорода, баллонов, криопродуктов ->
  tip = генератор азота ИЛИ генератор кислорода, sostoyanie = покупает ГАЗ.
  Это НЕ владелец генератора, а наш ЦЕЛЕВОЙ покупатель — не путать с «эксплуатирует»;
* аренда компрессорной установки -> sostoyanie = арендует;
* МКС и ПКС — ДВА РАЗНЫХ ТИПА, не путать между собой и не сваливать в «компрессор».
  МКС = МОДУЛЬНАЯ компрессорная станция: оборудование в блок-контейнере или модуле,
     стационарное решение «под ключ» — компрессор с осушителем, ресивером и автоматикой
     в утеплённом модуле. Признаки: «модульная компрессорная станция», «блочно-модульная»,
     «блок-контейнер», «контейнерного исполнения», «БМКС», «МКС», «компрессорная под ключ»,
     «компрессорная станция в модуле»;
  ПКС = ПЕРЕДВИЖНАЯ компрессорная станция: дизельная, на шасси или прицепе, для
     строительства, бурения, дорожных работ. Признаки: серии XATS, XAS, XAHS
     (Atlas Copco), PDS (Airman), DCA/DCW (Denyo), ЗИФ-ПВ, ДЭН, ПКСД; слова
     «передвижная», «на шасси», «на прицепе», «дизельная компрессорная»,
     гаражный или госномер рядом с машиной.
  ОБЕ дорогие и обе наша номенклатура — тип ставим ТОЧНЫЙ, не обобщаем;
* вакансия «машинист компрессорных установок», «аппаратчик воздухоразделения» ->
  машина у предприятия ЕСТЬ, sostoyanie = эксплуатирует;
* ТО, ремонт, ЗИП, фильтры, масло -> эксплуатирует.

Ответ — ТОЛЬКО массив JSON, по объекту на вход, в том же порядке:
[{"id":123,"tip":"...","sostoyanie":"...","sreda":"...","pochemu":"..."}]"""


def main():
    p = sqlite3.connect(PARK)
    cur = p.cursor()
    sdelano = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding='utf-8'):
            try: sdelano.add(json.loads(ln)['id'])
            except Exception: pass
    # размечаем то, что типизировано РЕГЭКСПОМ (сигналы), а не разобрано человеком/ЭПБ
    rows = [r for r in cur.execute(
        "select id, tip, chto_naydeno from fakt where kto='enrich.db/signals' "
        "or tip='' order by id") if r[0] not in sdelano]
    print('к разметке', len(rows), '| уже сделано', len(sdelano), flush=True)
    ok = 0
    for i in range(0, len(rows), PACHKA):
        pach = rows[i:i + PACHKA]
        vhod = json.dumps([{'id': r[0], 'tekst': (r[2] or '')[:400]} for r in pach],
                          ensure_ascii=False)
        try:
            otvet = sprosit(PROMPT + '\n\nВХОД:\n' + vhod)
            if isinstance(otvet, str):
                txt = otvet
            elif hasattr(otvet, 'content'):
                txt = ''.join(getattr(b, 'text', '') for b in otvet.content)
            else:
                txt = str(otvet)
            if i == 0:
                open(os.path.join(D, 'park_klass_syroy.txt'), 'w',
                     encoding='utf-8').write(repr(type(otvet)) + '\n---\n' + txt[:3000])
            m = re.search(r'\[.*\]', txt, re.S) or re.search(r'\[.*\]', '[' + txt, re.S)
            dannye = json.loads(m.group(0)) if m else []
        except Exception as e:
            print('пачка %s: СБОЙ %r' % (i, e), flush=True); continue
        with open(OUT, 'a', encoding='utf-8') as f:
            for d in dannye:
                f.write(json.dumps(d, ensure_ascii=False) + '\n')
            f.flush(); os.fsync(f.fileno())
        for d in dannye:
            cur.execute("update fakt set tip=?, sostoyanie=?, sreda=?, "
                        "pochemu=pochemu||' | провайдер: '||? where id=?",
                        (d.get('tip', ''), d.get('sostoyanie', ''), d.get('sreda', ''),
                         (d.get('pochemu') or '')[:200], d.get('id')))
            ok += 1
        p.commit()
        print('пачка %s-%s: размечено %s, всего %s' % (i, i + len(pach), len(dannye), ok),
              flush=True)
    print('ГОТОВО, размечено', ok, flush=True)
    print('--- НЕ НАША МАШИНА:', cur.execute(
        "select count(*) from fakt where tip='НЕ НАША МАШИНА'").fetchone()[0], flush=True)
    p.close()


if __name__ == '__main__':
    main()
