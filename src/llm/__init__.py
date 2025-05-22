import os
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from .gemini import GeminiLLM

openai_llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o-mini",  # or "gpt-4" if you have access
)

json_parser = JsonOutputParser()

__all__ = ["openai_llm", "json_parser", "GeminiLLM"]