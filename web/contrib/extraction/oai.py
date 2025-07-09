from enum import Enum
from openai import OpenAI

# Handle the case where no API key is set
try:
    client = OpenAI()
except Exception:
    # During migrations or when API key isn't needed, provide a dummy client
    print("Warning: OpenAI client initialization failed. This is fine for migrations.")
    client = None


class MODELS(Enum):
    GPT4o_MINI: str = "gpt-4o-mini-2024-07-18"
    GPT4o_16k: str = "gpt-4o-2024-11-20"
