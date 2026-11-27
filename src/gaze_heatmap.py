
import pandas as pd

REQUIRED = ("time_s", "x", "y", "confidence", "on_panel")


def read_raw(source):
    df = pd.read_csv(source, comment="#", encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in gaze CSV: {', '.join(missing)}")
    for col in ("time_s", "x", "y", "confidence"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "exercise" in df.columns:
        df["exercise"] = df["exercise"].astype(str).str.strip()
    return df


def list_exercises(source):
    df = read_raw(source)
    if "exercise" not in df.columns:
        return []
    return list(dict.fromkeys(df["exercise"].dropna()))


def select_exercise(df, exercise=None):
    if "exercise" not in df.columns:
        if exercise:
            raise ValueError("This CSV has no 'exercise' column, so it cannot be filtered by exercise.")
        return df
    names = list(dict.fromkeys(df["exercise"].dropna()))
    if exercise is None:
        if len(names) > 1:
            raise ValueError("This CSV contains several exercises; choose one of: " + "; ".join(names))
        return df
    if exercise not in names:
        raise ValueError(f"Exercise '{exercise}' not found. Available: " + "; ".join(names))
    return df[df["exercise"] == exercise]


def load_gaze_csv(source, min_conf=0.75, exercise=None):
    df = select_exercise(read_raw(source), exercise)
    df = df.dropna(subset=["time_s", "x", "y"])
    on_panel = df["on_panel"].astype(str).str.strip().str.lower().isin(["1", "1.0", "true"])
    df = df[on_panel & (df["confidence"] >= min_conf)]
    out = pd.DataFrame({"t": df["time_s"], "x": df["x"], "y": 1.0 - df["y"]})
    return out.reset_index(drop=True)