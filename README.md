# MAGS-Resume Studio

MAGS-Resume is an AI-powered career assistant designed to help you tailor resumes and answer application questions with precision. It uses a multi-agent graph workflow to refine your resume against specific job descriptions while maintaining the integrity of your professional narrative.

## Features

- **Resume Studio**: A side-by-side Streamlit UI to generate, edit, and diff-tailored resumes.
- **Multi-Agent Workflow**: Utilizes specialized agents (Writer, Reviewer) for iterative refinement.
- **Application Q&A**: A chat interface to draft answers for screening questions based on your resume and the job ad.
- **Token Tracking**: Detailed logging of LLM usage and costs in a local SQLite database.
- **Multi-Provider Support**: Compatible with OpenAI, Anthropic, Google Gemini, Mistral, and Cohere.

## Prerequisites

- [Conda](https://docs.conda.io/en/latest/) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
- API Keys for your preferred LLM providers (OpenAI, Anthropic, etc.)

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd MAGS-Resume
   ```

2. **Create the Conda environment:**
   ```bash
   conda env create -f environment.yml
   conda activate mags-resume
   ```

3. **Install the package in editable mode:**
   ```bash
   pip install -e .
   ```

## Configuration

1. Create a `config.yaml` file in the root directory. You can use the provided template if available, or create one with the following structure:
   ```yaml
   api_keys:
     openai: "your-key-here"
     anthropic: "your-key-here"
     gemini: "your-key-here"

   models:
     build_workflow:
       writer: { provider: "openai", model: "gpt-4o" }
       reviewers:
         - { provider: "anthropic", model: "claude-3-5-sonnet-20240620" }
     interactive_commands:
       chat: { provider: "google", model: "gemini-1.5-pro" }
   ```

## Usage

The project provides a unified CLI tool: `mags-resume`.

### Launching the Studio
To start the interactive Web UI:
```bash
mags-resume studio
```
Access the interface at `http://localhost:8501`.

### Checking Token Usage
To view a summary of tokens used and estimated costs:
```bash
mags-resume tokens
```

### Listing Available Models
To verify your API keys and see which models are available from your providers:
```bash
mags-resume list-models
```

### Cleaning Artifacts
To remove temporary files, logs, and the cache database:
```bash
mags-resume clean
```

## Container Deployment

### Docker
```bash
docker build -t mags-resume .
docker run -p 8501:8501 mags-resume
docker run -p 8501:8501 mags-resume studio
```

### Apptainer
```bash
apptainer build --force --fakeroot --ignore-fakeroot-command container.sif container.def
# Run with default port and auto-generated token
apptainer run container.sif studio
# Run with custom port, IP, and a specific token
apptainer run container.sif studio --port 8888 --ip 0.0.0.0 --token mysecrettoken123
```
