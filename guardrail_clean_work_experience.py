import re

def normalize(text):
    return re.sub(r"[^a-z0-9 ]+", "", text.strip().lower())

def extract_experience_pairs(resume_text):
    pattern = r"^(.*?)\s*–\s*(.*?),\s*.*?\d{4}.*?$"
    lines = resume_text.splitlines()
    exp_pairs = set()
    for line in lines:
        m = re.match(pattern, line.strip())
        if m:
            title, company = m.group(1).strip(), m.group(2).strip()
            exp_pairs.add((normalize(title), normalize(company)))
    return exp_pairs

def find_work_experience_bounds(text):
    pattern = re.compile(r"(?im)^\s*work experiences?\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return -1, -1
    start = match.start()
    # Find the next section header
    after = text[start:]
    next_section = re.search(r"(?m)^\s*[A-Z ]{3,}\s*$", after[1:])
    end = start + next_section.start() + 1 if next_section else len(text)
    return start, end

def clean_tailored_work_experience(tailored_resume, base_resume=None, verbose=False):
    if not base_resume:
        return tailored_resume

    base_pairs = extract_experience_pairs(base_resume)
    start, end = find_work_experience_bounds(tailored_resume)
    if start == -1:
        if verbose:
            print("No WORK EXPERIENCE section found.")
        return tailored_resume

    before = tailored_resume[:start]
    work_section = tailored_resume[start:end]
    after = tailored_resume[end:]

    lines = work_section.splitlines()
    cleaned_lines = []
    for line in lines:
        m = re.match(r"^(.*?)\s*–\s*(.*?),\s*.*?$", line.strip())
        if m:
            title, company = normalize(m.group(1)), normalize(m.group(2))
            if (title, company) in base_pairs:
                cleaned_lines.append(line)
            elif verbose:
                print(f"Removed hallucinated entry: {title}, {company}")
        else:
            cleaned_lines.append(line)

    return before + "\n" + "\n".join(cleaned_lines).strip() + "\n" + after
