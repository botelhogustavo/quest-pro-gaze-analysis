import argparse
import json
import random
from pathlib import Path

HZ = 100         # the headset logs about 100 samples/s
NOISE = 0.017    # per-sample jitter, normalized panel units (about 0.3 deg)
OFFSET = 0.045   # per-recording systematic shift (about 1 deg)
BLINKS_PER_SEC = 0.25

OPTIONS = ["option_A", "option_B", "option_C", "option_D"]
DEFAULT_AOIS = {
    "statement": (0.05, 0.75, 0.95, 0.95),
    "equation": (0.20, 0.55, 0.80, 0.72),
    "option_A": (0.05, 0.38, 0.95, 0.50),
    "option_B": (0.05, 0.26, 0.95, 0.37),
    "option_C": (0.05, 0.14, 0.95, 0.25),
    "option_D": (0.05, 0.03, 0.95, 0.13),
}


def load_aois(path):
    p = Path(path)
    if not p.exists():
        return DEFAULT_AOIS
    aois = {}
    for name, v in json.loads(p.read_text()).items():
        if name == "outside":
            continue
        aois[name] = v if isinstance(v, list) else (v["x_min"], v["y_min"], v["x_max"], v["y_max"])
    return aois


def point_in(box):
    x0, y0, x1, y1 = box
    return random.uniform(x0, x1), random.uniform(y0, y1)


def scanpath(answer):
    path = [("statement", random.lognormvariate(-0.1, 0.3)),
            ("equation", random.lognormvariate(-0.5, 0.3))]
    path += [(o, random.lognormvariate(-1.4, 0.4)) for o in OPTIONS]
    for _ in range(random.randint(1, 4)):
        path.append((random.choice(["statement", "equation"] + OPTIONS),
                     random.lognormvariate(-1.5, 0.4)))
    path.append((answer, random.lognormvariate(-1.0, 0.3)))
    return path


def sample(t, x, y):
    x += random.gauss(0, NOISE)
    y += random.gauss(0, NOISE)
    if random.random() < BLINKS_PER_SEC / HZ:
        return t, None, None, 0.0, 0
    conf = random.uniform(0.85, 1.0)
    if random.random() < 0.03:
        conf = random.uniform(0.1, 0.45)
    if random.random() < 0.01 or not (0 <= x <= 1 and 0 <= y <= 1):
        return t, None, None, conf, 0
    return t, x, y, conf, 1


def simulate(aois, answer):
    dt = 1 / HZ
    rows, t = [], 0.0
    ox, oy = random.gauss(0, OFFSET), random.gauss(0, OFFSET)
    prev = point_in(aois["statement"])
    for name, dur in scanpath(answer):
        target = point_in(aois[name])
        n = max(2, int(random.uniform(0.03, 0.06) / dt))  # saccade
        for i in range(1, n + 1):
            f = i / n
            rows.append(sample(t, prev[0] + (target[0] - prev[0]) * f + ox,
                                  prev[1] + (target[1] - prev[1]) * f + oy))
            t += dt
        dx, dy = random.gauss(0, 0.0004), random.gauss(0, 0.0004)
        for i in range(max(3, int(dur / dt))):  # fixation with a bit of drift
            rows.append(sample(t, target[0] + dx * i + ox, target[1] + dy * i + oy))
            t += dt
        prev = target
    return rows, t


def write_csv(path, rows, exercise):
    """Write rows in the GazeLogger format: exercise column plus '#' marker lines."""
    end = rows[-1][0] if rows else 0.0
    out = ["time_s,x,y,confidence,on_panel,exercise", "# start",
           f"# exercise,{rows[0][0] if rows else 0.0:.4f},{exercise}"]
    for t, x, y, c, on in rows:
        xy = f"{x:.4f},{y:.4f}" if x is not None else ","
        out.append(f"{t:.4f},{xy},{c:.2f},{on},{exercise}")
    out.append(f"# end,{end:.4f}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--participants", type=int, default=5)
    ap.add_argument("--exercises", type=int, default=2)
    ap.add_argument("--out", default="data/example")
    ap.add_argument("--aois", default="data/aois.json")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    aois = load_aois(args.aois)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    meta = ["participant_id,exercise_id,answer,correct_answer,is_correct,"
            "total_time_s,wears_glasses,notes"]
    for p in range(1, args.participants + 1):
        pid = f"P{p:02d}"
        glasses = int(random.random() < 0.3)
        for e in range(1, args.exercises + 1):
            eid = f"ex{e:02d}"
            correct = random.choice(OPTIONS)
            answer = correct if random.random() < 0.65 else random.choice(OPTIONS)
            rows, total = simulate(aois, answer)
            write_csv(out / f"gaze_{pid}_{eid}_sim.csv", rows, eid)
            meta.append(f"{pid},{eid},{answer},{correct},{int(answer == correct)},"
                        f"{total:.2f},{glasses},simulated")

    (out / "metadata.csv").write_text("\n".join(meta) + "\n")
    print(f"wrote {args.participants * args.exercises} recordings to {out}")


if __name__ == "__main__":
    main()