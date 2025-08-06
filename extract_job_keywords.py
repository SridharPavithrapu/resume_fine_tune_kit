import re
import json
import os
import requests

def call_groq(prompt):
    headers = {"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"}
    payload = {
        "model": os.getenv("GROQ_MODEL", "llama3-70b-8192"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    try:
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"❌ Groq API call failed: {e}")
        return ""

def extract_job_info(job_text):
    if len(job_text.strip()) < 300:
        print("⚠️ Job description too short. Skipping model.")
        return {
            "job_title": "Unknown Title",
            "skills": [],
            "verbs": []
        }

    prompt = f"""You are a job description parser.

Given the following job description, extract:
1. The most accurate job title (even if informal).
2. A list of 6-10 important hard/technical and soft skills mentioned.
3. A list of 6-10 strong action verbs that match responsibilities.

Respond in JSON with keys: job_title, skills, verbs.

Job description:
{job_text}
"""
    raw_output = call_groq(prompt)

    if os.getenv("DEBUG_RESUME") == "1":
        print("🔎 Raw model output:\n", raw_output)

    try:
        json_match = re.search(r"\{.*?\}", raw_output, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON block found in output.")

        parsed = json.loads(json_match.group(0))
        skills = list({s.strip().title() for s in parsed.get("skills", [])})
        verbs = list({v.strip().title() for v in parsed.get("verbs", [])})
        print("✅ LLM successfully parsed job info.")
        return {
            "job_title": parsed.get("job_title", "Unknown Title"),
            "skills": skills,
            "verbs": verbs
        }
    except Exception as e:
        print(f"⚠️ LLM failed to parse JSON: {e}")
        print("❌ Raw model output:\n", raw_output)
        print("🔁 Falling back to rule-based parsing...")

        # === Rule-based Fallback ===
        lines = job_text.splitlines()
        title = "Unknown Title"
        for line in lines:
            if "title" in line.lower() and len(line) < 100:
                title = re.sub(r"[^a-zA-Z0-9 ()\-]", "", line).strip()
                break

        skills_keywords = re.findall(
            r"\b(SQL|Python|Power BI|Excel|Tableau|ETL|data analysis|dashboards?|communication|collaboration|reporting|analytics?|business intelligence|project documentation|stakeholders?|metrics|forecasting|insights|visuali[sz]ation)\b",
            job_text, re.IGNORECASE
        )

        verbs = re.findall(
            r"\b(Analyze|Develop|Collaborate|Create|Manage|Lead|Deliver|Build|Improve|Optimize|Support|Implement|Design|Maintain|Translate|Document)\w*",
            job_text, re.IGNORECASE
        )

        return {
            "job_title": title,
            "skills": sorted(set(skill.strip().title() for skill in skills_keywords)),
            "verbs": sorted(set(verb.strip().title() for verb in verbs)),
        }