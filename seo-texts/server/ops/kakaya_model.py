# -*- coding: utf-8 -*-
"""Во что gen_provider превращает имя модели в окружении раннера (без вызова)."""
import os
import sys
sys.path.insert(0, r"C:\sender")
import gen_provider as g
for м in ("claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"):
    print(м, "->", g.resolve_model(м))
for к in ("PROVIDER_DEAD_MODELS", "PROVIDER_MODEL", "GEN_LETTER_MODEL", "GEN_CHECKER_MODEL", "LENS_MODEL",
          "LETTER_EFFORT", "PROVIDER_THINKING_FIELD", "PROVIDER_FALLBACK_CHEAP"):
    print(к, "=", os.environ.get(к))
