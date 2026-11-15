import json
from pathlib import Path

def write_json(content,path):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(content,ensure_ascii=False,indent=2),encoding='utf-8')
    return target
