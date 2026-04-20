import simpy
import pandas as pd
import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional

RANDOM_SEED = 42

PRIORYTET_IC = 1
PRIORYTET_REGIO = 3
PRIORYTET_TOWAROWY = 5


@dataclass
class SimConfig:
    l8_south_count: int = 10
    l8_north_count: int = 6
    l73_count: int = 7
    freight_count: int = 8
    start_hour: int = 6
    end_hour: int = 14

    czas_podejscia: float = 0.8
    czas_wjazd_na_peron: float = 1.5
    czas_wyjazd_z_peronu: float = 1.5
    czas_odjazdu: float = 0.8
    czas_przejazd_568: float = 1.5
    czas_wjazd_568: float = 0.8
    czas_wyjazd_568: float = 0.8

    czas_podejscia_kopalnia: float = 3.5
    czas_dojazd_kopalnia: float = 2.5
    czas_wyjazd_kopalnia: float = 2.5

    czas_wagon_mu: float = 1.8
    czas_wagon_sigma: float = 0.5
    czas_wagon_min: float = 0.4

    freight_north_ratio: float = 0.4

    def copy(self):
        import copy
        return copy.copy(self)


@dataclass
class Pociag:
    id: int
    typ: str
    kategoria: str
    liczba_wagonow: int
    liczba_pasazerow: int
    czas_pojawienia: float
    planowany_odjazd: float
    kierunek: str
    linia: str

    czas_wjazdu: float = 0.0
    czas_na_peronie: float = 0.0
    czas_wyjazdu: float = 0.0
    opoznienie: float = 0.0
    przydzielony_tor: str = ""
    wagony_stan: List[bool] = field(default_factory=list)
    cel_kopalni: str = "rozladunek"
    kierunek_po_kopalni: str = "Poludnie"

    czas_oczekiwania_suma: float = 0.0
    czas_na_stacji: float = 0.0
    czas_obslugi_kopalnia: float = 0.0
    liczba_oczekiwan: int = 0
    wagony_obsluzone: int = 0

    def __post_init__(self):
        if self.typ == "Towarowy":
            self.cel_kopalni = random.choice(["zaladunek", "rozladunek"])
            self.wagony_stan = []
            for _ in range(self.liczba_wagonow):
                if self.cel_kopalni == "rozladunek":
                    self.wagony_stan.append(random.random() < 0.85)
                else:
                    self.wagony_stan.append(random.random() < 0.15)
        elif not self.wagony_stan:
            self.wagony_stan = []


@dataclass
class TruckState:
    id: int
    track_idx: int
    wagon_idx: int
    action: str
    spawn_time: float
    duration: float
    progress: float = 0.0
    transfer_done: bool = False


class SimulationEngine:
    def __init__(self, config: Optional[SimConfig] = None):
        self.env = simpy.Environment()
        self.config = config if config is not None else SimConfig()

        self.glowica_polnocna = simpy.PriorityResource(self.env, capacity=1)
        self.glowica_poludniowa = simpy.PriorityResource(self.env, capacity=1)

        self.tor1 = simpy.PriorityResource(self.env, capacity=1)
        self.tor2 = simpy.PriorityResource(self.env, capacity=1)
        self.tor3 = simpy.PriorityResource(self.env, capacity=1)
        self.tor4 = simpy.PriorityResource(self.env, capacity=1)
        self.szlak568 = simpy.PriorityResource(self.env, capacity=1)

        self.szlak_kopalnia = simpy.PriorityResource(self.env, capacity=1)
        self.kopalnia_tor = [
            simpy.PriorityResource(self.env, capacity=1) for _ in range(3)
        ]

        self.visual: Dict[int, dict] = {}
        self.trucks: List[TruckState] = []
        self.truck_counter = 0

        self.log: List[dict] = []
        self.pociagi_zakonczone: List[Pociag] = []
        self.all_trains: List[Pociag] = []
        self.sim_finished = False

        self.resource_timeline: List[dict] = []
        self.wagon_service_log: List[dict] = []
        self._last_timeline_t: float = -1.0

    @property
    def semafor_n_red(self):
        return len(self.glowica_polnocna.users) > 0

    @property
    def semafor_s_red(self):
        return len(self.glowica_poludniowa.users) > 0

    @property
    def semafor_kop_red(self):
        return len(self.szlak_kopalnia.users) > 0

    @property
    def kopalnia_occupancy(self):
        return [len(t.users) > 0 for t in self.kopalnia_tor]

    @property
    def has_station_activity(self):
        return len(self.visual) > 0

    def track_busy(self, name):
        res = {"tor1": self.tor1, "tor2": self.tor2,
               "tor3": self.tor3, "tor4": self.tor4,
               "568": self.szlak568, "kop_szlak": self.szlak_kopalnia}
        r = res.get(name)
        return len(r.users) > 0 if r else False

    def _czas(self, pociag: Pociag, bazowy: float) -> float:
        if pociag.typ == "Towarowy":
            mnoznik = 1.5
            if pociag.wagony_stan:
                zapalowanie = sum(pociag.wagony_stan) / len(pociag.wagony_stan)
                mnoznik += zapalowanie * 0.7
            return bazowy * mnoznik
        elif pociag.typ == "IC":
            return bazowy * 0.85
        return bazowy

    def _vs(self, pociag, segment, duration=0.0):
        self.visual[pociag.id] = {
            "segment": segment,
            "t0": self.env.now,
            "duration": max(duration, 0.001),
            "train": pociag,
        }

    def _vs_remove(self, pociag):
        self.visual.pop(pociag.id, None)

    def loguj(self, pociag, zdarzenie, szczegoly=""):
        czas = self.env.now
        h, m = int(czas // 60), int(czas % 60)
        self.log.append({
            "czas": czas, "czas_str": f"{h:02d}:{m:02d}",
            "pociag_id": pociag.id, "typ": pociag.typ,
            "kategoria": pociag.kategoria, "linia": pociag.linia,
            "kierunek": pociag.kierunek, "zdarzenie": zdarzenie,
            "szczegoly": szczegoly,
        })

    def _snapshot_timeline(self):
        t = int(self.env.now)
        if t == self._last_timeline_t:
            return
        self._last_timeline_t = t
        self.resource_timeline.append({
            "czas_min": t,
            "czas_str": f"{t//60:02d}:{t%60:02d}",
            "gl_polnocna": int(self.semafor_n_red),
            "gl_poludniowa": int(self.semafor_s_red),
            "tor1": int(self.track_busy("tor1")),
            "tor2": int(self.track_busy("tor2")),
            "tor3": int(self.track_busy("tor3")),
            "tor4": int(self.track_busy("tor4")),
            "tor568": int(self.track_busy("568")),
            "szlak_kopalni": int(self.track_busy("kop_szlak")),
            "kop_0": int(self.kopalnia_occupancy[0]),
            "kop_1": int(self.kopalnia_occupancy[1]),
            "kop_2": int(self.kopalnia_occupancy[2]),
            "aktywne_pociagi": len(self.visual),
        })

    def czas_wymiany_pasazerow(self, pociag):
        if pociag.liczba_pasazerow == 0:
            return 0.5
        mu = pociag.liczba_pasazerow * 1.2
        sigma = 10
        czas = 0.5 + random.lognormvariate(
            math.log(mu), math.log(1 + sigma / mu)) / 60.0
        return max(0.5, min(czas, 10.0))

    def _wait_with_visual(self, pociag, req, seg_wait, info_text=""):
        t_start = self.env.now
        self._vs(pociag, seg_wait)
        if info_text:
            self.loguj(pociag, info_text)
        yield req
        dt = self.env.now - t_start
        pociag.czas_oczekiwania_suma += dt
        if dt > 0.01:
            pociag.liczba_oczekiwan += 1

    def _przejazd_peron(self, pociag, tor_name, tor_res,
                        glowica_wjazd, glowica_wyjazd,
                        seg_approach, seg_wait, seg_enter, seg_at,
                        seg_wait_exit, seg_move, seg_cross, seg_depart):
        cfg = self.config
        priorytet = PRIORYTET_IC if pociag.typ == "IC" else PRIORYTET_REGIO
        pociag.przydzielony_tor = tor_name

        t_app = self._czas(pociag, cfg.czas_podejscia)
        self._vs(pociag, seg_approach, t_app)
        yield self.env.timeout(t_app)

        req_t = tor_res.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_t, seg_wait, f"Czeka na zwolnienie {tor_name}")

        req_g = glowica_wjazd.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_g, seg_wait, "Czeka na wjazd przez glowice")
        self.loguj(pociag, f"Zajal glowice wjazdowa + {tor_name}")

        t_ent = self._czas(pociag, cfg.czas_wjazd_na_peron)
        t_clear_in = min(self._czas(pociag, 0.15 + pociag.liczba_wagonow * 0.05), t_ent)

        self._vs(pociag, seg_enter, t_ent)
        yield self.env.timeout(t_clear_in)
        glowica_wjazd.release(req_g)
        yield self.env.timeout(t_ent - t_clear_in)

        pociag.czas_na_peronie = self.env.now
        czas_wym = self.czas_wymiany_pasazerow(pociag)
        pociag.czas_na_stacji += czas_wym
        self._vs(pociag, seg_at, czas_wym)
        self.loguj(pociag, f"Na {tor_name}", f"Wymiana: {czas_wym:.1f} min")
        yield self.env.timeout(czas_wym)

        t_move = self._czas(pociag, cfg.czas_wyjazd_z_peronu) * 0.6
        self._vs(pociag, seg_move, t_move)
        self.loguj(pociag, f"Podjezdza pod semafor wyjazdowy z {tor_name}")
        yield self.env.timeout(t_move)

        req_g2 = glowica_wyjazd.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_g2, seg_wait_exit, "Czeka na glowice wyjazdowa")

        t_cross = self._czas(pociag, cfg.czas_wyjazd_z_peronu) * 0.4
        t_clear_out = min(self._czas(pociag, 0.15 + pociag.liczba_wagonow * 0.05), t_cross)

        self._vs(pociag, seg_cross, t_cross)
        self.loguj(pociag, f"Wyjezdza z {tor_name}")
        yield self.env.timeout(t_clear_out)

        glowica_wyjazd.release(req_g2)
        tor_res.release(req_t)

        yield self.env.timeout(t_cross - t_clear_out)

        t_dep = self._czas(pociag, cfg.czas_odjazdu)
        self._vs(pociag, seg_depart, t_dep)
        yield self.env.timeout(t_dep)
        self._vs_remove(pociag)

    def l8_z_polnocy_regio(self, pociag):
        if len(self.tor1.users) == 0:
            tn, tr = "tor1", self.tor1
        elif len(self.tor2.users) == 0:
            tn, tr = "tor2", self.tor2
        else:
            tn, tr = "tor1", self.tor1
        yield self.env.process(self._przejazd_peron(
            pociag, tn, tr,
            self.glowica_polnocna, self.glowica_poludniowa,
            "approach_n", "wait_jct_n",
            f"enter_{tn}_from_n", f"at_{tn}",
            f"wait_exit_{tn}", f"move_{tn}_to_s", f"cross_{tn}_to_s", "depart_s"))

    def l8_z_polnocy_przelotowy(self, pociag):
        if len(self.szlak568.users) == 0:
            yield self.env.process(self._przejazd_568(pociag, "ns"))
        elif len(self.tor1.users) == 0:
            yield self.env.process(self._przejazd_peron(
                pociag, "tor1", self.tor1,
                self.glowica_polnocna, self.glowica_poludniowa,
                "approach_n", "wait_jct_n",
                "enter_tor1_from_n", "at_tor1",
                "wait_exit_tor1", "move_tor1_to_s", "cross_tor1_to_s", "depart_s"))
        elif len(self.tor2.users) == 0:
            yield self.env.process(self._przejazd_peron(
                pociag, "tor2", self.tor2,
                self.glowica_polnocna, self.glowica_poludniowa,
                "approach_n", "wait_jct_n",
                "enter_tor2_from_n", "at_tor2",
                "wait_exit_tor2", "move_tor2_to_s", "cross_tor2_to_s", "depart_s"))
        else:
            yield self.env.process(self._przejazd_568(pociag, "ns"))

    def l8_z_poludnia_regio(self, pociag):
        if len(self.tor2.users) == 0:
            tn, tr = "tor2", self.tor2
        elif len(self.tor1.users) == 0:
            tn, tr = "tor1", self.tor1
        else:
            tn, tr = "tor2", self.tor2
        yield self.env.process(self._przejazd_peron(
            pociag, tn, tr,
            self.glowica_poludniowa, self.glowica_polnocna,
            "approach_s", "wait_jct_s",
            f"enter_{tn}_from_s", f"at_{tn}",
            f"wait_exit_{tn}", f"move_{tn}_to_n", f"cross_{tn}_to_n", "depart_n"))

    def l8_z_poludnia_przelotowy(self, pociag):
        if len(self.szlak568.users) == 0:
            yield self.env.process(self._przejazd_568(pociag, "sn"))
        elif len(self.tor2.users) == 0:
            yield self.env.process(self._przejazd_peron(
                pociag, "tor2", self.tor2,
                self.glowica_poludniowa, self.glowica_polnocna,
                "approach_s", "wait_jct_s",
                "enter_tor2_from_s", "at_tor2",
                "wait_exit_tor2", "move_tor2_to_n", "cross_tor2_to_n", "depart_n"))
        elif len(self.tor1.users) == 0:
            yield self.env.process(self._przejazd_peron(
                pociag, "tor1", self.tor1,
                self.glowica_poludniowa, self.glowica_polnocna,
                "approach_s", "wait_jct_s",
                "enter_tor1_from_s", "at_tor1",
                "wait_exit_tor1", "move_tor1_to_n", "cross_tor1_to_n", "depart_n"))
        else:
            yield self.env.process(self._przejazd_568(pociag, "sn"))

    def _przejazd_568(self, pociag, direction):
        cfg = self.config
        priorytet = (PRIORYTET_IC if pociag.typ == "IC"
                     else PRIORYTET_TOWAROWY if pociag.typ == "Towarowy"
                     else PRIORYTET_REGIO)
        pociag.przydzielony_tor = "568"

        if direction == "ns":
            g_in, g_out = self.glowica_polnocna, self.glowica_poludniowa
            segs = ("approach_n", "wait_jct_n", "enter_568_from_n",
                    "on_568_ns", "wait_568_exit_s", "cross_568_to_s", "depart_s")
        else:
            g_in, g_out = self.glowica_poludniowa, self.glowica_polnocna
            segs = ("approach_s", "wait_jct_s", "enter_568_from_s",
                    "on_568_sn", "wait_568_exit_n", "cross_568_to_n", "depart_n")

        s_app, s_wait, s_enter, s_on, s_wexit, s_cross, s_dep = segs

        t_app = self._czas(pociag, cfg.czas_podejscia)
        self._vs(pociag, s_app, t_app)
        yield self.env.timeout(t_app)

        req_568 = self.szlak568.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_568, s_wait, "Czeka na wolny tor 568")

        req_g = g_in.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_g, s_wait, "Czeka na wjazd przez glowice")
        self.loguj(pociag, "Zajal glowice wjazdowa + 568")

        t_ent = self._czas(pociag, cfg.czas_wjazd_568)
        t_clear_in = min(self._czas(pociag, 0.15 + pociag.liczba_wagonow * 0.05), t_ent)

        self._vs(pociag, s_enter, t_ent)
        yield self.env.timeout(t_clear_in)
        g_in.release(req_g)
        yield self.env.timeout(t_ent - t_clear_in)

        t_on = self._czas(pociag, cfg.czas_przejazd_568)
        self._vs(pociag, s_on, t_on)
        self.loguj(pociag, "Przejazd 568 do semafora wyjazdowego")
        yield self.env.timeout(t_on)

        req_g2 = g_out.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_g2, s_wexit, "Czeka na glowice wyjazdowa")

        t_cross = self._czas(pociag, cfg.czas_wyjazd_568)
        t_clear_out = min(self._czas(pociag, 0.15 + pociag.liczba_wagonow * 0.05), t_cross)

        self._vs(pociag, s_cross, t_cross)
        self.loguj(pociag, "Wyjezdza z 568")
        yield self.env.timeout(t_clear_out)

        g_out.release(req_g2)
        self.szlak568.release(req_568)

        yield self.env.timeout(t_cross - t_clear_out)

        t_dep = self._czas(pociag, cfg.czas_odjazdu)
        self._vs(pociag, s_dep, t_dep)
        yield self.env.timeout(t_dep)
        self._vs_remove(pociag)

    def l73_z_poludnia(self, pociag):
        if len(self.tor4.users) == 0:
            tn, tr = "tor4", self.tor4
        else:
            tn, tr = "tor3", self.tor3

        yield self.env.process(self._przejazd_peron(
            pociag, tn, tr,
            self.glowica_poludniowa, self.glowica_polnocna,
            "approach_l73", "wait_jct_l73",
            f"enter_{tn}_from_s", f"at_{tn}",
            f"wait_exit_{tn}", f"move_{tn}_to_n", f"cross_{tn}_to_n", "depart_n"))

    def l73_z_polnocy(self, pociag):
        if len(self.tor3.users) == 0:
            tn, tr = "tor3", self.tor3
        else:
            tn, tr = "tor4", self.tor4

        yield self.env.process(self._przejazd_peron(
            pociag, tn, tr,
            self.glowica_polnocna, self.glowica_poludniowa,
            "approach_n", "wait_jct_n",
            f"enter_{tn}_from_n", f"at_{tn}",
            f"wait_exit_{tn}", f"move_{tn}_to_s", f"cross_{tn}_to_s", "depart_l73"))

    def _obsluz_wagony(self, pociag, track_idx):
        cfg = self.config
        wagony_do_obslugi = []
        for i, stan in enumerate(pociag.wagony_stan):
            if pociag.cel_kopalni == "zaladunek" and not stan:
                wagony_do_obslugi.append(i)
            elif pociag.cel_kopalni == "rozladunek" and stan:
                wagony_do_obslugi.append(i)

        if not wagony_do_obslugi:
            yield self.env.timeout(1.0)
            return

        for w_idx in wagony_do_obslugi:
            czas_w = max(cfg.czas_wagon_min,
                         random.gauss(cfg.czas_wagon_mu, cfg.czas_wagon_sigma))

            self.truck_counter += 1
            truck = TruckState(
                id=self.truck_counter,
                track_idx=track_idx,
                wagon_idx=w_idx,
                action=pociag.cel_kopalni,
                spawn_time=self.env.now,
                duration=czas_w,
            )
            self.trucks.append(truck)
            self._vs(pociag, f"loading_kop_{track_idx}", czas_w)

            yield self.env.timeout(czas_w * 0.5)

            if pociag.cel_kopalni == "zaladunek":
                pociag.wagony_stan[w_idx] = True
            else:
                pociag.wagony_stan[w_idx] = False
            truck.transfer_done = True

            yield self.env.timeout(czas_w * 0.5)
            if truck in self.trucks:
                self.trucks.remove(truck)

            pociag.wagony_obsluzone += 1
            pociag.czas_obslugi_kopalnia += czas_w
            self.wagon_service_log.append({
                "pociag_id": pociag.id,
                "wagon_idx": w_idx,
                "akcja": pociag.cel_kopalni,
                "tor_kopalni": track_idx,
                "czas_obslugi_min": czas_w,
                "czas_zakonczenia": self.env.now,
            })

    def kopalnia_freight(self, pociag):
        cfg = self.config
        priorytet = PRIORYTET_TOWAROWY

        t_app_s = self._czas(pociag, cfg.czas_podejscia)
        self._vs(pociag, "approach_s", t_app_s)
        yield self.env.timeout(t_app_s)

        wolne = [i for i in range(3) if len(self.kopalnia_tor[i].users) == 0]
        track_idx = wolne[0] if wolne else random.randint(0, 2)
        req_kt = self.kopalnia_tor[track_idx].request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_kt, "wait_jct_s", f"Rezerwuje Tor K{track_idx}")

        req_branch = self.szlak_kopalnia.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_branch, "wait_jct_s", "Czeka na szlak kopalni")

        req_g_in = self.glowica_poludniowa.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_g_in, "wait_jct_s", "Czeka na glowice S (dojazd kopalnia)")

        t_app_kop = self._czas(pociag, cfg.czas_podejscia_kopalnia)
        self._vs(pociag, "approach_kop", t_app_kop)

        t_clear_in = min(self._czas(pociag, 0.15 + pociag.liczba_wagonow * 0.05), t_app_kop)
        yield self.env.timeout(t_clear_in)
        self.glowica_poludniowa.release(req_g_in)
        yield self.env.timeout(t_app_kop - t_clear_in)

        t_doj = self._czas(pociag, cfg.czas_dojazd_kopalnia)
        self._vs(pociag, f"enter_kop_{track_idx}", t_doj)

        t_clear_branch = min(self._czas(pociag, 0.15 + pociag.liczba_wagonow * 0.05), t_doj)
        yield self.env.timeout(t_clear_branch)
        self.szlak_kopalnia.release(req_branch)
        yield self.env.timeout(t_doj - t_clear_branch)

        akcja = "Rozladunek" if pociag.cel_kopalni == "rozladunek" else "Zaladunek"
        self.loguj(pociag, f"{akcja} tor K{track_idx}")
        yield self.env.process(self._obsluz_wagony(pociag, track_idx))
        self.trucks = [t for t in self.trucks if t.track_idx != track_idx]

        req_branch2 = self.szlak_kopalnia.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_branch2, f"wait_exit_kop_{track_idx}",
            "Czeka na szlak do wyjazdu z kopalni")

        t_wyj = self._czas(pociag, cfg.czas_wyjazd_kopalnia)
        self._vs(pociag, f"exit_kop_{track_idx}", t_wyj)
        self.loguj(pociag, "Wyjezdza z kopalni na szlak dojazdowy")

        t_clear_k = min(self._czas(pociag, 0.15 + pociag.liczba_wagonow * 0.05), t_wyj)
        yield self.env.timeout(t_clear_k)
        self.kopalnia_tor[track_idx].release(req_kt)
        yield self.env.timeout(t_wyj - t_clear_k)

        t_dep_kop = self._czas(pociag, cfg.czas_podejscia_kopalnia)
        self._vs(pociag, "depart_kop", t_dep_kop)
        yield self.env.timeout(t_dep_kop)

        req_g_out = self.glowica_poludniowa.request(priority=priorytet)
        yield from self._wait_with_visual(
            pociag, req_g_out, "wait_jct_s", "Czeka na glowice S (wyjazd)")

        if pociag.kierunek_po_kopalni == "Polnoc":
            yield self.env.process(self._freight_after_kop_to_north(pociag, req_g_out, req_branch2))
        else:
            t_dep_s = self._czas(pociag, cfg.czas_odjazdu)
            self._vs(pociag, "depart_s", t_dep_s)

            t_clear_out = min(self._czas(pociag, 0.15 + pociag.liczba_wagonow * 0.05), t_dep_s)
            yield self.env.timeout(t_clear_out)

            self.szlak_kopalnia.release(req_branch2)
            self.glowica_poludniowa.release(req_g_out)

            yield self.env.timeout(t_dep_s - t_clear_out)
            self._vs_remove(pociag)

    def _freight_after_kop_to_north(self, pociag, req_g_s, req_branch_to_release=None):
        cfg = self.config
        priorytet = PRIORYTET_TOWAROWY
        t_clear_base = self._czas(pociag, 0.15 + pociag.liczba_wagonow * 0.05)

        if len(self.szlak568.users) == 0:
            pociag.przydzielony_tor = "568"
            req_568 = self.szlak568.request(priority=priorytet)
            yield req_568

            t_ent = self._czas(pociag, cfg.czas_wjazd_568)
            self._vs(pociag, "enter_568_from_s", t_ent)

            t_clear_in = min(t_clear_base, t_ent)
            yield self.env.timeout(t_clear_in)

            self.glowica_poludniowa.release(req_g_s)
            if req_branch_to_release:
                self.szlak_kopalnia.release(req_branch_to_release)

            yield self.env.timeout(t_ent - t_clear_in)

            t_on = self._czas(pociag, cfg.czas_przejazd_568)
            self._vs(pociag, "on_568_sn", t_on)
            yield self.env.timeout(t_on)

            req_g_n = self.glowica_polnocna.request(priority=priorytet)
            yield from self._wait_with_visual(
                pociag, req_g_n, "wait_568_exit_n", "Czeka na glowice N")

            t_ex = self._czas(pociag, cfg.czas_wyjazd_568)
            self._vs(pociag, "exit_568_to_n", t_ex)

            t_clear_out = min(t_clear_base, t_ex)
            yield self.env.timeout(t_clear_out)

            self.szlak568.release(req_568)
            self.glowica_polnocna.release(req_g_n)

            yield self.env.timeout(t_ex - t_clear_out)
        else:
            tn, tr = ("tor1", self.tor1) if len(self.tor1.users) == 0 else ("tor2", self.tor2)
            pociag.przydzielony_tor = tn
            req_t = tr.request(priority=priorytet)
            yield from self._wait_with_visual(
                pociag, req_t, "wait_jct_s", f"Czeka na {tn}")

            t_ent = self._czas(pociag, cfg.czas_wjazd_na_peron)
            self._vs(pociag, f"enter_{tn}_from_s", t_ent)

            t_clear_in = min(t_clear_base, t_ent)
            yield self.env.timeout(t_clear_in)

            self.glowica_poludniowa.release(req_g_s)
            if req_branch_to_release:
                self.szlak_kopalnia.release(req_branch_to_release)

            yield self.env.timeout(t_ent - t_clear_in)

            self._vs(pociag, f"at_{tn}", 0.5)
            yield self.env.timeout(0.5)

            req_g_n = self.glowica_polnocna.request(priority=priorytet)
            yield from self._wait_with_visual(
                pociag, req_g_n, f"wait_exit_{tn}", "Czeka na glowice N")

            t_ex = self._czas(pociag, cfg.czas_wyjazd_z_peronu)
            self._vs(pociag, f"exit_{tn}_to_n", t_ex)

            t_clear_out = min(t_clear_base, t_ex)
            yield self.env.timeout(t_clear_out)

            tr.release(req_t)
            self.glowica_polnocna.release(req_g_n)

            yield self.env.timeout(t_ex - t_clear_out)

        t_dep = self._czas(pociag, cfg.czas_odjazdu)
        self._vs(pociag, "depart_n", t_dep)
        yield self.env.timeout(t_dep)
        self._vs_remove(pociag)

    def obsluz_pociag(self, pociag):
        yield self.env.timeout(max(0, pociag.czas_pojawienia - self.env.now))
        pociag.czas_wjazdu = self.env.now
        self.loguj(pociag, "POJAWIL SIE")

        if pociag.linia == "Kopalnia":
            yield self.env.process(self.kopalnia_freight(pociag))
        elif pociag.linia == "L73":
            if pociag.kierunek == "Z_Polnocy":
                yield self.env.process(self.l73_z_polnocy(pociag))
            else:
                yield self.env.process(self.l73_z_poludnia(pociag))
        elif pociag.kierunek == "Z_Polnocy":
            if pociag.kategoria == "Przelotowy":
                yield self.env.process(self.l8_z_polnocy_przelotowy(pociag))
            else:
                yield self.env.process(self.l8_z_polnocy_regio(pociag))
        else:
            if pociag.kategoria == "Przelotowy":
                yield self.env.process(self.l8_z_poludnia_przelotowy(pociag))
            else:
                yield self.env.process(self.l8_z_poludnia_regio(pociag))

        pociag.czas_wyjazdu = self.env.now
        pociag.opoznienie = max(0, pociag.czas_wyjazdu - pociag.planowany_odjazd)
        self.pociagi_zakonczone.append(pociag)

    def zaladuj_pociagi(self, pociagi: List[Pociag]):
        self.all_trains = pociagi
        for pociag in pociagi:
            self.env.process(self.obsluz_pociag(pociag))

    def step(self, dt: float):
        if self.sim_finished:
            return

        if len(self.all_trains) > 0 and len(self.pociagi_zakonczone) >= len(self.all_trains):
            self.sim_finished = True
            self._snapshot_timeline()
            return

        target = self.env.now + dt
        try:
            self.env.run(until=target)
        except simpy.core.EmptySchedule:
            self.sim_finished = True
        self._snapshot_timeline()

    def update_truck_progress(self):
        for truck in self.trucks:
            elapsed = self.env.now - truck.spawn_time
            truck.progress = min(1.0, elapsed / truck.duration)

    def export_to_excel(self, path: str):
        done = self.pociagi_zakonczone

        df_trains = pd.DataFrame([{
            "id": p.id,
            "typ": p.typ,
            "kategoria": p.kategoria,
            "linia": p.linia,
            "kierunek": p.kierunek,
            "liczba_wagonow": p.liczba_wagonow,
            "liczba_pasazerow": p.liczba_pasazerow,
            "czas_pojawienia_min": round(p.czas_pojawienia, 2),
            "planowany_odjazd_min": round(p.planowany_odjazd, 2),
            "czas_wjazdu_min": round(p.czas_wjazdu, 2),
            "czas_wyjazdu_min": round(p.czas_wyjazdu, 2),
            "opoznienie_min": round(p.opoznienie, 2),
            "czas_oczekiwania_suma_min": round(p.czas_oczekiwania_suma, 2),
            "liczba_oczekiwan": p.liczba_oczekiwan,
            "czas_obslugi_kopalnia_min": round(p.czas_obslugi_kopalnia, 2),
            "wagony_obsluzone": p.wagony_obsluzone,
            "cel_kopalni": p.cel_kopalni if p.typ == "Towarowy" else "",
            "kierunek_po_kopalni": p.kierunek_po_kopalni if p.typ == "Towarowy" else "",
            "przydzielony_tor": p.przydzielony_tor,
        } for p in done])

        df_log = pd.DataFrame(self.log)
        df_wagons = pd.DataFrame(self.wagon_service_log)
        df_timeline = pd.DataFrame(self.resource_timeline)

        stats_rows = []
        if not df_trains.empty:
            for typ in sorted(df_trains["typ"].unique()):
                sub = df_trains[df_trains["typ"] == typ]
                stats_rows.append({
                    "typ": typ,
                    "liczba": len(sub),
                    "sr_opoznienie_min": round(sub["opoznienie_min"].mean(), 2),
                    "max_opoznienie_min": round(sub["opoznienie_min"].max(), 2),
                    "opoznione": int((sub["opoznienie_min"] > 0).sum()),
                    "sr_czas_oczekiwania_min": round(sub["czas_oczekiwania_suma_min"].mean(), 2),
                })
            stats_rows.append({
                "typ": "RAZEM",
                "liczba": len(df_trains),
                "sr_opoznienie_min": round(df_trains["opoznienie_min"].mean(), 2),
                "max_opoznienie_min": round(df_trains["opoznienie_min"].max(), 2),
                "opoznione": int((df_trains["opoznienie_min"] > 0).sum()),
                "sr_czas_oczekiwania_min": round(df_trains["czas_oczekiwania_suma_min"].mean(), 2),
            })
        df_stats = pd.DataFrame(stats_rows)

        util_rows = []
        if not df_timeline.empty:
            for col in ["gl_polnocna", "gl_poludniowa", "tor1", "tor2",
                        "tor3", "tor4", "tor568", "szlak_kopalni",
                        "kop_0", "kop_1", "kop_2"]:
                util_rows.append({
                    "zasob": col,
                    "wykorzystanie_proc": round(df_timeline[col].mean() * 100, 2),
                })
        df_util = pd.DataFrame(util_rows)

        with pd.ExcelWriter(path, engine="openpyxl") as w:
            df_trains.to_excel(w, sheet_name="pociagi", index=False)
            df_stats.to_excel(w, sheet_name="statystyki", index=False)
            df_util.to_excel(w, sheet_name="wykorzystanie_zasobow", index=False)
            df_timeline.to_excel(w, sheet_name="szereg_czasowy", index=False)
            df_wagons.to_excel(w, sheet_name="obsluga_wagonow", index=False)
            df_log.to_excel(w, sheet_name="log_zdarzen", index=False)

        return path


def czas_na_minuty(t) -> float:
    if isinstance(t, pd.Timestamp):
        return t.hour * 60 + t.minute + t.second / 60.0
    if isinstance(t, pd.Timedelta):
        return t.total_seconds() / 60.0
    s = str(t)
    parts = s.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _distribute_times(count: int, st: float, en: float) -> List[float]:
    if count <= 0: return []
    if count == 1: return [(st + en) / 2]
    step = (en - st) / count
    base_times = [st + (i + 0.5) * step for i in range(count)]
    return [t + random.uniform(-step * 0.15, step * 0.15) for t in base_times]


def _assign_freight_direction(p: Pociag, cfg: SimConfig):
    if p.typ == "Towarowy":
        p.kierunek_po_kopalni = "Polnoc" if random.random() < cfg.freight_north_ratio else "Poludnie"


def generuj_pociagi_z_config(config: SimConfig) -> List[Pociag]:
    pociagi = []
    pid = 1
    start = config.start_hour * 60
    end = config.end_hour * 60

    for i, t in enumerate(_distribute_times(config.l8_south_count, start, end)):
        is_ic = (i % 3 == 1)
        typ = "IC" if is_ic else "Regio"
        kat = "Przelotowy" if is_ic else "Zatrzymujacy"
        wag = random.randint(5, 8) if is_ic else random.randint(2, 4)
        pas = 0 if is_ic else random.randint(30, 200)
        odjazd = t + (0 if is_ic else random.randint(2, 5))
        pociagi.append(Pociag(pid, typ, kat, wag, pas, t, odjazd, "Z_Poludnia", "L8"))
        pid += 1

    for i, t in enumerate(_distribute_times(config.l8_north_count, start, end)):
        is_ic = (i % 3 == 1)
        typ = "IC" if is_ic else "Regio"
        kat = "Przelotowy" if is_ic else "Zatrzymujacy"
        wag = random.randint(5, 8) if is_ic else random.randint(2, 4)
        pas = 0 if is_ic else random.randint(30, 150)
        odjazd = t + (0 if is_ic else random.randint(2, 5))
        pociagi.append(Pociag(pid, typ, kat, wag, pas, t, odjazd, "Z_Polnocy", "L8"))
        pid += 1

    for t in _distribute_times(config.l73_count, start, end):
        wag = random.randint(2, 3)
        pas = random.randint(20, 100)
        odjazd = t + random.randint(2, 4)
        pociagi.append(Pociag(pid, "Regio", "Zatrzymujacy", wag, pas, t, odjazd, "Z_Poludnia", "L73"))
        pid += 1

    for t in _distribute_times(config.freight_count, start, end):
        wag = random.randint(3, 8)
        p = Pociag(pid, "Towarowy", "Kopalnia", wag, 0, t, t + 40, "Z_Poludnia", "Kopalnia")
        _assign_freight_direction(p, config)
        pociagi.append(p)
        pid += 1

    return sorted(pociagi, key=lambda p: p.czas_pojawienia)


def generuj_pociagi_kopalnia_default(config: SimConfig) -> List[Pociag]:
    pociagi = []
    pid = 100
    for t in _distribute_times(8, 360, 840):
        wagony = random.randint(3, 8)
        p = Pociag(
            id=pid, typ="Towarowy", kategoria="Kopalnia",
            liczba_wagonow=wagony, liczba_pasazerow=0,
            czas_pojawienia=t, planowany_odjazd=t + 40,
            kierunek="Z_Poludnia", linia="Kopalnia")
        _assign_freight_direction(p, config)
        pociagi.append(p)
        pid += 1
    return pociagi


def wczytaj_rozklad(plik_l8: str, plik_l73: str) -> List[Pociag]:
    pociagi = []
    pid = 1

    df = pd.read_excel(plik_l8, sheet_name="z_poludnia", header=0)
    for _, row in df.iterrows():
        pociagi.append(Pociag(
            id=pid, typ=row["typPociagu"], kategoria=row["kategoria"],
            liczba_wagonow=int(row["liczbaWagonow"]),
            liczba_pasazerow=int(row["liczbaPasazerow"]),
            czas_pojawienia=czas_na_minuty(row["czasPojawienia"]),
            planowany_odjazd=czas_na_minuty(row["planowanyOdjazd"]),
            kierunek="Z_Poludnia", linia="L8"))
        pid += 1

    df = pd.read_excel(plik_l8, sheet_name="z_polnocy", header=0)
    for _, row in df.iterrows():
        pociagi.append(Pociag(
            id=pid, typ=row["typPociagu"], kategoria=row["kategoria"],
            liczba_wagonow=int(row["liczbaWagonow"]),
            liczba_pasazerow=int(row["liczbaPasazerow"]),
            czas_pojawienia=czas_na_minuty(row["czasPojawienia"]),
            planowany_odjazd=czas_na_minuty(row["planowanyOdjazd"]),
            kierunek="Z_Polnocy", linia="L8"))
        pid += 1

    df = pd.read_excel(plik_l73, sheet_name="baza_pociagow_linia73", header=0)
    for _, row in df.iterrows():
        pociagi.append(Pociag(
            id=pid, typ=row["typPociagu"], kategoria=row["kategoria"],
            liczba_wagonow=int(row["liczbaWagonow"]),
            liczba_pasazerow=int(row["liczbaPasazerow"]),
            czas_pojawienia=czas_na_minuty(row["czasPojawienia"]),
            planowany_odjazd=czas_na_minuty(row["planowanyOdjazd"]),
            kierunek="Z_Poludnia", linia="L73"))
        pid += 1

    return sorted(pociagi, key=lambda p: p.czas_pojawienia)


def dane_wbudowane() -> List[Pociag]:
    pociagi = []
    pid = 1
    l8_pld = [(370, "Regio", "Zatrzymujacy", 2, 80, 373), (375, "IC", "Przelotowy", 6, 0, 375), (405, "Regio", "Zatrzymujacy", 3, 120, 409), (410, "IC", "Przelotowy", 7, 0, 410), (450, "Regio", "Zatrzymujacy", 2, 60, 453), (470, "IC", "Przelotowy", 6, 0, 470), (495, "Regio", "Zatrzymujacy", 4, 180, 499), (500, "IC", "Przelotowy", 8, 0, 500), (540, "Regio", "Zatrzymujacy", 2, 50, 543), (570, "IC", "Przelotowy", 6, 0, 570)]
    for cp, typ, kat, wag, pas, po in l8_pld:
        pociagi.append(Pociag(pid, typ, kat, wag, pas, cp, po, "Z_Poludnia", "L8"))
        pid += 1
    l8_pln = [(385, "Regio", "Przelotowy", 2, 0, 385), (435, "IC", "Zatrzymujacy", 6, 0, 438), (465, "Regio", "Przelotowy", 3, 120, 465), (490, "IC", "Zatrzymujacy", 7, 0, 493), (525, "Regio", "Przelotowy", 2, 60, 525), (560, "IC", "Zatrzymujacy", 6, 0, 563)]
    for cp, typ, kat, wag, pas, po in l8_pln:
        pociagi.append(Pociag(pid, typ, kat, wag, pas, cp, po, "Z_Polnocy", "L8"))
        pid += 1
    l73 = [(365, "Regio", "Zatrzymujacy", 2, 45, 368), (395, "Regio", "Zatrzymujacy", 2, 30, 398), (425, "Regio", "Zatrzymujacy", 3, 90, 428), (460, "Regio", "Zatrzymujacy", 2, 55, 463), (505, "Regio", "Zatrzymujacy", 2, 40, 508), (550, "Regio", "Zatrzymujacy", 2, 35, 553), (585, "Regio", "Zatrzymujacy", 3, 80, 588)]
    for cp, typ, kat, wag, pas, po in l73:
        pociagi.append(Pociag(pid, typ, kat, wag, pas, cp, po, "Z_Poludnia", "L73"))
        pid += 1
    return sorted(pociagi, key=lambda p: p.czas_pojawienia)


def create_simulation(use_excel=True, config: SimConfig = None) -> SimulationEngine:
    random.seed(RANDOM_SEED)
    if config is None:
        config = SimConfig()
    engine = SimulationEngine(config=config)

    if use_excel:
        try:
            pociagi = wczytaj_rozklad("baza_pociagow_linia8.xlsx", "baza_pociagow_linia73.xlsx")
            kop = generuj_pociagi_kopalnia_default(config)
            for p in pociagi:
                _assign_freight_direction(p, config)
            pociagi = sorted(pociagi + kop, key=lambda p: p.czas_pojawienia)
        except Exception:
            pociagi = dane_wbudowane()
            kop = generuj_pociagi_kopalnia_default(config)
            for p in pociagi:
                _assign_freight_direction(p, config)
            pociagi = sorted(pociagi + kop, key=lambda p: p.czas_pojawienia)
    else:
        pociagi = generuj_pociagi_z_config(config)

    engine.zaladuj_pociagi(pociagi)
    return engine