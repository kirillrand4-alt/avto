# -*- coding: utf-8 -*-
# 13.10, владелец: «проверь чтобы лишнего не отбросила». Третий фильтр строгой перепроверки (_oprov_strogo_meyer7.py):
# сайты с ответами «нет» + «связи нет» делятся на «посторонний» (каталог, портал, СМИ, банк, администрация, личный сайт,
# магазин, организация ДРУГОГО региона или чужой отрасли — контакты сайта снимаются) и «возможно группа» (сайт крупной
# компании/группы того же региона и близкой отрасли, где компания может быть дочкой/площадкой — контакты остаются с пометкой).
# Итог — meyer7-oprov-strogo3.jsonl + дроп.
import io, json, os, sys, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender'); os.chdir(DIR)
os.environ.update({'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna'})
import pilot_konveyer as PK  # noqa: E402
os.environ.update(PK.Волны().env_шага('kc_kontakty.py'))
import kc_kontakty as KK  # noqa: E402
print('===ИТОГ===', time.strftime('%H:%M:%S'))
цели = {json.loads(s)['ключ']: json.loads(s) for s in io.open(r'C:\seostat\drop\drop-storage\meyer7-oprov-strogo-celi.jsonl', encoding='utf-8') if s.strip()}
р = {}
for s in io.open(os.path.join(DIR, 'meyer7-oprov-strogo.jsonl'), encoding='utf-8'):
    y = json.loads(s)
    р[y['ключ']] = y
от = [y for y in р.values() if y.get('отсев')]
ПР = ('Сайт признан НЕ принадлежащим компании. Классифицируй каждый случай:\n'
      '«посторонний» — каталог/справочник/портал/СМИ/банк/администрация/госорган/личный сайт/интернет-магазин/сервис, ИЛИ сайт '
      'организации из ДРУГОГО региона, ИЛИ совсем другой отрасли без связи с компанией;\n'
      '«возможно группа» — сайт крупной компании/группы/холдинга ТОГО ЖЕ региона и близкой отрасли, где компания могла бы быть '
      'дочкой, филиалом, площадкой, элеватором/хозяйством группы (хотя на сайте не названа).\n'
      'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер,"класс":"посторонний|возможно группа","почему":"до 15 слов"}}]\n\n{б}')
ВЫХ = os.path.join(DIR, 'meyer7-oprov-strogo3.jsonl')
out = []
for k in range(0, len(от), 8):
    п_ = от[k:k + 8]
    б = '\n\n'.join('%d. КОМПАНИЯ: %s, ИНН %s, %s, ОКВЭД %s (%s), руководитель %s\n САЙТ: %s | заголовок: %s | юрлица на сайте: %s\n'
                    ' Почему «не её»: %s | %s' % (j, y['имя'], y['ключ'], цели[y['ключ']]['регион'], цели[y['ключ']]['оквэд'],
                                                  цели[y['ключ']]['сегм'][:50], цели[y['ключ']]['директор'] or '-', y['сайт'],
                                                  y.get('заголовок', '')[:100], '; '.join(y.get('юр_на_сайте') or []) or '-',
                                                  y['почему1'][:150], y['признак2'][:150])
                    for j, y in enumerate(п_, 1))
    о = KK.модель(ПР.format(б=б), True) or {}
    for j, y in enumerate(п_, 1):
        x = о.get(j) or {}
        out.append(dict(y, класс=x.get('класс') or '', почему3=x.get('почему') or ''))
with io.open(ВЫХ, 'w', encoding='utf-8') as f:
    f.write('\n'.join(json.dumps(x, ensure_ascii=False) for x in out) + '\n')
    f.flush(); os.fsync(f.fileno())
import shutil, collections  # noqa: E401
shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
shutil.copyfile(os.path.join(DIR, 'meyer7-oprov-strogo.jsonl'), r'C:\seostat\drop\drop-storage\meyer7-oprov-strogo.jsonl')
print(dict(collections.Counter(x['класс'] for x in out)))
