# AI Code Review Agent

A code review agent optimized for following strict guidelines and providing actionable feedback on merge requests.

## Current Support

**VCS Platforms:**
- GitLab (via GitLab CI/CD)

**LLM Providers:**
- Azure OpenAI

**Note:** Support for additional VCS platforms (GitHub) and LLM providers (OpenAI, Anthropic, etc.) is planned for future releases.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- GitLab project with CI/CD enabled
- Azure OpenAI API access

## Setup

### 1. Configure Environment Variables

The agent requires the following environment variables. In GitLab CI, set these as [CI/CD variables](https://docs.gitlab.com/ee/ci/variables/) (Settings → CI/CD → Variables):

```bash
# GitLab Configuration
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=<your-gitlab-token>

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY=<your-azure-key>
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_DEPLOYMENT_NAME=gpt-4o

# Optional: Langfuse Observability
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

### GitLab CI Variables

In your GitLab project, set these CI/CD variables:
- `GITLAB_TOKEN`: Personal/project access token with `api` scope
- `AZURE_OPENAI_API_KEY`: Your Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint URL
- `AZURE_DEPLOYMENT_NAME`: Your GPT-4 deployment name
- `AGENT_REPO_URL`: URL to this repository (for cloning in CI)

Optional observability variables:
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_PUBLIC_KEY`

## GitLab CI/CD Integration

Add this job to your `.gitlab-ci.yml`:

```yaml
stages:
  - review

ai_code_review:
  stage: review
  image: python:3.11-slim
  variables:
    TARGET_PROJECT_ID: $CI_PROJECT_ID
    TARGET_MR_IID: $CI_MERGE_REQUEST_IID

  before_script:
    - apt-get update && apt-get install -y git
    - pip install uv

  script:
    - echo "🤖 Fetching AI Code Review Agent..."
    - git clone $AGENT_REPO_URL agent_code
    - cd agent_code

    - echo "📦 Installing Agent Dependencies..."
    - uv sync --frozen

    - echo "🚀 Running Review..."
    - uv run python -m code_reviewer $TARGET_MR_IID $TARGET_PROJECT_ID

  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
```

The agent will automatically post review comments on merge requests when triggered.

## Local Development

1. Clone the repository
2. Copy `.env.example` to `.env` and fill in your credentials
3. Install dependencies: `uv sync`
4. Run a review: `uv run python -m code_reviewer <MR_IID> <PROJECT_ID>`

## Current Support

**VCS Platforms:** GitLab only
**LLM Providers:** Azure OpenAI only

More platforms and providers coming soon.

## Architecture

The agent follows a ports and adapters (hexagonal) architecture:
- Core review engine is provider-agnostic
- Adapters for VCS and LLM can be easily swapped/extended
- Structured outputs using Instructor and Pydantic