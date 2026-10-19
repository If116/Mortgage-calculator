"""Loan amortization math.

Everything here is pure Python + pandas so it can be unit tested and reused
outside the Streamlit app.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

MONTHS_PER_YEAR = 12


@dataclass(frozen=True)
class LoanInputs:
    """Parameters describing a fixed-rate loan.

    Attributes:
        principal: Amount borrowed (home price minus down payment).
        annual_rate: Nominal annual interest rate as a decimal (0.065 = 6.5%).
        years: Loan term in years.
        extra_monthly: Additional principal paid every month.
        lump_sums: One-time extra principal payments, keyed by month number (1-based).
        annual_property_tax: Yearly property tax, paid monthly in escrow.
        annual_insurance: Yearly homeowner's insurance, paid monthly in escrow.
        monthly_pmi: Private mortgage insurance, charged until the balance
            falls to `pmi_cutoff_ltv` of `home_value`.
        home_value: Original home value, used for the PMI cutoff.
        pmi_cutoff_ltv: Loan-to-value ratio at which PMI is removed.
    """

    principal: float
    annual_rate: float
    years: int
    extra_monthly: float = 0.0
    lump_sums: dict[int, float] = field(default_factory=dict)
    annual_property_tax: float = 0.0
    annual_insurance: float = 0.0
    monthly_pmi: float = 0.0
    home_value: float | None = None
    pmi_cutoff_ltv: float = 0.78

    def __post_init__(self) -> None:
        if self.principal <= 0:
            raise ValueError("principal must be positive")
        if self.annual_rate < 0:
            raise ValueError("annual_rate cannot be negative")
        if self.years <= 0:
            raise ValueError("years must be positive")
        if self.extra_monthly < 0 or any(v < 0 for v in self.lump_sums.values()):
            raise ValueError("extra payments cannot be negative")

    @property
    def n_payments(self) -> int:
        return self.years * MONTHS_PER_YEAR

    @property
    def monthly_rate(self) -> float:
        return self.annual_rate / MONTHS_PER_YEAR


@dataclass(frozen=True)
class LoanSummary:
    """Headline numbers for a loan."""

    scheduled_payment: float  # principal + interest only
    total_monthly_payment: float  # P&I + escrow + PMI + extra, first month
    total_interest: float
    total_paid: float  # principal + interest (excludes escrow and PMI)
    total_pmi: float
    months_to_payoff: int
    months_saved: int


def monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    """Standard fixed-rate amortizing payment (principal + interest).

    Uses the annuity formula P * r / (1 - (1 + r)^-n), falling back to
    straight-line repayment when the rate is zero.
    """
    n = years * MONTHS_PER_YEAR
    r = annual_rate / MONTHS_PER_YEAR
    if r == 0:
        return principal / n
    return principal * r / (1 - (1 + r) ** -n)


def amortization_schedule(loan: LoanInputs) -> pd.DataFrame:
    """Month-by-month schedule including extra payments, escrow and PMI.

    The loan ends early if extra principal pays off the balance before the
    scheduled term.
    """
    payment = monthly_payment(loan.principal, loan.annual_rate, loan.years)
    escrow = (loan.annual_property_tax + loan.annual_insurance) / MONTHS_PER_YEAR
    home_value = loan.home_value or loan.principal
    pmi_cutoff_balance = loan.pmi_cutoff_ltv * home_value

    balance = loan.principal
    rows = []
    cumulative_interest = 0.0

    for month in range(1, loan.n_payments + 1):
        interest = balance * loan.monthly_rate
        scheduled_principal = min(payment - interest, balance)
        extra = loan.extra_monthly + loan.lump_sums.get(month, 0.0)
        extra = min(extra, balance - scheduled_principal)
        pmi = loan.monthly_pmi if balance > pmi_cutoff_balance else 0.0

        balance -= scheduled_principal + extra
        cumulative_interest += interest

        rows.append(
            {
                "month": month,
                "year": (month - 1) // MONTHS_PER_YEAR + 1,
                "payment": scheduled_principal + interest,
                "principal": scheduled_principal,
                "interest": interest,
                "extra_principal": extra,
                "escrow": escrow,
                "pmi": pmi,
                "total_payment": scheduled_principal + interest + extra + escrow + pmi,
                "balance": max(balance, 0.0),
                "cumulative_interest": cumulative_interest,
            }
        )

        # Small tolerance avoids an extra row caused by floating-point dust.
        if balance <= 0.005:
            break

    return pd.DataFrame(rows)


def yearly_summary(schedule: pd.DataFrame) -> pd.DataFrame:
    """Collapse a monthly schedule into one row per year."""
    return schedule.groupby("year").agg(
        principal=("principal", "sum"),
        extra_principal=("extra_principal", "sum"),
        interest=("interest", "sum"),
        pmi=("pmi", "sum"),
        ending_balance=("balance", "last"),
    ).reset_index()


def summarize(loan: LoanInputs, schedule: pd.DataFrame | None = None) -> LoanSummary:
    """Headline numbers for a loan."""
    if schedule is None:
        schedule = amortization_schedule(loan)
    payment = monthly_payment(loan.principal, loan.annual_rate, loan.years)
    first = schedule.iloc[0]
    total_interest = float(schedule["interest"].sum())
    return LoanSummary(
        scheduled_payment=payment,
        total_monthly_payment=float(first["total_payment"]) - loan.lump_sums.get(1, 0.0),
        total_interest=total_interest,
        total_paid=loan.principal + total_interest,
        total_pmi=float(schedule["pmi"].sum()),
        months_to_payoff=len(schedule),
        months_saved=loan.n_payments - len(schedule),
    )


def compare_scenarios(scenarios: dict[str, LoanInputs]) -> pd.DataFrame:
    """Side-by-side summary table for several named loans."""
    rows = []
    for name, loan in scenarios.items():
        s = summarize(loan)
        rows.append(
            {
                "scenario": name,
                "rate": loan.annual_rate,
                "term_years": loan.years,
                "monthly_p_and_i": s.scheduled_payment,
                "extra_monthly": loan.extra_monthly,
                "total_interest": s.total_interest,
                "total_paid": s.total_paid,
                "payoff_years": s.months_to_payoff / MONTHS_PER_YEAR,
            }
        )
    return pd.DataFrame(rows).set_index("scenario")


def refinance_analysis(
    current_balance: float,
    current_rate: float,
    current_months_left: int,
    new_rate: float,
    new_years: int,
    closing_costs: float,
    roll_costs_into_loan: bool = False,
) -> dict[str, float | int | None]:
    """Compare keeping the current loan against refinancing.

    Returns monthly savings, the break-even month (when cumulative savings
    exceed closing costs), and lifetime interest for both options. A
    break-even of None means the refinance never pays for itself.
    """
    if current_months_left <= 0:
        raise ValueError("current_months_left must be positive")

    r_old = current_rate / MONTHS_PER_YEAR
    if r_old == 0:
        old_payment = current_balance / current_months_left
    else:
        old_payment = current_balance * r_old / (1 - (1 + r_old) ** -current_months_left)
    old_interest = old_payment * current_months_left - current_balance

    new_principal = current_balance + (closing_costs if roll_costs_into_loan else 0.0)
    new_payment = monthly_payment(new_principal, new_rate, new_years)
    new_interest = new_payment * new_years * MONTHS_PER_YEAR - new_principal

    monthly_savings = old_payment - new_payment
    upfront = 0.0 if roll_costs_into_loan else closing_costs

    if monthly_savings <= 0:
        break_even = None
    elif upfront == 0:
        break_even = 0
    else:
        break_even = int(-(-upfront // monthly_savings))  # ceiling division

    return {
        "old_payment": old_payment,
        "new_payment": new_payment,
        "monthly_savings": monthly_savings,
        "break_even_month": break_even,
        "old_total_interest": old_interest,
        "new_total_interest": new_interest,
        "lifetime_cost_difference": (new_interest + closing_costs) - old_interest,
    }
