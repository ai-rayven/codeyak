from typing import List
from .models import FileDiff, Guideline, MRComment

def build_review_messages(
    diffs: List[FileDiff],
    guidelines: List[Guideline],
    existing_comments: List[MRComment] = None
) -> List[dict]:
    # 1. System Prompt: Define the Persona and Rules
    system_content = (
        "You are an automated code review agent. "
        "Your task is to strictly enforce the provided guidelines.\n\n"
        "Guidelines:\n"
    )

    for g in guidelines:
        system_content += f"- [{g.id}] {g.description}\n"

    system_content += (
        "\nInstructions:\n"
        "1. Only report violations of the specific guidelines listed above.\n"
        "2. Ignore general best practices not in the list.\n"
    )

    if existing_comments:
        system_content += (
            "3. You have access to existing review comments below. "
            "Use them as context but still report any violations you find. "
            "The system will deduplicate overlapping comments.\n"
        )

    # 2. User Prompt: Context + Code
    user_content = ""

    # 2a. Add existing comments section (if any)
    if existing_comments:
        inline_comments = [c for c in existing_comments if c.is_inline]
        general_comments = [c for c in existing_comments if not c.is_inline]

        if inline_comments or general_comments:
            user_content += "=== EXISTING REVIEW COMMENTS ===\n\n"

            if inline_comments:
                user_content += "Inline Comments:\n"
                for comment in inline_comments:
                    user_content += (
                        f"- [{comment.author}] {comment.file_path}:{comment.line_number}\n"
                        f"  {comment.body}\n\n"
                    )

            if general_comments:
                user_content += "General Comments:\n"
                for comment in general_comments:
                    user_content += f"- [{comment.author}] {comment.body}\n\n"

            user_content += "=== END EXISTING COMMENTS ===\n\n"

    # 2b. Add file changes
    user_content += "Review the following file changes:\n\n"
    for diff in diffs:
        user_content += f"--- FILE: {diff.file_path} ---\n"
        user_content += diff.diff_content
        user_content += "\n\n"

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]