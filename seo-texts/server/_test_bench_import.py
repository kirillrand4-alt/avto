import json, subprocess, sys
r = subprocess.run([sys.executable, '-c', 'import pilot_bench_modeli as B; print(B.вызов("deepseek-v4-flash", "Ответь одним словом: ок")); print(B.вызов("claude-haiku-4-5", "Ответь одним словом: ок"))'],
                   cwd=r'C:\sender\server', capture_output=True, text=True, timeout=300)
print('===ИТОГ==='); print(r.stdout[-800:], r.stderr[-800:])
