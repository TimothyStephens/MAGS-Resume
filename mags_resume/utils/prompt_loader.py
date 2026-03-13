from pathlib import Path

def load_prompt(filename: str) -> str:
    """Loads a prompt template from the mags_resume/prompts directory."""
    # 1. Check Current Working Directory (Local Override)
    cwd_path = Path.cwd() / filename
    if cwd_path.exists():
        return cwd_path.read_text(encoding="utf-8").strip()

    # Define structure paths
    # __file__ = mags_resume/utils/prompt_loader.py
    package_root = Path(__file__).resolve().parent.parent # mags_resume/
    project_root = package_root.parent                    # MAGS-Resume/

    # 2. Check Project Root "prompts" directory
    project_path = project_root / "prompts" / filename
    if project_path.exists():
        return project_path.read_text(encoding="utf-8").strip()

    # 3. Check Package "prompts" directory (Default fallback)
    package_path = package_root / "prompts" / filename
    if package_path.exists():
        return package_path.read_text(encoding="utf-8").strip()

    raise FileNotFoundError(
        f"Prompt file '{filename}' not found.\n"
        f"Searched locations:\n"
        f"1. {cwd_path}\n"
        f"2. {project_path}\n"
        f"3. {package_path}"
    )