
review_code (trace)
    input:
        file_count 
    user_id: 
        author, if local use git config ??
    tags: 
        project_name
        no_violations = only if the posted violation count is 0
    output:
        violation_count

generate_change_summary (generation)
    - entire prompt (chatml format)
    - output

generate_guideline_violations (generation)
    - entire prompt (chatml format)
    - output
    