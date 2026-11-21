#!/usr/bin/env python3
"""
extra_figures.py  -  additional analyses for the FlightWindow proposal

Reads the weather files that flyable_hours.py already downloaded
(output/cache/<City>_<Year>.csv) and produces eight extra figures that answer
questions a reviewer is likely to ask:

  Fig 3  Why are days lost: rain, wind, both, or timing?        (tests the rain-vs-wind inference)
  Fig 4  Cause of loss as the wind limit changes
  Fig 5  Year-to-year spread and bootstrap 95% intervals        (how uncertain is Table 1?)
  Fig 6  Time of day: when in the day is flying possible?
  Fig 7  Distributions of gusts, 100 m wind and wet days        (what sits behind the limits?)
  Fig 8  Robustness to the definition of a usable day           (window length, precipitation limit)
  Fig 9  Do bad days cluster? (persistence, spell lengths)      (tests the independence assumption in Table 4)
  Fig 10 Empirical campaign delay from historical start dates   (replaces the 10 x (1/p - 1) approximation)

Everything is computed from the same real data. Nothing is simulated.
Where a figure contradicts a sentence in the paper, change the sentence.

Usage
  python extra_figures.py                      # reads ./output/cache, writes ./extra_output
  python extra_figures.py --cache output/cache --ref-gust 12 --campaign-days 10

Outputs (in extra_output/): fig3 ... fig10 PNG, several CSV files, and
extra_summary.md (key numbers computed from your data, with caption drafts).

Requires numpy, pandas, matplotlib only.
"""

import argparse
import re
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CITY_ORDER = ["Nanjing", "Suzhou", "Wuxi", "Yangzhou", "Changzhou"]
CITY_COL = {"Nanjing": "#1f77b4", "Suzhou": "#ff7f0e", "Wuxi": "#2ca02c", "Yangzhou": "#d62728", "Changzhou": "#9467bd"}
CAUSES = ["Rain", "Wind", "Both", "Timing mismatch"]
CAUSE_COL = {"Rain": "#3b82c4", "Wind": "#e08a1e", "Both": "#8e44ad", "Timing mismatch": "#8a8f98"}

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 200, "font.size": 10, "axes.titlesize": 11,
    "axes.titleweight": "bold", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "legend.frameon": False,
})


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_cache(cache_dir, y0, y1):
    by_city = {}
    for f in sorted(Path(cache_dir).glob("*.csv")):
        m = re.match(r"(.+)_(\d{4})\.csv$", f.name)
        if not m:
            continue
        city, year = m.group(1).replace("_", " "), int(m.group(2))
        if y0 <= year <= y1:
            by_city.setdefault(city, []).append(pd.read_csv(f, parse_dates=["time"]))
    if not by_city:
        sys.exit(f"No cache files found in '{cache_dir}'. Run flyable_hours.py first (it creates output/cache).")
    out = {}
    for city in sorted(by_city, key=lambda c: CITY_ORDER.index(c) if c in CITY_ORDER else 99):
        out[city] = pd.concat(by_city[city]).drop_duplicates("time").set_index("time").sort_index()
    return out


class CityData:
    """Operational-hours arrays (days x hours) for one city."""

    def __init__(self, df, h0, h1):
        op = df[(df.index.hour >= h0) & (df.index.hour < h1)]
        keys = [op.index.normalize(), op.index.hour]
        piv = {c: op[c].groupby(keys).first().unstack()
               for c in ["wind_gusts_10m", "wind_speed_100m", "precipitation"]}
        idx = piv["wind_gusts_10m"].index
        for t in piv.values():
            idx = idx.intersection(t.index)
        for k in piv:
            piv[k] = piv[k].loc[idx]
        good = ~(piv["wind_gusts_10m"].isna().any(axis=1) | piv["wind_speed_100m"].isna().any(axis=1)
                 | piv["precipitation"].isna().any(axis=1))
        self.days = idx[good.to_numpy()]
        self.g = piv["wind_gusts_10m"].loc[self.days].to_numpy(float)
        self.w = piv["wind_speed_100m"].loc[self.days].to_numpy(float)
        self.p = piv["precipitation"].loc[self.days].to_numpy(float)


def max_run(ok):
    run = np.zeros(ok.shape[0], dtype=int)
    best = run.copy()
    for k in range(ok.shape[1]):
        run = (run + 1) * ok[:, k]
        best = np.maximum(best, run)
    return best


def usable(cd, L, P, D):
    wind_ok = (cd.g <= L) & (cd.w <= L)
    rain_ok = cd.p <= P
    return max_run(wind_ok & rain_ok) >= D, wind_ok, rain_ok


def decompose(cd, L, P, D):
    u, wind_ok, rain_ok = usable(cd, L, P, D)
    uw = max_run(wind_ok) >= D
    ur = max_run(rain_ok) >= D
    cat = np.full(len(u), "usable", dtype=object)
    lost = ~u
    cat[lost & uw & ~ur] = "Rain"
    cat[lost & ~uw & ur] = "Wind"
    cat[lost & ~uw & ~ur] = "Both"
    cat[lost & uw & ur] = "Timing mismatch"
    return pd.Series(cat, index=cd.days)


def annotate(ax, arr, fmt="{:.0f}", fs=7, thresh=None):
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            ax.text(j, i, fmt.format(arr[i, j]), ha="center", va="center", fontsize=fs)


def save(fig, outdir, name):
    fig.savefig(outdir / name, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {name}")


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def fig3_cause_by_month(data, a, outdir, S):
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    annual = {}
    city_axes = []
    for ax, (city, cd) in zip(axes.flat, data.items()):
        city_axes.append(ax)
        cat = decompose(cd, a.ref_gust, a.precip_max, a.min_window)
        tab = pd.crosstab(cat.index.month, cat.values, normalize="index") * 100
        tab = tab.reindex(index=range(1, 13), columns=CAUSES + ["usable"], fill_value=0)[CAUSES]
        bottom = np.zeros(12)
        for c in CAUSES:
            ax.bar(range(12), tab[c], bottom=bottom, color=CAUSE_COL[c], label=c, width=0.8)
            bottom += tab[c].to_numpy()
        ax.set_xticks(range(12))
        ax.set_xticklabels(MONTHS, fontsize=8)
        ax.set_title(city)
        ax.set_ylabel("% of days lost")
        allc = cat.value_counts(normalize=True) * 100
        annual[city] = {c: float(allc.get(c, 0.0)) for c in CAUSES}
        S[f"cause_monthly_{city}"] = tab
    ymax = max(x.get_ylim()[1] for x in city_axes)
    for x in city_axes:
        x.set_ylim(0, ymax)
    ax = axes.flat[5]
    ann = pd.DataFrame(annual).T[CAUSES]
    mean_ann = ann.mean()
    ax.barh(CAUSES[::-1], [mean_ann[c] for c in CAUSES[::-1]], color=[CAUSE_COL[c] for c in CAUSES[::-1]])
    for i, c in enumerate(CAUSES[::-1]):
        ax.text(mean_ann[c] + 0.05, i, f"{mean_ann[c]:.1f}%", va="center")
    ax.set_title("Annual loss by cause (mean of 5 cities)")
    ax.set_xlabel("% of all days")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=CAUSE_COL[c]) for c in CAUSES], labels=CAUSES,
              loc="lower right", title="Cause of lost day")
    fig.suptitle(f"Why are days lost? Cause of unusable days by month (wind limit {a.ref_gust:g} m/s)",
                 fontweight="bold", fontsize=13)
    save(fig, outdir, "fig3_cause_by_month.png")
    ann.round(2).to_csv(outdir / "cause_annual_by_city.csv")
    S["cause_annual"] = ann


def fig4_cause_vs_limit(data, a, outdir, S):
    Ls = np.arange(6, 19, 1)
    res = {c: np.zeros((len(Ls), len(CAUSES))) for c in data}
    for city, cd in data.items():
        for i, L in enumerate(Ls):
            cat = decompose(cd, L, a.precip_max, a.min_window)
            vc = cat.value_counts(normalize=True) * 100
            res[city][i] = [float(vc.get(c, 0.0)) for c in CAUSES]
    mean = np.mean([res[c] for c in res], axis=0)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    ax1.stackplot(Ls, mean.T, labels=CAUSES, colors=[CAUSE_COL[c] for c in CAUSES], alpha=0.9)
    ax1.axvline(a.ref_gust, color="k", ls="--", lw=1)
    ax1.text(a.ref_gust + 0.15, ax1.get_ylim()[1] * 0.92, "reference limit", fontsize=8)
    ax1.set_xlabel("Wind limit (m/s)")
    ax1.set_ylabel("% of days lost (mean of 5 cities)")
    ax1.set_title("Which constraint removes days as the wind limit changes")
    ax1.legend(loc="upper right")
    for city in res:
        ax2.plot(Ls, res[city].sum(axis=1), color=CITY_COL.get(city), lw=2, label=city)
    ax2.axvline(a.ref_gust, color="k", ls="--", lw=1)
    ax2.set_xlabel("Wind limit (m/s)")
    ax2.set_ylabel("Total % of days lost")
    ax2.set_title("Total loss by city")
    ax2.legend()
    save(fig, outdir, "fig4_cause_vs_wind_limit.png")
    rows = []
    for city in res:
        for i, L in enumerate(Ls):
            rows.append([city, L] + list(res[city][i]))
    pd.DataFrame(rows, columns=["city", "wind_limit"] + CAUSES).round(2).to_csv(outdir / "cause_vs_wind_limit.csv", index=False)
    S["rain_floor"] = float(mean[-1, 0] + mean[-1, 2] + mean[-1, 3])


def fig5_interannual(data, a, outdir, S):
    rng = np.random.default_rng(42)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    annual_year = {}
    ci_rows = []
    city_axes = []
    for ax, (city, cd) in zip(axes.flat, data.items()):
        city_axes.append(ax)
        u, _, _ = usable(cd, a.ref_gust, a.precip_max, a.min_window)
        df = pd.DataFrame({"u": u * 100.0, "y": cd.days.year, "m": cd.days.month})
        pv = df.pivot_table(index="y", columns="m", values="u", aggfunc="mean").reindex(columns=range(1, 13))
        arr = pv.to_numpy()
        for row in arr:
            ax.plot(range(12), row, color="grey", alpha=0.35, lw=1)
        boots = np.array([arr[rng.integers(0, len(arr), len(arr))].mean(axis=0) for _ in range(a.boot)])
        lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
        mean = arr.mean(axis=0)
        ax.fill_between(range(12), lo, hi, color=CITY_COL.get(city), alpha=0.3, label="95% bootstrap interval of mean")
        ax.plot(range(12), mean, color=CITY_COL.get(city), lw=2.5, label="mean over years")
        ax.set_xticks(range(12))
        ax.set_xticklabels(MONTHS, fontsize=8)
        ax.set_title(f"{city}  (grey = individual years)")
        ax.set_ylabel("% usable days")
        annual_year[city] = df.groupby("y")["u"].mean()
        for m in range(12):
            ci_rows.append([city, MONTHS[m], mean[m], lo[m], hi[m], np.nanmin(arr[:, m]), np.nanmax(arr[:, m])])
    lo_all = min(x.get_ylim()[0] for x in city_axes)
    for x in city_axes:
        x.set_ylim(max(0, lo_all), 101)
    ax = axes.flat[5]
    ay = pd.DataFrame(annual_year).T
    im = ax.imshow(ay.to_numpy(), aspect="auto", cmap="RdYlGn", vmin=max(0, np.floor(ay.to_numpy().min() - 2)), vmax=100)
    ax.set_xticks(range(ay.shape[1]))
    ax.set_xticklabels(ay.columns, rotation=60, fontsize=8)
    ax.set_yticks(range(ay.shape[0]))
    ax.set_yticklabels(ay.index)
    annotate(ax, ay.to_numpy(), fmt="{:.0f}", fs=8)
    ax.grid(False)
    ax.set_title("Annual usable-day share by year, %")
    axes.flat[0].legend(loc="lower left", fontsize=8)
    fig.suptitle(f"Year-to-year spread and bootstrap 95% intervals (wind limit {a.ref_gust:g} m/s)",
                 fontweight="bold", fontsize=13)
    save(fig, outdir, "fig5_interannual_uncertainty.png")
    ci = pd.DataFrame(ci_rows, columns=["city", "month", "mean", "ci_low", "ci_high", "worst_year", "best_year"]).round(1)
    ci.to_csv(outdir / "monthly_bootstrap_intervals.csv", index=False)
    S["ci"] = ci
    S["annual_by_year"] = ay


def fig6_diurnal(raw, a, outdir, S):
    hours = np.arange(5, 20)
    maps, prof = [], {}
    for city, df in raw.items():
        ok = (df["wind_gusts_10m"] <= a.ref_gust) & (df["wind_speed_100m"] <= a.ref_gust) & (df["precipitation"] <= a.precip_max)
        t = ok.groupby([ok.index.month, ok.index.hour]).mean().unstack() * 100
        maps.append(t.reindex(index=range(1, 13), columns=hours).to_numpy())
        prof[city] = (ok.groupby(ok.index.hour).mean() * 100).reindex(hours)
    mean = np.mean(maps, axis=0)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.2), gridspec_kw={"width_ratios": [1.5, 1]}, constrained_layout=True)
    im = ax1.imshow(mean, aspect="auto", cmap="RdYlGn", vmin=50, vmax=100)
    ax1.set_xticks(range(len(hours)))
    ax1.set_xticklabels([f"{h}:00" for h in hours], rotation=60, fontsize=8)
    ax1.set_yticks(range(12))
    ax1.set_yticklabels(MONTHS)
    annotate(ax1, mean, fmt="{:.0f}", fs=7)
    ax1.grid(False)
    ax1.set_title("Share of hours that are flyable, % (mean of 5 cities)")
    fig.colorbar(im, ax=ax1, label="% of hours")
    for city, s in prof.items():
        ax2.plot(hours, s, color=CITY_COL.get(city), lw=2, label=city)
    ax2.axvspan(a.day_start, a.day_end, color="grey", alpha=0.1, label="operational hours")
    ax2.set_xlabel("Hour of day (local)")
    ax2.set_ylabel("% of hours flyable (all months)")
    ax2.set_title("Daily profile by city")
    ax2.legend(fontsize=8)
    fig.suptitle(f"Time of day: when is flying possible? (wind limit {a.ref_gust:g} m/s)", fontweight="bold", fontsize=13)
    save(fig, outdir, "fig6_time_of_day.png")
    pd.DataFrame(mean, index=MONTHS, columns=[f"{h}:00" for h in hours]).round(1).to_csv(outdir / "flyable_hour_share_month_by_hour.csv")
    S["diurnal_mean"] = mean
    S["hours"] = hours


def fig7_distributions(data, a, outdir, S):
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(17, 5), constrained_layout=True)
    for city, cd in data.items():
        for ax, arr, lab in ((ax1, cd.g.max(axis=1), "Daily maximum 10 m gust (m/s)"),
                             (ax2, cd.w.max(axis=1), "Daily maximum 100 m wind (m/s)")):
            x = np.sort(arr)
            ax.plot(x, np.arange(1, len(x) + 1) / len(x) * 100, color=CITY_COL.get(city), lw=2, label=city)
            ax.set_xlabel(lab)
        wet = pd.Series((cd.p > a.precip_max).any(axis=1) * 100.0, index=cd.days)
        ax3.plot(range(12), wet.groupby(wet.index.month).mean().reindex(range(1, 13)), color=CITY_COL.get(city), lw=2, marker="o", ms=3, label=city)
    for ax in (ax1, ax2):
        for L in (8, 10, 12):
            ax.axvline(L, color="k", ls=":", lw=1)
            ax.text(L + 0.1, 3, f"{L}", fontsize=8)
        ax.set_ylabel("% of days with maximum at or below x")
        ax.set_xlim(0, 30)
    ax1.set_title("Gust distribution (empirical CDF)")
    ax2.set_title("100 m wind distribution (empirical CDF)")
    ax1.legend(fontsize=8)
    ax3.set_xticks(range(12))
    ax3.set_xticklabels(MONTHS, fontsize=8)
    ax3.set_ylabel(f"% of days with at least one hour above {a.precip_max:g} mm")
    ax3.set_title("Days with rain in operational hours")
    fig.suptitle("What sits behind the limits: wind and rain distributions", fontweight="bold", fontsize=13)
    save(fig, outdir, "fig7_distributions.png")


def fig8_robustness(data, a, outdir, S):
    Ls = np.array([6, 8, 10, 12, 14, 16, 18])
    Ds = np.arange(1, 7)
    Ps = [0.0, 0.1, 0.5, 1.0, 2.0]
    gridD = np.zeros((len(Ds), len(Ls)))
    gridP = np.zeros((len(Ps), len(Ls)))
    rows = []
    for city, cd in data.items():
        for j, L in enumerate(Ls):
            for i, D in enumerate(Ds):
                v = usable(cd, L, a.precip_max, D)[0].mean() * 100
                gridD[i, j] += v / len(data)
                rows.append([city, L, D, a.precip_max, v])
            for i, P in enumerate(Ps):
                v = usable(cd, L, P, a.min_window)[0].mean() * 100
                gridP[i, j] += v / len(data)
                rows.append([city, L, a.min_window, P, v])
    pd.DataFrame(rows, columns=["city", "wind_limit", "min_window_h", "precip_limit_mm_h", "usable_day_pct"]).drop_duplicates().round(2).to_csv(outdir / "robustness_grid.csv", index=False)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.2), constrained_layout=True)
    for ax, grid, ylab, ylabels, title in (
        (ax1, gridD, "Required consecutive flyable hours", [f"{d} h" for d in Ds], "Sensitivity to the window length"),
        (ax2, gridP, "Precipitation limit (mm per hour)", [f"{p:g}" for p in Ps], "Sensitivity to the precipitation limit"),
    ):
        im = ax.imshow(grid, aspect="auto", cmap="RdYlGn", vmin=40, vmax=100, origin="lower")
        ax.set_xticks(range(len(Ls)))
        ax.set_xticklabels([f"{L} m/s" for L in Ls])
        ax.set_yticks(range(len(ylabels)))
        ax.set_yticklabels(ylabels)
        annotate(ax, grid, fmt="{:.0f}", fs=9)
        ax.grid(False)
        ax.set_xlabel("Wind limit")
        ax.set_ylabel(ylab)
        ax.set_title(title)
        fig.colorbar(im, ax=ax, label="% of days usable (mean of 5 cities)")
    fig.suptitle("Robustness: how much do the results depend on how a usable day is defined?", fontweight="bold", fontsize=13)
    save(fig, outdir, "fig8_robustness.png")
    S["robust_D"] = (Ls, Ds, gridD)
    S["robust_P"] = (Ls, Ps, gridP)


def spell_lengths(q):
    lens, run = [], 0
    for v in q:
        if v:
            run += 1
        elif run:
            lens.append(run)
            run = 0
    if run:
        lens.append(run)
    return np.array(lens)


def fig9_persistence(data, a, outdir, S):
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(17, 5), constrained_layout=True)
    names, base, cond = [], [], []
    ks = np.arange(1, 11)
    emp_all, geo_all = [], []
    maxlag = 14
    rows = []
    for city, cd in data.items():
        u, _, _ = usable(cd, a.ref_gust, a.precip_max, a.min_window)
        q = ~u
        pbar = q.mean()
        pcond = q[1:][q[:-1]].mean() if q[:-1].sum() else np.nan
        names.append(city)
        base.append(pbar * 100)
        cond.append(pcond * 100)
        lens = spell_lengths(q)
        emp = np.array([(lens >= k).mean() for k in ks])
        geo = pbar ** (ks - 1)
        emp_all.append(emp)
        geo_all.append(geo)
        ax2.plot(ks, np.where(emp > 0, emp, np.nan), color=CITY_COL.get(city), alpha=0.5, lw=1.2)
        x = u.astype(float) - u.mean()
        ac = np.array([(x[:-k] * x[k:]).sum() / (x * x).sum() for k in range(1, maxlag + 1)])
        ax3.plot(range(1, maxlag + 1), ac, color=CITY_COL.get(city), marker="o", ms=3, lw=1.5, label=city)
        rows.append([city, pbar * 100, pcond * 100, lens.mean(), lens.max(), (lens >= 3).mean() * 100])
    xpos = np.arange(len(names))
    ax1.bar(xpos - 0.2, base, 0.4, color="#9aa5b1", label="P(day unusable)")
    ax1.bar(xpos + 0.2, cond, 0.4, color="#c0392b", label="P(unusable | yesterday unusable)")
    for x, b, c in zip(xpos, base, cond):
        ax1.text(x - 0.2, b + 0.4, f"{b:.1f}", ha="center", fontsize=8)
        ax1.text(x + 0.2, c + 0.4, f"{c:.1f}", ha="center", fontsize=8)
    ax1.set_xticks(xpos)
    ax1.set_xticklabels(names)
    ax1.set_ylabel("%")
    ax1.set_ylim(0, max(max(base), max(cond)) * 1.3)
    ax1.set_title("Bad days follow bad days")
    ax1.legend(fontsize=8)
    emp_mean = np.mean(emp_all, axis=0)
    ax2.plot(ks, np.where(emp_mean > 0, emp_mean, np.nan), color="k", lw=2.5, marker="o", label="observed (mean of cities)")
    ax2.plot(ks, np.mean(geo_all, axis=0), color="k", lw=2, ls="--", label="if days were independent")
    ax2.set_yscale("log")
    ax2.set_ylim(1e-4, 1.5)
    ax2.set_xlabel("Spell length k (consecutive unusable days)")
    ax2.set_ylabel("P(spell lasts at least k days)")
    ax2.set_title("Spells of unusable days")
    ax2.legend(fontsize=8)
    band = 1.96 / np.sqrt(len(next(iter(data.values())).days))
    ax3.axhspan(-band, band, color="grey", alpha=0.2, label="95% band if independent")
    ax3.axhline(0, color="k", lw=0.8)
    ax3.set_xlabel("Lag (days)")
    ax3.set_ylabel("Autocorrelation of daily usable flag")
    ax3.set_title("Autocorrelation")
    ax3.legend(fontsize=8)
    fig.suptitle(f"Do bad-weather days cluster? (wind limit {a.ref_gust:g} m/s)", fontweight="bold", fontsize=13)
    save(fig, outdir, "fig9_persistence.png")
    tab = pd.DataFrame(rows, columns=["city", "P_unusable_pct", "P_unusable_given_yesterday_unusable_pct",
                                      "mean_spell_days", "longest_spell_days", "share_of_spells_ge3_days_pct"]).round(2)
    tab.to_csv(outdir / "persistence_summary.csv", index=False)
    S["persist"] = tab


def campaign_extra(u, K):
    cs = np.cumsum(u.astype(int))
    n = len(u)
    starts = np.arange(n)
    base = np.where(starts > 0, cs[np.maximum(starts - 1, 0)], 0)
    j = np.searchsorted(cs, base + K, side="left")
    ok = j < n
    return starts[ok], (j[ok] - starts[ok] + 1) - K


def fig10_campaign(data, a, outdir, S):
    K = a.campaign_days
    by_month = {m: [] for m in range(1, 13)}
    rows = []
    emp_city, frm_city, p90_city = [], [], []
    for city, cd in data.items():
        u, _, _ = usable(cd, a.ref_gust, a.precip_max, a.min_window)
        st, ex = campaign_extra(u, K)
        months = cd.days.month[st]
        for m in range(1, 13):
            by_month[m].extend(ex[months == m])
        p = u.mean()
        emp_city.append(ex.mean())
        frm_city.append(K * (1 / p - 1))
        p90_city.append(np.percentile(ex, 90))
        for grp, mask in (("All start dates", np.ones(len(ex), bool)),
                          ("Start in Jun-Jul", np.isin(months, [6, 7])),
                          ("Start in Nov-Dec", np.isin(months, [11, 12]))):
            for k2 in (3, 5, 10, 15, 20):
                st2, ex2 = campaign_extra(u, k2)
                m2 = cd.days.month[st2]
                sel = {"All start dates": np.ones(len(ex2), bool), "Start in Jun-Jul": np.isin(m2, [6, 7]),
                       "Start in Nov-Dec": np.isin(m2, [11, 12])}[grp]
                rows.append([city, k2, grp, ex2[sel].mean(), np.percentile(ex2[sel], 50), np.percentile(ex2[sel], 90)])
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 5.4), constrained_layout=True,
                                        gridspec_kw={"width_ratios": [1.5, 1, 1]})
    bp = ax1.boxplot([by_month[m] for m in range(1, 13)], positions=range(12), widths=0.6, showfliers=False, patch_artist=True)
    for b in bp["boxes"]:
        b.set(facecolor="#cfe0f3", edgecolor="#2f5496")
    for med in bp["medians"]:
        med.set(color="#c0392b", lw=2)
    ax1.plot(range(12), [np.mean(by_month[m]) for m in range(1, 13)], "kD", ms=4, label="mean")
    ax1.set_xticks(range(12))
    ax1.set_xticklabels(MONTHS)
    ax1.set_ylabel(f"Extra calendar days beyond {K}")
    ax1.set_title(f"Extra days to finish a {K}-usable-day campaign, by start month")
    ax1.legend(fontsize=8)
    xp = np.arange(len(data))
    ax2.bar(xp - 0.27, emp_city, 0.27, label="empirical mean", color="#2f5496")
    ax2.bar(xp, frm_city, 0.27, label="independence formula", color="#9aa5b1")
    ax2.bar(xp + 0.27, p90_city, 0.27, label="empirical 90th percentile", color="#c0392b")
    ax2.set_xticks(xp)
    ax2.set_xticklabels(list(data.keys()), rotation=30)
    ax2.set_ylim(0, max(max(emp_city), max(frm_city), max(p90_city)) * 1.4)
    ax2.set_title("Empirical vs formula (all start dates)")
    ax2.legend(fontsize=8)
    sm = pd.DataFrame(rows, columns=["city", "K", "group", "mean", "p50", "p90"])
    for grp, col in (("Start in Jun-Jul", "#c0392b"), ("All start dates", "#2f5496"), ("Start in Nov-Dec", "#2ca02c")):
        g = sm[sm.group == grp].groupby("K")["mean"].mean()
        ax3.plot(g.index, g.values, marker="o", lw=2, color=col, label=grp)
    ax3.set_xlabel("Campaign length K (usable days needed)")
    ax3.set_ylabel("Mean extra calendar days")
    ax3.set_title("Delay grows with campaign length")
    ax3.legend(fontsize=8)
    fig.suptitle(f"Empirical campaign delay from every historical start date (wind limit {a.ref_gust:g} m/s)", fontweight="bold", fontsize=13)
    save(fig, outdir, "fig10_campaign_delay.png")
    sm.round(2).to_csv(outdir / "campaign_delay_summary.csv", index=False)
    S["campaign"] = dict(K=K, emp=dict(zip(data.keys(), emp_city)), frm=dict(zip(data.keys(), frm_city)),
                         p90=dict(zip(data.keys(), p90_city)), sm=sm)


# ---------------------------------------------------------------------------
# Summary text (all numbers computed from your data)
# ---------------------------------------------------------------------------
def write_summary(a, outdir, S, ncities, ndays):
    L = []
    L.append("# Extra analyses: computed summary and caption drafts\n")
    L.append(f"Reference wind limit {a.ref_gust:g} m/s; precipitation limit {a.precip_max:g} mm/h; usable day = at least "
             f"{a.min_window} consecutive flyable hours between {a.day_start}:00 and {a.day_end}:00. "
             f"{ncities} cities, about {ndays} days each.\n")
    L.append("## Where each figure goes in the paper\n")
    L.append("| Figure | File | Put it in | Why |\n|---|---|---|---|")
    L.append("| 3 | fig3_cause_by_month.png | Section 4.2, after the rainy-season finding | Tests the rain-versus-wind inference; update that finding to match |")
    L.append("| 4 | fig4_cause_vs_wind_limit.png | Section 4.2, after Figure 2 (or Appendix C) | Shows which constraint binds at each wind limit |")
    L.append("| 5 | fig5_interannual_uncertainty.png | Section 4.2, after Table 1 | Shows uncertainty on Table 1 |")
    L.append("| 6 | fig6_time_of_day.png | Appendix C | Operational-window justification |")
    L.append("| 7 | fig7_distributions.png | Appendix C | Distributions behind the limits |")
    L.append("| 8 | fig8_robustness.png | Section 4.4 (risks) | Evidence that the definition of a usable day is not driving the result |")
    L.append("| 9 | fig9_persistence.png | Section 5.2, before Table 4 | Tests the independence assumption used in Table 4 |")
    L.append("| 10 | fig10_campaign_delay.png | Section 5.2, after Table 4 | Empirical delay; replace or confirm the formula-based numbers |\n")

    if "cause_annual" in S:
        ann = S["cause_annual"]
        m = ann.mean()
        tot = m.sum()
        L.append("## Cause of lost days (Figure 3)\n")
        L.append(f"Averaged over the five cities, {tot:.1f}% of days are unusable at {a.ref_gust:g} m/s. Of all days: rain only "
                 f"{m['Rain']:.1f}%, wind only {m['Wind']:.1f}%, both {m['Both']:.1f}%, timing mismatch "
                 f"{m['Timing mismatch']:.1f}%. Rain-only losses are {100 * m['Rain'] / tot:.0f}% of all lost days.\n")
        L.append("```\n" + ann.round(2).to_string() + "\n```")
        L.append("")
    if "ci" in S:
        ci = S["ci"]
        jul = ci[ci.month == "Jul"]
        L.append("## Uncertainty (Figure 5)\n")
        L.append("July usable-day share, mean over years with bootstrap 95% interval and worst/best single year:\n")
        for _, r in jul.iterrows():
            L.append(f"- {r['city']}: {r['mean']:.1f}% (interval {r['ci_low']:.1f} to {r['ci_high']:.1f}; worst year {r['worst_year']:.1f}, best year {r['best_year']:.1f})")
        L.append("")
    if "persist" in S:
        p = S["persist"]
        L.append("## Clustering of bad days (Figure 9)\n")
        L.append(f"Mean probability that a day is unusable: {p['P_unusable_pct'].mean():.1f}%. Given that yesterday was unusable: "
                 f"{p['P_unusable_given_yesterday_unusable_pct'].mean():.1f}%. Mean spell length {p['mean_spell_days'].mean():.2f} days; "
                 f"longest spell {int(p['longest_spell_days'].max())} days.\n")
        L.append("```\n" + p.to_string(index=False) + "\n```")
        L.append("")
    if "campaign" in S:
        c = S["campaign"]
        L.append(f"## Campaign delay (Figure 10), K = {c['K']} usable days\n")
        for city in c["emp"]:
            L.append(f"- {city}: empirical mean {c['emp'][city]:.1f} extra days, independence formula {c['frm'][city]:.1f}, 90th percentile {c['p90'][city]:.1f}")
        sm = c["sm"]
        jj = sm[(sm.K == c["K"]) & (sm.group == "Start in Jun-Jul")]["mean"]
        nd = sm[(sm.K == c["K"]) & (sm.group == "Start in Nov-Dec")]["mean"]
        L.append(f"\nStarting in June-July the mean extra delay is {jj.min():.1f} to {jj.max():.1f} days across cities; starting in November-December it is {nd.min():.1f} to {nd.max():.1f} days.\n")
    if "robust_D" in S:
        Ls, Ds, g = S["robust_D"]
        j12 = int(np.argmin(np.abs(Ls - a.ref_gust)))
        L.append("## Robustness (Figure 8)\n")
        L.append(f"At {Ls[j12]} m/s the mean usable-day share ranges from {g[:, j12].min():.1f}% (longest window tested, {Ds[int(np.argmin(g[:, j12]))]} h) "
                 f"to {g[:, j12].max():.1f}% (shortest, {Ds[int(np.argmax(g[:, j12]))]} h).\n")

    L.append("## Caption drafts (edit the sentences to match what you see)\n")
    L.append(f"- **Figure 3.** Cause of unusable days by city and month at a {a.ref_gust:g} m/s wind limit. A day is attributed to rain if it would have been usable under the wind rule alone, to wind if it would have been usable under the rain rule alone, to both if neither rule alone gives a usable window, and to timing mismatch if each rule alone is satisfied but not within the same consecutive hours.")
    L.append("- **Figure 4.** Share of days lost, by cause, as the wind limit is varied (left) and total loss by city (right).")
    L.append("- **Figure 5.** Monthly usable-day share for each year (grey), the mean over years (line) and a bootstrap 95% interval obtained by resampling years (band). The lower right panel shows the annual share by year.")
    L.append("- **Figure 6.** Share of hours that are flyable by month and hour of day (mean of five cities) and the daily profile by city.")
    L.append("- **Figure 7.** Empirical distributions of the daily maximum gust and 100 m wind during operational hours, and the share of days with rain in operational hours by month.")
    L.append("- **Figure 8.** Sensitivity of the usable-day share to the required window length (left) and to the precipitation limit (right).")
    L.append("- **Figure 9.** Persistence of unusable days: probability of an unusable day, with and without an unusable day before it (left); distribution of spell lengths compared with independent days (centre); autocorrelation of the daily usable flag (right).")
    L.append(f"- **Figure 10.** Extra calendar days needed to complete a {a.campaign_days}-usable-day campaign, computed from every historical start date, by start month (left), compared with the independence formula (centre), and as a function of campaign length (right).")
    (outdir / "extra_summary.md").write_text("\n".join(L), encoding="utf-8")
    print("  saved extra_summary.md")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Extra analyses and figures for the FlightWindow proposal")
    ap.add_argument("--cache", default="output/cache", help="folder with <City>_<Year>.csv files from flyable_hours.py")
    ap.add_argument("--outdir", default="extra_output")
    ap.add_argument("--years", nargs=2, type=int, default=[2015, 2025])
    ap.add_argument("--ref-gust", type=float, default=12)
    ap.add_argument("--precip-max", type=float, default=0.1)
    ap.add_argument("--min-window", type=int, default=3)
    ap.add_argument("--day-start", type=int, default=7)
    ap.add_argument("--day-end", type=int, default=17)
    ap.add_argument("--campaign-days", type=int, default=10)
    ap.add_argument("--boot", type=int, default=1000, help="bootstrap repetitions")
    a = ap.parse_args()

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    raw = load_cache(a.cache, *a.years)
    print(f"Loaded cities: {', '.join(raw)}")
    data = {c: CityData(df, a.day_start, a.day_end) for c, df in raw.items()}
    ndays = int(np.mean([len(cd.days) for cd in data.values()]))
    print(f"About {ndays} complete days per city")

    S = {}
    steps = [
        ("Figure 3", lambda: fig3_cause_by_month(data, a, outdir, S)),
        ("Figure 4", lambda: fig4_cause_vs_limit(data, a, outdir, S)),
        ("Figure 5", lambda: fig5_interannual(data, a, outdir, S)),
        ("Figure 6", lambda: fig6_diurnal(raw, a, outdir, S)),
        ("Figure 7", lambda: fig7_distributions(data, a, outdir, S)),
        ("Figure 8", lambda: fig8_robustness(data, a, outdir, S)),
        ("Figure 9", lambda: fig9_persistence(data, a, outdir, S)),
        ("Figure 10", lambda: fig10_campaign(data, a, outdir, S)),
    ]
    for name, fn in steps:
        print(f"{name} ...")
        try:
            fn()
        except Exception:
            print(f"  {name} FAILED, continuing:")
            traceback.print_exc()
    write_summary(a, outdir, S, len(data), ndays)
    print(f"\nDone. Everything is in: {outdir.resolve()}")


if __name__ == "__main__":
    main()
