import requests

BASE_URL = "http://127.0.0.1:1234/v1"
MODEL = "llama-pllum-8b-chat"

def chat(prompt: str) -> str:
    url = f"{BASE_URL}/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Jesteś pomocnym asystentem"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 300,
        "stream": False,
    }

    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

if __name__ == "__main__":
    print(chat("Jaka jest zima w Polsce"))
