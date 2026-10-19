# Mortgage Calculator

An interactive mortgage and loan calculator built with Python, pandas, and Streamlit. It shows the true monthly cost of a home loan, breaks down every payment into principal and interest, and models how extra payments, shorter terms, or refinancing change the total cost.

**Live demo:** (https://if116-mortgage-calculator.streamlit.app/)



## Features

- **Full monthly payment**: principal and interest plus property tax, insurance, and PMI, with PMI automatically dropping off at 78% loan-to-value.
- **Amortization schedule**: monthly and yearly views, downloadable as CSV.
- **Extra payment modeling**: recurring extra principal and one-time lump sums, showing interest saved and how much sooner the loan is paid off.
- **Loan comparison**: up to three scenarios side by side (e.g. 15 vs. 30 year), with cumulative interest charted over time.
- **Refinance analysis**: monthly savings, break-even month, and lifetime cost versus keeping the current loan, including the option to roll closing costs into the new loan.

## Example insight

On a $360,000 loan at 6.5% for 30 years, paying an extra $300 per month saves about $144,000 in interest and pays the loan off a little over 8 years early.

## How it works

The monthly payment uses the standard annuity formula:

$$M = P \cdot \frac{r}{1 - (1 + r)^{-n}}$$

where $P$ is the principal, $r$ the monthly rate, and $n$ the number of payments. Each month the schedule computes interest on the remaining balance, applies the scheduled principal, then applies any extra principal, ending early once the balance reaches zero.

## Project structure

```
mortgage-calculator/
├── app.py              # Streamlit UI
├── mortgage/
│   ├── __init__.py
│   └── core.py         # Pure calculation logic, no UI code
├── tests/
│   └── test_core.py    # Unit tests for the math
├── requirements.txt
└── requirements-dev.txt
```

The calculation logic is kept separate from the UI so it can be tested independently and reused (for example, behind an API).

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
streamlit run app.py
```

Run the tests:

```bash
pytest
```

## Possible extensions

- Adjustable-rate mortgage (ARM) modeling
- Rent vs. buy comparison
- Affordability calculator based on income and debt-to-income ratio
- Pulling current average rates from the FRED API

## Disclaimer

For educational purposes only. Actual loan terms depend on your lender.
