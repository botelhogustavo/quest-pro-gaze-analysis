import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from matplotlib.patches import Polygon, Rectangle
from PIL import Image
from scipy.ndimage import gaussian_filter

import analyze_gaze as ag
import gaze_heatmap as gh

HERE = Path(__file__).resolve().parent
DEFAULT_AOIS = HERE / "config" / "aois.json"
PANEL_ASPECT = 297 / 210
GAP_S = 0.2
FROZEN_WARN_S = 1.0


def save_bytes(data, suffix):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


@st.cache_data(show_spinner=False)
def process(csv_bytes, exercise, min_conf, min_dur, max_disp, max_gap, cfg_json):
    cfg = json.loads(cfg_json)
    panel = {"x_min": 0.0, "x_max": 1.0, "y_min": 0.0, "y_max": 1.0}
    panel.update(cfg.get("panel", {}))
    aois = cfg.get("aois", [])
    table = gh.select_exercise(gh.read_raw(io.BytesIO(csv_bytes)), exercise)
    path = save_bytes(table[list(gh.REQUIRED)].to_csv(index=False).encode("utf-8"), ".csv")
    try:
        raw = ag.load_csv(path)
    finally:
        path.unlink(missing_ok=True)
    valid, qc = ag.filter_samples(raw, min_conf)
    valid = ag.normalize_xy(valid, panel)
    t0 = float(raw["time_s"].min())
    valid["t"] = valid["time_s"] - t0
    fx = ag.detect_fixations(valid, min_dur, max_disp, max_gap)
    fx["aoi"] = [ag.assign_aoi(r.u, r.v, aois) for r in fx.itertuples()]
    metrics = ag.aoi_metrics(fx, aois, t0)
    return raw, valid, qc, fx, metrics, t0


def base_axes(img):
    ratio = img.shape[0] / img.shape[1] if img is not None else PANEL_ASPECT
    w = min(7.0, 7.0 / ratio)
    fig, ax = plt.subplots(figsize=(w, w * ratio))
    if img is not None:
        ax.imshow(img, extent=(0, 1, 0, 1))
    else:
        ax.set_facecolor("#eeeeee")
    ax.set(xlim=(0, 1), ylim=(0, 1), xticks=[], yticks=[], aspect="auto")
    fig.tight_layout()
    return fig, ax


def draw_aois(ax, aois):
    for a in aois:
        if "polygon" in a:
            ax.add_patch(Polygon(a["polygon"], fill=False, ec="tab:blue", lw=1.5))
            lx, ly = a["polygon"][0]
        else:
            ax.add_patch(Rectangle((a["x"], a["y"]), a["w"], a["h"], fill=False, ec="tab:blue", lw=1.5))
            lx, ly = a["x"], a["y"] + a["h"]
        ax.text(lx, ly, a["name"], color="tab:blue", fontsize=8, va="bottom",
                bbox=dict(fc="white", alpha=0.7, pad=1, lw=0))


def split_on_gaps(df, gap=GAP_S):
    if df.empty:
        return []
    cuts = [0, *np.where(df["t"].diff().to_numpy() > gap)[0], len(df)]
    return [df.iloc[a:b] for a, b in zip(cuts[:-1], cuts[1:])]


def longest_frozen_run(valid):
    if len(valid) < 2:
        return 0.0
    moved = ((valid[["u", "v"]].diff().abs().sum(axis=1) > 0) | (valid["t"].diff() > GAP_S)).to_numpy().copy()
    moved[0] = True
    t = valid["t"].groupby(np.cumsum(moved))
    return float((t.max() - t.min()).max())


def heatmap_fig(valid, img, aois, smoothing, show_aois):
    aspect = img.shape[0] / img.shape[1] if img is not None else PANEL_ASPECT
    nx = 200
    ny = max(1, int(round(nx * aspect)))
    counts, _, _ = np.histogram2d(valid["v"], valid["u"], bins=[ny, nx], range=[[0, 1], [0, 1]])
    hm = gaussian_filter(counts, sigma=smoothing * nx)
    hm = hm / hm.max() if hm.max() > 0 else hm
    fig, ax = base_axes(img)
    ax.imshow(np.ma.masked_less(hm, 0.04), extent=(0, 1, 0, 1), origin="lower", cmap="jet",
              vmin=0, vmax=1, alpha=0.55, interpolation="bilinear", aspect="auto")
    if show_aois:
        draw_aois(ax, aois)
    return fig


def replay_fig(valid, img, aois, t, trail, show_aois):
    fig, ax = base_axes(img)
    past = valid[(valid["t"] <= t) & (valid["t"] >= t - trail)]
    for piece in split_on_gaps(past):
        if len(piece) > 1:
            ax.plot(piece["u"], piece["v"], "-", color="black", lw=1.5)
    if len(past):
        ax.scatter(past["u"].iloc[-1], past["v"].iloc[-1], s=140, c="red", edgecolors="white",
                   linewidths=2, zorder=5)
    if show_aois:
        draw_aois(ax, aois)
    return fig


def render_video(csv_bytes, exercise, img_bytes, fps, scale, trail, heatmap, min_conf):
    csv_path = save_bytes(csv_bytes, ".csv")
    img_path = save_bytes(img_bytes, ".png")
    out = save_bytes(b"", ".mp4")
    cmd = [sys.executable, str(HERE / "gaze_video.py"), str(csv_path), str(img_path), "-o", str(out),
           "--fps", str(fps), "--scale", str(scale), "--trail", str(trail), "--min-conf", str(min_conf)]
    if exercise:
        cmd += ["--exercise", exercise]
    if heatmap:
        cmd.append("--heatmap")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        data = out.read_bytes() if res.returncode == 0 else None
        return data, res.stderr.strip()
    finally:
        for p in (csv_path, img_path, out):
            p.unlink(missing_ok=True)


def aoi_path(fx):
    seq = [a for a in fx["aoi"] if a != "none"]
    return [a for i, a in enumerate(seq) if i == 0 or a != seq[i - 1]]


def show_fig(fig):
    st.pyplot(fig)
    plt.close(fig)


def main():
    st.set_page_config(page_title="Dashboard de eye tracking", layout="wide")
    st.title("Dashboard de eye tracking")

    with st.sidebar:
        st.header("Entradas")
        csv_file = st.file_uploader("CSV do olhar", type=["csv"])
        exercise = None
        if csv_file is not None:
            try:
                names = gh.list_exercises(io.BytesIO(csv_file.getvalue()))
            except Exception as e:
                st.error(f"Não foi possível ler o CSV: {e}")
                return
            if names:
                exercise = st.selectbox("Exercício", names)
        img_file = st.file_uploader("Imagem do painel deste exercício (opcional)",
                                    type=["png", "jpg", "jpeg"], key=f"img_{exercise}")
        panel_images = st.session_state.setdefault("panel_images", {})
        if img_file is not None:
            panel_images[exercise] = img_file.getvalue()
        elif exercise in panel_images:
            st.caption("Usando a imagem enviada antes para este exercício.")
            if st.button("Remover imagem", key=f"rm_{exercise}"):
                del panel_images[exercise]
                st.rerun()
        aois_file = st.file_uploader("JSON de AOIs (opcional)", type=["json"])
        st.header("Filtragem")
        min_conf = st.slider("Confiança mínima", 0.0, 1.0, 0.5, 0.05)
        st.header("Fixações (I-DT)")
        min_dur = st.slider("Duração mínima (s)", 0.05, 0.50, 0.10, 0.01)
        max_disp = st.slider("Dispersão máxima", 0.005, 0.10, 0.03, 0.005)
        max_gap = st.slider("Intervalo máximo (s)", 0.01, 0.20, 0.05, 0.01)
        st.header("Exibição")
        show_aois = st.checkbox("Mostrar AOIs", value=True)
        smoothing = st.slider("Suavização do mapa de calor (% da largura)", 0.5, 10.0, 3.0, 0.5) / 100

    if csv_file is None:
        st.info("Envie um CSV de olhar na barra lateral para começar.")
        return

    if aois_file is not None:
        cfg_json = aois_file.getvalue().decode("utf-8")
    elif DEFAULT_AOIS.exists():
        cfg_json = DEFAULT_AOIS.read_text(encoding="utf-8")
    else:
        cfg_json = json.dumps({"aois": []})
    aois = json.loads(cfg_json).get("aois", [])

    csv_bytes = csv_file.getvalue()
    try:
        raw, valid, qc, fx, metrics, t0 = process(csv_bytes, exercise, min_conf, min_dur, max_disp, max_gap, cfg_json)
    except Exception as e:
        st.error(f"Não foi possível processar o CSV: {e}")
        return

    img = None
    img_bytes = st.session_state.get("panel_images", {}).get(exercise)
    if img_bytes is not None:
        img = np.array(Image.open(io.BytesIO(img_bytes)).convert("RGB"))

    if valid.empty:
        st.warning("Nenhuma amostra válida. Diminua a confiança mínima ou verifique se on_panel é 1 no CSV.")
        st.json(qc)
        return

    tab_over, tab_heat, tab_aoi, tab_replay = st.tabs(["Visão geral", "Mapa de calor", "Estatísticas de AOI", "Replay do olhar"])

    with tab_over:
        duration = float(raw["time_s"].max() - t0)
        c = st.columns(5)
        c[0].metric("Duração", f"{duration:.1f} s")
        c[1].metric("Amostras válidas", f"{qc['valid_ratio']:.0%}")
        c[2].metric("Fixações", len(fx))
        c[3].metric("Fixação média", f"{fx['duration_s'].mean() * 1000:.0f} ms" if len(fx) else "-")
        c[4].metric("Maior fixação", f"{fx['duration_s'].max() * 1000:.0f} ms" if len(fx) else "-")
        frozen = longest_frozen_run(valid)
        if frozen >= FROZEN_WARN_S:
            st.warning(f"As coordenadas do olhar ficaram exatamente iguais por {frozen:.1f} s. "
                       "O eye tracker pode ter travado; confira essas amostras antes de interpretar os resultados.")
        st.subheader("Qualidade dos dados")
        st.dataframe(pd.DataFrame({"amostras": {
            "total": qc["samples_total"], "válidas": qc["samples_valid"],
            "descartadas (NaN)": qc["dropped_nan"], "descartadas (confiança baixa)": qc["dropped_low_conf"],
            "descartadas (fora do painel)": qc["dropped_off_panel"]}}))
        st.subheader("Fixações")
        st.dataframe(fx, use_container_width=True)
        st.download_button("Baixar CSV de fixações", fx.to_csv(index=False), "fixations.csv", "text/csv")

    with tab_heat:
        show_fig(heatmap_fig(valid, img, aois, smoothing, show_aois))
        if img is None:
            st.caption("Envie a imagem do painel na barra lateral para ver o mapa de calor sobre ela.")

    with tab_aoi:
        if not aois:
            st.info("Nenhuma AOI carregada. Envie um JSON de AOIs na barra lateral.")
        else:
            shown = metrics.copy()
            st.dataframe(shown.style.format({
                "dwell_time_s": "{:.2f}", "mean_fix_dur_s": "{:.3f}",
                "time_to_first_fix_s": "{:.2f}", "dwell_pct": "{:.1f}"}, na_rep="-"),
                use_container_width=True)
            st.subheader("Tempo de permanência por AOI (s)")
            st.bar_chart(metrics.set_index("aoi")["dwell_time_s"])
            path = aoi_path(fx)
            st.subheader("Trajeto do olhar entre AOIs")
            st.write(" → ".join(path) if path else "Nenhuma fixação dentro das AOIs.")
            if len(path) > 1:
                pairs = pd.DataFrame({"from": path[:-1], "to": path[1:]})
                st.subheader("Transições (das linhas para as colunas)")
                st.dataframe(pd.crosstab(pairs["from"], pairs["to"]))
            st.download_button("Baixar CSV de métricas por AOI", metrics.to_csv(index=False),
                               "aoi_metrics.csv", "text/csv")

    with tab_replay:
        t_max = float(valid["t"].max())
        c1, c2 = st.columns([3, 1])
        trail = c2.slider("Rastro (s)", 0.1, 2.0, 0.5, 0.1)
        t = c1.slider("Tempo (s)", 0.0, t_max, 0.0, 0.05)
        show_fig(replay_fig(valid, img, aois, t, trail, show_aois))
        st.subheader("Gerar MP4")
        if img_bytes is None:
            st.caption("Envie a imagem do painel para gerar um vídeo.")
        else:
            v1, v2, v3 = st.columns(3)
            fps = v1.selectbox("FPS", [10, 15, 24, 30], index=1)
            scale = v2.selectbox("Escala", [0.5, 1.0, 1.5, 2.0], index=1)
            with_hm = v3.checkbox("Incluir mapa de calor", value=False)
            if st.button("Gerar vídeo"):
                with st.spinner("Gerando o vídeo. Gravações longas e configurações altas levam alguns minutos."):
                    data, err = render_video(csv_bytes, exercise, img_bytes, fps, scale, trail, with_hm, min_conf)
                if data is None:
                    st.error(f"Falha ao gerar o vídeo: {err}")
                else:
                    st.session_state["video"] = (exercise, data)
            saved = st.session_state.get("video")
            if saved and saved[0] == exercise:
                st.video(saved[1])
                st.download_button("Baixar MP4", saved[1], "gaze.mp4", "video/mp4")


if __name__ == "__main__":
    main()