import os
import requests

# --------------------- Remote Bullet Model (Together.ai) --------------------- #
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
TOGETHER_MODEL = "mistralai/Mixtral-8x7B-Instruct-v0.1"

def call_summary_model(prompt: str, max_new_tokens: int = 512) -> str:
    raise NotImplementedError("Summary model is handled via Groq. This function should not be used.")

def call_bullet_model(prompt: str, max_tokens: int = 1024) -> str:
    if not TOGETHER_API_KEY:
        raise EnvironmentError("TOGETHER_API_KEY not set.")

    try:
        response = requests.post(
            "https://api.together.xyz/inference",
            headers={"Authorization": f"Bearer {TOGETHER_API_KEY}"},
            json={
                "model": TOGETHER_MODEL,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "top_p": 0.9,
                "stop": ["###"],  # or just leave it out entirely
            }
        )

        print("🧪 Raw Together.ai response (truncated):")
        print(response.text[:1000])

        if response.status_code != 200:
            print(f"❌ Together.ai API failed: {response.status_code} – {response.text}")
            return ""

        response_json = response.json()
        choices = response_json.get("choices", [])

        if not choices or "text" not in choices[0]:
            print("❌ Together.ai response missing expected text field.")
            return ""

        output = choices[0]["text"].strip()
        output = output.replace("❗", "")
        print("🔎 Bullet model response (preview):", output[:300])
        return output

    except Exception as e:
        print(f"❌ Exception during Together.ai call: {e}")
        return ""

