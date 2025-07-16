from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import os
from datetime import datetime

model_path = "mistral-merged"
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    device_map="auto"
)

SAVE_LOGS = True
LOG_DIR = "prompt_logs"
os.makedirs(LOG_DIR, exist_ok=True)

def format_prompt(base_resume, jd, style_guide, ats_keywords=None, ats_sections=None):
    prompt = style_guide.strip()
    prompt += "\n\nBASE RESUME:\n" + base_resume.strip()
    prompt += "\n\nJOB DESCRIPTION:\n" + jd.strip()
    if (ats_keywords and len(ats_keywords)) or (ats_sections and len(ats_sections)):
        prompt += "\n\nATS FEEDBACK (optional; only present after first attempt):"
        if ats_keywords and len(ats_keywords):
            prompt += f"\nMissing keywords: {', '.join(ats_keywords)}"
        if ats_sections and len(ats_sections):
            prompt += f"\nMissing sections: {', '.join(ats_sections)}"
    return prompt.strip()

def save_prompt_and_output(prompt, output):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(LOG_DIR, f"prompt_{timestamp}.txt")
    with open(file_path, "w") as f:
        f.write("----- PROMPT -----\n")
        f.write(prompt + "\n\n")
        f.write("----- OUTPUT -----\n")
        f.write(output)

def tailor_resume(
    base_resume,
    jd,
    style_guide,
    ats_keywords=None,
    ats_sections=None,
    max_tokens=2048,
    temperature=0.1,
):
    full_prompt = format_prompt(base_resume, jd, style_guide, ats_keywords, ats_sections)
    inputs = tokenizer(full_prompt, return_tensors="pt", truncation=True).to(model.device)
    output = model.generate(
        **inputs,
        max_new_tokens=max_tokens,
        temperature=temperature,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    output_text = tokenizer.decode(output[0], skip_special_tokens=True)
    if output_text.startswith(full_prompt):
        output_text = output_text[len(full_prompt):].strip()
    if not output_text.strip():
        output_text = "[ERROR] Tailored resume generation returned empty output."

    if SAVE_LOGS:
        save_prompt_and_output(full_prompt, output_text)

    return output_text.strip()
