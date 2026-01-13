import gitlab
import os
from typing import List
from gitlab.v4.objects import ProjectMergeRequest

from ...core.ports import VCSClient
from ...core.models import FileDiff, GuidelineViolation

class GitLabAdapter(VCSClient):
    def __init__(self, url: str, token: str, project_id: str):
        self.gl = gitlab.Gitlab(url=url, private_token=token)
        self.project = self.gl.projects.get(project_id)
        # Cache for MR objects to avoid re-fetching for every comment
        self._mr_cache = {}

    def _get_mr(self, mr_iid: str) -> ProjectMergeRequest:
        if mr_iid not in self._mr_cache:
            self._mr_cache[mr_iid] = self.project.mergerequests.get(mr_iid)
        return self._mr_cache[mr_iid]

    def get_diff(self, mr_id: str) -> List[FileDiff]:
        mr = self._get_mr(mr_id)
        
        # 'changes()' fetches the diffs. 
        # access_raw_diffs=True is vital for large files.
        changes = mr.changes(access_raw_diffs=True)
        
        diffs = []
        for change in changes['changes']:
            # Skip deleted files
            if change['deleted_file']:
                continue
                
            diffs.append(FileDiff(
                file_path=change['new_path'],
                old_path=change['old_path'],
                diff_content=change['diff'],
                language=self._detect_language(change['new_path'])
            ))
            
        return diffs

    def post_comment(self, mr_id: str, violation: GuidelineViolation) -> None:
        mr = self._get_mr(mr_id)
        
        # We need the "diff_refs" to anchor the comment to a specific version
        # otherwise GitLab rejects the position.
        diff_refs = mr.diff_refs
        
        payload = {
            "body": violation.to_comment(),
            "position": {
                "position_type": "text",
                "base_sha": diff_refs['base_sha'],
                "head_sha": diff_refs['head_sha'],
                "start_sha": diff_refs['start_sha'],
                "new_path": violation.file_path,
                "new_line": violation.line_number,
            }
        }
        
        try:
            mr.discussions.create(payload)
            print(f"✅ Posted comment on {violation.file_path}:{violation.line_number}")
        except Exception as e:
            print(f"❌ Failed to post comment: {e}")

    def _detect_language(self, path: str) -> str:
        """Simple extension-based detection"""
        ext = path.split('.')[-1].lower()
        mapping = {
            'py': 'python', 'js': 'javascript', 'ts': 'typescript', 
            'java': 'java', 'cs': 'csharp', 'go': 'go'
        }
        return mapping.get(ext, 'text')