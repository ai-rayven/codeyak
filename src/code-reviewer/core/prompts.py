from typing import List
from .models import FileDiff, Guideline

def build_review_messages(diffs: List[FileDiff], guidelines: List[Guideline]) -> List[dict]:
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

    # 2. User Prompt: Context + Code
    user_content = "Review the following file changes:\n\n"
    for diff in diffs:
        user_content += f"--- FILE: {diff.file_path} ---\n"
        user_content += diff.diff_content
        user_content += "\n\n"

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]