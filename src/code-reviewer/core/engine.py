from typing import List
import json
from .ports import VCSClient, LLMClient
from .models import Guideline, ReviewResult
from .grouping import create_file_groups
from .prompts import build_review_messages

class ReviewEngine:
    def __init__(self, vcs: VCSClient, llm: LLMClient):
        self.vcs = vcs
        self.llm = llm

    def run(self, mr_id: str):
        print(f"Starting review for MR {mr_id}...")

        # 1. Fetch & Parse Data
        diffs = self.vcs.get_diff(mr_id)
        if not diffs:
            print("No changes found.")
            return

        # 2. Prepare Chunks (Grouping Logic)
        groups = create_file_groups(diffs)
        guidelines = self._load_guidelines()
        print(f"Split {len(diffs)} files into {len(groups)} analysis groups.")

        # 3. Analyze each group
        for group in groups:
            print(f"   Processing Group {group.group_id} ({len(group.files)} files)...")
            
            messages = build_review_messages(group.files, guidelines)
            
            result = self.llm.generate(messages, response_model=ReviewResult)
            
            self._process_results(mr_id, result)

            print(f" {json.dumps(result)}")

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
                description="Avoid hardcoded secrets, API keys, or passwords."
            ),
            Guideline(
                id="STYLE-01", 
                description="No long functions." 
            ),
            Guideline(
                id="STYLE-02",
                description="The code must be very easy to read and understand."
            ),
            Guideline(
                id="STYLE-03",
                description="No long functions and no God services."
            ),
            Guideline(
                id="ERR-01", 
                description="Do not catch exceptions unless you are handling them. Let them bubble up.", 
            ),
        ]