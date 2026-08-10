# -*- coding: utf-8 -*-
"""Чиним МОДЕЛЬ там, где мой разбор взял технологическую позицию вместо марки.

Нашла 3-я сессия, я подтвердил своим прибором: 181 факт стоит с model из списка
Ц16/К3/ЦК3/ЦК4/ТВ1/… — это не серии машин, а номера позиций в цехе. У 89 из них ранг
машины держится ТОЛЬКО на этой «серии», то есть класс проставлен по выдумке.

В тексте настоящая марка обычно рядом и названа словом:
  «Поршневой компрессор тех. поз. К-3 марка ВП-50/8»      -> ВП-50/8
  «Турбовоздуходувка 67106А; Шифр - ТВ-2»                 -> 67106А
  «трубопроводы обвязки нагнетателя ГПА-1, КЦ №2, ГКС-21»  -> марки нет вообще

Регэкспом это не берётся (проверено: на третьем примере он выдаёт номер ОПО), поэтому
разбор — провайдером. Ничего не пишем в базу здесь: только jsonl с fsync, применение
отдельным шагом после просмотра.
"""
import sqlite3, json, os, re, sys, time, urllib.request, csv, io

sys.path.insert(0, '/home/user/avto/seo-texts')
from gen_provider import env

_E = env()
_BASE = (_E.get('PROVIDER_BASE_URL') or 'https://router.cheap').rstrip('/')
_KEY = _E['PROVIDER_API_KEY']
_NP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MODEL = os.environ.get('PARK_MODEL', 'gemini-3.5-flash')
D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, 'park_serii_fix.jsonl')
PACHKA = 20

PROMPT = """В каждой записи — текст надзорного документа про промышленную машину и то,
что мой разбор ЗАПИСАЛ как модель. Есть подозрение, что записана не марка машины, а её
ТЕХНОЛОГИЧЕСКАЯ ПОЗИЦИЯ в цехе (тех. поз., шифр, технологический индекс, номер агрегата
ГПА-1, К-3, ТВ-2, ЦК-4 и подобное).

Различай:
* МАРКА/МОДЕЛЬ — заводское обозначение машины: ВП-50/8, 4ВМ10-120/9, ЦК-135/8, 67106А,
  ГА55, К-250-61-1. Часто идёт после слов «марка», «тип», «модель» или сразу за словом
  «компрессор/воздуходувка/нагнетатель».
* ПОЗИЦИЯ — номер места в цехе: «тех. поз. К-3», «Шифр - ТВ-2», «(ЦК-4)», «ГПА-1»,
  «технологический индекс К-3», «агрегат № 2». Позиция моделью НЕ является.

По каждому входу верни:
  id
  model_verno   ДА (записана настоящая марка) | НЕТ (записана позиция)
  model_nastoyashchaya  если НЕТ и марка видна в тексте — она; если марки в тексте нет — пустая строка
  pozicia       если записана позиция — она же, иначе пустая строка
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


def _norm(s):
    return re.sub(r'[^A-Za-zА-Яа-я0-9]', '', (s or '')).upper().replace('Ё', 'Е')


def main():
    lozh = [r['seriya'].strip() for r in csv.DictReader(
        io.open(os.path.join(D, 'DLYA-VSEH-3s-SLOVAR-36-lozhnyh-seriy.csv'),
                encoding='utf-8-sig'), delimiter=';')]
    ns = {_norm(x) for x in lozh}
    p = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True)
    rows = [r for r in p.execute(
        "select id, model, tip, substr(chto_naydeno,1,400), chem_rang from fakt "
        "where coalesce(model,'')<>''") if _norm(r[1]) in ns]
    p.close()
    sdelano = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding='utf-8'):
            try:
                sdelano.add(json.loads(ln)['id'])
            except Exception:
                pass
    zad = [r for r in rows if r[0] not in sdelano]
    print('подозрительных фактов %d | к разбору %d' % (len(rows), len(zad)), flush=True)
    for i in range(0, len(zad), PACHKA):
        pach = zad[i:i + PACHKA]
        vhod = json.dumps([{'id': r[0], 'zapisano_kak_model': r[1], 'tip': r[2],
                            'tekst': re.sub(r'\s+', ' ', r[3] or '')} for r in pach],
                          ensure_ascii=False)
        try:
            t = sprosit(PROMPT + '\n\nВХОД:\n' + vhod)
            m = re.search(r'\[.*\]', t, re.S)
            dan = json.loads(m.group(0)) if m else []
        except Exception as e:
            print('пачка %d СБОЙ %r' % (i, e), flush=True)
            continue
        rang = {r[0]: r[4] for r in pach}
        with open(OUT, 'a', encoding='utf-8') as f:
            for d in dan:
                if d.get('id') in rang:
                    d['chem_rang_bylo'] = rang[d['id']]
                    f.write(json.dumps(d, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        print('пачка %d-%d: %d' % (i, i + len(pach), len(dan)), flush=True)
    print('ГОТОВО', flush=True)


if __name__ == '__main__':
    main()
