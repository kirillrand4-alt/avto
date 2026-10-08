import io, json, os
п = r'C:\sender\server\kc-raspakovka.json'
o = json.load(io.open(п, encoding='utf-8')) if os.path.exists(п) else {}
o = {k: o.get(k) for k in ('архив', 'ожидается_байт', 'распаковано_файлов', 'sha256_совпал', 'куда', 'верхние_папки', 'конец', 'итог')}
o['папка_есть'] = os.path.isdir(r'C:\seostat\kc-proekty')
o['на_дропе_части'] = [f for f in os.listdir(r'C:\seostat\drop\drop-storage') if f.startswith('kc-proekty')][:10]
print('===ИТОГ==='); print(json.dumps(o, ensure_ascii=False, indent=1))
