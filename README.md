<p align="center">
  <img src="https://raw.githubusercontent.com/ai-rayven/codeyak/main/images/codeyak-logo.png" alt="CodeYak" width="200">
</p>
<h1 align="center">CodeYak</h1>
<p align="center"><strong>Automated code review that enforces your team's standards.</strong></p>
<p align="center">
  <a href="https://pypi.org/project/codeyak/"><img src="https://img.shields.io/pypi/v/codeyak" alt="PyPI"></a>
  <a href="https://pypi.org/project/codeyak/"><img src="https://img.shields.io/pypi/pyversions/codeyak" alt="Python"></a>
  <a href="https://github.com/ai-rayven/codeyak/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/codeyak" alt="License"></a>
</p>

---

CodeYak reviews your code changes against configurable guidelines using AI. Define your team's standards in simple YAML files, and CodeYak enforces them on every commit — locally or in CI.

**Designed to be cheap to run.** CodeYak uses smart context building — it parses your code with tree-sitter to send only the relevant snippets and function signatures to the LLM, not entire files. A typical MR review costs fractions of a cent. Hook up [Langfuse](#observability-with-langfuse) to track exactly what you're spending.

- **Review local changes** before you push
- **Review GitLab merge requests** with inline comments and code suggestions
- **Summarize changes** — get an AI-generated summary of local changes, commits, or merge requests
- **Learn from your repo's history** to auto-generate project-specific guidelines
- **Built-in presets** for security and code quality — or write your own

<!-- TODO: Add demo video/GIF here
<div align="center">
  <a href="https://link-to-video">
    <img src="https://raw.githubusercontent.com/ai-rayven/codeyak/main/images/demo.gif" alt="CodeYak Demo" width="700">
  </a>
</div>
-->

## Quick Start

### 1. Install

```bash
uv tool install codeyak
```

Or with pip:

```bash
pip install codeyak
```

### 2. Generate guidelines from your repo's history

```bash
yak learn
```

CodeYak analyzes your commit history — bug fixes, reverts, security patches — and generates guidelines that reflect lessons your team has already learned the hard way. Guidelines are saved to `.codeyak/project.yaml`.

### 3. Review your changes

```bash
yak review
```

That's it. CodeYak reviews your uncommitted changes against your guidelines and reports violations in the terminal.

### 4. Add to CI

See [GitLab CI Integration](#gitlab-ci-integration) to run CodeYak automatically on every merge request.

> On first run, `yak` prompts for configuration (Azure OpenAI credentials). Settings are stored in `~/.config/codeyak/config.toml`.

## Commands

### `yak review` — Review local changes

Reviews uncommitted changes in your current git repo against your guidelines.

```bash
# Review changes in the current repo
yak review

# Review changes in a specific repo
yak review --path /path/to/repo
```

Violations are printed to the terminal with the file, line number, guideline that was violated, and an explanation.

### `yak mr` — Review a GitLab merge request

Reviews a merge request and posts inline comments directly on the MR, including code suggestions when applicable.

```bash
yak mr <MR_ID> <PROJECT_ID>
```

CodeYak will:
- Fetch the MR diff and existing comments
- Review changes against guidelines from the target repo's `.codeyak/` directory
- Post inline comments on specific lines where violations are found
- Post a summary comment with an overview of the changes
- Skip violations that have already been commented on (safe to re-run)

### `yak summary` — Summarize code changes

Generates an AI-powered summary of code changes — local uncommitted changes, a GitLab merge request, or the last N commits.

```bash
# Summarize uncommitted local changes
yak summary

# Summarize a GitLab merge request
yak summary --mr <MR_ID> --project <PROJECT_ID>

# Summarize the last N commits
yak summary --commits 5

# Summarize changes in a specific repo
yak summary --path /path/to/repo
```

### `yak learn` — Generate guidelines from history

Analyzes your git history to discover patterns from bug fixes, reverts, and security patches, then generates actionable review guidelines.

```bash
# Analyze the last year of commits (default)
yak learn

# Analyze a specific time range
yak learn --days 180
```

The generated guidelines are saved to `.codeyak/project.yaml`. If guidelines already exist, new ones are merged in without duplicating existing rules.

**How it works:** CodeYak classifies each commit by type (bug fix, revert, refactor, security fix, etc.), focuses on "high-signal" commits where something went wrong, extracts lessons from the diffs, and synthesizes them into actionable guidelines.

## Guidelines

CodeYak uses `.codeyak/*.yaml` files in your repo for review guidelines. All YAML files in the directory are loaded. Without custom files, CodeYak uses the built-in `default` preset.

### Built-in Presets

| Preset | What it covers |
|--------|---------------|
| `default` | Includes code-quality |
| `code-quality` | Single responsibility, naming, code organization, dead code removal, overengineering |
| `security` | Injection prevention, auth, cryptography, secrets, session management, data protection |

### Writing custom guidelines

Create a `.codeyak/` directory in your repo and add YAML files:

`.codeyak/my-rules.yaml`:
```yaml
guidelines:
  - label: rate-limiting
    description: All API endpoints must include rate limiting.

  - label: no-print-statements
    description: Use structured logging instead of print(). No print statements in production code.
```

Each guideline needs a `label` (short identifier) and a `description` (what the reviewer should enforce).

### Combining presets with custom rules

Use `includes` to pull in built-in presets alongside your own rules:

```yaml
includes:
  - builtin:security
  - builtin:code-quality

guidelines:
  - label: api-timeout
    description: All external API calls must have timeout limits.

  - label: validate-responses
    description: Always validate external API responses before use.
```

### Guidelines generated by `yak learn`

The `learn` command outputs structured guidelines with context about why each rule was generated:

```yaml
guidelines:
  - label: normalize-and-validate-config-inputs
    description: |
      Normalize external configs (strip trailing slashes from endpoints,
      canonicalize formats) and validate them early on application startup
      boundary to prevent subtle runtime errors.
    # Confidence: high
    # Reasoning: Trailing slash in Azure endpoint broke authentication;
    # normalizing and validating at boundaries avoids such mismatches.
```

## GitLab CI Integration

Add CodeYak as a review stage in your `.gitlab-ci.yml`:

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

### Required CI/CD variables

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT_NAME` | Model deployment name (e.g., `gpt-4o`) |
| `GITLAB_TOKEN` | GitLab API token with `api` scope |

### Optional variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITLAB_URL` | GitLab instance URL | `https://gitlab.com` |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key (observability) | — |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key (observability) | — |
| `LANGFUSE_HOST` | Langfuse host URL | — |

## Configuration

CodeYak checks for configuration in this order:

1. **Config file** — `~/.config/codeyak/config.toml` (created on first run)
2. **Environment variables** — for CI/CD and containerized environments
3. **`.env` file** — in the current directory, for local development

Copy the included `.env.example` to get started:

```bash
cp .env.example .env
# Edit .env with your credentials
```

## Observability with Langfuse

CodeYak integrates with [Langfuse](https://langfuse.com) to give you full visibility into how your reviews are performing. When connected, you can:

- **Track token usage and cost** across reviews — see exactly what each review costs and optimize your guidelines to reduce spend
- **Trace every LLM call** — inspect the prompts, responses, and latency for each review step (guideline evaluation, summary generation, code suggestions)
- **Monitor review quality over time** — identify which guidelines produce the most violations, spot false positives, and tune your rules based on real data
- **Debug unexpected results** — when a review flags something odd, trace back to the exact prompt and model response to understand why

Set the Langfuse environment variables (see [Optional variables](#optional-variables)) and every review is automatically traced.

## License

MIT
