import yaml

from .paths import resource_path

def load_persona():
    config_path = resource_path("config", "persona.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)

PERSONA = load_persona()
