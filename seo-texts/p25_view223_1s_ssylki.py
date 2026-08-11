# -*- coding: utf-8 -*-
"""1-я сессия (запись 135) выполнила мою просьбу и отдала ТРИ СВОИ НАСТОЯЩИЕ ссылки с
числами: 6317002858 — 4 198 знаков ДОКАЗАНО, 1657036630 — 5 997 ДОКАЗАНО, 7708044880 — 108
знаков НЕ доказано, контроль 66. Прохожу их СВОИМ прибором. Совпадёт — значит различие было
в моих выдуманных реквизитах, и их 5 985 ссылок годны.
"""
import sys
sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R
B = 'https://zakupki.gov.ru/epz/organization/view223/info.html'
CELI = [('6317002858', B + '?&inn=6317002858&kpp=631701001&ogrn=1026301426348', '4198, ДОКАЗАНО'),
        ('1657036630', B + '?&inn=1657036630&kpp=165501001&ogrn=1021603139690', '5997, ДОКАЗАНО'),
        ('7708044880', B + '?&inn=7708044880&kpp=772501001&ogrn=1037739477764', '108, НЕ доказано')]
sovpalo = 0
for inn, u, ih in CELI:
    try:
        r = R.submit('browser_probe',
                     {'url': u, 'proxy': False, 'ignore_https_errors': True, 'after_ms': 7000,
                      'eval_js': {'return': '(() => {const t=document.body?'
                                            'document.body.innerText:"";return [t.length,'
                                            '(/ИНН[^0-9]{0,12}%s/.test(t)?1:0),'
                                            '(/ОГРН/.test(t)?1:0),'
                                            '(/Местонахождени/.test(t)?1:0)].join(";");})()'
                                            % inn}}, timeout=200)
        d = r.get('data') or {}
        ch = str(d.get('eval_js_value') or '').split(';')
        if len(ch) != 4:
            print('  %-12s ОТВЕТА НЕТ (ok=%s, err=%s)' % (inn, d.get('eval_js_ok'),
                                                          str(d.get('eval_js_err'))[:40]))
            continue
        dok = ch[1] == '1' and ch[2] == '1' and ch[3] == '1'
        moyo = '%s знаков, %s' % (ch[0], 'ДОКАЗАНО' if dok else 'НЕ доказано')
        ih_dok = 'ДОКАЗАНО' in ih
        ok = (dok == ih_dok)
        sovpalo += 1 if ok else 0
        print('  %-12s у них: %-18s у меня: %-22s %s'
              % (inn, ih, moyo, 'СОШЛОСЬ' if ok else 'РАСХОЖДЕНИЕ'))
    except Exception as e:  # noqa: BLE001
        print('  %-12s ЗАДАНИЕ УПАЛО: %s' % (inn, str(e)[:50]))
print('\n########## ЧИСЛА')
print('  ссылок сверено 3, вердикты СОШЛИСЬ %d из 3' % sovpalo)
