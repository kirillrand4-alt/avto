import os, sys, time
os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
sys.path.insert(0, r"C:\sender")
import gen_provider
for m in ("claude-sonnet-4-6",):
    t = time.time()
    try:
        r = gen_provider._raw_stream([{"role": "user", "content": "Ответь одним словом: да"}], m, 20, thinking=False, effort="low")
        print(m, "OK", "".join(b.text for b in r.content if getattr(b, "type", "") == "text")[:30], round(time.time() - t, 1), "с")
    except Exception as e:
        print(m, "ОШИБКА", type(e).__name__, str(e)[:200], round(time.time() - t, 1), "с")
