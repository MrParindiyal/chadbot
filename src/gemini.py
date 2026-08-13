from dotenv import load_dotenv
from google import genai
from google.genai import types
import os
import ratelimit

load_dotenv()
GEMINI_API = os.getenv("GEMINI_API")
client = genai.Client(api_key=GEMINI_API)
grounding_tool = types.Tool(google_search=types.GoogleSearch())

config = types.GenerateContentConfig(
    tools=[grounding_tool],
    system_instruction="""
        Role: Discord Bot Support AI. 
        Style: Concise and short, group-chat casual. 
        Rules: No intros/outros (e.g., "Here is..."). No LLM-style phrasing. No need to format in markdown using '#'. If bulletpoints are needed use '-' followed by a space chr. instead of '#' or '*'. Instead of using markdown, wrap text in '_' to italicize and '**' to make it bold. Densely pack information to replicate a group chat message. Space character is also counted during limits. Hard limit total characters in response to 1800. Keep sentence length below 20 words.
        DO NOT CROSS THE 1900 CHARACTER LIMIT IN YOUR RESPONSE IN ANY CASE.
    """,
)


@ratelimit.limits(calls=12, period=60)
@ratelimit.limits(calls=499, period=86400)
def generative_response(user_prompt):
    config.tools = []  # search grounding not available for 3rd gen models
    config.system_instruction += (
        "If you don't know something, DENY to answer. DO NOT HALLUCINATE."
    )
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=user_prompt,
        config=config,
    )
    content = str(response.text)
    return content[:1996] + ("..." if len(content) > 1996 else "")


@ratelimit.limits(calls=3, period=60)
@ratelimit.limits(calls=18, period=86400)
def generative_search(user_prompt):
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=user_prompt,
        config=config,
    )
    content = str(response.text)
    return content[:1996] + ("..." if len(content) > 1996 else "")
