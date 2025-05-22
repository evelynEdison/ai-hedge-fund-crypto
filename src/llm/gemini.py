import google.generativeai as genai

class GeminiLLM:
    def __init__(self, api_key: str, model_name: str = "gemini-pro"):
        """
        Initializes the GeminiLLM client.

        Args:
            api_key: The API key for accessing the Gemini API.
            model_name: The name of the Gemini model to use (e.g., "gemini-pro").
        """
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(self.model_name)

    def generate_text(self, prompt: str) -> str:
        """
        Generates text using the Gemini API.

        Args:
            prompt: The prompt string to send to the API.

        Returns:
            The generated text as a string.

        Raises:
            Exception: If there is an error during API communication.
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            # Handle potential errors during API communication
            # For example, log the error or raise a custom exception
            print(f"Error generating text: {e}")
            raise Exception(f"Error generating text: {e}") from e
