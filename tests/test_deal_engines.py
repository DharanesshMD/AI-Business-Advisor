"""
Unit tests for the Deal Intelligence Agent engines.
Test DCF calculation, comparable companies analysis, and HHI antitrust risk.
"""
import pytest
from backend.agents.deal import (
    _dcf_valuation,
    _comps_valuation,
    _precedent_transactions_valuation,
    _hhi_analysis,
    _generate_verdict,
)


class TestDCFValuation:
    def test_dcf_with_complete_financials(self):
        financials = {
            "free_cash_flow": 100_000_000,
            "shares_outstanding": 10_000_000,
            "current_price": 150.0,
            "revenue_growth": 0.10,
            "total_debt": 50_000_000,
            "cash": 20_000_000,
        }
        res = _dcf_valuation(
            financials, wacc=0.10, terminal_growth=0.03, forecast_years=5
        )
        assert res["method"] == "DCF"
        assert res["data_source"] == "live"
        assert res["pv_forecast_fcf"] > 0
        assert res["pv_terminal_value"] > 0
        assert res["intrinsic_value_per_share"] is not None

    def test_dcf_fallback_to_net_income(self):
        financials = {
            "net_income": 100_000_000,
            "shares_outstanding": 10_000_000,
            "current_price": 50.0,
        }
        res = _dcf_valuation(financials, wacc=0.10, terminal_growth=0.03)
        assert res["data_source"] == "estimated"
        assert res["intrinsic_value_per_share"] is not None

    def test_dcf_fallback_to_mock_data(self):
        financials = {
            "market_cap": 2_000_000_000,
            "shares_outstanding": 10_000_000,
        }
        res = _dcf_valuation(financials)
        assert res["data_source"] == "mock"
        assert res["intrinsic_value_per_share"] is not None


class TestCompsValuation:
    def test_comps_valuation(self):
        target = {
            "ebitda": 50_000_000,
            "net_income": 20_000_000,
            "shares_outstanding": 10_000_000,
            "current_price": 25.0,
            "total_debt": 10_000_000,
            "cash": 5_000_000,
        }
        peers = [
            {"ev_ebitda": 10.0, "pe_ratio": 15.0},
            {"ev_ebitda": 12.0, "pe_ratio": 20.0},
            {"ev_ebitda": 14.0, "pe_ratio": 25.0},
        ]
        res = _comps_valuation(target, peers)
        assert res["peer_count"] == 3
        # Medians of [10, 12, 14] and [15, 20, 25] are 12 and 20
        assert res["multiples"]["median_ev_ebitda"] == 12.0
        assert res["multiples"]["median_pe"] == 20.0

        # Implied EV from EBITDA = 12 * 50M = 600M
        assert res["implied_ev_from_ebitda"] == 600_000_000

        # Equity from EBITDA = EV - debt + cash = 600M - 10M + 5M = 595M
        # Per share = 59.5
        assert res["implied_price_ev_ebitda_method"] == 59.5

        # EPS = 20M / 10M = 2.0
        # Price from PE = 20 * 2.0 = 40.0
        assert res["implied_price_pe_method"] == 40.0

        # Blended = (59.5 + 40.0) / 2 = 49.75
        assert res["blended_implied_price"] == 49.75

    def test_comps_with_missing_peer_data(self):
        target = {"ebitda": 10_000_000}
        peers = [
            {"ev_ebitda": None, "pe_ratio": 10.0},
            {"ev_ebitda": 8.0, "pe_ratio": None},
        ]
        res = _comps_valuation(target, peers)
        assert res["multiples"]["median_ev_ebitda"] == 8.0
        assert res["multiples"]["median_pe"] == 10.0


class TestPrecedentTransactions:
    def test_precedent_transactions(self):
        target = {"current_price": 100.0, "market_cap": 1_000_000_000}
        res = _precedent_transactions_valuation(target, control_premium=0.25)
        assert res["implied_offer_price"] == 125.0
        assert res["implied_deal_equity_value"] == 1_250_000_000


class TestHHIAnalysis:
    def test_unconcentrated_market(self):
        res = _hhi_analysis(acquirer_market_share=5.0, target_market_share=5.0)
        assert res["market_concentration"] == "Unconcentrated"
        assert res["regulatory_risk"] == "Low"
        assert res["delta_hhi"] == 50  # (10^2) - (5^2 + 5^2) = 100 - 50 = 50

    def test_moderately_concentrated_low_delta(self):
        other = [40.0]  # HHI base is 1600+
        res = _hhi_analysis(5.0, 5.0, other_shares=other)
        assert res["market_concentration"] == "Moderately Concentrated"
        assert res["regulatory_risk"] == "Low-Medium"

    def test_moderately_concentrated_high_delta(self):
        other = [40.0]
        res = _hhi_analysis(10.0, 10.0, other_shares=other)
        assert res["market_concentration"] == "Moderately Concentrated"
        assert res["regulatory_risk"] == "Medium"
        assert res["delta_hhi"] == 200  # (20^2) - (10^2 + 10^2) = 400 - 200 = 200

    def test_highly_concentrated_presumed_illegal(self):
        other = [50.0]  # HHI base 2500+
        res = _hhi_analysis(15.0, 15.0, other_shares=other)
        assert res["market_concentration"] == "Highly Concentrated"
        assert res["regulatory_risk"] == "High"
        assert res["delta_hhi"] == 450  # (30^2) - (15^2 + 15^2) = 900 - 450 = 450

    def test_decimal_input_conversion(self):
        # Should auto-convert 0.15 to 15.0
        res = _hhi_analysis(acquirer_market_share=0.15, target_market_share=0.10)
        assert res["acquirer_share_pct"] == 15.0
        assert res["target_share_pct"] == 10.0


class TestVerdictGeneration:
    def test_attractive_verdict(self):
        res = _generate_verdict(100.0, {"low": 120.0, "high": 150.0}, "Low", "live")
        assert res["valuation_signal"] == "ATTRACTIVE"

    def test_rich_verdict(self):
        res = _generate_verdict(160.0, {"low": 120.0, "high": 150.0}, "Low", "live")
        assert res["valuation_signal"] == "RICH"

    def test_fair_value_verdict(self):
        res = _generate_verdict(130.0, {"low": 120.0, "high": 150.0}, "Low", "live")
        assert res["valuation_signal"] == "FAIR VALUE"
