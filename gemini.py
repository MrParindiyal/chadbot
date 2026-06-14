from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()
GEMINI_API = os.getenv("GEMINI_API")

def generative_response(user_prompt): 
    client = genai.Client(api_key=GEMINI_API)

    grounding_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    config = types.GenerateContentConfig(
        tools=[grounding_tool],
        system_instruction="""
            Role: Discord Bot Support AI. 
            Style: Concise and short, group-chat casual. 
            Rules: No intros/outros (e.g., "Here is..."). No LLM-style phrasing. No need to format in markdown using '#'. If bulletpoints are needed use '-' followed by a space chr. instead of '#' or '*'. Instead of using markdown, wrap text in '_' to italicize and '**' to make it bold. Densely pack information to replicate a group chat message. Space character is also counted during limits. Hard limit total characters in response to 1800. Keep sentence length below 20 words.
            DO NOT CROSS THE 1800 CHARACTER LIMIT IN YOUR RESPONSE IN ANY CASE.
        """
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=user_prompt,
        config=config,
    )

    return str(response.text)
