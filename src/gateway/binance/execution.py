import logging
from decimal import Decimal, ROUND_DOWN, InvalidOperation

# Assuming the client will be passed and is an instance of Binance Spot Client
# from src.gateway.binance.client import Client # Actual import will depend on how Client is structured
from src.gateway.binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, TIME_IN_FORCE_GTC
from src.gateway.binance.exceptions import BinanceAPIException, BinanceOrderException

logger = logging.getLogger(__name__)

def place_order_from_signal(signal: dict, client, live_trading_enabled: bool = False) -> dict:
    """
    Places an order based on a trading signal.

    Args:
        signal (dict): A dictionary containing the trading signal. 
                       Expected keys: 'symbol', 'action' ('buy', 'sell', 'hold'), 'quantity'.
        client: An instance of the Binance client.
        live_trading_enabled (bool): If True, places real orders. Otherwise, it's a dry run.

    Returns:
        dict: A dictionary containing the outcome of the order placement.
    """
    try:
        symbol = signal.get('symbol')
        action = signal.get('action', 'hold').lower()
        quantity_input = signal.get('quantity')

        if not symbol:
            logger.error("Signal missing 'symbol'.")
            return {"status": "error", "message": "Signal missing 'symbol'."}
        
        if action == "hold":
            logger.info(f"Action for {symbol} is 'hold'. No order placed.")
            return {"status": "no_action", "message": f"Hold signal for {symbol}. No order placed."}

        if quantity_input is None:
            logger.error(f"Signal for {symbol} missing 'quantity'.")
            return {"status": "error", "message": f"Signal for {symbol} missing 'quantity'."}

        try:
            original_quantity = Decimal(str(quantity_input))
        except InvalidOperation:
            logger.error(f"Invalid quantity format for {symbol}: {quantity_input}")
            return {"status": "error", "message": f"Invalid quantity format for {symbol}: {quantity_input}"}


        signal_details = {"symbol": symbol, "action": action, "original_quantity": float(original_quantity)}

        if not live_trading_enabled:
            logger.info(f"DRY RUN: Would place {action} order for {original_quantity} of {symbol}.")
            return {"status": "dry_run", "message": "Order not placed (dry run).", "signal": signal_details}

        # --- Live Trading Logic ---
        logger.info(f"LIVE TRADING: Processing {action} signal for {original_quantity} of {symbol}.")

        try:
            symbol_info = client.get_symbol_info(symbol)
            if not symbol_info:
                logger.error(f"Could not retrieve symbol info for {symbol}.")
                raise ValueError(f"Symbol info not found for {symbol}.")
        except Exception as e:
            logger.error(f"Error fetching symbol info for {symbol}: {e}")
            return {"status": "error", "message": f"Error fetching symbol info for {symbol}: {str(e)}"}

        # Filter extraction and quantity adjustment
        min_qty_str, max_qty_str, step_size_str = None, None, None
        min_notional_str = None

        for f in symbol_info.get('filters', []):
            if f['filterType'] == 'LOT_SIZE':
                min_qty_str = f.get('minQty')
                max_qty_str = f.get('maxQty')
                step_size_str = f.get('stepSize')
            elif f['filterType'] == 'MIN_NOTIONAL' or f['filterType'] == 'NOTIONAL': # Spot uses NOTIONAL, Futures MIN_NOTIONAL
                min_notional_str = f.get('minNotional', f.get('notional')) # some variations in key name

        if not all([min_qty_str, max_qty_str, step_size_str]):
            logger.error(f"LOT_SIZE filter not found or incomplete for {symbol}.")
            return {"status": "error", "message": f"LOT_SIZE filter not found/incomplete for {symbol}."}

        try:
            min_qty = Decimal(min_qty_str)
            max_qty = Decimal(max_qty_str)
            step_size = Decimal(step_size_str)
        except InvalidOperation:
            logger.error(f"Invalid number format in LOT_SIZE filter for {symbol}.")
            return {"status": "error", "message": f"Invalid number format in LOT_SIZE filter for {symbol}."}


        adjusted_quantity = original_quantity

        if adjusted_quantity < min_qty:
            logger.warning(f"Original quantity {original_quantity} for {symbol} is less than minQty {min_qty}. Cannot proceed.")
            return {"status": "error", "message": f"Quantity {original_quantity} less than minQty {min_qty}."}
        if adjusted_quantity > max_qty:
            logger.warning(f"Original quantity {original_quantity} for {symbol} exceeds maxQty {max_qty}. Adjusting to maxQty.")
            adjusted_quantity = max_qty
        
        # Adjust for stepSize: quantity = floor(quantity / stepSize) * stepSize
        if step_size > Decimal('0'): # step_size can be 0 for some symbols, meaning no stepping
            adjusted_quantity = (adjusted_quantity // step_size) * step_size
        else: # if step_size is 0, it means any quantity (within min/max) is fine.
            pass


        if adjusted_quantity < min_qty or adjusted_quantity <= Decimal('0'):
            logger.error(f"Adjusted quantity {adjusted_quantity} for {symbol} is too small or zero. Original: {original_quantity}. MinQty: {min_qty}")
            return {"status": "error", "message": f"Adjusted quantity {adjusted_quantity} too small or zero."}
        
        # MIN_NOTIONAL check (simplified for market orders with quantity)
        # For a precise check, current price * adjusted_quantity should be >= min_notional
        # This is tricky for MARKET orders as price is unknown.
        # Some APIs allow quoteOrderQty for market orders to specify notional value directly.
        # Here, we log a warning if min_notional is present, as python-binance's order_market_buy/sell
        # using 'quantity' might still fail if the resulting notional value is too low.
        if min_notional_str:
            try:
                min_notional = Decimal(min_notional_str)
                # A rough check: if min_qty * (some recent price) < min_notional, it could be an issue.
                # For now, we'll just log that the check might be needed by the exchange.
                logger.info(f"MIN_NOTIONAL for {symbol} is {min_notional}. Order with quantity {adjusted_quantity} will be attempted. "
                            "Exchange will verify actual notional value.")
            except InvalidOperation:
                logger.warning(f"Could not parse minNotional value for {symbol}: {min_notional_str}")


        adjusted_quantity_float = float(adjusted_quantity) # Binance client usually expects float

        # Determine side
        if action == "buy":
            side = SIDE_BUY
        elif action == "sell":
            side = SIDE_SELL
        else:
            logger.error(f"Invalid action '{action}' for {symbol}. Must be 'buy', 'sell', or 'hold'.")
            return {"status": "error", "message": f"Invalid action '{action}'."}

        order_params = {
            "symbol": symbol,
            "side": side,
            "type": ORDER_TYPE_MARKET, # Explicitly market order
            "quantity": adjusted_quantity_float,
        }

        logger.info(f"Attempting to place {action} order for {adjusted_quantity_float} of {symbol}. Params: {order_params}")

        try:
            if action == "buy":
                response = client.order_market_buy(symbol=symbol, quantity=adjusted_quantity_float)
            elif action == "sell":
                response = client.order_market_sell(symbol=symbol, quantity=adjusted_quantity_float)
            
            logger.info(f"Successfully placed {action} order for {symbol}. Response: {response}")
            return {"status": "success", "order_details": response, "adjusted_quantity": adjusted_quantity_float}
        
        except BinanceAPIException as e:
            logger.error(f"Binance API Exception for {symbol} {action} order: {e}")
            return {"status": "error", "message": f"Binance API Error: {e.status_code} - {e.message}"}
        except BinanceOrderException as e:
            logger.error(f"Binance Order Exception for {symbol} {action} order: {e}")
            return {"status": "error", "message": f"Binance Order Error: {e.code} - {e.message}"}
        except Exception as e:
            logger.error(f"Generic exception during {symbol} {action} order: {e}")
            return {"status": "error", "message": f"An unexpected error occurred: {str(e)}"}

    except Exception as e:
        # Catch-all for unexpected errors in the function itself
        logger.error(f"Critical error in place_order_from_signal: {e}", exc_info=True)
        return {"status": "error", "message": f"Critical internal error: {str(e)}"}

# Example Usage (for illustration - requires a mock client and signal)
if __name__ == '__main__':
    # Setup basic logging for example
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # --- Mock Client and Data ---
    class MockBinanceClient:
        def get_symbol_info(self, symbol):
            if symbol == "BTCUSDT":
                return {
                    "symbol": "BTCUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.00001000", "maxQty": "9000.00000000", "stepSize": "0.00001000"},
                        {"filterType": "NOTIONAL", "notional": "10.00000000", "applyToMarket": True, "avgPriceMins": 5} # Spot uses NOTIONAL
                    ]
                }
            elif symbol == "ETHUSDT":
                 return {
                    "symbol": "ETHUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.00010000", "maxQty": "90000.00000000", "stepSize": "0.00010000"},
                        {"filterType": "NOTIONAL", "notional": "10.00000000", "applyToMarket": True, "avgPriceMins": 5}
                    ]
                }
            return None

        def order_market_buy(self, symbol, quantity):
            logger.info(f"MOCK: Market buy for {quantity} of {symbol}")
            if symbol == "BTCUSDT" and quantity < 0.00001:
                 raise BinanceOrderException(request=None, response=MagicMock(status_code=400, text='{"code":-1013,"msg":"Filter failure: LOT_SIZE"}'))
            return {"symbol": symbol, "orderId": 123, "status": "FILLED", "executedQty": str(quantity)}

        def order_market_sell(self, symbol, quantity):
            logger.info(f"MOCK: Market sell for {quantity} of {symbol}")
            return {"symbol": symbol, "orderId": 124, "status": "FILLED", "executedQty": str(quantity)}

    mock_client = MockBinanceClient()
    from unittest.mock import MagicMock


    # --- Test Cases ---
    logger.info("\n--- Testing Dry Run ---")
    signal_dry = {"symbol": "BTCUSDT", "action": "buy", "quantity": 0.005}
    print(place_order_from_signal(signal_dry, mock_client, live_trading_enabled=False))

    logger.info("\n--- Testing Live Buy (Success) ---")
    signal_live_buy = {"symbol": "BTCUSDT", "action": "buy", "quantity": "0.005555"} # Will be adjusted
    print(place_order_from_signal(signal_live_buy, mock_client, live_trading_enabled=True))
    
    logger.info("\n--- Testing Live Sell (Success) ---")
    signal_live_sell = {"symbol": "ETHUSDT", "action": "sell", "quantity": 0.1234}
    print(place_order_from_signal(signal_live_sell, mock_client, live_trading_enabled=True))

    logger.info("\n--- Testing Hold Action ---")
    signal_hold = {"symbol": "BTCUSDT", "action": "hold", "quantity": 1}
    print(place_order_from_signal(signal_hold, mock_client, live_trading_enabled=True))

    logger.info("\n--- Testing Quantity Too Small (Original) ---")
    signal_too_small_orig = {"symbol": "BTCUSDT", "action": "buy", "quantity": 0.000001}
    print(place_order_from_signal(signal_too_small_orig, mock_client, live_trading_enabled=True))

    logger.info("\n--- Testing Quantity Too Small (After Step Size Adjustment) ---")
    # This needs a specific setup where step adjustment makes it < min_qty
    # e.g. min_qty = 0.01, step_size = 0.1, quantity = 0.05 -> adjusted_qty = 0
    # For BTCUSDT: min_qty=0.00001, step_size=0.00001. So any valid original_quantity >= min_qty won't become < min_qty after step adjustment.
    # Let's make a custom mock for this.
    class MockClientStepFail(MockBinanceClient):
        def get_symbol_info(self, symbol):
            if symbol == "STEPFAIL":
                return {
                    "symbol": "STEPFAIL",
                    "filters": [ # minQty = 0.1, stepSize = 1.0. Qty like 0.5 will become 0.0
                        {"filterType": "LOT_SIZE", "minQty": "0.1", "maxQty": "1000.0", "stepSize": "1.0"},
                        {"filterType": "NOTIONAL", "notional": "10.0"}
                    ]
                }
            return super().get_symbol_info(symbol)
    
    mock_client_step_fail = MockClientStepFail()
    signal_step_fail = {"symbol": "STEPFAIL", "action": "buy", "quantity": "0.5"} # adjusted to 0.0 by stepSize 1.0
    print(place_order_from_signal(signal_step_fail, mock_client_step_fail, live_trading_enabled=True))


    logger.info("\n--- Testing Quantity Exceeds Max ---")
    signal_exceeds_max = {"symbol": "BTCUSDT", "action": "buy", "quantity": "10000.0"} # maxQty is 9000
    print(place_order_from_signal(signal_exceeds_max, mock_client, live_trading_enabled=True))


    logger.info("\n--- Testing Invalid Symbol ---")
    signal_invalid_symbol = {"symbol": "XYZUSDT", "action": "buy", "quantity": 1}
    print(place_order_from_signal(signal_invalid_symbol, mock_client, live_trading_enabled=True))

    logger.info("\n--- Testing BinanceOrderException (e.g. LOT_SIZE failure from exchange) ---")
    # To test this, order_market_buy needs to raise it for a specific case
    # Our current mock for BTCUSDT has minQty 0.00001. Let's try to send less.
    signal_lot_fail_exchange = {"symbol": "BTCUSDT", "action": "buy", "quantity": "0.0000001"} # This will pass our initial check as 0.0000001 < 0.00001 is false
                                                                                            # then adjusted_quantity becomes 0.00000 after stepsize.
                                                                                            # so it will be caught by "Adjusted quantity ... too small or zero."
                                                                                            # The mock needs to be more specific.
    # The mock client's order_market_buy will raise BinanceOrderException if quantity < 0.00001
    # Our code adjusts 0.0000001 to 0 after step_size. So this won't hit the mock client exception.
    # Let's try a quantity that is valid after adjustment but the mock client would reject.
    # This isn't possible with the current mock as our logic is stricter or matches.
    # For this test, we'd assume our logic passed but exchange rejected.
    # The mock for order_market_buy is already set to raise for quantity < 0.00001.
    # Our code should adjust 0.000001 to 0.0. Let's test this path.
    signal_lot_fail_adjusted_zero = {"symbol": "BTCUSDT", "action": "buy", "quantity": "0.000001"} # minQty is 0.00001. stepSize is 0.00001. This becomes 0.
    print(place_order_from_signal(signal_lot_fail_adjusted_zero, mock_client, live_trading_enabled=True))
    # The above will print: {"status": "error", "message": "Adjusted quantity 0 too small or zero."}

    # To truly test the BinanceOrderException from client:
    # We need a quantity that passes our internal checks but fails on the mock client.
    # e.g. our min_qty = 0.01, mock_client_min_qty = 0.02.
    # Our current mock client is simple.
    # For now, the exception handling is there, a more complex mock setup would be needed for full coverage.

    logger.info("\n--- Testing Missing Quantity ---")
    signal_no_qty = {"symbol": "BTCUSDT", "action": "buy"}
    print(place_order_from_signal(signal_no_qty, mock_client, live_trading_enabled=True))

    logger.info("\n--- Testing Invalid Quantity Format ---")
    signal_invalid_qty = {"symbol": "BTCUSDT", "action": "buy", "quantity": "not_a_number"}
    print(place_order_from_signal(signal_invalid_qty, mock_client, live_trading_enabled=True))

    logger.info("\n--- Testing Missing Symbol ---")
    signal_no_symbol = {"action": "buy", "quantity": 1}
    print(place_order_from_signal(signal_no_symbol, mock_client, live_trading_enabled=True))

    logger.info("\n--- Testing Incomplete LOT_SIZE filter ---")
    class MockClientIncompleteFilter(MockBinanceClient):
        def get_symbol_info(self, symbol):
            if symbol == "INCOMPLETE":
                return {
                    "symbol": "INCOMPLETE",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.1"} # Missing maxQty, stepSize
                    ]
                }
            return super().get_symbol_info(symbol)
    mock_client_incomplete = MockClientIncompleteFilter()
    signal_incomplete_filter = {"symbol": "INCOMPLETE", "action": "buy", "quantity": "1"}
    print(place_order_from_signal(signal_incomplete_filter, mock_client_incomplete, live_trading_enabled=True))

```
