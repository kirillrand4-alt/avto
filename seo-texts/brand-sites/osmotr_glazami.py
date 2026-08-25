#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Осмотр вёрстки глазами модели через провайдерский API, не сессией.

    python3 osmotr_glazami.py [--tolko 5] [--model claude-fable-5]

ПОЧЕМУ НЕ АГЕНТАМИ СЕССИИ. Шесть смотрящих агентов на 32 страницы
положили сессию в лимит на середине работы. Правило владельца прямое:
тяжёлое - через провайдерский API, квоту сессии беречь. Зрение у шлюза
проверено отдельным вызовом и работает.

ПОЧЕМУ ТРИ КАДРА, А НЕ ВСЯ СТРАНИЦА. Страница высотой двадцать тысяч
пикселей, ужатая до размера, который принимает модель, превращается
в нечитаемую полосу. Поэтому снимаем три экрана в характерных местах:
верх с оглавлением и первым экраном, середину с таблицей, низ с FAQ
и финальным призывом. Текст на них читается в натуральную величину.

РЕЗЮМИРУЕМОСТЬ. Результат каждой страницы дописывается в jsonl с fsync
сразу же. Повторный запуск пропускает уже осмотренные: прогон на 133
страницы длинный, а песочница переживала рестарт не раз.
"""
import argparse
import base64
import glob
import io
import json
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
sys.path.insert(0, DIR)

ZHURNAL = os.path.join(DIR, 'osmotr-glazami.jsonl')

VOPROS = """Ты смотришь на страницу перед публикацией на сайт компрессорной компании.
Три снимка одной страницы: верх, середина, низ. Ширина настольная.

Оцени ТОЛЬКО вид, не содержание текста и не цифры.

1. Плашка призыва (серая, с полосой слева) - заметна, не сломана?
2. Кнопка под ней - похожа на кнопку, надпись читается, размер разумный?
3. Таблицы - есть линии и отбивка, колонки не слиплись, шапка над своими данными?
4. Заголовки - видна разница уровней, ничего не прилипло вплотную?
5. Оглавление - читается как список?
6. Общий ритм - нет слипшихся блоков, дыр, наездов?

Ответь СТРОГО так:
ОЦЕНКА: <число от 1 до 10>
ДЕФЕКТЫ:
- <дефект>: критично|заметно|мелочь
(если дефектов нет, напиши «- нет»)

Без вступлений и похвал. Пиши по-русски."""


def kadry(put, br, shirina=1280, vysota=900):
    """Три экрана: верх, середина, низ."""
    st = br.new_page(viewport={'width': shirina, 'height': vysota})
    out = []
    try:
        st.goto('file://' + os.path.abspath(put), wait_until='load', timeout=45000)
        st.wait_for_timeout(400)
        vsego = st.evaluate('() => document.body.scrollHeight')
        for doly in (0, .45, .92):
            st.evaluate(f'() => window.scrollTo(0, {int(vsego * doly)})')
            st.wait_for_timeout(200)
            out.append(st.screenshot())
    finally:
        st.close()
    return out


def szhat(png, predel=1500):
    """Ужать до предела по длинной стороне - иначе кадр тяжелее, чем нужно."""
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert('RGB')
    if max(im.size) > predel:
        k = predel / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=82)
    return base64.b64encode(buf.getvalue()).decode()


def uzhe_osmotreno():
    est = set()
    if os.path.exists(ZHURNAL):
        for l in open(ZHURNAL, encoding='utf-8'):
            try:
                est.add(json.loads(l)['slug'])
            except Exception:
                pass
    return est


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vhod', default=os.path.join(DIR, 'predprosmotr-vse'))
    ap.add_argument('--model', default='claude-fable-5')
    ap.add_argument('--tolko', type=int, default=0, help='0 - все')
    a = ap.parse_args()

    import gen_provider as G
    from playwright.sync_api import sync_playwright

    fajly = sorted(glob.glob(os.path.join(a.vhod, '*', '*.html')))
    gotovo = uzhe_osmotreno()
    ochered = [p for p in fajly if os.path.basename(p)[:-5] not in gotovo]
    if a.tolko:
        ochered = ochered[:a.tolko]
    print(f'к осмотру {len(ochered)} страниц, уже осмотрено {len(gotovo)}', flush=True)

    klient = G.make_client()
    kand = sorted(glob.glob('/opt/pw-browsers/chromium*/chrome-linux/chrome'))
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=kand[-1] if kand else None)
        for n, put in enumerate(ochered, 1):
            slug = os.path.basename(put)[:-5]
            try:
                snimki = kadry(put, br)
                soderzhimoe = [{'type': 'image',
                                'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                           'data': szhat(s)}} for s in snimki]
                soderzhimoe.append({'type': 'text', 'text': VOPROS})
                r = G.call(klient, [{'role': 'user', 'content': soderzhimoe}],
                           model=a.model, attempts=4, max_tokens=1200)
                otvet = ''.join(b.text for b in r.content if b.type == 'text').strip()
                zapis = {'slug': slug, 'otvet': otvet}
            except Exception as e:
                zapis = {'slug': slug, 'oshibka': str(e)[:200]}
            # ДОЛГОВЕЧНОСТЬ: пишем сразу и с fsync, а не копим в памяти
            with open(ZHURNAL, 'a', encoding='utf-8') as f:
                f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            ocenka = ''
            if 'otvet' in zapis:
                import re
                m = re.search(r'ОЦЕНКА:\s*(\d+)', zapis['otvet'])
                ocenka = m.group(1) if m else '?'
            print(f'{n}/{len(ochered)} {slug[:46]:46} '
                  f'{"оценка " + ocenka if ocenka else zapis.get("oshibka", "")[:60]}', flush=True)
        br.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
