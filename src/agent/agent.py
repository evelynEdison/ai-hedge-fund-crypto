from typing import List, Dict
from langchain_core.messages import HumanMessage
from datetime import datetime
from utils import Interval, save_graph_as_png, parse_str_to_json
from .workflow import Workflow
# Ensure these imports are correct and Client is available
from src.gateway.binance.client import Client 
from src.gateway.binance.execution import place_order_from_signal
from src.utils.settings import load_settings


class Agent:

    @staticmethod
    def run(
            primary_interval: Interval,
            intervals: List[Interval],
            tickers: List[str],
            end_date: datetime,
            portfolio: Dict,
            strategies: List[str],
            show_reasoning: bool = False,
            show_agent_graph: bool = False,
            model_name: str = "gpt-4o",
            model_provider: str = "OpenAI"
    ):
        """
        Executes the trading workflow using the specified configuration.
        Parameters:
            primary_interval (Interval): The primary time interval used for decision making.
            intervals (List[Interval]): List of all time intervals to process data for.
            tickers (List[str]): List of asset symbols to include in the backtest or live run.
            end_date (str): The end date for historical data used in the workflow.
            portfolio (Dict): The initial state of the portfolio, including cash, positions, and margins.
            strategies (List[str]): List of trading strategies to include in the workflow.
            show_reasoning (bool, optional): If True, includes model reasoning in the output. Defaults to False.
            show_agent_graph (bool, optional): If True, saves and displays the graph of the agent workflow. Defaults to False.
            model_name (str, optional): The name of the LLM model to use. Defaults to "gpt-4o".
            model_provider (str, optional): The provider of the LLM model (e.g., "OpenAI", "Gemini"). Defaults to "OpenAI".

        Returns:
        None
        """
        # Create a new workflow if analysts are customized
        workflow = Workflow.create_workflow(intervals=intervals, strategies=strategies)
        agent = workflow.compile()

        if show_agent_graph:
            file_path = ""
            for strategy_name in strategies:
                file_path += strategy_name + "_"
                file_path += "graph.png"
            save_graph_as_png(agent, file_path)

        final_state = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="Make trading decisions based on the provided data.",
                    )
                ],
                "data": {
                    "primary_interval": primary_interval,
                    "intervals": intervals,
                    "tickers": tickers,
                    "portfolio": portfolio,
                    "end_date": end_date,
                    "analyst_signals": {},
                },
                "metadata": {
                    "show_reasoning": show_reasoning,
                    "model_name": model_name,
                    "model_provider": model_provider,
                },
            },
        )
        # print("the final state:", final_state["data"]["analyst_signals"])
        decisions = parse_str_to_json(final_state["messages"][-1].content)
        analyst_signals = final_state["data"]["analyst_signals"] # Extracted for clarity
        order_results = [] # Initialize order_results for all cases

        current_settings = load_settings()

        # Check if live_trading_enabled is True as per current subtask instructions
        if hasattr(current_settings, 'live_trading_enabled') and current_settings.live_trading_enabled is True:
            # API keys expected under a 'trading' attribute in settings as per subtask
            # e.g. current_settings.trading.BINANCE_API_KEY
            # Using getattr for safe access to nested attributes
            trading_settings = getattr(current_settings, 'trading', None)
            api_key = getattr(trading_settings, 'BINANCE_API_KEY', None) if trading_settings else None
            api_secret = getattr(trading_settings, 'BINANCE_API_SECRET', None) if trading_settings else None

            if api_key and api_secret:
                try:
                    binance_client = Client(api_key=api_key, api_secret=api_secret)
                    
                    if isinstance(decisions, dict):
                        for symbol, signal_data in decisions.items():
                            if isinstance(signal_data, dict):
                                # Construct signal ensuring all necessary keys from signal_data are included
                                signal = {
                                    "symbol": symbol,
                                    "action": signal_data.get("action"),
                                    "quantity": signal_data.get("quantity")
                                    # Add other relevant fields from signal_data if place_order_from_signal expects them
                                }
                                
                                # Basic validation of signal components
                                if not all(key in signal and signal[key] is not None for key in ["symbol", "action", "quantity"]):
                                    order_results.append({
                                        "status": "error", 
                                        "message": f"Signal for {symbol} is incomplete or missing essential fields (action, quantity). Signal: {signal}",
                                        "symbol": symbol
                                    })
                                    continue # Move to next signal

                                result = place_order_from_signal(
                                    signal, 
                                    binance_client, 
                                    live_trading_enabled=True # Explicitly pass True
                                )
                                order_results.append(result)
                            else:
                                order_results.append({
                                    "status": "error",
                                    "message": f"Signal data for {symbol} is not a dictionary: {signal_data}",
                                    "symbol": symbol
                                })
                    elif decisions is not None: # decisions might be a string if JSON parsing failed
                         order_results.append({
                            "status": "error",
                            "message": f"Decisions format is invalid (expected dict, got {type(decisions).__name__}): {decisions}"
                        })
                    # If decisions is None (e.g. from parse_str_to_json), it might mean no valid decisions.
                    # This case is implicitly handled as the loop `for symbol, signal_data in decisions.items()` won't run.

                except Exception as e:
                    # Catch errors during client initialization or other unexpected issues
                    order_results.append({
                        "status": "critical_error",
                        "message": f"Failed to initialize Binance client or critical error in live trading block: {str(e)}"
                    })
            else:
                # Live trading enabled but API keys are missing
                order_results.append({
                    "status": "config_error",
                    "message": "Live trading mode is enabled, but Binance API keys are missing or not found under 'settings.trading.BINANCE_API_KEY' and 'settings.trading.BINANCE_API_SECRET'."
                })
        
        return {
            "decisions": decisions,
            "analyst_signals": analyst_signals,
            "order_results": order_results, # Always include order_results
        }
