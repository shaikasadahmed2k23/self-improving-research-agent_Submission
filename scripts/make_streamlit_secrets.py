"""Write deploy/streamlit_secrets.local.toml (gitignored): the secrets template with your keys from .env filled in,
ready to paste into Streamlit Cloud. Key values are never printed."""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import config  # noqa: E402,F401  (loads .env into the environment)

template = (ROOT / "deploy" / "streamlit_secrets.toml").read_text(encoding="utf-8")
filled, missing = template, []
for key in ("GROQ_API_KEY", "GOOGLE_API_KEY", "TAVILY_API_KEY", "NVIDIA_API_KEY"):
    value = os.getenv(key, "")
    if not value:
        missing.append(key)
    filled = re.sub(rf'^{key} = ""$', lambda _: f"{key} = {json.dumps(value)}", filled, flags=re.M)
out = ROOT / "deploy" / "streamlit_secrets.local.toml"
out.write_text(filled, encoding="utf-8")
print(f"Wrote {out.relative_to(ROOT)}" + (f" (missing in .env: {', '.join(missing)})" if missing else " (all 4 keys filled)"))
