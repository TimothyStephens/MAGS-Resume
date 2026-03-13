import typer
import subprocess
import os
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from mags_resume.utils.db import init_db, get_token_summary
from mags_resume.utils.config_parser import load_config, resolve_config_path
from mags_resume.utils.logger import logger

app = typer.Typer(help="MAGS-Resume Studio CLI", add_completion=False, context_settings={"help_option_names": ["-h", "--help"]})
console = Console()

_CONFIG_HELP_TEXT = "Path to the configuration YAML file (default: config.yaml)."

def find_default_config_path() -> Path:
    return Path("config.yaml")

def format_llm_error(e: Exception) -> str:
    """Helper to format exception messages for table display."""
    return str(e).split('\n')[0][:100]

@app.command()
def studio(
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging of agent communications.")
):
    """ 
    Launch the side-by-side Streamlit Web UI.
    
    This command starts the interactive Resume Studio in your default web browser.
    """
    if debug:
        os.environ["MAGS_DEBUG"] = "true"
        console.print("[yellow]Debug mode enabled. Detailed logs will be written to workflow.log[/yellow]")

    # Locates ui.py in the package and runs it with streamlit
    ui_path = Path(__file__).parent / "ui.py"
    console.print(Panel("[bold green]Starting MAGS-Resume Studio...[/bold green]\n\nAccess the UI at [underline]http://localhost:8501[/underline]", expand=False))
    subprocess.run(["streamlit", "run", str(ui_path)])

@app.command()
def tokens():
    """
    Display a rich table of token usage and costs across all models and runs.
    
    Reads from the local SQLite database to show aggregated token counts by Agent Role and Model.
    """
    init_db() # Ensure DB and table exist
    per_role_summary, per_model_summary, total = get_token_summary()

    if not per_role_summary:
        console.print("[yellow]No token usage has been recorded yet.[/yellow]")
        return

    # --- Per Role Table ---
    role_table = Table(
        title="Token Usage by Agent/Role", 
        show_header=True, 
        header_style="bold cyan",
        show_footer=True,
        footer_style="bold"
    )
    role_table.add_column("Agent/Role", style="green", footer="Total")
    role_table.add_column("Model", style="yellow")
    role_table.add_column("Input Tokens", justify="right")
    role_table.add_column("Output Tokens", justify="right")
    role_table.add_column("Total Tokens", justify="right", footer=f"{total[0] + total[1]:,}")

    for role, model, in_tokens, out_tokens in per_role_summary:
        role_table.add_row(
            role,
            model,
            f"{in_tokens:,}",
            f"{out_tokens:,}",
            f"{in_tokens + out_tokens:,}"
        )
    console.print(role_table)

    # --- Per Model Table ---
    if per_model_summary:
        model_table = Table(
            title="Token Usage by Model",
            show_header=True,
            header_style="bold cyan",
            show_footer=True,
            footer_style="bold"
        )
        model_table.add_column("Model", style="yellow", footer="Total")
        model_table.add_column("Input Tokens", justify="right", footer=f"{total[0]:,}")
        model_table.add_column("Output Tokens", justify="right", footer=f"{total[1]:,}")
        model_table.add_column("Total Tokens", justify="right", footer=f"{total[0] + total[1]:,}")

        for model, in_tokens, out_tokens in per_model_summary:
            model_table.add_row(
                model,
                f"{in_tokens:,}",
                f"{out_tokens:,}",
                f"{in_tokens + out_tokens:,}"
            )
        
        console.print(model_table)


@app.command(name="list-models")
def list_models(
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help=_CONFIG_HELP_TEXT, resolve_path=True
    ),
):
    """List available models from the configured providers (OpenAI, Google, etc.)."""
    if config_path is None:
        config_path = find_default_config_path()

    config_path = resolve_config_path(config_path)

    if not config_path.exists():
        project_root = Path(__file__).resolve().parent.parent
        template = project_root / "config.template.yaml"
        
        console.print(Panel(
            f"[bold red]Config Not Found[/bold red]\n\n"
            f"Looking for: [yellow]{config_path}[/yellow]\n\n"
            f"Please create a config file. You can use the template at:\n[bold]{template}[/bold]\n\n"
            f"Fill in your API keys and preferred models.",
            title="Error", expand=False
        ))
        raise typer.Exit(1)

    logger.info(f"Using configuration: {config_path}")
    config = load_config(config_path)
    api_keys = config.get("api_keys", {})
    
    table = Table(title="Available Models", show_header=True, header_style="bold cyan")
    table.add_column("Provider", style="green")
    table.add_column("Model ID", style="yellow")

    # 1. OpenAI
    if api_keys.get("openai"):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_keys["openai"])
            # List models
            models = client.models.list()
            # Extract and sort just the model IDs (e.g., 'gpt-4o', 'gpt-4-turbo')
            gpt_models = sorted([m.id for m in models.data if "gpt" in m.id])
            for m in gpt_models:
                table.add_row("OpenAI", m)
        except Exception as e:
            table.add_row("OpenAI", f"[red]Error: {format_llm_error(e)}[/red]")

    # 2. Google (Gemini)
    if api_keys.get("gemini"):
        try:
            try:
                # Try the new Google GenAI SDK first
                from google import genai
                client = genai.Client(api_key=api_keys["gemini"])
                for m in client.models.list():
                    name = m.name.replace("models/", "")
                    table.add_row("Google", name)
            except ImportError:
                # Fallback to the deprecated SDK, suppressing the FutureWarning
                try:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        import google.generativeai as genai
                    genai.configure(api_key=api_keys["gemini"])
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods:
                            name = m.name.replace("models/", "")
                            table.add_row("Google", name)
                except ImportError:
                    table.add_row("Google", "[yellow]Skipped: 'google.genai' or 'google-generativeai' not installed[/yellow]")
        except Exception as e:
            table.add_row("Google", f"[red]Error: {format_llm_error(e)}[/red]")

    # 3. Anthropic
    if api_keys.get("anthropic"):
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=api_keys["anthropic"])
            response = client.models.list()
            model_ids = sorted([model.id for model in response.data])
            for m in model_ids:
                table.add_row("Anthropic", m)
        except Exception as e:
            table.add_row("Anthropic", f"[red]Error: {format_llm_error(e)}[/red]")

    # 4. Mistral
    if api_keys.get("mistral"):
        try:
            try:
                from mistralai.client import MistralClient
                client = MistralClient(api_key=api_keys["mistral"])
                models = client.list_models()
                for m in models.data:
                    table.add_row("Mistral", m.id)
            except ImportError:
                table.add_row("Mistral", "[yellow]Skipped: 'mistralai' not installed[/yellow]")
        except Exception as e:
            table.add_row("Mistral", f"[red]Error: {format_llm_error(e)}[/red]")

    # 5. Cohere
    if api_keys.get("cohere"):
        # Cohere does not have a simple model listing API like others.
        # We provide a static list of known recent models.
        known_models = ["command-r-plus", "command-r", "command", "command-light"]
        for m in known_models:
            table.add_row("Cohere (Static)", m)

    # 4. Custom / Local (e.g. Ollama)
    # Scan config for custom_openai providers to find base_urls
    custom_urls = set()
    models_config = config.get("models", {})    
    build_config = models_config.get("build_workflow", {})
    interactive_config = models_config.get("interactive_commands", {})

    # Combine all agent configs from new and old structures for scanning
    all_agent_configs = {
        **models_config, 
        **build_config, 
        **interactive_config
    }
    
    # Check roles relevant to MAGS-Resume
    # "writer" is the main agent, "chat" is for interactive CLI
    for role in ["writer", "chat"]:
        m_cfg = all_agent_configs.get(role, {})
        if m_cfg.get("provider") == "custom_openai" and m_cfg.get("base_url"):
            custom_urls.add(m_cfg.get("base_url"))
            
    # Check reviewers list
    reviewers_list = build_config.get("reviewers", []) or models_config.get("reviewers", [])
    for r_cfg in reviewers_list:
        if r_cfg.get("provider") == "custom_openai" and r_cfg.get("base_url"):
            custom_urls.add(r_cfg.get("base_url"))

    for url in custom_urls:
        try:
            from openai import OpenAI
            # Use dummy key for local
            client = OpenAI(base_url=url, api_key="dummy")
            models = client.models.list()
            for m in models.data:
                table.add_row(f"Custom ({url})", m.id)
        except Exception as e:
            table.add_row(f"Custom ({url})", f"[red]Error: {format_llm_error(e)}[/red]")

    console.print(table)

@app.command()
def clean(
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion without confirmation.")
):
    """Remove all generated cache files, logs, and temporary git worktrees."""
    console.print(Panel("[bold yellow]Cleaning up MAGS-Resume artifacts...[/bold yellow]"))

    # Find artifacts to delete
    mags_dir = Path(".MAGS-Resume")
    db_file = mags_dir / "cache.db"
    log_file = mags_dir / "workflow.log"
    
    # Temporary files or worktrees (if any)
    tmp_docx = [f for f in os.listdir('.') if f.endswith('.docx') and f.startswith('tmp')]

    items_to_delete = []
    if db_file.exists():
        items_to_delete.append(db_file)
    if log_file.exists():
        items_to_delete.append(log_file)
    items_to_delete.extend([Path(f) for f in tmp_docx])

    if not items_to_delete:
        console.print("[green]✓ No artifacts to clean.[/green]")
        raise typer.Exit()

    console.print("The following items will be permanently deleted:")
    for item in items_to_delete:
        console.print(f"- [red]{item}[/red]")

    if not force:
        if not typer.confirm("\nAre you sure you want to proceed?"):
            console.print("[yellow]Clean operation cancelled.[/yellow]")
            raise typer.Exit()

    console.print("") 
    for f in tmp_docx:
        if os.path.exists(f): os.remove(f); console.print(f"Deleted temp file: {f}")

    if db_file.exists(): os.remove(db_file); console.print(f"Deleted database: {db_file}")
    if log_file.exists(): os.remove(log_file); console.print(f"Deleted log file: {log_file}")
        
    # Try to remove the directory if empty
    if mags_dir.exists() and not any(mags_dir.iterdir()):
        os.rmdir(mags_dir)
        console.print(f"Removed directory: {mags_dir}")
    
    console.print("\n[bold green]✓ Cleanup complete.[/bold green]")

if __name__ == "__main__":
    app()