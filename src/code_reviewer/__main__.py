import sys
import os
from .config import settings
from .adapters.vcs.gitlab import GitLabAdapter
from .adapters.llm.azure import AzureAdapter
from .core.engine import ReviewEngine

def main():
    # 1. Parse CLI Arguments
    if len(sys.argv) < 2:
        print("Usage: uv run python -m code_review_agent <MR_ID> [PROJECT_ID]")
        sys.exit(1)

    mr_id = sys.argv[1]
    
    # In GitLab CI, this env var is always present. Locally, you can pass it as arg 2.
    project_id = sys.argv[2] if len(sys.argv) > 2 else os.getenv("CI_PROJECT_ID")
    
    if not project_id:
        print("❌ Error: Project ID is required. Pass it as the second argument or set CI_PROJECT_ID.")
        sys.exit(1)

    print(f"🔧 Initializing Agent for Project {project_id}, MR {mr_id}...")

    # 2. Instantiate Adapters (The Plumbing)
    # We explicitly inject the dependencies here.
    try:
        vcs = GitLabAdapter(
            url=settings.GITLAB_URL,
            token=settings.GITLAB_TOKEN,
            project_id=project_id
        )
        
        llm = AzureAdapter(
            api_key=settings.AZURE_OPENAI_API_KEY,
            endpoint=settings.AZURE_OPENAI_ENDPOINT,
            deployment_name=settings.AZURE_DEPLOYMENT_NAME
        )
    except Exception as e:
        print(f"❌ Configuration Error: {e}")
        sys.exit(1)

    # 3. Instantiate Engine (The Brain)
    bot = ReviewEngine(vcs=vcs, llm=llm)

    # 4. Run!
    bot.run(mr_id)

if __name__ == "__main__":
    main()