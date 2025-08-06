import re

KNOWN_DEGREES = [
    "Master of Science in Computer Science, University of Bridgeport",
    "Bachelor of Technology in Computer Science & Engineering, KMIT"
]

KNOWN_CERTS = [
    "Google Data Analytics (Coursera)",
    "Excel for Business (Coursera)"
]

# ----------- Utility -----------

def normalize(text):
    """Normalize text for comparison (lowercase, remove punctuation)."""
    return re.sub(r"[^a-z0-9 ]+", "", text.strip().lower())

def fix_broken_headers(text):
    """
    Fixes broken headers like 'WO\nRK EXPERIENCE'.
    Preserves job headers (e.g. "Analyst – Cognizant") by only merging broken full-caps words.
    """
    # Fix only known broken section headers
    broken_headers = [
        ("ED\nUCATION", "EDUCATION"),
        ("WO\nRK EXPERIENCE", "WORK EXPERIENCE"),
        ("CE\nRTIFICATIONS", "CERTIFICATIONS"),
        ("SU\nMMARY", "SUMMARY"),
        ("SK\nILLS", "SKILLS"),
    ]

    for broken, fixed in broken_headers:
        text = text.replace(broken, fixed)

    # Carefully join only all-caps broken headers, not job titles
    def fix_caps(match):
        return match.group(0).replace("\n", "")

    return re.sub(r"\b([A-Z]{2,})\n([A-Z]{2,})\b", fix_caps, text)


def find_section_bounds(text, section_name):
    """Find start and end character positions of a section in the resume."""
    text = fix_broken_headers(text)  # ensure headers are normalized first
    pattern = re.compile(rf"(?m)^{section_name.upper()}\s*$")
    match = pattern.search(text)
    if not match:
        return -1, -1
    start = match.start()
    after = text[start + 1:]
    next_section = re.search(r"(?m)^[A-Z ]{{3,}}$", after)
    end = start + 1 + next_section.start() if next_section else len(text)
    return start, end

def remove_placeholder_bullets(text):
    """Removes bullets like '- Additional relevant responsibility 1' used as fallback fillers."""
    return re.sub(r"- Additional relevant responsibility \d+\n?", "", text)


# ----------- WORK EXPERIENCE -----------

def extract_experience_pairs(resume_text):
    """
    Extract pairs of (job title, company) from WORK EXPERIENCE headers.
    Format expected: "Job Title – Company, Year"
    """
    pattern = r"^(.*?)\s*–\s*(.*?),\s*.*?\d{4}.*?$"
    lines = resume_text.splitlines()
    exp_pairs = set()
    for line in lines:
        m = re.match(pattern, line.strip())
        if m:
            title, company = m.group(1).strip(), m.group(2).strip()
            exp_pairs.add((normalize(title), normalize(company)))
    return exp_pairs

def clean_tailored_work_experience(tailored_resume, base_resume=None, verbose=False):
    if not base_resume:
        return tailored_resume

    base_pairs = extract_experience_pairs(base_resume)
    start, end = find_section_bounds(tailored_resume, "WORK EXPERIENCE")
    if start == -1:
        if verbose:
            print("❌ No WORK EXPERIENCE section found.")
        return tailored_resume

    before = tailored_resume[:start]
    work_section = tailored_resume[start:end]
    after = tailored_resume[end:]

    lines = work_section.splitlines()
    cleaned_lines = []
    skip_next = False
    skip_counter = 0

    for line in lines:
        line_stripped = line.strip()
        m = re.match(r"^(.*?)\s*–\s*(.*?),\s*.*?$", line_stripped)
        if m:
            title, company = normalize(m.group(1)), normalize(m.group(2))
            if (title, company) in base_pairs:
                skip_next = False
                skip_counter = 0
                cleaned_lines.append(line)
            else:
                if verbose:
                    print(f"🧹 Removed hallucinated job: {m.group(1)} – {m.group(2)}")
                skip_next = True
                skip_counter = 0
        elif skip_next:
            if line_stripped.startswith("•") or line_stripped.startswith("-"):
                skip_counter += 1
                if skip_counter <= 10:
                    continue
            skip_next = False
            skip_counter = 0
            cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)

    return before + "\n" + "\n".join(cleaned_lines).strip() + "\n" + after

def remove_hallucinated_titles(text):
    """
    Removes job blocks where job titles start with ❗ or other hallucinated markers.
    """
    lines = text.splitlines()
    cleaned = []
    skip_block = False

    for line in lines:
        if re.match(r"^❗.*–.*", line.strip()):
            skip_block = True
            continue
        if skip_block:
            if line.strip().startswith("-") or line.strip().startswith("•") or not line.strip():
                continue
            else:
                skip_block = False
        if not skip_block:
            cleaned.append(line)
    return "\n".join(cleaned)


# ----------- CERTIFICATIONS -----------

def extract_certifications(text):
    start, end = find_section_bounds(text, "CERTIFICATIONS")
    if start == -1:
        return []
    lines = text[start:end].splitlines()[1:]
    return [normalize(line) for line in lines if line.strip()]

def clean_certifications_section(tailored_resume, base_resume=None, verbose=False):
    if not base_resume:
        return tailored_resume

    base_certs = extract_certifications(base_resume)
    start, end = find_section_bounds(tailored_resume, "CERTIFICATIONS")
    if start == -1:
        return tailored_resume

    before = tailored_resume[:start]
    cert_section = tailored_resume[start:end]
    after = tailored_resume[end:]

    lines = cert_section.splitlines()
    cleaned = [lines[0]]  # header
    for line in lines[1:]:
        norm_line = normalize(line)
        if any(norm_base in norm_line for norm_base in base_certs):
            cleaned.append(line)
        elif verbose:
            print(f"🧹 Removed hallucinated cert: {line.strip()}")

    return before + "\n" + "\n".join(cleaned).strip() + "\n" + after


# ----------- EDUCATION -----------

def extract_education(text):
    start, end = find_section_bounds(text, "EDUCATION")
    if start == -1:
        return []
    lines = text[start:end].splitlines()[1:]
    return [normalize(line) for line in lines if line.strip()]

def clean_education_section(tailored_resume, base_resume=None, verbose=False):
    if not base_resume:
        return tailored_resume

    base_edu = extract_education(base_resume)
    start, end = find_section_bounds(tailored_resume, "EDUCATION")
    if start == -1:
        return tailored_resume

    before = tailored_resume[:start]
    edu_section = tailored_resume[start:end]
    after = tailored_resume[end:]

    lines = edu_section.splitlines()
    cleaned = [lines[0]]  # header
    for line in lines[1:]:
        norm_line = normalize(line)
        if any(norm_base in norm_line for norm_base in base_edu):
            cleaned.append(line)
        elif verbose:
            print(f"🧹 Removed hallucinated education entry: {line.strip()}")

    return before + "\n" + "\n".join(cleaned).strip() + "\n" + after



# ----------- Final Patch Utility -----------

def clean_full_resume(tailored_resume, base_resume=None, verbose=False):
    if not base_resume:
        return tailored_resume

    text = tailored_resume
    text = fix_broken_headers(text)
    text = remove_placeholder_bullets(text)
    text = remove_hallucinated_titles(text)
    text = clean_tailored_work_experience(text, base_resume, verbose)

    # 💡 Inject original CERTIFICATIONS and EDUCATION directly
    for sec_name in ["CERTIFICATIONS", "EDUCATION"]:
        start, end = find_section_bounds(text, sec_name)
        base_start, base_end = find_section_bounds(base_resume, sec_name)
        if start != -1 and base_start != -1:
            before = text[:start]
            after = text[end:]
            original_block = base_resume[base_start:base_end].strip()
            text = before + "\n" + original_block + "\n" + after
            if verbose:
                print(f"🔁 Replaced {sec_name} section with original.")

    return text


def patch_job_titles_with_original(tailored_text, original_text):
    """
    Replaces hallucinated or altered job headers in tailored_text with those from the original resume.
    """
    import re

    original_jobs = re.findall(r"(.*?–.*?),?\s*(.+)", original_text.split("WORK EXPERIENCE")[-1], flags=re.DOTALL)
    original_titles = set()
    for job in original_jobs:
        header = job[0].strip()
        if len(header) > 5 and not header.startswith("-"):
            original_titles.add(header)

    # Replace any hallucinated/short headers in tailored_text with originals
    new_lines = []
    for line in tailored_text.splitlines():
        if "–" in line and not line.strip().startswith("-"):
            for orig in original_titles:
                if all(tok in line for tok in orig.split("–")) or orig.split("–")[0] in line:
                    line = orig
                    break
        new_lines.append(line)
    return "\n".join(new_lines)
