import math

import pytest

from mortgage import (
    LoanInputs,
    amortization_schedule,
    compare_scenarios,
    monthly_payment,
    refinance_analysis,
    summarize,
)


def test_monthly_payment_matches_known_value():
    # $300k at 6% for 30 years is a textbook $1,798.65/month.
    assert monthly_payment(300_000, 0.06, 30) == pytest.approx(1798.65, abs=0.01)


def test_zero_rate_is_straight_line():
    assert monthly_payment(120_000, 0.0, 10) == pytest.approx(1000.0)


def test_schedule_pays_off_exactly():
    schedule = amortization_schedule(LoanInputs(250_000, 0.055, 30))
    assert len(schedule) == 360
    assert schedule["balance"].iloc[-1] == pytest.approx(0, abs=0.01)
    assert (schedule["principal"].sum()) == pytest.approx(250_000, abs=0.01)


def test_extra_payments_shorten_loan_and_cut_interest():
    base = summarize(LoanInputs(300_000, 0.065, 30))
    extra = summarize(LoanInputs(300_000, 0.065, 30, extra_monthly=300))
    assert extra.months_to_payoff < base.months_to_payoff
    assert extra.total_interest < base.total_interest
    assert extra.months_saved == 360 - extra.months_to_payoff


def test_lump_sum_applied_in_correct_month():
    schedule = amortization_schedule(LoanInputs(200_000, 0.06, 30, lump_sums={12: 10_000}))
    assert schedule.loc[schedule["month"] == 12, "extra_principal"].iloc[0] == 10_000
    assert schedule.loc[schedule["month"] == 11, "extra_principal"].iloc[0] == 0


def test_lump_sum_larger_than_balance_is_capped():
    schedule = amortization_schedule(LoanInputs(10_000, 0.05, 5, lump_sums={2: 1_000_000}))
    assert len(schedule) == 2
    assert schedule["balance"].iloc[-1] == 0


def test_pmi_drops_off_at_cutoff():
    loan = LoanInputs(
        360_000, 0.065, 30, monthly_pmi=150, home_value=400_000, pmi_cutoff_ltv=0.78
    )
    schedule = amortization_schedule(loan)
    assert schedule["pmi"].iloc[0] == 150
    assert schedule["pmi"].iloc[-1] == 0
    # PMI is only charged while the opening balance is above 78% of value.
    opening = schedule["balance"] + schedule["principal"] + schedule["extra_principal"]
    charged = schedule["pmi"] > 0
    assert (opening[charged] > 0.78 * 400_000).all()


def test_escrow_included_in_total_payment():
    loan = LoanInputs(300_000, 0.06, 30, annual_property_tax=6_000, annual_insurance=1_200)
    s = summarize(loan)
    assert s.total_monthly_payment == pytest.approx(1798.65 + 600, abs=0.01)


def test_compare_scenarios_15_vs_30():
    table = compare_scenarios(
        {"30-year": LoanInputs(300_000, 0.065, 30), "15-year": LoanInputs(300_000, 0.058, 15)}
    )
    assert table.loc["15-year", "monthly_p_and_i"] > table.loc["30-year", "monthly_p_and_i"]
    assert table.loc["15-year", "total_interest"] < table.loc["30-year", "total_interest"]


def test_refinance_break_even():
    result = refinance_analysis(
        current_balance=280_000,
        current_rate=0.075,
        current_months_left=330,
        new_rate=0.06,
        new_years=30,
        closing_costs=6_000,
    )
    assert result["monthly_savings"] > 0
    expected = math.ceil(6_000 / result["monthly_savings"])
    assert result["break_even_month"] == expected


def test_refinance_to_higher_rate_never_breaks_even():
    result = refinance_analysis(200_000, 0.04, 300, 0.07, 30, 5_000)
    assert result["break_even_month"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"principal": 0, "annual_rate": 0.05, "years": 30},
        {"principal": 100_000, "annual_rate": -0.01, "years": 30},
        {"principal": 100_000, "annual_rate": 0.05, "years": 0},
        {"principal": 100_000, "annual_rate": 0.05, "years": 30, "extra_monthly": -50},
    ],
)
def test_invalid_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        LoanInputs(**kwargs)
