"""Use a local virtual key. No provider key is needed by this client."""
import os
import httpx
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4000/v1",
    api_key=os.environ["LITELLM_API_KEY"],
    http_client=httpx.Client(trust_env=False),
)
response = client.chat.completions.create(
    model=os.environ["LITELLM_MODEL"],  # Exact public name from the dashboard.
    messages=[{"role": "user", "content": "Say hello."}],
    max_tokens=100,
)
print(response.choices[0].message.content)
client.close()
