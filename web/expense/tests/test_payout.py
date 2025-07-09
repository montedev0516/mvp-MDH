from decimal import Decimal
from django.test import TestCase
from unittest.mock import Mock
from expense.utils import calculate_final_amount


class PayoutCalculationTest(TestCase):
    def setUp(self):
        self.payout = Mock()

    def test_real_world_conversion_case(self):
        """Test the exact scenario from the app"""
        # Set the original amounts
        self.payout.cad_revenue = Decimal("1000.00")
        self.payout.cad_commission = Decimal("120.00")
        self.payout.cad_expenses = Decimal("1069.12")
        self.payout.cad_payout = Decimal("-189.12")  # Net CAD amount

        self.payout.usd_revenue = Decimal("5800.00")
        self.payout.usd_commission = Decimal("696.00")
        self.payout.usd_expenses = Decimal("0.00")
        self.payout.usd_payout = Decimal("5104.00")  # Net USD amount

        # Using exchange rate that will be rounded to 1.33
        exchange_rate = Decimal("1.33")

        # Test conversion to CAD
        result = calculate_final_amount(self.payout, "CAD", exchange_rate)

        # Let's see the exact calculations
        print("\nDetailed calculation:")
        print(f"CAD Payout: {self.payout.cad_payout}")
        print(f"USD Payout: {self.payout.usd_payout}")
        print(f"Exchange Rate (rounded): {exchange_rate}")
        print(f"Actual Result: {result}")

        # Calculate expected
        expected = Decimal("6599.20")  # -189.12 + (5104.00 * 1.33)

        self.assertEqual(result, expected)

    def test_exchange_rate_rounding(self):
        """Test that exchange rates are properly rounded to 2 decimal places"""
        self.payout.cad_payout = Decimal("-189.12")
        self.payout.usd_payout = Decimal("5104.00")

        test_cases = [
            ("1.3333", "1.33", "6599.20"),  # 5104 * 1.33 = 6788.32 - 189.12 = 6599.20
            ("1.3349", "1.33", "6599.20"),  # Same as above
            ("1.3350", "1.34", "6650.24"),  # 5104 * 1.34 = 6839.36 - 189.12 = 6650.24
            ("1.33", "1.33", "6599.20"),  # Already at 2 decimals
        ]

        for raw_rate, expected_rate, expected_result in test_cases:
            with self.subTest(raw_rate=raw_rate):
                exchange_rate = Decimal(raw_rate)
                expected_rate = Decimal(expected_rate)
                expected_result = Decimal(expected_result)

                result = calculate_final_amount(self.payout, "CAD", exchange_rate)

                # Verify exchange rate rounding
                rounded_rate = exchange_rate.quantize(
                    Decimal("0.01"), rounding="ROUND_HALF_UP"
                )
                self.assertEqual(rounded_rate, expected_rate)

                # Verify final amount
                self.assertEqual(
                    result,
                    expected_result,
                    f"Failed for rate {raw_rate}. Expected {expected_result}, got {result}",
                )

    def test_zero_values(self):
        """Test handling of zero values"""
        self.payout.cad_payout = Decimal("0.00")
        self.payout.usd_payout = Decimal("1000.00")
        exchange_rate = Decimal("1.33")

        result = calculate_final_amount(self.payout, "CAD", exchange_rate)
        expected = Decimal("1330.00")  # 1000 * 1.33
        self.assertEqual(result, expected)

    def test_negative_values(self):
        """Test handling of negative values"""
        self.payout.cad_payout = Decimal("-500.00")
        self.payout.usd_payout = Decimal("-1000.00")
        exchange_rate = Decimal("1.33")

        result = calculate_final_amount(self.payout, "CAD", exchange_rate)
        expected = Decimal("-1830.00")  # -500 + (-1000 * 1.33)
        self.assertEqual(result, expected)
