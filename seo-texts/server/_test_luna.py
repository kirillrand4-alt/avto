import json, subprocess, sys
код = '''
import pilot_bench_modeli as B, json
out = {}
for м in ("gpt-6-luna", "gpt-5.6-luna"):
    r = []
    for _ in range(3):
        try:
            т, вх, вых, с = B.вызов(м, "Ответь одним словом: ок")
            r.append("ок %r %d/%d %.1fс" % (т[:10], вх, вых, с))
        except Exception as e:
            r.append("ошибка " + str(e)[:120])
    out[м] = r
print(json.dumps(out, ensure_ascii=False))
'''
р = subprocess.run([sys.executable, '-c', код], cwd=r'C:\sender\server', capture_output=True, text=True, timeout=400)
print('===ИТОГ==='); print(р.stdout[-1500:], р.stderr[-500:])
