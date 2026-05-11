import os
import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

BG   = "#1e2328"
BGAX = "#181c20"
C_IC    = "#dc3c3c"
C_REGIO = "#3c8cdc"
C_TOW   = "#b48c3c"
C_L73   = "#64c864"


def _overlay_normal(ax, data, color):
    mu, sigma = float(np.mean(data)), float(np.std(data))
    if sigma < 1e-9 or len(data) < 5:
        return
    counts, edges = np.histogram(data, bins=20)
    bin_w = float(edges[1] - edges[0])
    scale = len(data) * bin_w
    x = np.linspace(edges[0], edges[-1], 400)
    y = np.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
    ax.plot(x, y * scale, color=color, linewidth=2.0, linestyle="--",
            label=f"N(μ={mu:.2f}, σ={sigma:.2f})")


def _overlay_lognormal(ax, data, color):
    data_pos = data[data > 1e-6]
    if len(data_pos) < 5:
        return
    log_d = np.log(data_pos)
    mu_l, sigma_l = float(np.mean(log_d)), float(np.std(log_d))
    if sigma_l < 1e-9:
        return
    counts, edges = np.histogram(data_pos, bins=20)
    bin_w = float(edges[1] - edges[0])
    scale = len(data_pos) * bin_w
    x = np.linspace(max(edges[0], 1e-6), edges[-1], 400)
    y = (np.exp(-0.5 * ((np.log(x) - mu_l) / sigma_l) ** 2)
         / (x * sigma_l * np.sqrt(2 * np.pi)))
    e_x = np.exp(mu_l + sigma_l ** 2 / 2)
    ax.plot(x, y * scale, color=color, linewidth=2.0, linestyle="--",
            label=f"LogN(μ_log={mu_l:.2f}, σ_log={sigma_l:.2f})\nE[X]={e_x:.2f} min")


def _overlay_exponential(ax, data, color):
    data_pos = data[data > 0]
    if len(data_pos) < 5 or data_pos.mean() == 0:
        return
    lam = 1.0 / float(data_pos.mean())
    counts, edges = np.histogram(data_pos, bins=20)
    bin_w = float(edges[1] - edges[0])
    scale = len(data_pos) * bin_w
    x = np.linspace(0, edges[-1], 400)
    y = lam * np.exp(-lam * x)
    ax.plot(x, y * scale, color=color, linewidth=2.0, linestyle="--",
            label=f"Exp(λ={lam:.3f})\nE[X]={1/lam:.2f} min")


def _make_ax(title):
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(9, 5), facecolor=BG)
    ax.set_facecolor(BGAX)
    ax.set_title(title, fontsize=11, color="white", pad=7)
    ax.tick_params(colors="white")
    ax.grid(axis="y", alpha=0.2)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    return fig, ax


def _save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)


def export_rozklady(engine, out_dir: str) -> list:
    os.makedirs(out_dir, exist_ok=True)
    saved = []

    # 1. Czasy obsługi wagonów – rozkład normalny Gaussa
    if engine.wagon_service_log:
        df = pd.DataFrame(engine.wagon_service_log)

        fig, ax = _make_ax("Czas obsługi wagonów w kopalni")
        data = df["czas_obslugi_min"].values
        ax.hist(data, bins=20, color=C_TOW, alpha=0.70, edgecolor="none", label="Dane")
        _overlay_normal(ax, data, "#ffdd88")
        ax.set_xlabel("Czas obsługi wagonu [min]", fontsize=9, color="white")
        ax.set_ylabel("Liczba wagonów", fontsize=9, color="white")
        ax.legend(fontsize=8, facecolor=BG, labelcolor="white", framealpha=0.6)
        png = os.path.join(out_dir, "6_obslugi_wagonow.png")
        _save(fig, png)
        saved.append(png)

    # 2. Odstępy między przybywającymi pasażerami – rozkład wykładniczy
    if engine.pasazer_log:
        df_pas = pd.DataFrame(engine.pasazer_log)
        intervals = []
        for _, grp in df_pas.groupby("pociag_id"):
            times = grp["czas_przybycia"].sort_values().values
            if len(times) > 1:
                intervals.extend(np.diff(times).tolist())
        intervals = np.array([v for v in intervals if v > 0])

        if len(intervals) > 5:
            fig, ax = _make_ax("Odstępy między przybywającymi pasażerami")
            ax.hist(intervals, bins=30, color=C_REGIO, alpha=0.70, edgecolor="none", label="Dane")
            _overlay_exponential(ax, intervals, "#88ccff")
            ax.set_xlabel("Odstęp między pasażerami [min]", fontsize=9, color="white")
            ax.set_ylabel("Liczba odstępów", fontsize=9, color="white")
            ax.legend(fontsize=8, facecolor=BG, labelcolor="white", framealpha=0.6)
            png = os.path.join(out_dir, "7_odstepy_pasazerow.png")
            _save(fig, png)
            saved.append(png)

    # 3. Czas wymiany pasażerów na peronie – rozkład log-normalny
    if engine.platform_exchange_log:
        df = pd.DataFrame(engine.platform_exchange_log)

        fig, ax = _make_ax("Czas wymiany pasażerów na peronie")
        data = df["czas_wymiany_min"].values
        ax.hist(data, bins=20, color=C_L73, alpha=0.70, edgecolor="none", label="Dane")
        _overlay_lognormal(ax, data, "#aaffaa")
        ax.set_xlabel("Czas wymiany pasażerów [min]", fontsize=9, color="white")
        ax.set_ylabel("Liczba pociągów", fontsize=9, color="white")
        ax.legend(fontsize=8, facecolor=BG, labelcolor="white", framealpha=0.6)
        png = os.path.join(out_dir, "8_wymiana_pasazerow.png")
        _save(fig, png)
        saved.append(png)

    return saved


def export_podsumowanie(xlsx_path: str, out_dir: str) -> list:
    import pandas as pd
    from matplotlib.ticker import MaxNLocator

    os.makedirs(out_dir, exist_ok=True)
    saved = []

    xl = pd.ExcelFile(xlsx_path)
    df_p  = pd.read_excel(xl, "pociagi")
    df_st = pd.read_excel(xl, "statystyki")
    df_ut = pd.read_excel(xl, "wykorzystanie_zasobow")
    df_ts = pd.read_excel(xl, "szereg_czasowy")
    df_ph = pd.read_excel(xl, "pasazerowie_historia")

    TYP_COLORS = {"IC": C_IC, "Regio": C_REGIO, "Towarowy": C_TOW}
    C_L73  = "#64c864"
    C_GREY = "#646464"
    T_MIN, T_MAX = 360, 840

    def hhm(minutes):
        h, m = divmod(int(minutes), 60)
        return f"{h:02d}:{m:02d}"

    def ts_ticks(ax, ts_col, step_min=60):
        vals = ts_col.values
        ticks = np.arange(vals.min(), vals.max() + 1, step_min)
        ax.set_xticks(ticks)
        ax.set_xticklabels([hhm(v) for v in ticks], fontsize=8)

    def trim_ts(df, col="czas_min"):
        return df[(df[col] >= T_MIN) & (df[col] <= T_MAX)].copy()

    def _sv(fig, name):
        path = os.path.join(out_dir, name)
        fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
        plt.close(fig)
        saved.append(path)

    TKW = dict(fontsize=11, color="white", pad=7)
    LKW = dict(fontsize=9, color="white")

    plt.style.use("dark_background")

    # 1. Opóźnienia wg typu
    df_st_filt = df_st[df_st["typ"] != "RAZEM"].copy()

    typy   = df_st_filt["typ"].tolist()
    x      = np.arange(len(typy))
    w      = 0.35
    colors = [TYP_COLORS.get(t, C_GREY) for t in typy]

    fig, ax = plt.subplots(figsize=(9, 5), facecolor=BG)
    ax.set_facecolor(BGAX)
    bars_sr  = ax.bar(x - w/2, df_st_filt["sr_opoznienie_min"],  w, label="Śr. opóźnienie",  color=colors, alpha=0.85)
    bars_max = ax.bar(x + w/2, df_st_filt["max_opoznienie_min"], w, label="Max opóźnienie", color=colors, alpha=0.45)
    for bar in list(bars_sr) + list(bars_max):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=8, color="white")
    ax.set_xticks(x)
    ax.set_xticklabels(typy, **LKW)
    ax.set_ylabel("Opóźnienie [min]", **LKW)
    ax.set_title("Opóźnienia wg typu pociągu", **TKW)
    ax.legend(fontsize=8, facecolor=BG, labelcolor="white", framealpha=0.6)
    ax.tick_params(colors="white")
    ax.grid(axis="y", alpha=0.2)
    _sv(fig, "1_opoznienia_wg_typu.png")

    # 2. Histogram opóźnień indywidualnych
    fig, ax = plt.subplots(figsize=(9, 5), facecolor=BG)
    ax.set_facecolor(BGAX)
    for typ, col in TYP_COLORS.items():
        sub = df_p[(df_p["typ"] == typ) & (df_p["opoznienie_min"] >= 0)]
        if sub.empty:
            continue
        ax.hist(sub["opoznienie_min"], bins=20, color=col, alpha=0.65, label=typ, edgecolor="none")
    ax.set_xlabel("Opóźnienie [min]", **LKW)
    ax.set_ylabel("Liczba pociągów", **LKW)
    ax.set_title("Rozkład opóźnień indywidualnych", **TKW)
    ax.legend(fontsize=8, facecolor=BG, labelcolor="white", framealpha=0.6)
    ax.tick_params(colors="white")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", alpha=0.2)
    _sv(fig, "2_rozklad_opoznien.png")

    # 3. Wykorzystanie zasobów
    nazwy_zasob = {
        "gl_polnocna": "Głowica N", "gl_poludniowa": "Głowica S",
        "tor1": "Tor 1 (L8)", "tor2": "Tor 2 (L8)",
        "tor3": "Tor 3 (L73)", "tor4": "Tor 4 (L73)",
        "tor568": "Tor 568",
        "szlak_kopalni_wejscie": "Szlak→Kopalnia",
        "szlak_kopalni_wyjscie": "Szlak←Kopalnia",
        "kop_0": "Kopalnia K0", "kop_1": "Kopalnia K1", "kop_2": "Kopalnia K2",
    }
    df_ut_named = df_ut.copy()
    df_ut_named["nazwa"] = df_ut_named["zasob"].map(nazwy_zasob).fillna(df_ut_named["zasob"])
    df_ut_named = df_ut_named.sort_values("wykorzystanie_proc", ascending=True)

    bar_colors = []
    for z in df_ut_named["zasob"]:
        if "gl_" in z:              bar_colors.append("#a070c0")
        elif "kopalnia" in z:       bar_colors.append(C_TOW)
        elif "kop_" in z:           bar_colors.append("#c89040")
        elif "tor568" in z:         bar_colors.append("#8080b0")
        elif z in ("tor1", "tor2"): bar_colors.append(C_REGIO)
        else:                       bar_colors.append(C_L73)

    fig, ax = plt.subplots(figsize=(9, 6), facecolor=BG)
    ax.set_facecolor(BGAX)
    bars = ax.barh(df_ut_named["nazwa"], df_ut_named["wykorzystanie_proc"],
                   color=bar_colors, alpha=0.8, height=0.7)
    for bar in bars:
        bw = bar.get_width()
        ax.text(bw + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{bw:.1f}%", va="center", fontsize=8, color="white")
    ax.set_xlabel("Wykorzystanie [%]", **LKW)
    ax.set_title("Wykorzystanie zasobów stacji", **TKW)
    ax.tick_params(colors="white")
    ax.set_xlim(0, max(df_ut_named["wykorzystanie_proc"]) * 1.25)
    ax.grid(axis="x", alpha=0.2)
    ax.axvline(x=50, color="white", linestyle="--", alpha=0.3, linewidth=0.8)
    _sv(fig, "3_zasoby_stacji.png")

    # 4. Pasażerowie na peronach w czasie
    df_ph_t = trim_ts(df_ph)

    pas_cols = {
        "L8_Polnoc":    (C_REGIO,    "L8 →N"),
        "L8_Poludnie":  ("#2060a0",  "L8 →S"),
        "L73_Polnoc":   (C_L73,     "L73 →N"),
        "L73_Poludnie": ("#408040",  "L73 →S"),
        "IC_Polnoc":    (C_IC,      "IC →N"),
        "IC_Poludnie":  ("#803030",  "IC →S"),
    }
    x_ts         = df_ph_t["czas_min"].values
    stack_vals   = [df_ph_t[k].values for k in pas_cols]
    stack_colors = [v[0] for v in pas_cols.values()]
    stack_labels = [v[1] for v in pas_cols.values()]

    fig, ax = plt.subplots(figsize=(13, 5), facecolor=BG)
    ax.set_facecolor(BGAX)
    ax.stackplot(x_ts, stack_vals, colors=stack_colors, labels=stack_labels, alpha=0.75)
    ax.set_ylabel("Pasażerowie na peronach", **LKW)
    ax.set_title("Pasażerowie na peronach w czasie (6:00–14:00)", **TKW)
    ax.legend(fontsize=8, facecolor=BG, labelcolor="white", framealpha=0.6, loc="upper left", ncol=3)
    ax.tick_params(colors="white")
    ax.grid(alpha=0.15)
    ts_ticks(ax, df_ph_t["czas_min"])
    _sv(fig, "4_pasazerowie_w_czasie.png")

    # 5. Aktywność stacji w czasie
    df_ts_t = trim_ts(df_ts)

    fig, ax = plt.subplots(figsize=(13, 5), facecolor=BG)
    ax.set_facecolor(BGAX)
    ax.plot(df_ts_t["czas_min"], df_ts_t["aktywne_pociagi"],
            color="white", linewidth=1.4, label="Aktywne pociągi", zorder=5)
    ax.fill_between(df_ts_t["czas_min"], df_ts_t["aktywne_pociagi"], color="white", alpha=0.08)

    ax_r = ax.twinx()
    ax_r.set_facecolor(BGAX)
    ax_r.plot(df_ts_t["czas_min"], df_ts_t["szlak_kopalni_pociagi"],
              color=C_TOW, linewidth=1.0, linestyle="--", label="Szlak kopalnia", alpha=0.8)
    ax_r.set_ylabel("Szlak kopalnia", fontsize=8, color=C_TOW)
    ax_r.tick_params(colors=C_TOW, labelsize=7)
    ax_r.set_ylim(0, 5)

    ax.set_ylabel("Aktywne pociągi na stacji", **LKW)
    ax.set_title("Aktywność na stacji w czasie (6:00–14:00)", **TKW)
    ax.tick_params(colors="white")
    ax.grid(alpha=0.15)
    ax.set_ylim(bottom=0)
    ts_ticks(ax, df_ts_t["czas_min"])
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax_r.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2,
              fontsize=8, facecolor=BG, labelcolor="white", framealpha=0.6)
    _sv(fig, "5_aktywnosc_stacji.png")

    return saved
