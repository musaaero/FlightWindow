# Extra analyses: computed summary and caption drafts

Reference wind limit 12 m/s; precipitation limit 0.1 mm/h; usable day = at least 3 consecutive flyable hours between 7:00 and 17:00. 5 cities, about 4018 days each.

## Where each figure goes in the paper

| Figure | File | Put it in | Why |
|---|---|---|---|
| 3 | fig3_cause_by_month.png | Section 4.2, after the rainy-season finding | Tests the rain-versus-wind inference; update that finding to match |
| 4 | fig4_cause_vs_wind_limit.png | Section 4.2, after Figure 2 (or Appendix C) | Shows which constraint binds at each wind limit |
| 5 | fig5_interannual_uncertainty.png | Section 4.2, after Table 1 | Shows uncertainty on Table 1 |
| 6 | fig6_time_of_day.png | Appendix C | Operational-window justification |
| 7 | fig7_distributions.png | Appendix C | Distributions behind the limits |
| 8 | fig8_robustness.png | Section 4.4 (risks) | Evidence that the definition of a usable day is not driving the result |
| 9 | fig9_persistence.png | Section 5.2, before Table 4 | Tests the independence assumption used in Table 4 |
| 10 | fig10_campaign_delay.png | Section 5.2, after Table 4 | Empirical delay; replace or confirm the formula-based numbers |

## Cause of lost days (Figure 3)

Averaged over the five cities, 9.8% of days are unusable at 12 m/s. Of all days: rain only 7.0%, wind only 1.7%, both 0.6%, timing mismatch 0.6%. Rain-only losses are 72% of all lost days.

```
           Rain  Wind  Both  Timing mismatch
Nanjing    6.87  0.47  0.32             0.27
Suzhou     7.32  2.24  0.67             0.65
Wuxi       7.14  2.31  0.67             0.60
Yangzhou   6.82  1.64  0.47             0.52
Changzhou  7.07  1.79  0.62             0.75
```

## Uncertainty (Figure 5)

July usable-day share, mean over years with bootstrap 95% interval and worst/best single year:

- Nanjing: 80.9% (interval 76.5 to 85.6; worst year 67.7, best year 93.5)
- Suzhou: 79.8% (interval 74.2 to 85.9; worst year 67.7, best year 100.0)
- Wuxi: 82.4% (interval 78.0 to 87.1; worst year 71.0, best year 96.8)
- Yangzhou: 78.0% (interval 74.2 to 81.8; worst year 67.7, best year 87.1)
- Changzhou: 77.7% (interval 72.1 to 84.5; worst year 64.5, best year 96.8)

## Clustering of bad days (Figure 9)

Mean probability that a day is unusable: 9.8%. Given that yesterday was unusable: 23.5%. Mean spell length 1.31 days; longest spell 6 days.

```
     city  P_unusable_pct  P_unusable_given_yesterday_unusable_pct  mean_spell_days  longest_spell_days  share_of_spells_ge3_days_pct
  Nanjing            7.94                                    22.26             1.29                   5                          6.45
   Suzhou           10.88                                    23.57             1.31                   6                          5.99
     Wuxi           10.73                                    21.81             1.28                   5                          6.53
 Yangzhou            9.46                                    25.53             1.34                   4                          7.42
Changzhou           10.23                                    24.57             1.33                   5                          7.74
```

## Campaign delay (Figure 10), K = 10 usable days

- Nanjing: empirical mean 0.9 extra days, independence formula 0.9, 90th percentile 2.0
- Suzhou: empirical mean 1.3 extra days, independence formula 1.2, 90th percentile 3.0
- Wuxi: empirical mean 1.2 extra days, independence formula 1.2, 90th percentile 3.0
- Yangzhou: empirical mean 1.1 extra days, independence formula 1.0, 90th percentile 3.0
- Changzhou: empirical mean 1.2 extra days, independence formula 1.1, 90th percentile 3.0

Starting in June-July the mean extra delay is 2.1 to 2.6 days across cities; starting in November-December it is 0.3 to 0.8 days.

## Robustness (Figure 8)

At 12 m/s the mean usable-day share ranges from 77.0% (longest window tested, 6 h) to 96.4% (shortest, 1 h).

## Caption drafts (edit the sentences to match what you see)

- **Figure 3.** Cause of unusable days by city and month at a 12 m/s wind limit. A day is attributed to rain if it would have been usable under the wind rule alone, to wind if it would have been usable under the rain rule alone, to both if neither rule alone gives a usable window, and to timing mismatch if each rule alone is satisfied but not within the same consecutive hours.
- **Figure 4.** Share of days lost, by cause, as the wind limit is varied (left) and total loss by city (right).
- **Figure 5.** Monthly usable-day share for each year (grey), the mean over years (line) and a bootstrap 95% interval obtained by resampling years (band). The lower right panel shows the annual share by year.
- **Figure 6.** Share of hours that are flyable by month and hour of day (mean of five cities) and the daily profile by city.
- **Figure 7.** Empirical distributions of the daily maximum gust and 100 m wind during operational hours, and the share of days with rain in operational hours by month.
- **Figure 8.** Sensitivity of the usable-day share to the required window length (left) and to the precipitation limit (right).
- **Figure 9.** Persistence of unusable days: probability of an unusable day, with and without an unusable day before it (left); distribution of spell lengths compared with independent days (centre); autocorrelation of the daily usable flag (right).
- **Figure 10.** Extra calendar days needed to complete a 10-usable-day campaign, computed from every historical start date, by start month (left), compared with the independence formula (centre), and as a function of campaign length (right).