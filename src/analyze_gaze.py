import numpy as np
import pandas as pd

import gaze_heatmap as gh

NONE = "none"
FIX_COLUMNS = ["fix_id", "start_s", "end_s", "duration_s", "u", "v", "n_samples"]


def load_csv(path):
    df = gh.read_raw(path)
    df = df[list(gh.REQUIRED)].copy()
    return df.sort_values("time_s", kind="stable").reset_index(drop=True)


def _on_panel_mask(series):
    return series.astype(str).str.strip().str.lower().isin(["1", "1.0", "true"])


def filter_samples(raw, min_conf):
    """Drop invalid samples. Each dropped sample is counted once, in this order:
    NaN (time/x/y missing) -> low confidence -> off panel."""
    total = len(raw)
    has_xy = raw[["time_s", "x", "y"]].notna().all(axis=1)
    df = raw[has_xy]
    dropped_nan = total - len(df)

    conf_ok = df["confidence"] >= min_conf  # NaN confidence counts as low
    dropped_low_conf = int((~conf_ok).sum())
    df = df[conf_ok]

    on_panel = _on_panel_mask(df["on_panel"])
    dropped_off_panel = int((~on_panel).sum())
    df = df[on_panel]

    valid = df.sort_values("time_s", kind="stable").reset_index(drop=True)
    qc = {
        "samples_total": int(total),
        "samples_valid": int(len(valid)),
        "valid_ratio": (len(valid) / total) if total else 0.0,
        "dropped_nan": int(dropped_nan),
        "dropped_low_conf": dropped_low_conf,
        "dropped_off_panel": dropped_off_panel,
    }
    return valid, qc


def normalize_xy(valid, panel):
    """Add u, v: gaze position relative to the panel bounds (0..1)."""
    out = valid.copy()
    x_min, x_max = panel.get("x_min", 0.0), panel.get("x_max", 1.0)
    y_min, y_max = panel.get("y_min", 0.0), panel.get("y_max", 1.0)
    w = (x_max - x_min) or 1.0
    h = (y_max - y_min) or 1.0
    out["u"] = (out["x"] - x_min) / w
    out["v"] = (out["y"] - y_min) / h
    return out


def detect_fixations(valid, min_dur, max_disp, max_gap):
    if valid.empty:
        return pd.DataFrame(columns=FIX_COLUMNS)

    t = valid["t"].to_numpy(float)
    u = valid["u"].to_numpy(float)
    v = valid["v"].to_numpy(float)
    n = len(t)
    rows = []
    i = 0
    while i < n:
        j = i
        while j + 1 < n and t[j] - t[i] < min_dur and t[j + 1] - t[j] <= max_gap:
            j += 1
        if t[j] - t[i] < min_dur:
            i += 1
            continue

        uw, vw = u[i:j + 1], v[i:j + 1]
        u_lo, u_hi, v_lo, v_hi = uw.min(), uw.max(), vw.min(), vw.max()
        if (u_hi - u_lo) + (v_hi - v_lo) > max_disp:
            i += 1
            continue

        while j + 1 < n and t[j + 1] - t[j] <= max_gap:
            nu_lo, nu_hi = min(u_lo, u[j + 1]), max(u_hi, u[j + 1])
            nv_lo, nv_hi = min(v_lo, v[j + 1]), max(v_hi, v[j + 1])
            if (nu_hi - nu_lo) + (nv_hi - nv_lo) > max_disp:
                break
            u_lo, u_hi, v_lo, v_hi = nu_lo, nu_hi, nv_lo, nv_hi
            j += 1

        rows.append({
            "fix_id": len(rows) + 1,
            "start_s": t[i],
            "end_s": t[j],
            "duration_s": t[j] - t[i],
            "u": float(u[i:j + 1].mean()),
            "v": float(v[i:j + 1].mean()),
            "n_samples": j - i + 1,
        })
        i = j + 1

    return pd.DataFrame(rows, columns=FIX_COLUMNS)


def _rect(a):
    if "x_min" in a:
        return a["x_min"], a["y_min"], a["x_max"], a["y_max"]
    return a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]


def _in_polygon(x, y, poly):
    inside = False
    n = len(poly)
    for k in range(n):
        x1, y1 = poly[k]
        x2, y2 = poly[(k + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def assign_aoi(u, v, aois):
    for a in aois:
        if "polygon" in a:
            if _in_polygon(u, v, a["polygon"]):
                return a["name"]
        else:
            x0, y0, x1, y1 = _rect(a)
            if x0 <= u <= x1 and y0 <= v <= y1:
                return a["name"]
    return NONE


def aoi_metrics(fx, aois, t0=0.0):
    if "aoi" not in fx.columns:
        fx = fx.assign(aoi=[])
    total = float(fx["duration_s"].sum()) if len(fx) else 0.0
    rows = []
    for a in aois:
        name = a["name"]
        sub = fx[fx["aoi"] == name]
        dwell = float(sub["duration_s"].sum()) if len(sub) else 0.0
        rows.append({
            "aoi": name,
            "n_fixations": int(len(sub)),
            "dwell_time_s": dwell,
            "mean_fix_dur_s": float(sub["duration_s"].mean()) if len(sub) else np.nan,
            "time_to_first_fix_s": float(sub["start_s"].min()) if len(sub) else np.nan,
            "dwell_pct": 100.0 * dwell / total if total > 0 else 0.0,
        })
    return pd.DataFrame(rows, columns=["aoi", "n_fixations", "dwell_time_s", "mean_fix_dur_s",
                                       "time_to_first_fix_s", "dwell_pct"])