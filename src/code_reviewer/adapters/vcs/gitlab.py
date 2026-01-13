import gitlab
from typing import List
from gitlab.v4.objects import ProjectMergeRequest

from ...core.ports import VCSClient
from ...core.models import FileDiff, GuidelineViolation
from ...core.exceptions import LineNotInDiffError, VCSCommentError

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
            ))
            
        return diffs

    def post_comment(self, mr_id: str, violation: GuidelineViolation) -> None:
        """
        Post an inline comment on a specific line in the MR diff.

        Raises:
            LineNotInDiffError: When the line is not part of the diff
            VCSCommentError: When posting fails for other reasons
        """
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
        except gitlab.exceptions.GitlabCreateError as e:
            # Translate GitLab-specific exceptions to domain exceptions
            if e.response_code == 400 and 'line_code' in str(e):
                raise LineNotInDiffError(
                    f"Line {violation.line_number} in {violation.file_path} is not part of the diff"
                ) from e
            else:
                raise VCSCommentError(f"Failed to post comment: {e}") from e
        except Exception as e:
            raise VCSCommentError(f"Unexpected error posting comment: {e}") from e

    def post_general_comment(self, mr_id: str, message: str) -> None:
        """
        Post a general comment on the MR (not tied to a specific line).

        Raises:
            VCSCommentError: When posting fails
        """
        mr = self._get_mr(mr_id)

        try:
            mr.notes.create({'body': message})
            print("✅ Posted general comment on MR")
        except gitlab.exceptions.GitlabCreateError as e:
            raise VCSCommentError(f"Failed to post general comment: {e}") from e
        except Exception as e:
            raise VCSCommentError(f"Unexpected error posting general comment: {e}") from e
