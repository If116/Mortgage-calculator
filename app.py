"""Streamlit front end for the mortgage calculator.

Run locally with:  streamlit run app.py
"""

import plotly.graph_objects as go
import streamlit as st

from mortgage import LoanInputs, amortization_schedule, compare_scenarios, refinance_analysis, summarize
from mortgage.core import yearly_summary

st.set_page_config(page_title="Mortgage Calculator", page_icon="🏠", layout="wide")

PRINCIPAL_COLOR = "#2F6F5E"
INTEREST_COLOR = "#C9A227"
EXTRA_COLOR = "#7FB3A3"


def money(x: float) -> str:
    return f"${x:,.0f}"


def months_to_text(months: int) -> str:
    years, rem = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} yr")
    if rem:
        parts.append(f"{rem} mo")
    return " ".join(parts) or "0 mo"


st.title("Mortgage calculator")
st.caption("See your monthly payment, where every dollar goes, and how extra payments or a refinance change the picture.")

calc_tab, compare_tab, refi_tab = st.tabs(["Payment & schedule", "Compare loans", "Refinance"])

# ---------------------------------------------------------------- Calculator
with calc_tab:
    with st.sidebar:
        st.header("Your loan")
        home_price = st.number_input("Home price", 10_000, 10_000_000, 450_000, step=5_000)
        down_pct = st.slider("Down payment (%)", 0.0, 50.0, 20.0, 0.5)
        rate = st.number_input("Interest rate (%)", 0.0, 20.0, 6.5, 0.05) / 100
        years = st.selectbox("Term (years)", [30, 20, 15, 10], index=0)

        st.subheader("Taxes & insurance")
        tax = st.number_input("Property tax per year", 0, 100_000, 5_400, step=100)
        insurance = st.number_input("Home insurance per year", 0, 50_000, 1_500, step=100)
        pmi = 0.0
        if down_pct < 20:
            pmi = st.number_input(
                "PMI per month", 0, 2_000, 150, step=10,
                help="Usually required under 20% down. Removed once you owe 78% of the home's value.",
            )

        st.subheader("Pay it off faster")
        extra = st.number_input("Extra principal per month", 0, 50_000, 0, step=50)
        lump = st.number_input("One-time extra payment", 0, 1_000_000, 0, step=1_000)
        lump_month = st.number_input("Paid in month", 1, years * 12, 12, disabled=lump == 0)

    down_payment = home_price * down_pct / 100
    principal = home_price - down_payment

    if principal <= 0:
        st.error("The down payment covers the full price, so there's no loan to calculate. Lower the down payment to continue.")
        st.stop()

    loan = LoanInputs(
        principal=principal,
        annual_rate=rate,
        years=years,
        extra_monthly=extra,
        lump_sums={int(lump_month): lump} if lump else {},
        annual_property_tax=tax,
        annual_insurance=insurance,
        monthly_pmi=pmi,
        home_value=home_price,
    )
    baseline = LoanInputs(principal=principal, annual_rate=rate, years=years)

    schedule = amortization_schedule(loan)
    summary = summarize(loan, schedule)
    base_summary = summarize(baseline)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Monthly payment", money(summary.total_monthly_payment),
              help="Principal, interest, taxes, insurance, PMI and any extra principal.")
    c2.metric("Loan amount", money(principal), f"{money(down_payment)} down", delta_color="off")
    c3.metric("Total interest", money(summary.total_interest),
              f"-{money(base_summary.total_interest - summary.total_interest)}" if extra or lump else None,
              delta_color="inverse" if extra or lump else "off")
    c4.metric("Paid off in", months_to_text(summary.months_to_payoff),
              f"{months_to_text(summary.months_saved)} sooner" if summary.months_saved else None)

    left, right = st.columns([1, 2])

    with left:
        st.subheader("Where your monthly payment goes")
        first = schedule.iloc[0]
        parts = {
            "Principal": first["principal"] + extra,
            "Interest": first["interest"],
            "Taxes & insurance": first["escrow"],
            "PMI": first["pmi"],
        }
        parts = {k: v for k, v in parts.items() if v > 0}
        donut = go.Figure(go.Pie(
            labels=list(parts), values=list(parts.values()), hole=0.6,
            marker_colors=[PRINCIPAL_COLOR, INTEREST_COLOR, "#8C8C8C", "#B5533C"][: len(parts)],
            sort=False, textinfo="percent",
        ))
        donut.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300, showlegend=True,
                            legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(donut, use_container_width=True)

    with right:
        st.subheader("Balance over time")
        base_schedule = amortization_schedule(baseline)
        balance = go.Figure()
        balance.add_trace(go.Scatter(x=base_schedule["month"] / 12, y=base_schedule["balance"],
                                     name="Standard payments", line=dict(color="#8C8C8C", dash="dot")))
        if extra or lump:
            balance.add_trace(go.Scatter(x=schedule["month"] / 12, y=schedule["balance"],
                                         name="With extra payments", line=dict(color=PRINCIPAL_COLOR, width=3)))
        balance.update_layout(xaxis_title="Years", yaxis_title="Remaining balance", yaxis_tickprefix="$",
                              height=330, margin=dict(t=10, b=10), hovermode="x unified",
                              legend=dict(orientation="h", y=1.1))
        st.plotly_chart(balance, use_container_width=True)

    st.subheader("Principal vs. interest by year")
    yearly = yearly_summary(schedule)
    bars = go.Figure()
    bars.add_bar(x=yearly["year"], y=yearly["principal"], name="Principal", marker_color=PRINCIPAL_COLOR)
    if yearly["extra_principal"].sum() > 0:
        bars.add_bar(x=yearly["year"], y=yearly["extra_principal"], name="Extra principal", marker_color=EXTRA_COLOR)
    bars.add_bar(x=yearly["year"], y=yearly["interest"], name="Interest", marker_color=INTEREST_COLOR)
    bars.update_layout(barmode="stack", xaxis_title="Year", yaxis_tickprefix="$", height=350,
                       margin=dict(t=10, b=10), legend=dict(orientation="h", y=1.1))
    st.plotly_chart(bars, use_container_width=True)

    with st.expander("Full amortization schedule"):
        view = st.radio("Show", ["Yearly", "Monthly"], horizontal=True)
        table = yearly if view == "Yearly" else schedule[
            ["month", "payment", "principal", "interest", "extra_principal", "escrow", "pmi", "balance"]
        ]
        st.dataframe(table.style.format("${:,.2f}", subset=[c for c in table.columns if c not in ("year", "month")]),
                     use_container_width=True, hide_index=True)
        st.download_button("Download schedule (CSV)", schedule.to_csv(index=False), "amortization_schedule.csv", "text/csv")

# ------------------------------------------------------------------ Compare
with compare_tab:
    st.subheader("Compare up to three loans")
    st.caption("Same loan amount, different terms or rates. A common question is 15 vs. 30 years.")
    amount = st.number_input("Loan amount", 10_000, 10_000_000, int(principal), step=5_000, key="cmp_amount")

    defaults = [("30-year fixed", 6.5, 30, 0), ("15-year fixed", 5.8, 15, 0), ("30-year + $300/mo", 6.5, 30, 300)]
    cols = st.columns(3)
    scenarios = {}
    for i, (col, (name, r, t, x)) in enumerate(zip(cols, defaults)):
        with col:
            label = st.text_input("Name", name, key=f"name{i}")
            r_in = st.number_input("Rate (%)", 0.0, 20.0, r, 0.05, key=f"rate{i}") / 100
            t_in = st.selectbox("Term", [30, 20, 15, 10], index=[30, 20, 15, 10].index(t), key=f"term{i}")
            x_in = st.number_input("Extra per month", 0, 50_000, x, step=50, key=f"extra{i}")
            scenarios[label or f"Loan {i + 1}"] = LoanInputs(amount, r_in, t_in, extra_monthly=x_in)

    table = compare_scenarios(scenarios)
    st.dataframe(
        table.style.format({
            "rate": "{:.2%}", "term_years": "{:.0f}", "monthly_p_and_i": "${:,.0f}", "extra_monthly": "${:,.0f}",
            "total_interest": "${:,.0f}", "total_paid": "${:,.0f}", "payoff_years": "{:.1f}",
        }),
        use_container_width=True,
    )

    fig = go.Figure()
    for name, sc in scenarios.items():
        sched = amortization_schedule(sc)
        fig.add_trace(go.Scatter(x=sched["month"] / 12, y=sched["cumulative_interest"], name=name))
    fig.update_layout(title="Interest paid over time", xaxis_title="Years", yaxis_tickprefix="$",
                      height=380, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    cheapest = table["total_interest"].idxmin()
    priciest = table["total_interest"].idxmax()
    gap = table.loc[priciest, "total_interest"] - table.loc[cheapest, "total_interest"]
    st.info(f"**{cheapest}** costs {money(gap)} less in interest than **{priciest}** over the life of the loan.")

# ---------------------------------------------------------------- Refinance
with refi_tab:
    st.subheader("Should you refinance?")
    a, b = st.columns(2)
    with a:
        st.markdown("**Current loan**")
        cur_bal = st.number_input("Remaining balance", 1_000, 10_000_000, 320_000, step=5_000)
        cur_rate = st.number_input("Current rate (%)", 0.0, 20.0, 7.5, 0.05) / 100
        cur_left = st.number_input("Years left", 1, 40, 27)
    with b:
        st.markdown("**New loan**")
        new_rate = st.number_input("New rate (%)", 0.0, 20.0, 6.25, 0.05) / 100
        new_years = st.selectbox("New term (years)", [30, 20, 15, 10], key="refi_term")
        costs = st.number_input("Closing costs", 0, 100_000, 7_000, step=500)
        roll = st.checkbox("Roll closing costs into the new loan")

    res = refinance_analysis(cur_bal, cur_rate, cur_left * 12, new_rate, new_years, costs, roll)

    m1, m2, m3 = st.columns(3)
    m1.metric("New monthly payment", money(res["new_payment"]),
              f"{money(-res['monthly_savings'])}/mo" if res["monthly_savings"] < 0 else f"-{money(res['monthly_savings'])}/mo",
              delta_color="inverse")
    be = res["break_even_month"]
    m2.metric("Break-even", "Never" if be is None else months_to_text(be))
    diff = res["lifetime_cost_difference"]
    m3.metric("Lifetime cost vs. staying", money(abs(diff)) + (" more" if diff > 0 else " less"))

    if be is None:
        st.warning("The new payment isn't lower, so the closing costs are never recovered through monthly savings.")
    else:
        st.write(f"You'd recover the closing costs after **{months_to_text(be)}**. Refinancing makes sense if you expect to keep the loan longer than that.")
    if new_years * 12 > cur_left * 12 and diff > 0:
        st.caption("The new loan has a longer term than what's left on your current one, so you may pay more interest overall even with a lower monthly payment.")

st.divider()
st.caption("Estimates only, for educational purposes. Actual payments depend on your lender, taxes and insurance.")
