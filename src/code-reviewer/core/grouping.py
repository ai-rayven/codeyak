from typing import List
from .models import FileDiff, FileGroup

# 12,000 tokens * 3.5 chars/token = ~42,000 chars
MAX_CHARS_PER_GROUP = 42000 

def create_file_groups(diffs: List[FileDiff]) -> List[FileGroup]:
    groups = []
    current_batch: List[FileDiff] = []
    current_chars = 0
    group_id = 1

    for diff in diffs:
        # 1. Simple length check (File path + Content)
        # This works for ANY model (OpenAI, Anthropic, Mistral)
        content_len = len(diff.file_path) + len(diff.diff_content)
        
        # Store for debugging (no longer called 'tokens')
        diff.tokens = int(content_len / 3.5) 

        # 2. Check overflow
        if current_batch and (current_chars + content_len > MAX_CHARS_PER_GROUP):
            groups.append(FileGroup(
                files=current_batch,
                group_id=group_id,
                total_tokens=int(current_chars / 3.5) # Approximate
            ))
            group_id += 1
            current_batch = []
            current_chars = 0

        current_batch.append(diff)
        current_chars += content_len

    if current_batch:
        groups.append(FileGroup(
            files=current_batch,
            group_id=group_id,
            total_tokens=int(current_chars / 3.5)
        ))

    return groups