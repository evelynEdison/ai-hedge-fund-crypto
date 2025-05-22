from pydantic_settings import BaseSettings
from pydantic import model_validator, BaseModel
from datetime import datetime
import yaml
from typing import List
from dotenv import load_dotenv
from .constants import Interval

load_dotenv()


class SignalSettings(BaseModel):
    intervals: List[Interval]
    tickers: List[str]
    strategies: List[str]


class Settings(BaseSettings):
    mode: str
    start_date: datetime
    end_date: datetime
    primary_interval: Interval
    initial_cash: int
    margin_requirement: float
    show_reasoning: bool
    show_agent_graph: bool = True
    signals: SignalSettings
    llm: 'LLMSettings'  # Forward reference for LLMSettings

    @model_validator(mode='after')
    def check_primary_interval_in_intervals(self):
        if self.primary_interval not in self.signals.intervals:
            raise ValueError(
                f"primary_interval '{self.primary_interval}' must be in signals.intervals {self.signals.intervals}")
        return self


class LLMSettings(BaseModel):
    GEMINI_API_KEY: str = ""


def load_settings(yaml_path: str = "config.yaml") -> Settings:
    with open(yaml_path, "r") as f:
        yaml_data = yaml.safe_load(f)
    # Ensure 'llm' key exists in yaml_data, if not, provide a default
    if 'llm' not in yaml_data:
        yaml_data['llm'] = {} # Provide default empty dict for llm settings
    return Settings(**yaml_data)


# Load and use
settings = load_settings()

# print(settings.mode)
# print(settings.primary_interval)
# print(settings.start_date)
# print(settings.end_date)
# print(settings.signals)
