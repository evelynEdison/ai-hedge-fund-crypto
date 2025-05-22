from pydantic_settings import BaseSettings
from pydantic import model_validator, BaseModel # BaseModel is used for SignalSettings
from datetime import datetime
import yaml
from typing import List
from dotenv import load_dotenv
from .constants import Interval

load_dotenv() # Ensures .env is loaded


class SignalSettings(BaseModel): # This remains BaseModel as it's purely from YAML
    intervals: List[Interval]
    tickers: List[str]
    strategies: List[str]


class LLMSettings(BaseSettings):
    GEMINI_API_KEY: str = ""
    # OPENAI_API_KEY: str = "" # If you want to manage OpenAI key via LLMSettings too

    class Config:
        env_file = '.env'
        extra = 'ignore'
        # env_prefix = 'LLM_' # Example if you prefix LLM related env vars


class TradingSettings(BaseSettings):
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    LIVE_TRADING_ENABLED: bool = False

    class Config:
        env_file = '.env'
        extra = 'ignore'
        # env_prefix = 'TRADING_' # Example if you prefix trading related env vars


class Settings(BaseSettings):
    mode: str
    start_date: datetime
    end_date: datetime
    primary_interval: Interval
    initial_cash: int
    margin_requirement: float
    show_reasoning: bool
    show_agent_graph: bool = True
    signals: SignalSettings       # Populated from YAML
    llm: LLMSettings          # Populated from .env via LLMSettings()
    trading: TradingSettings    # Populated from .env via TradingSettings()

    @model_validator(mode='after')
    def check_primary_interval_in_intervals(self):
        if self.primary_interval not in self.signals.intervals:
            raise ValueError(
                f"primary_interval '{self.primary_interval}' must be in signals.intervals {self.signals.intervals}")
        return self

    # Optional: If Settings itself needs to load top-level fields from .env
    # class Config:
    #     env_file = '.env'
    #     extra = 'ignore'


def load_settings(yaml_path: str = "config.yaml") -> Settings:
    try:
        with open(yaml_path, "r") as f:
            yaml_data = yaml.safe_load(f)
        if yaml_data is None: # Handle empty YAML file
            yaml_data = {}
    except FileNotFoundError:
        print(f"Warning: Configuration file '{yaml_path}' not found. Using defaults and environment variables.")
        yaml_data = {}
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file '{yaml_path}': {e}. Using defaults and environment variables.")
        yaml_data = {}

    # Instantiate sub-models that load from .env first
    llm_settings_from_env = LLMSettings()
    trading_settings_from_env = TradingSettings()

    # Remove any keys from yaml_data that correspond to these sub-models
    # to ensure .env is the sole source for these specific settings blocks.
    if 'llm' in yaml_data:
        del yaml_data['llm']
    if 'trading' in yaml_data:
        del yaml_data['trading']
        
    # Construct the main Settings object, injecting the .env-loaded sub-models
    # and the rest from YAML.
    return Settings(
        llm=llm_settings_from_env, 
        trading=trading_settings_from_env, 
        **yaml_data
    )


# Load and use globally (optional, depending on application structure)
# This ensures 'settings' is available for import elsewhere, pre-loaded.
settings = load_settings()

# Example accesses (for testing or use in other modules):
# print(f"Mode: {settings.mode}")
# print(f"Gemini Key: {settings.llm.GEMINI_API_KEY}")
# print(f"Trading Enabled: {settings.trading.LIVE_TRADING_ENABLED}")
# print(f"Binance API Key for trading: {settings.trading.BINANCE_API_KEY}")
