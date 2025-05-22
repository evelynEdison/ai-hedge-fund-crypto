import unittest
from unittest.mock import patch, MagicMock
import os

# Attempt to import GeminiLLM, adjust path if necessary based on project structure
# Assuming src is in PYTHONPATH or tests are run from a location where src is accessible
try:
    from src.llm.gemini import GeminiLLM
except ImportError:
    # This is a fallback if the above path doesn't work, may need adjustment
    # e.g. if 'src' is not directly in sys.path during test execution
    # For now, we proceed assuming the first import works.
    # If ModuleNotFoundError occurs, this indicates a path issue.
    pass 

# Define a dummy API key for testing purposes
# It's good practice to not use real keys in tests.
DUMMY_API_KEY = "test_api_key"

class TestGeminiLLM(unittest.TestCase):

    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_initialization_success(self, mock_generative_model, mock_configure):
        """Test successful initialization of GeminiLLM."""
        llm = GeminiLLM(api_key=DUMMY_API_KEY, model_name="gemini-test-model")
        mock_configure.assert_called_once_with(api_key=DUMMY_API_KEY)
        mock_generative_model.assert_called_once_with("gemini-test-model")
        self.assertEqual(llm.model_name, "gemini-test-model")

    @patch('google.generativeai.configure')
    def test_initialization_failure_no_api_key(self, mock_configure):
        """
        Test if GeminiLLM handles missing API key during configuration.
        Note: genai.configure itself might not raise an error for a "" key,
        but the API calls would fail. We're testing if it's called.
        The actual enforcement of a valid key is often done by the SDK on API call.
        """
        # We can't directly test genai.configure raising an error for an empty key
        # as it might not. The real test is if API calls fail later.
        # For now, we ensure configure is called.
        # If genai.configure were to raise an error for empty string, we'd test that.
        GeminiLLM(api_key="", model_name="gemini-test-model")
        mock_configure.assert_called_once_with(api_key="")
        # A more robust test would involve mocking an API call to see it fail
        # if the key is indeed invalid/empty, but that's closer to generate_text tests.

    @patch('google.generativeai.GenerativeModel')
    @patch('google.generativeai.configure') # Also mock configure to isolate the test
    def test_generate_text_success(self, mock_configure, mock_generative_model):
        """Test successful text generation."""
        # Mock the model instance and its generate_content method
        mock_model_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Generated text"
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance

        llm = GeminiLLM(api_key=DUMMY_API_KEY, model_name="gemini-pro")
        prompt = "Test prompt"
        response_text = llm.generate_text(prompt)

        mock_generative_model.assert_called_once_with("gemini-pro")
        mock_model_instance.generate_content.assert_called_once_with(prompt)
        self.assertEqual(response_text, "Generated text")

    @patch('google.generativeai.GenerativeModel')
    @patch('google.generativeai.configure')
    def test_generate_text_api_error(self, mock_configure, mock_generative_model):
        """Test text generation when the API call raises an error."""
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.side_effect = Exception("API Error")
        mock_generative_model.return_value = mock_model_instance

        llm = GeminiLLM(api_key=DUMMY_API_KEY, model_name="gemini-pro")
        prompt = "Test prompt for error"

        with self.assertRaisesRegex(Exception, "Error generating text: API Error"):
            llm.generate_text(prompt)
        
        mock_model_instance.generate_content.assert_called_once_with(prompt)

    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_model_name_usage(self, mock_generative_model, mock_configure):
        """Test that the specified model_name is used."""
        custom_model_name = "gemini-custom-model"
        llm = GeminiLLM(api_key=DUMMY_API_KEY, model_name=custom_model_name)
        
        mock_configure.assert_called_once_with(api_key=DUMMY_API_KEY)
        # Check that GenerativeModel was called with the custom model name
        mock_generative_model.assert_called_once_with(custom_model_name)
        self.assertEqual(llm.model_name, custom_model_name)

        # Further check if generate_text uses this model (implicitly tested if instance is correct)
        # To be more explicit, we can mock generate_content on the instance passed by mock_generative_model
        mock_model_instance = mock_generative_model.return_value # Get the mocked model instance
        mock_response = MagicMock()
        mock_response.text = "some text"
        mock_model_instance.generate_content.return_value = mock_response
        
        llm.generate_text("hello")
        mock_model_instance.generate_content.assert_called_once_with("hello")


if __name__ == '__main__':
    # This is to allow running the tests directly from this file
    # For project-wide testing, a test runner like `python -m unittest discover src/test` is preferred.
    
    # Need to ensure that 'src' is in the Python path if running this file directly
    # and 'src.llm.gemini' is the correct module path.
    # One way to handle this if running the file directly:
    import sys
    if os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) not in sys.path:
         sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

    try:
        from llm.gemini import GeminiLLM # Relative import if src is in path
    except ImportError:
        # Fallback if the test structure means src.llm.gemini is needed
        from src.llm.gemini import GeminiLLM


    unittest.main()
