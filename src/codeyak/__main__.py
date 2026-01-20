import sys
import os
from .config import get_settings
from codeyak.infrastructure import GitLabAdapter, AzureAdapter
from codeyak.services import (
    CodeReviewer,
    GuidelinesProvider,
    CodeProvider,
    CodeReviewContextBuilder,
    FeedbackPublisher,
    SummaryGenerator,
)
from langfuse import Langfuse

def log_settings():
    # Log all settings for debugging
    print("\n📋 Configuration Settings:")
    print(f"  GITLAB_URL: {get_settings().GITLAB_URL}")
    print(f"  GITLAB_TOKEN: {get_settings().GITLAB_TOKEN[:8]}...{get_settings().GITLAB_TOKEN[-4:] if len(get_settings().GITLAB_TOKEN) > 12 else '***'}")
    print(f"  AZURE_OPENAI_API_KEY: {get_settings().AZURE_OPENAI_API_KEY[:8]}...{get_settings().AZURE_OPENAI_API_KEY[-4:] if len(get_settings().AZURE_OPENAI_API_KEY) > 12 else '***'}")
    print(f"  AZURE_OPENAI_ENDPOINT: {get_settings().AZURE_OPENAI_ENDPOINT}")
    print(f"  AZURE_OPENAI_API_VERSION: {get_settings().AZURE_OPENAI_API_VERSION}")
    print(f"  AZURE_DEPLOYMENT_NAME: {get_settings().AZURE_DEPLOYMENT_NAME}")
    print(f"  LANGFUSE_SECRET_KEY: {'(set)' if get_settings().LANGFUSE_SECRET_KEY else '(not set)'}")
    print(f"  LANGFUSE_PUBLIC_KEY: {'(set)' if get_settings().LANGFUSE_PUBLIC_KEY else '(not set)'}")
    print(f"  LANGFUSE_HOST: {get_settings().LANGFUSE_HOST}")
    print()

def main():
    # 1. Parse CLI Arguments
    if len(sys.argv) < 2:
        print("Usage: uv run python -m codeyak <MR_ID> [PROJECT_ID]")
        sys.exit(1)

    mr_id = sys.argv[1]
    
    # In GitLab CI, this env var is always present. Locally, you can pass it as arg 2.
    project_id = sys.argv[2] if len(sys.argv) > 2 else os.getenv("CI_PROJECT_ID")
    
    if not project_id:
        print("❌ Error: Project ID is required. Pass it as the second argument or set CI_PROJECT_ID.")
        sys.exit(1)

    print(f"🔧 Initializing Agent for Project {project_id}, MR {mr_id}...")

    log_settings()

    # Initialize Langfuse if configured
    langfuse_enabled = bool(
        get_settings().LANGFUSE_SECRET_KEY and
        get_settings().LANGFUSE_PUBLIC_KEY
    )

    langfuse = None
    if langfuse_enabled:
        langfuse = Langfuse(
            secret_key=get_settings().LANGFUSE_SECRET_KEY,
            public_key=get_settings().LANGFUSE_PUBLIC_KEY,
            host=get_settings().LANGFUSE_HOST
        )
        print("✅ Langfuse tracing enabled")
    else:
        print("⚠️ Langfuse tracing disabled (keys not configured)")

    # 2. Instantiate Adapters (The Plumbing)
    # We explicitly inject the dependencies here.
    try:
        vcs = GitLabAdapter(
            url=get_settings().GITLAB_URL,
            token=get_settings().GITLAB_TOKEN,
            project_id=project_id
        )
        
        llm = AzureAdapter(
            api_key=get_settings().AZURE_OPENAI_API_KEY,
            endpoint=get_settings().AZURE_OPENAI_ENDPOINT,
            deployment_name=get_settings().AZURE_DEPLOYMENT_NAME,
            api_version=get_settings().AZURE_OPENAI_API_VERSION
        )
    except Exception as e:
        print(f"❌ Configuration Error: {e}")
        sys.exit(1)

    # 3. Instantiate Services
    context = CodeReviewContextBuilder()
    guidelines = GuidelinesProvider(vcs)
    code = CodeProvider(vcs)
    feedback = FeedbackPublisher(vcs)
    summary = SummaryGenerator(llm, langfuse)

    # 4. Instantiate Reviewer (The Brain)
    bot = CodeReviewer(
        context=context,
        guidelines=guidelines,
        code=code,
        feedback=feedback,
        llm=llm,
        summary=summary,
        langfuse=langfuse,
    )

    # 5. Run!
    bot.review_merge_request(mr_id)

    # 6. Flush Langfuse traces
    if langfuse:
        print("Flushing Langfuse traces...")
        langfuse.flush()

if __name__ == "__main__":
    main()