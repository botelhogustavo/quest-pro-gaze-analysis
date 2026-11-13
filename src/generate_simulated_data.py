import numpy as np
from pathlib import Path

HZ = 72                                   # amostras por segundo
LARG_GRAUS, ALT_GRAUS = 16.0, 22.4        # painel 0,42 x 0,594 m a 1,5 m
RUIDO_GRAUS = 0.5                         # ruído do rastreador (desvio-padrão)

# Centro de cada AOI (x, y de 0 a 1, origem embaixo à esquerda)
AOIS = {
    "enunciado": (0.50, 0.875),
    "equacao":   (0.50, 0.60),
    "alt_A":     (0.275, 0.34),
    "alt_B":     (0.725, 0.34),
    "alt_C":     (0.275, 0.14),
    "alt_D":     (0.725, 0.14),
}

def simular_sessao(sequencia, rng, taxa_piscada=0.25):
    """Gera um DataFrame-like (lista de linhas) a partir de uma sequência de AOIs."""
    alvos = []
    for aoi in sequencia:
        cx, cy = AOIS[aoi]
        for _ in range(rng.integers(1, 4)):               # 1 a 3 fixações por visita
            x = cx + rng.normal(0, 0.03)
            y = cy + rng.normal(0, 0.02)
            alvos.append((x, y, rng.uniform(0.2, 0.5)))   # duração 200 a 500 ms

    xs, ys = [], []
    for i, (x, y, dur) in enumerate(alvos):
        n = max(int(dur * HZ), 3)
        xs += list(x + rng.normal(0, RUIDO_GRAUS / LARG_GRAUS, n))
        ys += list(y + rng.normal(0, RUIDO_GRAUS / ALT_GRAUS, n))
        if i < len(alvos) - 1:                            # sacada até a próxima fixação
            nx, ny, _ = alvos[i + 1]
            m = max(int(rng.uniform(0.03, 0.06) * HZ), 2)
            xs += list(np.linspace(x, nx, m + 2)[1:-1])
            ys += list(np.linspace(y, ny, m + 2)[1:-1])

    xs, ys = np.array(xs), np.array(ys)
    n = len(xs)
    tempo = np.cumsum(rng.normal(1 / HZ, 0.0008, n))
    conf = np.clip(rng.normal(0.96, 0.03, n), 0, 1)

    # Piscadas: perda de sinal de 100 a 300 ms
    duracao = tempo[-1]
    for t_ini in rng.uniform(0, duracao, rng.poisson(taxa_piscada * duracao)):
        mask = (tempo >= t_ini) & (tempo <= t_ini + rng.uniform(0.1, 0.3))
        xs[mask], ys[mask] = np.nan, np.nan
        conf[mask] = rng.uniform(0, 0.2, mask.sum())

    fora = (xs < 0) | (xs > 1) | (ys < 0) | (ys > 1)      # olhar fora do painel
    xs[fora], ys[fora] = np.nan, np.nan
    acertou = (~np.isnan(xs)).astype(int)
    return tempo, xs, ys, conf, acertou

def salvar_csv(caminho, dados):
    tempo, xs, ys, conf, ac = dados
    with open(caminho, "w") as f:
        f.write("tempo,x,y,confianca,acertou\n# inicio\n")
        for t, x, y, c, a in zip(tempo, xs, ys, conf, ac):
            xs_ = "" if np.isnan(x) else f"{x:.4f}"
            ys_ = "" if np.isnan(y) else f"{y:.4f}"
            f.write(f"{t:.4f},{xs_},{ys_},{c:.2f},{a}\n")

if __name__ == "__main__":
    rng = np.random.default_rng(42)
    pasta = Path("data/exemplo"); pasta.mkdir(parents=True, exist_ok=True)

    # Dois "perfis" fictícios para ter o que comparar depois
    perfis = {
        "P01": ["enunciado", "equacao", "alt_A", "equacao", "alt_B", "alt_B"],        # sistemático
        "P02": ["enunciado", "alt_A", "alt_B", "alt_C", "alt_D", "equacao", "alt_B"], # tentativa
    }
    for pid, seq in perfis.items():
        salvar_csv(pasta / f"gaze_{pid}_ex01_sim.csv", simular_sessao(seq, rng))
        print("gerado:", pid)