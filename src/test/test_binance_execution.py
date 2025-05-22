import unittest
from unittest.mock import patch, MagicMock
import logging
from decimal import Decimal

# Assuming the file is in src.gateway.binance.execution
from src.gateway.binance.execution import place_order_from_signal
from src.gateway.binance.exceptions import BinanceAPIException, BinanceOrderException

# Disable logging for tests unless specifically testing log output
# logging.disable(logging.CRITICAL) # Or use self.assertLogs for specific log checks

class TestPlaceOrderFromSignal(unittest.TestCase):

    def setUp(self):
        """Setup common mock client and symbol info for tests."""
        self.mock_client = MagicMock()
        self.symbol = "ETHUSDT"
        self.default_symbol_info = {
            "symbol": self.symbol,
            "filters": [
                {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "10000.0", "stepSize": "0.001"},
                {"filterType": "MIN_NOTIONAL", "minNotional": "10.0"}, 
                # Spot often uses NOTIONAL instead of MIN_NOTIONAL, or both.
                # The function place_order_from_signal checks for 'NOTIONAL' as fallback.
            ]
        }
        self.mock_client.get_symbol_info.return_value = self.default_symbol_info
        
        # Patch the logger used within execution.py to capture log messages for assertions
        # self.execution_logger_patch = patch('src.gateway.binance.execution.logger')
        # self.mock_execution_logger = self.execution_logger_patch.start()
        # self.addCleanup(self.execution_logger_patch.stop)


    # 1. Test "hold" action
    def test_hold_action(self):
        signal = {"symbol": self.symbol, "action": "hold", "quantity": "1"}
        with self.assertLogs(logger='src.gateway.binance.execution', level='INFO') as cm:
            result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        self.assertEqual(result['status'], "no_action")
        self.assertIn(f"Hold signal for {self.symbol}", result['message'])
        self.mock_client.order_market_buy.assert_not_called()
        self.mock_client.order_market_sell.assert_not_called()
        # Check log message
        self.assertTrue(any(f"Action for {self.symbol} is 'hold'. No order placed." in log_msg for log_msg in cm.output))

    # 2. Test "dry run" mode
    def test_dry_run_mode(self):
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "1"}
        with self.assertLogs(logger='src.gateway.binance.execution', level='INFO') as cm:
            result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=False)
        self.assertEqual(result['status'], "dry_run")
        self.assertIn("Order not placed (dry run)", result['message'])
        self.mock_client.order_market_buy.assert_not_called()
        self.mock_client.order_market_sell.assert_not_called()
        self.assertTrue(any(f"DRY RUN: Would place buy order for 1 of {self.symbol}" in log_msg for log_msg in cm.output))

    # 3. Test successful market buy order (live mode)
    def test_successful_market_buy_live(self):
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "1.234"}
        expected_adjusted_quantity = 1.234 # stepSize is 0.001
        self.mock_client.order_market_buy.return_value = {"status": "FILLED", "orderId": "123"}
        
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        
        self.assertEqual(result['status'], "success")
        self.assertEqual(result['adjusted_quantity'], expected_adjusted_quantity)
        self.mock_client.get_symbol_info.assert_called_once_with(self.symbol)
        self.mock_client.order_market_buy.assert_called_once_with(symbol=self.symbol, quantity=expected_adjusted_quantity)
        self.mock_client.order_market_sell.assert_not_called()

    # 4. Test successful market sell order (live mode)
    def test_successful_market_sell_live(self):
        signal = {"symbol": self.symbol, "action": "sell", "quantity": "2.345"}
        expected_adjusted_quantity = 2.345
        self.mock_client.order_market_sell.return_value = {"status": "FILLED", "orderId": "124"}

        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)

        self.assertEqual(result['status'], "success")
        self.assertEqual(result['adjusted_quantity'], expected_adjusted_quantity)
        self.mock_client.get_symbol_info.assert_called_once_with(self.symbol)
        self.mock_client.order_market_sell.assert_called_once_with(symbol=self.symbol, quantity=expected_adjusted_quantity)
        self.mock_client.order_market_buy.assert_not_called()

    # 5. Test quantity adjustment (stepSize)
    def test_quantity_adjustment_step_size(self):
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "1.2345"} # stepSize is 0.001
        expected_adjusted_quantity = 1.234 # 1.2345 adjusted down to 1.234
        self.mock_client.order_market_buy.return_value = {"status": "FILLED", "orderId": "125"}

        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        
        self.assertEqual(result['status'], "success")
        self.assertEqual(result['adjusted_quantity'], expected_adjusted_quantity)
        self.mock_client.order_market_buy.assert_called_once_with(symbol=self.symbol, quantity=expected_adjusted_quantity)

    # 6. Test quantity less than minQty
    def test_quantity_less_than_min_qty(self):
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "0.0001"} # minQty is 0.001
        
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        
        self.assertEqual(result['status'], "error")
        self.assertIn("less than minQty", result['message'])
        self.mock_client.order_market_buy.assert_not_called()

    # 7. Test quantity greater than maxQty
    def test_quantity_greater_than_max_qty(self):
        # default maxQty is "10000.0"
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "10001.0"}
        # The function adjusts to maxQty if > maxQty
        expected_adjusted_quantity = 10000.0
        self.mock_client.order_market_buy.return_value = {"status": "FILLED", "orderId": "126"}
        
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)

        self.assertEqual(result['status'], "success") # Should succeed after adjustment
        self.assertEqual(result['adjusted_quantity'], expected_adjusted_quantity)
        self.mock_client.order_market_buy.assert_called_once_with(symbol=self.symbol, quantity=expected_adjusted_quantity)


    # 8. Test MIN_NOTIONAL failure (conceptual) / logging
    def test_min_notional_logging(self):
        # Current implementation logs MIN_NOTIONAL presence but doesn't fail pre-emptively for market orders.
        # We'll test that the log occurs.
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "0.5"} # Assumes 0.5 * price > minNotional (10.0)
                                                                      # This test focuses on the log message.
        self.mock_client.order_market_buy.return_value = {"status": "FILLED", "orderId": "127"}

        with self.assertLogs(logger='src.gateway.binance.execution', level='INFO') as cm:
            result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        
        self.assertEqual(result['status'], "success") # Order proceeds
        self.assertTrue(any(f"MIN_NOTIONAL for {self.symbol} is 10.0. Order with quantity 0.5 will be attempted." in log_msg for log_msg in cm.output))


    # 9. Test client.get_symbol_info returns None
    def test_get_symbol_info_none(self):
        self.mock_client.get_symbol_info.return_value = None
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "1"}
        
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        
        self.assertEqual(result['status'], "error")
        self.assertIn(f"Error fetching symbol info for {self.symbol}", result['message']) # Updated to match actual error message
        self.mock_client.order_market_buy.assert_not_called()

    # 10. Test BinanceAPIException during order placement
    def test_binance_api_exception_on_order(self):
        self.mock_client.order_market_buy.side_effect = BinanceAPIException(request=None, response=MagicMock(status_code=400, text='{"code":-1001,"msg":"API error"}'))
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "1"}
        
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        
        self.assertEqual(result['status'], "error")
        self.assertIn("Binance API Error", result['message'])

    # 11. Test BinanceOrderException during order placement
    def test_binance_order_exception_on_order(self):
        self.mock_client.order_market_buy.side_effect = BinanceOrderException(request=None, response=MagicMock(status_code=400, text='{"code":-2010,"msg":"Order error"}'))
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "1"}
        
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        
        self.assertEqual(result['status'], "error")
        self.assertIn("Binance Order Error", result['message'])

    # 12. Test adjusted quantity becomes zero
    def test_adjusted_quantity_becomes_zero(self):
        custom_symbol_info = {
            "symbol": self.symbol,
            "filters": [
                {"filterType": "LOT_SIZE", "minQty": "0.01", "maxQty": "1000.0", "stepSize": "0.1"}, # minQty=0.01, stepSize=0.1
                {"filterType": "MIN_NOTIONAL", "minNotional": "10.0"},
            ]
        }
        self.mock_client.get_symbol_info.return_value = custom_symbol_info
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "0.05"} # 0.05 // 0.1 * 0.1 = 0.0
        
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        
        self.assertEqual(result['status'], "error")
        self.assertIn("Adjusted quantity 0.0 too small or zero", result['message'])
        self.mock_client.order_market_buy.assert_not_called()

    def test_missing_symbol_in_signal(self):
        signal = {"action": "buy", "quantity": "1"} # Missing "symbol"
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        self.assertEqual(result['status'], "error")
        self.assertIn("Signal missing 'symbol'", result['message'])

    def test_missing_quantity_in_signal(self):
        signal = {"symbol": self.symbol, "action": "buy"} # Missing "quantity"
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        self.assertEqual(result['status'], "error")
        self.assertIn(f"Signal for {self.symbol} missing 'quantity'", result['message'])

    def test_invalid_quantity_format(self):
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "not_a_number"}
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        self.assertEqual(result['status'], "error")
        self.assertIn(f"Invalid quantity format for {self.symbol}", result['message'])
        
    def test_incomplete_lot_size_filter(self):
        self.mock_client.get_symbol_info.return_value = {
            "symbol": self.symbol,
            "filters": [{"filterType": "LOT_SIZE", "minQty": "0.001"}] # Missing maxQty, stepSize
        }
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "1"}
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        self.assertEqual(result['status'], "error")
        self.assertIn("LOT_SIZE filter not found/incomplete", result['message'])

    def test_invalid_number_in_lot_size_filter(self):
        self.mock_client.get_symbol_info.return_value = {
            "symbol": self.symbol,
            "filters": [{"filterType": "LOT_SIZE", "minQty": "invalid", "maxQty": "100", "stepSize": "0.01"}]
        }
        signal = {"symbol": self.symbol, "action": "buy", "quantity": "1"}
        result = place_order_from_signal(signal, self.mock_client, live_trading_enabled=True)
        self.assertEqual(result['status'], "error")
        self.assertIn("Invalid number format in LOT_SIZE filter", result['message'])


if __name__ == '__main__':
    unittest.main()
