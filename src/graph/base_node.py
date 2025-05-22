from typing import Dict, Any, List
from .state import AgentState
from src.llm import GeminiLLM
from src.utils.settings import load_settings

class BaseNode:
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses must implement __call__")

    def call_model(self, model_provider: str, model_name: str, messages: List[Dict[str, str]], stream: bool = False) -> str:
        """
        Calls the specified language model with the given messages.

        Args:
            model_provider: The provider of the model (e.g., "Gemini", "OpenAI").
            model_name: The specific model name.
            messages: A list of message dictionaries, e.g., [{"role": "user", "content": "Hello"}].
            stream: Boolean indicating if streaming should be used (currently not implemented for Gemini).

        Returns:
            The response text from the model.

        Raises:
            ValueError: If the API key is not configured for the selected provider,
                        or if an unsupported model provider is chosen.
        """
        messages_str = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in messages])

        if model_provider == "Gemini":
            s = load_settings()
            api_key = s.llm.GEMINI_API_KEY
            if not api_key:
                raise ValueError("GEMINI_API_KEY not configured in settings.")
            
            llm = GeminiLLM(api_key=api_key, model_name=model_name)
            response = llm.generate_text(prompt=messages_str)
            return response
        # Add other providers like OpenAI as needed
        # elif model_provider == "OpenAI":
        #     # Ensure openai_llm and necessary API keys are handled
        #     raise NotImplementedError("OpenAI provider not yet implemented in call_model.")
        else:
            raise ValueError(f"Unsupported model provider: {model_provider}")