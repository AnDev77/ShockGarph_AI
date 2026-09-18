# Methodology

## Probability layer

Compare the raw market probability baseline with grouped chronological logistic
calibration. Brier score is primary; log loss and expected calibration error are
secondary. Never split snapshots from the same event across data splits.

## Event study layer

Estimate expected returns over `[-120, -21]` trading days and report abnormal
returns and CAR over `[-5, +5]`. Align event timestamps to the first tradable
session for each asset and bootstrap confidence intervals by event.

## Transmission layer

Use sparse lagged associations and label them as associations, not causal effects.
Every edge carries its lag, coefficient, confidence interval, and sample size.

## Risk layer

Combine scenario-conditional asset returns with validated portfolio weights.
Report expected return, historical VaR, Expected Shortfall, and contribution by
asset and event. Results are risk information, not trading advice.

