"""
YAML loader utility using ruamel.yaml to preserve order and comments if needed.
"""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

# Configure YAML parser for round-trip safely
yaml_parser = YAML(typ='safe')
yaml_parser.default_flow_style = False
yaml_parser.preserve_quotes = True


def load_yaml(path: Path | str) -> dict[str, Any]:
    """Load a YAML file into a dictionary."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"YAML file not found: {file_path}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml_parser.load(f)
        
    if data is None:
        return {}
    return data


def save_yaml(data: dict[str, Any], path: Path | str) -> None:
    """Save a dictionary to a YAML file."""
    file_path = Path(path)
    
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, "w", encoding="utf-8") as f:
        yaml_parser.dump(data, f)
