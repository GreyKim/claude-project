"""템플릿에 dashboard_data.json을 주입해 최종 dashboard.html을 생성한다."""
import json

TEMPLATE_PATH = "/Users/1109701/workspace/study/claude-project/templates/dashboard_template.html"
DATA_PATH = "/Users/1109701/workspace/study/claude-project/data/dashboard_data.json"
OUT_PATH = "/Users/1109701/workspace/study/claude-project/dashboard.html"

with open(TEMPLATE_PATH, encoding="utf-8") as f:
    template = f.read()
with open(DATA_PATH, encoding="utf-8") as f:
    data = json.load(f)

html = template.replace("__DASHBOARD_DATA_JSON__", json.dumps(data, ensure_ascii=False))

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"built -> {OUT_PATH}")
