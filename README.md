# CodeYak

AI-powered code review with configurable guidelines.

## Installation

```bash
uv tool install codeyak
```

## CLI Usage

```bash
# Review local uncommitted changes
yak review

# Review a GitLab merge request
yak mr <MR_ID> <PROJECT_ID>
```

On first run, `yak` prompts for configuration (Azure OpenAI credentials, GitLab token).

## GitLab CI

```yaml
codeyak:
  stage: review
  image: python:3.12-slim
  before_script:
    - pip install uv && uv tool install codeyak
  script:
    - yak mr $CI_MERGE_REQUEST_IID $CI_PROJECT_ID
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
```

Required CI/CD variables: `GITLAB_TOKEN`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_DEPLOYMENT_NAME`

## Guidelines

CodeYak uses `.codeyak/*.yaml` files for review guidelines. Without custom files, it uses the `default` preset.

### Built-in Presets

- `default` - includes code-quality
- `security` - injection prevention, auth, cryptography, secrets
- `code-quality` - SRP, naming, organization, error handling

### Custom Guidelines

`.codeyak/my-rules.yaml`:
```yaml
guidelines:
  - label: rate-limiting
    description: All API endpoints must include rate limiting.
```

### Include Presets

```yaml
includes:
  - builtin:security
  - builtin:code-quality

guidelines:
  - label: api-timeout
    description: All external API calls must have timeout limits.
```

## Environment Variables

```bash
# Required
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_ENDPOINT=<endpoint>
AZURE_DEPLOYMENT_NAME=gpt-4o

# For GitLab MR reviews
GITLAB_URL=https://gitlab.com  # optional, defaults to gitlab.com
GITLAB_TOKEN=<token>

# Optional observability
LANGFUSE_SECRET_KEY=<key>
LANGFUSE_PUBLIC_KEY=<key>
LANGFUSE_HOST=https://cloud.langfuse.com
```
