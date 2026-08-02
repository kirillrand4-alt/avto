# -*- coding: utf-8 -*-
"""Сравнение моделей провайдера на двух наших настоящих задачах.

Задача владельца: прогнать китайские (glm, deepseek) и Gemini на том же, что делает fable-5,
и посмотреть, годятся ли они. Две задачи, обе живые, а не синтетические:

  А. СВОБОДНЫЙ ТЕКСТ → ЛЮДИ. Тексты предостережений Ростехнадзора из ЕРКНМ: там работники
     названы поимённо с должностью. Эталон — то, что вынул fable-5 (erknm-lica.csv).
  Б. РАСПОЗНАВАНИЕ PDF. Страница документа рендерится в картинку и отдаётся модели глазами.
     Меряем, сколько знаков осмысленного текста вернулось и нашлись ли контакты.

Ключевое различие эндпоинтов, на котором легко обжечься: **не-Claude модели через
Anthropic-совместимый `/v1/messages` виснут** (проверено: glm-5.2 и gemini-3.6-flash не
ответили за 60 с, deepseek ответил пустотой). Работают они через OpenAI-совместимый
`/v1/chat/completions` с `Authorization: Bearer`. Claude-модели ходят своим путём.

Использование:
    python3 sravnenie_modeley.py --tekst   # задача А
    python3 sravnenie_modeley.py --pdf     # задача Б
"""
import base64
import csv
import json
import os
import re
import sys
import time
import urllib.request

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
BASE = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
KEY = os.environ['PROVIDER_API_KEY']
RAB = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad'

MODELI = ['glm-5.2', 'deepseek-v4-pro', 'deepseek-v4-flash',
          'gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.1-pro-preview',
          'claude-fable-5']


def zapros(model, soobshcheniya, max_tokens=4000, timeout=180):
    """Один вызов. Claude идёт Anthropic-путём, остальные — OpenAI-путём."""
    if model.startswith('claude'):
        telo = {'model': model, 'max_tokens': max_tokens, 'messages': soobshcheniya}
        url, zag = BASE + '/v1/messages', {
            'x-api-key': KEY, 'anthropic-version': '2023-06-01',
            'content-type': 'application/json', 'User-Agent': 'curl/8.5.0'}
    else:
        # OpenAI-формат: картинка идёт как image_url с data-URI, а не как source/base64
        msgs = []
        for m in soobshcheniya:
            c = m['content']
            if isinstance(c, list):
                nc = []
                for b in c:
                    if b.get('type') == 'text':
                        nc.append({'type': 'text', 'text': b['text']})
                    elif b.get('type') == 'image':
                        nc.append({'type': 'image_url', 'image_url': {
                            'url': 'data:image/png;base64,' + b['source']['data']}})
                msgs.append({'role': m['role'], 'content': nc})
            else:
                msgs.append(m)
        telo = {'model': model, 'max_tokens': max_tokens, 'messages': msgs}
        url, zag = BASE + '/v1/chat/completions', {
            'Authorization': 'Bearer ' + KEY, 'content-type': 'application/json',
            'User-Agent': 'curl/8.5.0'}
    t0 = time.time()
    req = urllib.request.Request(url, data=json.dumps(telo).encode(), headers=zag)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode('utf-8', 'replace'))
    except Exception as e:  # noqa: BLE001
        return '', round(time.time() - t0, 1), f'{type(e).__name__}: {str(e)[:70]}'
    if model.startswith('claude'):
        txt = ''.join(b.get('text', '') for b in d.get('content', []))
    else:
        txt = (((d.get('choices') or [{}])[0].get('message') or {}).get('content') or '')
    return txt, round(time.time() - t0, 1), ''


PROMPT_LICA = """Тексты предостережений Ростехнадзора. В них названы работники предприятий.

Верни ТОЛЬКО JSON: {"lyudi":[{"imya":"","dolzhnost":"","chej":"предприятие|надзорный орган"}]}
Правила: ни одного имени, которого нет в тексте; должность в именительном падеже; сотрудника
надзорного органа помечай как надзорный орган, а не выбрасывай."""


def zadacha_tekst(skolko=12):
    f = [x for x in csv.DictReader(open(os.path.join(L, 'SVOD-tri-sostoyaniya.csv'),
                                        encoding='utf-8-sig'), delimiter=';')]
    FIO = re.compile(r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:ович|евич|овна|евна)')
    TEH = re.compile(r'главн\w+\s+(?:инженер|механик|энергетик)|начальник', re.I)
    zap = [re.sub(r'\s+', ' ', x['tekst']) for x in f
           if FIO.search(x.get('tekst') or '') and TEH.search(x.get('tekst') or '')][:skolko]
    vhod = PROMPT_LICA + '\n\nЗАПИСИ:\n' + '\n\n'.join(f'{i+1}. {t[:1500]}' for i, t in enumerate(zap))
    etalon = set()
    for t in zap:
        etalon |= {m.group(0) for m in FIO.finditer(t)}
    print(f'записей {len(zap)}, имён в тексте (шаблоном) {len(etalon)}\n', file=sys.stderr)
    print(f'{"модель":24} {"сек":>6} {"людей":>6} {"из них выдумано":>16}  примечание')
    for m in MODELI:
        txt, sek, err = zapros(m, [{'role': 'user', 'content': vhod}])
        if err:
            print(f'{m:24} {sek:>6} {"—":>6} {"—":>16}  {err}')
            continue
        mm = re.search(r'\{.*\}', txt, re.S)
        try:
            lyudi = json.loads(mm.group(0)).get('lyudi', []) if mm else []
        except json.JSONDecodeError:
            print(f'{m:24} {sek:>6} {"—":>6} {"—":>16}  JSON не разобран ({len(txt)} знаков)')
            continue
        vsego = len(lyudi)
        # выдумка: фамилии нет ни в одном поданном тексте
        vydum = sum(1 for c in lyudi if (c.get('imya') or '').split()
                    and (c['imya'].split()[0] not in ' '.join(zap)))
        print(f'{m:24} {sek:>6} {vsego:>6} {vydum:>16}  ')


def zadacha_pdf(fajl='ip_omsk.pdf', stranica=0):
    import fitz
    put = os.path.join(RAB, fajl)
    if not os.path.exists(put):
        import subprocess
        subprocess.run(['bash', os.path.join(BAZA, 'server', 'drop_client.sh'), 'down', fajl],
                       cwd=RAB, capture_output=True, timeout=600)
    doc = fitz.open(put)
    pix = doc[stranica].get_pixmap(dpi=140)
    png = pix.tobytes('png')
    b64 = base64.b64encode(png).decode()
    print(f'{fajl}, страница {stranica+1}, картинка {len(png)//1024} КБ, страниц в документе {len(doc)}\n',
          file=sys.stderr)
    soob = [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'Это страница российского документа. Верни ВЕСЬ текст со страницы '
                                 'дословно, сохраняя таблицы построчно. Ничего не додумывай.'},
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': b64}}]}]
    print(f'{"модель":24} {"сек":>6} {"знаков":>8} {"цифр":>6} {"кир.слов":>9}  начало')
    for m in MODELI:
        txt, sek, err = zapros(m, soob, max_tokens=8000, timeout=300)
        if err:
            print(f'{m:24} {sek:>6} {"—":>8} {"—":>6} {"—":>9}  {err}')
            continue
        kir = len(re.findall(r'[А-Яа-яЁё]{3,}', txt))
        cif = len(re.findall(r'\d', txt))
        print(f'{m:24} {sek:>6} {len(txt):>8} {cif:>6} {kir:>9}  {re.sub(chr(10), " ", txt)[:60]}')


if __name__ == '__main__':
    if '--pdf' in sys.argv:
        zadacha_pdf()
    else:
        zadacha_tekst()
