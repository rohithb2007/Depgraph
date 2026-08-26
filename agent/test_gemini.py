from dotenv import load_dotenv
from google import genai
import os

load_dotenv()

if not os.getenv("GEMINI_API_KEY"):
    raise RuntimeError("GEMINI_API_KEY was not loaded")

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="Say hello in one short sentence. Do not mention APIs or code."
)

print(response.text)