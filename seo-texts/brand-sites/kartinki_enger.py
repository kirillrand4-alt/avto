# -*- coding: utf-8 -*-
"""Картинки товарных категорий Enger через картиночные модели шлюза.

Шлюз отдаёт 524 (таймаут Cloudflare) на долгих запросах, поэтому: ретраи с
отступом, разные модели по кругу, каждый готовый файл пишется на диск сразу
и повторно не заказывается. Прогон переживает рестарт песочницы.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

RAB = os.environ.get('KARTINKI_DIR', '.')
BAZA = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
KLYUCH = os.environ.get('PROVIDER_API_KEY', '')
# Порядок попыток: сначала та, что дешевле по прайсу шлюза, потом запасные.
MODELI = ('gpt-image-2', 'gpt-image-2.5', 'gpt-image-2.5-flare')
POPYTOK = 5

# Фон просим белый, а не прозрачный: вырезаем сами - так контролируем край.
# Палитра задана жёстко: владелец требует, чтобы все карточки серии читались
# как одна линейка - графит плюс светло-серые панели, как на шести готовых.
PALITRA = (' Colour palette strictly graphite: dark graphite grey RAL 7024 frame, '
           'base and structural parts, light warm grey RAL 7035 panels, matte '
           'finish, no beige, no cream, no white paint, no blue, no green.')

HVOST = (' Studio product photography, three-quarter front view from the left, '
         'even soft lighting, pure flat white background #FFFFFF, no floor, no '
         'shadow on the background, no text, no logos, no watermark, no people, '
         'photorealistic industrial equipment render, centered, full machine in frame.')

ZADANIYA = {
    'nizkogo-davleniya': (
        'Industrial low-pressure screw air compressor in a rectangular sound-proof '
        'cabinet, light grey panels with dark graphite frame and base skids, '
        'control panel with small display on the upper right of the front panel.'),
    # Форма снята с настоящих снимков поставок: это турбомашина, а не насос.
    'centrobezhnye': (
        'Large industrial centrifugal turbo air compressor package. Massive round '
        'volute casing with a wide bolted flange ring on its face, a large diameter '
        'air inlet duct entering from the side and a large discharge duct leaving '
        'upward, heavy bolted gearbox body behind the volute, intercooler vessel '
        'along the base, all mounted on a heavy welded base frame, tall control '
        'cabinet standing at the left end of the frame.'),
    'peredvizhnye': (
        'Portable diesel screw air compressor on a two-wheel road trailer with a '
        'drawbar and support jack, dark graphite metal canopy with side service '
        'doors and ventilation louvres, road lights on the rear.'),
    'spiralnye': (
        'Compact oil-free scroll air compressor, tall narrow rectangular cabinet, '
        'light grey panels with dark graphite frame and low dark base, round '
        'pressure gauge and small round indicator lamps on the upper front panel.'),
}


def poprosit(model, zadanie, timeout):
    telo = json.dumps({'model': model, 'prompt': zadanie + HVOST,
                       'size': '1024x1024', 'n': 1}).encode()
    r = urllib.request.Request(
        BAZA + '/v1/images/generations', data=telo,
        headers={'Authorization': 'Bearer ' + KLYUCH,
                 'User-Agent': 'curl/8.5.0',
                 'Content-Type': 'application/json'})
    d = json.loads(urllib.request.urlopen(r, timeout=timeout).read().decode())
    it = d['data'][0]
    if it.get('b64_json'):
        return base64.b64decode(it['b64_json'])
    ssylka = urllib.request.Request(it['url'], headers={'User-Agent': 'curl/8.5.0'})
    return urllib.request.urlopen(ssylka, timeout=180).read()


def main():
    os.makedirs(os.path.join(RAB, 'syrye'), exist_ok=True)
    for imya, zadanie in ZADANIYA.items():
        put = os.path.join(RAB, 'syrye', imya + '.png')
        if os.path.exists(put) and os.path.getsize(put) > 20000:
            print('%s: уже есть' % imya, flush=True)
            continue
        for n in range(POPYTOK):
            model = MODELI[n % len(MODELI)]
            try:
                bajty = poprosit(model, zadanie + PALITRA, 300)
            except urllib.error.HTTPError as e:
                print('%s: %s HTTP %s' % (imya, model, e.code), flush=True)
            except Exception as e:
                print('%s: %s %s' % (imya, model, type(e).__name__), flush=True)
            else:
                with open(put, 'wb') as f:
                    f.write(bajty)
                    f.flush()
                    os.fsync(f.fileno())
                print('%s: готово через %s, %.0f КБ' % (imya, model, len(bajty) / 1024),
                      flush=True)
                break
            time.sleep(2 ** n)
        else:
            print('%s: не вышло за %d попыток' % (imya, POPYTOK), flush=True)


if __name__ == '__main__':
    main()
