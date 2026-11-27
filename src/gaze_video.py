import argparse
import shutil
import subprocess

import cv2
import numpy as np
from matplotlib import colormaps
from scipy.ndimage import gaussian_filter

from gaze_heatmap import list_exercises, load_gaze_csv

TRAIL_GAP_S = 0.2  


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def main():
    ap = argparse.ArgumentParser(
        description="Render an MP4 with the current gaze (red dot and trail) over a panel image, "
                    "optionally with the accumulated heatmap.")
    ap.add_argument("csv")
    ap.add_argument("image", nargs="?", help="panel image (not needed with --list-exercises)")
    ap.add_argument("-o", "--output", default="gaze_video.mp4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--scale", type=float, default=2.0,
                    help="magnification factor of the image in the video (default 2)")
    ap.add_argument("--sigma", type=float, default=22,
                    help="heatmap blur radius in pixels of the original image")
    ap.add_argument("--trail", type=float, default=0.5,
                    help="duration of the gaze trail in seconds")
    ap.add_argument("--heatmap", action="store_true",
                    help="show the accumulated heatmap in the background")
    ap.add_argument("--min-conf", type=float, default=0.0,
                    help="minimum sample confidence")
    ap.add_argument("--exercise", default=None,
                    help="exercise name to render (required when the CSV has several exercises)")
    ap.add_argument("--list-exercises", action="store_true",
                    help="print the exercises found in the CSV and exit")
    args = ap.parse_args()

    if args.list_exercises:
        print("\n".join(list_exercises(args.csv)) or "(no exercise column in this CSV)")
        return

    if not args.image:
        raise SystemExit("The panel image argument is required.")
    try:
        df = load_gaze_csv(args.csv, args.min_conf, args.exercise)
    except ValueError as e:
        raise SystemExit(str(e))
    df = df.sort_values("t").reset_index(drop=True)
    if df.empty:
        raise SystemExit("No valid on-panel samples for this selection.")
    base = cv2.imread(args.image)
    if base is None:
        raise SystemExit(f"Could not read image: {args.image}")
    h0, w0 = base.shape[:2]
    W = int(round(w0 * args.scale / 2)) * 2
    H = int(round(h0 * args.scale / 2)) * 2
    base = cv2.resize(base, (W, H), interpolation=cv2.INTER_CUBIC)

    step = 3
    gh, gw = h0 // step, w0 // step
    xs = np.clip((df.x.values * gw).astype(int), 0, gw - 1)
    ys = np.clip((df.y.values * gh).astype(int), 0, gh - 1)
    t = df.t.values

    final_grid = np.zeros((gh, gw))
    np.add.at(final_grid, (ys, xs), 1)
    peak = gaussian_filter(final_grid, sigma=args.sigma / step).max()
    if peak == 0:
        peak = 1.0

    jet = (colormaps["jet"](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)[:, ::-1]

    cmd = [find_ffmpeg(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(args.fps), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
           "-movflags", "+faststart", args.output]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    t_start = float(t.min())
    n_frames = int(np.ceil((t.max() - t_start + 0.5) * args.fps))
    grid = np.zeros((gh, gw))
    used = 0
    for f in range(n_frames):
        tf = t_start + f / args.fps
        upto = np.searchsorted(t, tf, side="right")
        if upto > used:
            np.add.at(grid, (ys[used:upto], xs[used:upto]), 1)
            used = upto

        frame = base.copy()

        if args.heatmap and used:
            hm = gaussian_filter(grid, sigma=args.sigma / step) / peak
            hm = cv2.resize(np.clip(hm, 0, 1), (W, H), interpolation=cv2.INTER_CUBIC)
            color = jet[(np.clip(hm, 0, 1) * 255).astype(np.uint8)]
            alpha = (0.55 * (hm > 0.04))[..., None]
            frame = (frame * (1 - alpha) + color * alpha).astype(np.uint8)

        start = np.searchsorted(t, tf - args.trail, side="left")
        pts = np.stack([df.x.values[start:used] * W,
                        df.y.values[start:used] * H], axis=1).astype(np.int32)
        breaks = np.where(np.diff(t[start:used]) > TRAIL_GAP_S)[0] + 1
        for piece in np.split(pts, breaks):
            if len(piece) > 1:
                cv2.polylines(frame, [piece.reshape(-1, 1, 2)], False, (0, 0, 0), 2, cv2.LINE_AA)
        if len(pts):
            cv2.circle(frame, tuple(int(v) for v in pts[-1]), 9, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, tuple(int(v) for v in pts[-1]), 9, (255, 255, 255), 2, cv2.LINE_AA)

        label = f"{min(tf, t.max()):.1f} s"  # session time, same as time_s in the CSV
        cv2.putText(frame, label, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, label, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    proc.wait()
    print(f"{n_frames} frames -> {args.output}")


if __name__ == "__main__":
    main()