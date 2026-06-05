from pathlib import Path
import re

def load_prompt(filename: str) -> str:
    """
    Loads a prompt template from the mags_resume/prompts directory.
    Supports `{{include filename.md}}` directives to recursively embed other prompts.
    """
    content = _load_raw_prompt(filename)
    
    # Regex to find {{include ...}}
    include_pattern = re.compile(r"\{\{include\s+([\w\.\-]+)\s*\}\}")

    # Replace all occurrences by recursively calling this function
    def replace_include(match):
        include_filename = match.group(1)
        return load_prompt(include_filename)

    return include_pattern.sub(replace_include, content).strip()

def _load_raw_prompt(filename: str) -> str:
    """Helper to load a single prompt file without processing includes."""
    # 1. Check Current Working Directory (Local Override)
    cwd_path = Path.cwd() / filename
    if cwd_path.exists():
        return cwd_path.read_text(encoding="utf-8")

    # Define structure paths
    # __file__ = mags_resume/utils/prompt_loader.py
    package_root = Path(__file__).resolve().parent.parent # mags_resume/
    project_root = package_root.parent                    # MAGS-Resume/

    # Search in standard prompt locations
    search_paths = [project_root / "prompts" / filename, package_root / "prompts" / filename]
    for path in search_paths:
        if path.exists():
            return path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"Prompt file '{filename}' not found in standard locations: CWD, project/prompts, package/prompts."
    )