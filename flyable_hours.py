#!/usr/bin/env python3
"""
flyable_hours.py  -  Step 1 of FlightWindow

Question answered: how often are Jiangsu low-altitude sites actually flyable?

What it does
  1. Downloads hourly historical weather (ERA5-based, via the free Open-Meteo
     archive API) for five Jiangsu cities: 10 m gusts, 100 m wind, precipitation.
  2. Labels each hour flyable / not flyable for a sweep of wind limits.
  3. Counts a DAY as usable if it has at least MIN_WINDOW consecutive flyable
     hours inside the operational hours (default 07:00-17:00 local).
  4. Writes Table 1 (usable-day share by city and month), Table 2 (sensitivity
     to the wind limit), two figures, and a short summary with the loss rate w
     for Section 5.2 of the manuscript.

Usage
  python flyable_hours.py                 # real data, 2015-2025, output in ./output
  python flyable_hours.py --years 2018 2025 --ref-gust 10
  python flyable_hours.py --demo          # SYNTHETIC data, only to test the pipeline

IMPORTANT
  * City-centre coordinates are placeholders. Replace them with your real test
    sites using --sites-json (see SITES_HELP below).
  * The wind limits are a SWEEP, not regulations. Pick the reference limit from
    a real aircraft datasheet or rule and cite it in the manuscript.
  * ERA5 has a ~25 km grid. It does not capture street-level wind. State this
    limitation in the manuscript (it is already in Section 4.1).
  * Never put --demo output in the manuscript. It is random data.

If the download fails (network blocks, rate limits), see MANUAL FALLBACK at the
bottom of this file.

Requires: python 3.9+, numpy, pandas, matplotlib. No other packages.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Sites: (latitude, longitude). The five cities named in Jiangsu's low-altitude
# plans. Coordinates are approximate city locations - replace with real sites.
# ---------------------------------------------------------------------------
SITES = {
    "Nanjing": (32.06, 118.63),   # approx. Pukou area
    "Suzhou": (31.30, 120.62),
    "Wuxi": (31.49, 120.31),
    "Yangzhou": (32.39, 119.42),
    "Changzhou": (31.81, 119.97),
}
SITES_HELP = 'JSON file like {"Pukou test zone": [32.06, 118.63], "Jinji Lake": [31.31, 120.72]}'

API = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARS = ["wind_gusts_10m", "wind_speed_100m", "precipitation"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------------------------------------------------------------------------
# Data acquisition
# ---------------------------------------------------------------------------
def fetch_year(name, lat, lon, year, cache_dir, retries=5):
    """Download one city-year of hourly data (cached as CSV)."""
    cache = cache_dir / f"{name.replace(' ', '_')}_{year}.csv"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["time"])

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "Asia/Shanghai",
    }
    url = API + "?" + urllib.parse.urlencode(params)

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FlightWindow-student-project"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            h = payload["hourly"]
            df = pd.DataFrame({"time": pd.to_datetime(h["time"])})
            for v in HOURLY_VARS:
                df[v] = h[v]
            df.to_csv(cache, index=False)
            return df
        except urllib.error.HTTPError as e:
            last_err = e
            wait = 10 * attempt if e.code == 429 else 3 * attempt
            print(f"  {name} {year}: HTTP {e.code}, retry {attempt}/{retries} in {wait}s", file=sys.stderr)
            time.sleep(wait)
        except Exception as e:  # network errors, bad JSON, etc.
            last_err = e
            print(f"  {name} {year}: {e!r}, retry {attempt}/{retries}", file=sys.stderr)
            time.sleep(3 * attempt)
    raise RuntimeError(
        f"Could not download {name} {year}: {last_err!r}\n"
        "See MANUAL FALLBACK at the bottom of flyable_hours.py."
    )


def load_real(sites, y0, y1, cache_dir):
    out = {}
    for name, (lat, lon) in sites.items():
        parts = []
        for year in range(y0, y1 + 1):
            print(f"Downloading {name} {year} ...")
            parts.append(fetch_year(name, lat, lon, year, cache_dir))
            time.sleep(0.5)  # be polite to the free API
        df = pd.concat(parts).set_index("time").sort_index()
        out[name] = df
    return out


def load_demo(sites, y0, y1):
    """Synthetic weather, ONLY to test that the pipeline runs. Not real."""
    out = {}
    times = pd.date_range(f"{y0}-01-01", f"{y1}-12-31 23:00", freq="h")
    n_days = len(times) // 24
    for name in sites:
        rng = np.random.default_rng(zlib.crc32(name.encode()) % (2**32))
        doy = times.dayofyear.to_numpy()
        seasonal = 1 + 0.25 * np.cos(2 * np.pi * (doy - 80) / 365)
        regime = np.repeat(rng.lognormal(0, 0.45, n_days), 24)[: len(times)]
        diurnal = 1 + 0.15 * np.sin(2 * np.pi * (times.hour.to_numpy() - 9) / 24)
        w100 = 5.0 * seasonal * regime * diurnal + rng.normal(0, 0.6, len(times))
        w100 = np.clip(w100, 0, None)
        gust = w100 * 0.8 * (1.2 + 0.3 * rng.random(len(times)))
        rainy_day = np.repeat(rng.random(n_days) < 0.28, 24)[: len(times)]
        rain_hour = rng.random(len(times)) < 0.4
        precip = np.where(rainy_day & rain_hour, rng.exponential(0.8, len(times)), 0.0)
        out[name] = pd.DataFrame(
            {"wind_gusts_10m": gust, "wind_speed_100m": w100, "precipitation": precip},
            index=times,
        )
    return out


# ---------------------------------------------------------------------------
# Flyability logic
# ---------------------------------------------------------------------------
def daily_usable(df, wind_limit, precip_limit, min_window, h0, h1, use_100m=True):
    """
    Returns (usable, flyable_share):
      usable        bool Series per day: >= min_window consecutive flyable hours
                    inside operational hours [h0, h1)
      flyable_share float Series per day: share of operational hours flyable
    An hour is flyable if 10 m gust <= wind_limit, precipitation <= precip_limit
    and (optionally) 100 m sustained wind <= wind_limit.
    """
    ok = (df["wind_gusts_10m"] <= wind_limit) & (df["precipitation"] <= precip_limit)
    if use_100m:
        ok = ok & (df["wind_speed_100m"] <= wind_limit)
    ok = ok & df[["wind_gusts_10m", "precipitation", "wind_speed_100m"]].notna().all(axis=1)

    op = ok[(ok.index.hour >= h0) & (ok.index.hour < h1)]
    table = op.groupby([op.index.normalize(), op.index.hour]).first().unstack()
    table = table.dropna()  # keep complete days only
    arr = table.to_numpy().astype(int)

    run = np.zeros(len(arr), dtype=int)
    best = np.zeros(len(arr), dtype=int)
    for k in range(arr.shape[1]):
        run = (run + 1) * arr[:, k]
        best = np.maximum(best, run)

    usable = pd.Series(best >= min_window, index=table.index)
    flyable_share = pd.Series(arr.mean(axis=1), index=table.index)
    return usable, flyable_share


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def to_markdown(df, floatfmt="{:.1f}"):
    cols = [str(df.index.name or "")] + [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for idx, row in df.iterrows():
        cells = [str(idx)] + [floatfmt.format(v) if isinstance(v, (float, np.floating)) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def make_figures(monthly_ref, sens_days, ref, outdir, demo):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tag = "SYNTHETIC DEMO - NOT REAL DATA\n" if demo else ""

    fig, ax = plt.subplots(figsize=(10, 3.8))
    im = ax.imshow(monthly_ref.to_numpy(), aspect="auto", vmin=0, vmax=100, cmap="RdYlGn")
    ax.set_xticks(range(12))
    ax.set_xticklabels(MONTHS)
    ax.set_yticks(range(len(monthly_ref)))
    ax.set_yticklabels(monthly_ref.index)
    for i in range(monthly_ref.shape[0]):
        for j in range(monthly_ref.shape[1]):
            ax.text(j, i, f"{monthly_ref.iat[i, j]:.0f}", ha="center", va="center", fontsize=8)
    ax.set_title(f"{tag}Share of days with a usable flight window (wind limit {ref} m/s), %")
    fig.colorbar(im, ax=ax, label="% of days")
    fig.tight_layout()
    fig.savefig(outdir / "fig1_heatmap.png", dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.2))
    for city in sens_days.index:
        ax.plot(sens_days.columns, sens_days.loc[city], marker="o", label=city)
    ax.set_xlabel("Wind limit applied to gusts and 100 m wind (m/s)")
    ax.set_ylabel("Annual share of usable days (%)")
    ax.set_title(f"{tag}Sensitivity of usable days to the wind limit")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "fig2_sensitivity.png", dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="FlightWindow step 1: flyable-window climatology for Jiangsu sites")
    ap.add_argument("--years", nargs=2, type=int, default=[2015, 2025], metavar=("START", "END"))
    ap.add_argument("--gusts", nargs="+", type=float, default=[8, 10, 12, 14, 16], help="wind limits to sweep (m/s)")
    ap.add_argument("--ref-gust", type=float, default=12, help="reference limit for Table 1 / Figure 1 (m/s)")
    ap.add_argument("--precip-max", type=float, default=0.1, help="max precipitation per hour still flyable (mm)")
    ap.add_argument("--min-window", type=int, default=3, help="consecutive flyable hours needed for a usable day")
    ap.add_argument("--day-start", type=int, default=7, help="first operational hour (local)")
    ap.add_argument("--day-end", type=int, default=17, help="end of operational hours (local, exclusive)")
    ap.add_argument("--no-100m", action="store_true", help="ignore 100 m wind, use gusts only")
    ap.add_argument("--sites-json", type=str, help=f"override sites. {SITES_HELP}")
    ap.add_argument("--outdir", type=str, default=None)
    ap.add_argument("--demo", action="store_true", help="use SYNTHETIC data to test the pipeline")
    
    # Fix for running in Jupyter/Colab notebooks: pass an empty list instead of sys.argv
    args = ap.parse_args([])

    sites = SITES
    if args.sites_json:
        with open(args.sites_json, encoding="utf-8") as f:
            sites = {k: tuple(v) for k, v in json.load(f).items()}

    gusts = sorted(set(args.gusts) | {args.ref_gust})
    outdir = Path(args.outdir or ("demo_output" if args.demo else "output"))
    outdir.mkdir(parents=True, exist_ok=True)
    cache_dir = outdir / "cache"
    cache_dir.mkdir(exist_ok=True)

    y0, y1 = args.years
    if args.demo:
        print("*** DEMO MODE: synthetic data. Do NOT use these numbers in the manuscript. ***")
        data = load_demo(sites, y0, y1)
    else:
        data = load_real(sites, y0, y1, cache_dir)

    ref = args.ref_gust
    ref_label = f"{ref:g}"
    monthly_ref = {}
    sens_days = {}
    sens_hours = {}
    loss_rate = {}
    n_days = {}

    for city, df in data.items():
        sens_days[city] = {}
        sens_hours[city] = {}
        for g in gusts:
            usable, share = daily_usable(
                df, g, args.precip_max, args.min_window, args.day_start, args.day_end, use_100m=not args.no_100m
            )
            sens_days[city][g] = 100 * usable.mean()
            sens_hours[city][g] = 100 * share.mean()
            if g == ref:
                monthly_ref[city] = (100 * usable.groupby(usable.index.month).mean()).reindex(range(1, 13))
                loss_rate[city] = 100 - 100 * usable.mean()
                n_days[city] = len(usable)

    t1 = pd.DataFrame(monthly_ref).T
    t1.columns = MONTHS
    t1.index.name = "City"
    t2 = pd.DataFrame(sens_days).T
    t2.columns = [f"{c:g} m/s" for c in t2.columns]
    t2.index.name = "City"
    t3 = pd.DataFrame(sens_hours).T
    t3.columns = [f"{c:g} m/s" for c in t3.columns]
    t3.index.name = "City"

    t1.round(1).to_csv(outdir / "table1_usable_day_share_by_month.csv")
    t2.round(1).to_csv(outdir / "table2_usable_day_share_sensitivity.csv")
    t3.round(1).to_csv(outdir / "table3_flyable_hour_share_sensitivity.csv")

    worst = t1.idxmin(axis=1)
    worst_val = t1.min(axis=1)
    best = t1.idxmax(axis=1)
    best_val = t1.max(axis=1)

    lines = []
    lines.append(f"FlightWindow step 1 summary ({'SYNTHETIC DEMO' if args.demo else 'real data'})")
    lines.append(f"Years {y0}-{y1}; operational hours {args.day_start}:00-{args.day_end}:00; "
                 f"usable day = >= {args.min_window} consecutive flyable hours")
    lines.append(f"Flyable hour = gust <= limit, precipitation <= {args.precip_max} mm/h"
                 + ("" if args.no_100m else ", 100 m wind <= limit"))
    lines.append(f"Reference wind limit: {ref_label} m/s (sweep: {', '.join(f'{g:g}' for g in gusts)})")
    lines.append("")
    lines.append(f"Table 1. Share of days with a usable window by month, % (limit {ref_label} m/s)")
    lines.append(to_markdown(t1.round(1)))
    lines.append("")
    lines.append("Table 2. Annual share of usable days by wind limit, %")
    lines.append(to_markdown(t2.round(1)))
    lines.append("")
    lines.append("Table 3. Annual share of operational hours that are flyable, %")
    lines.append(to_markdown(t3.round(1)))
    lines.append("")
    lines.append(f"Key numbers at {ref_label} m/s (for the executive summary and Section 4.2)")
    for city in t1.index:
        lines.append(
            f"- {city}: {100 - loss_rate[city]:.1f}% of days usable overall "
            f"(best {best[city]} {best_val[city]:.0f}%, worst {worst[city]} {worst_val[city]:.0f}%), "
            f"{n_days[city]} days analysed"
        )
    lines.append("")
    lines.append("Loss rate w for Section 5.2 (share of days that are NOT usable, i.e. the climatological")
    lines.append("weather loss for a weather-blind booking, before accounting for forecast skill):")
    for city in t1.index:
        lines.append(f"- {city}: w = {loss_rate[city]:.1f}%")
    lines.append("")
    lines.append("Reminder: w here is the CLIMATOLOGICAL baseline, i.e. the loss rate of weather-blind booking.")
    lines.append("A planner that uses forecasts aims to push the real loss below this; how far depends on")
    lines.append("forecast skill at the booking lead time, which is measured in the forecaster step.")
    summary = "\n".join(lines)
    (outdir / "summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)

    make_figures(t1, t2.set_axis([float(c.split()[0]) for c in t2.columns], axis=1), ref_label, outdir, args.demo)
    print(f"\nSaved tables, summary.md, fig1_heatmap.png and fig2_sensitivity.png in: {outdir.resolve()}")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# MANUAL FALLBACK (if the Open-Meteo download is blocked or rate-limited)
#   1. Get hourly ERA5 for your point from any source you can reach
#      (Copernicus CDS ERA5 hourly single levels: 10m wind gust since previous
#      post-processing, 100m u/v wind components, total precipitation).
#   2. Save one CSV per city-year in <outdir>/cache/ named
#         <City>_<Year>.csv      e.g. Nanjing_2019.csv
#      with columns: time, wind_gusts_10m (m/s), wind_speed_100m (m/s),
#      precipitation (mm per hour). time must be local time (UTC+8).
#   3. Run the script again. It reads the cache instead of downloading.
#   Note: wind_speed_100m = sqrt(u100^2 + v100^2). If you only have gusts, run
#   with --no-100m and say so in the manuscript.
# ---------------------------------------------------------------------------
