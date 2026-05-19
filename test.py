import os
from openai import OpenAI

client = OpenAI(
    base_url="https://apicz.boyuerichdata.com/v1/",
    api_key=os.environ["BOYUE_API_KEY"],
)

print(client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": "ping"}],
    max_tokens=8,
))