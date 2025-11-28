# Forte: A Synergistic Multi-Agent Framework for AI-Powered Code Reviews

Forte is a cutting-edge, automated code review assistant that deploys a synergistic multi-agent framework powered by state-of-the-art Large Language Models (LLMs). By providing intelligent, context-aware feedback on GitLab Merge Requests, Forte streamlines development workflows, enhances code quality, and accelerates the delivery lifecycle.

## Key Features

- **Automated Review Cycle**: Seamlessly integrates into the CI/CD pipeline, triggering reviews on Merge Request creation and updates.
- **Synergistic Multi-Agent System**: Forte utilizes a team of specialized AI agents that collaborate to perform a holistic analysis of your code. Each agent is an expert in a specific domain, ensuring comprehensive and high-quality feedback.
- **Multi-LLM Support**: Agnostic to the underlying model provider, with out-of-the-box support for OpenAI (GPT) and Google (Gemini).
- **Intelligent Auto-Tagging**: Leverages LLMs to analyze MR context and automatically apply relevant labels (e.g., `bug`, `security`, `refactor`).
- **Enterprise Integration**: Connects with Jira to enrich the review context with relevant ticket information.
- **Extensible by Design**: Built with a modular architecture that allows for easy addition of new features and agents. GitHub support is planned.

## The Agentic Framework

Forte's intelligence is rooted in its extensible agentic architecture, located in `app/review/agentic/`. This framework allows for the parallel execution of specialized agents, each designed to analyze a unique facet of the code submission.

### Core Agents

The system is composed of several key agents, each inheriting from a base agent class defined in `app/review/agentic/agents/base.py`:

- **Task Context Agent (`task_agent.py`)**: This agent acts as the project manager, performing initial research on the Merge Request to understand its purpose and scope by analyzing the title, description, and commit history.
- **Code Analysis Agent (`code_agent.py`)**: Conducts a deep dive into the source code changes, providing a concise summary of the modifications.
- **Architecture Visualization Agent (`diagram_agent.py`)**: Generates system-level architecture diagrams in Mermaid format to visually represent the impact of the changes.
- **Code Quality Agent (`naming_agent.py`)**: Enforces best practices by scrutinizing naming conventions, documentation, and overall code clarity.
- **Test Coverage Agent (`test_agent.py`)**: Evaluates the thoroughness of testing and identifies potential gaps in test coverage.

This modular design, centered around the `app/review/agentic/agents/` directory, allows for easy extension. New agents can be developed and integrated to introduce novel analysis capabilities, such as security vulnerability scanning or performance profiling.

## Getting Started

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configuration

Bootstrap your configuration by creating a `.env` file from the provided `.env.example`.

**Core Variables:**

- `GITLAB_URL`: Your GitLab instance URL.
- `GITLAB_TOKEN`: A GitLab Personal Access Token with `api` scope.
- `GITLAB_WEBHOOK_SECRET`: A secret for webhook payload validation.
- `WEBHOOK_URL`: The public endpoint for your Forte server.

**LLM Configuration (Google Gemini by default):**

- `AGENTIC_PROVIDER`: `google` or `openai`.
- `GOOGLE_API_KEY` / `OPENAI_API_KEY`: Your API key for the chosen provider.
- `AGENTIC_MODEL`: The specific model to use (e.g., `gemini-1.5-flash`, `gpt-4o-mini`).

For local development, `ngrok` can be used to expose your local server: `ngrok http 8080`.

### 3. Launch the Service

```bash
python main.py serve
```

### 4. Register Webhooks

Activate the assistant by registering webhooks for your target projects.

```bash
python main.py register-hooks
```

## Project Architecture

The project is architected on SOLID principles for maintainability and scalability:

- `app/review/agentic/`: The core of the AI engine. This directory contains the agent orchestrator (`generator.py`), LLM clients (`llm.py`), and the specialized agents.
- `app/review/agentic/agents/`: Home to the individual AI agents. Each file (`code_agent.py`, `diagram_agent.py`, etc.) defines a specialized agent. This modular structure is key to the project's extensibility.
- `app/vcs/`: A hardware abstraction layer (HAL) for version control systems, enabling future support for platforms like GitHub.
- `app/webhook/`: Ingress controller for webhook processing.
- `app/server/`: FastAPI web server application.
- `main.py`: CLI entry point for server management and utility commands.

## Future Roadmap

- **GitHub Integration**: Extend VCS support to GitHub Pull Requests.
- **Enhanced Agent Capabilities**: Introduce new agents for security vulnerability analysis, performance profiling, and dependency checking.
- **Granular Configuration**: Implement project-level configuration for fine-tuning review rules.

## Troubleshooting

- **401 Invalid webhook token**: Ensure `GITLAB_WEBHOOK_SECRET` matches the secret in your GitLab webhook configuration.
- **Agentic reviewer failures**: Verify your LLM provider API keys and model names are correctly configured.
- **Enable verbose logging**: `export LOG_LEVEL=DEBUG`.
