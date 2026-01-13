from typing import List
from .ports import VCSClient, LLMClient
from .models import Guideline, ReviewResult
from .grouping import create_file_groups
from .prompts import build_review_messages

class ReviewEngine:
    def __init__(self, vcs: VCSClient, llm: LLMClient):
        self.vcs = vcs
        self.llm = llm

    def run(self, mr_id: str):
        print(f"🚀 Starting review for MR {mr_id}...")

        # 1. Fetch & Parse Data
        diffs = self.vcs.get_diff(mr_id)
        if not diffs:
            print("No changes found.")
            return

        # 2. Prepare Chunks (Grouping Logic)
        groups = create_file_groups(diffs)
        guidelines = self._load_guidelines()
        print(f"📦 Split {len(diffs)} files into {len(groups)} analysis groups.")

        # 3. Analyze each group
        for group in groups:
            print(f"   Processing Group {group.group_id} ({len(group.files)} files)...")
            
            # A. Build Prompt (Pure Logic)
            messages = build_review_messages(group.files, guidelines)
            
            # B. Call AI (Generic Gateway)
            # We ask for a 'ReviewResult' object, and the adapter guarantees it.
            result = self.llm.generate(messages, response_model=ReviewResult)
            
            # C. Post Comments (Side Effect)
            self._process_results(mr_id, result)

        print("✅ Review complete.")

    def _process_results(self, mr_id: str, result: ReviewResult):
        """Iterates through findings and posts them to GitLab."""
        for violation in result.violations:
            print(f"     found {violation.guideline_id} in {violation.file_path}")
            self.vcs.post_comment(mr_id, violation)

    def _load_guidelines(self) -> List[Guideline]:
        """
        V1: Hardcoded rules. 
        V2: Load from guidelines.md or a database.
        """
        return [
            Guideline(
                id="SEC-01", 
                description="Avoid hardcoded secrets, API keys, or passwords.", 
                severity="critical"
            ),
            Guideline(
                id="PERF-01", 
                description="Avoid N+1 query problems inside loops.", 
                severity="major"
            ),
            Guideline(
                id="ERR-01", 
                description="Do not use bare 'except:' clauses. Catch specific exceptions.", 
                severity="minor"
            ),
        ]