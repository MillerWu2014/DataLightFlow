import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.parent))
from src.datalight.config import load_taxonomy
from src.datalight.pipeline.generation.taxonomy import _taxonomy_system_prompt, TAG_JSON_SUFFIX, build_taxonomy_catalog

yaml_file = Path("configs/datalight.yaml")
taxonomy = load_taxonomy(yaml_file)


print(taxonomy.task_type)
print(taxonomy.categories)
print(taxonomy.reasoning_style)

r = _taxonomy_system_prompt("", TAG_JSON_SUFFIX)
print(r)

catage = build_taxonomy_catalog(taxonomy)
print(catage)
