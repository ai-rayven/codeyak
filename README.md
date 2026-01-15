# AI Code Review Agent

![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)
![Platform](https://img.shields.io/badge/platform-GitLab-orange)
![LLM](https://img.shields.io/badge/LLM-Azure%20OpenAI-green)

Automatically review GitLab merge requests using customizable guidelines powered by AI.

**Key Features:**
- Flexible guidelines system with built-in presets (security, style, balanced)
- Multi-pass focused reviews
- Smart comment deduplication
- GitLab CI/CD integration

**Platform Support:** GitLab + Azure OpenAI (GitHub, OpenAI, Anthropic coming soon)

## Quick Start

1. **Configure CI/CD variables** in GitLab (Settings → CI/CD → Variables):
   - `GITLAB_TOKEN`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_DEPLOYMENT_NAME`, `AGENT_REPO_URL`

2. **Add to `.gitlab-ci.yml`**:
   ```yaml
   ai_code_review:
     stage: review
     image: python:3.12-slim
     before_script:
       - apt-get update && apt-get install -y git && pip install uv
     script:
       - git clone $AGENT_REPO_URL agent_code && cd agent_code
       - uv sync --frozen
       - uv run python -m code_reviewer $CI_MERGE_REQUEST_IID $CI_PROJECT_ID
     rules:
       - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
   ```

3. **Open a merge request** - the agent automatically reviews and posts inline comments

## Guidelines System

Control review behavior with YAML guideline files. The agent uses:
- **Project guidelines** (`.code_review/*.yaml`) if present
- **Built-in `default` preset** otherwise

Each YAML file runs a separate focused review pass.

### Built-in Presets

**`default`** - Comprehensive balanced review (32 guidelines)
- Imports: `security` + `readability` + `maintainability`
- Covers all aspects of code quality

**`security`** - Security-focused (15 guidelines)
- Secrets management, injection prevention (SQL, XSS, command)
- Authentication, authorization, session management
- Strong cryptography, password hashing
- Data encryption, safe error handling

**`readability`** - Code clarity (7 guidelines)
- Function length and clarity
- Descriptive and intentional naming
- Self-documenting code, meaningful comments

**`maintainability`** - Long-term code health (10 guidelines)
- Single Responsibility, low complexity
- Logical organization, code proximity
- DRY principle, no dead code
- Proper exception handling

### Custom Guidelines

Create `.code_review/my-rules.yaml`:

```yaml
guidelines:
  - label: rate-limiting
    description: All API endpoints must include rate limiting.

  - label: n-plus-one
    description: Avoid N+1 queries by using eager loading.
```

Guidelines are automatically assigned IDs based on the filename and label:
- File: `my-rules.yaml` → Prefix: `my-rules`
- Label: `rate-limiting` → ID: `my-rules/rate-limiting`

**ID format:** `prefix/label` (e.g., `security/sql-injection`, `custom/rate-limiting`)
**Label requirements:** lowercase, alphanumeric, hyphens only

### Using Built-in Presets

Include presets with your custom rules:

```yaml
includes:
  - builtin:security
  - builtin:readability

guidelines:
  - label: api-timeout
    description: All external API calls must have timeout limits.
```

**Available includes:** `builtin:default`, `builtin:security`, `builtin:readability`, `builtin:maintainability`

### Multi-Pass Reviews

Multiple files = multiple focused passes:

```
.code_review/
├── 01-security.yaml      # Security pass
├── 02-style.yaml         # Style pass
└── 03-project-rules.yaml # Custom rules pass
```

Each file can include built-in presets or define custom guidelines.

## Environment Variables

**Required:**
```bash
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=<your-token>
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_ENDPOINT=<your-endpoint>
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_DEPLOYMENT_NAME=gpt-4o
```

**Optional:**
```bash
LANGFUSE_SECRET_KEY=<key>    # For observability
LANGFUSE_PUBLIC_KEY=<key>
LANGFUSE_HOST=https://cloud.langfuse.com
```

## Local Development

```bash
# Install
git clone <repo-url> && cd code-reviewer
cp .env.example .env  # Fill in credentials
uv sync

# Run review
uv run python -m code_reviewer <MR_IID> <PROJECT_ID>

# Test with custom guidelines
mkdir -p .code_review
echo "includes:
  - builtin:security" > .code_review/security.yaml
uv run python -m code_reviewer <MR_IID> <PROJECT_ID>
```

## How It Works

1. Fetches MR diff and existing review comments
2. Runs review pass(es) based on active guidelines
3. Compares violations against existing comments (same file + guideline + within 10 lines)
4. Posts only new, unique findings as inline comments

Built with hexagonal architecture for easy extensibility (pluggable VCS and LLM adapters).

---

Built with ❤️ using Python and AI
