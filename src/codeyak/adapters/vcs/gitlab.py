import gitlab
from typing import List
from gitlab.v4.objects import ProjectMergeRequest

from ...core.ports import VCSClient
from ...core.models import FileDiff, GuidelineViolation, MRComment
from ...core.exceptions import LineNotInDiffError, VCSCommentError, VCSFetchCommentsError

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

    def get_comments(self, mr_id: str) -> List[MRComment]:
        """
        Fetch all comments from GitLab MR (discussions + notes).

        Raises:
            VCSFetchCommentsError: When fetching comments fails
        """
        mr = self._get_mr(mr_id)
        comments = []

        try:
            # 1. Fetch discussions (includes inline diff comments)
            discussions = mr.discussions.list(get_all=True)

            for discussion in discussions:
                notes_data = discussion.attributes.get('notes', [])

                for note_dict in notes_data:
                    comment_id = str(note_dict.get('id', ''))
                    body = note_dict.get('body', '')
                    author_dict = note_dict.get('author', {})
                    author = author_dict.get('username', 'unknown')
                    created_at = note_dict.get('created_at', '')

                    position = note_dict.get('position')

                    if position and position.get('position_type') == 'text':
                        # Inline comment
                        file_path = position.get('new_path') or position.get('old_path')
                        line_number = position.get('new_line') or position.get('old_line')

                        comments.append(MRComment(
                            id=comment_id,
                            body=body,
                            author=author,
                            created_at=created_at,
                            file_path=file_path,
                            line_number=line_number,
                            guideline_id=MRComment.parse_guideline_id(body),
                            is_inline=True
                        ))
                    else:
                        # General comment - try to parse file/line info
                        parsed_file, parsed_line = MRComment.parse_file_and_line(body)
                        comments.append(MRComment(
                            id=comment_id,
                            body=body,
                            author=author,
                            created_at=created_at,
                            file_path=parsed_file,
                            line_number=parsed_line,
                            guideline_id=MRComment.parse_guideline_id(body),
                            is_inline=False
                        ))

            # 2. Fetch standalone notes (avoid duplicates)
            notes = mr.notes.list(get_all=True)

            for note in notes:
                note_id = str(note.id)
                if any(c.id == note_id for c in comments):
                    continue

                # Try to parse file/line info from general comment body
                parsed_file, parsed_line = MRComment.parse_file_and_line(note.body)
                comments.append(MRComment(
                    id=note_id,
                    body=note.body,
                    author=note.author.get('username', 'unknown') if hasattr(note, 'author') else 'unknown',
                    created_at=note.created_at,
                    file_path=parsed_file,
                    line_number=parsed_line,
                    guideline_id=MRComment.parse_guideline_id(note.body),
                    is_inline=False
                ))

            # Sort chronologically
            comments.sort(key=lambda c: c.created_at)

            print(f"📝 Fetched {len(comments)} comments from MR {mr_id}")

            # Print out each comment for visibility
            if comments:
                print("\n=== EXISTING COMMENTS ===")
                for comment in comments:
                    guideline_info = f" [{comment.guideline_id}]" if comment.guideline_id else ""
                    if comment.is_inline:
                        print(f"  [{comment.author}] {comment.file_path}:{comment.line_number}{guideline_info}")
                        print(f"    {comment.body}")
                    else:
                        # General comment - show parsed location if available
                        if comment.file_path and comment.line_number:
                            print(f"  [{comment.author}] (General) {comment.file_path}:{comment.line_number}{guideline_info}")
                        else:
                            print(f"  [{comment.author}] (General comment){guideline_info}")
                        print(f"    {comment.body}")
                print("=== END COMMENTS ===\n")

            return comments

        except gitlab.exceptions.GitlabGetError as e:
            raise VCSFetchCommentsError(f"Failed to fetch comments: {e}") from e
        except Exception as e:
            raise VCSFetchCommentsError(f"Unexpected error fetching comments: {e}") from e
