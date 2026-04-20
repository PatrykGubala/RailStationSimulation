import pygame
import math
import os
import datetime
from engine import (SimulationEngine, create_simulation, Pociag, SimConfig)

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (100, 100, 100)
LIGHT_GRAY = (180, 180, 180)
DARK_GRAY = (50, 50, 50)
BG_COLOR = (30, 35, 40)
PANEL_BG = (20, 25, 30)
EDIT_BG = (25, 30, 40)
BTN_COLOR = (60, 70, 90)

TRACK_COLOR = (160, 160, 160)
TRACK_568_COLOR = (140, 140, 170)
TRACK_L73_COLOR = (130, 170, 130)
TRACK_KOP_COLOR = (170, 140, 90)
PLATFORM_COLOR = (60, 65, 85)
PLATFORM_EDGE = (100, 105, 140)
PLATFORM_STRIPE = (80, 85, 115)

SIGNAL_RED = (220, 40, 40)
SIGNAL_GREEN = (40, 200, 40)
SIGNAL_DARK = (40, 40, 40)

COLOR_IC = (220, 60, 60)
COLOR_REGIO = (60, 140, 220)
COLOR_TOWAROWY = (180, 140, 60)
COLOR_WAGON = (80, 80, 80)
COLOR_WAGON_TOW_FULL = (180, 120, 40)
COLOR_WAGON_TOW_EMPTY = (80, 70, 50)

TRUCK_COLOR = (200, 170, 70)
TRUCK_LOADED = (150, 120, 50)

LABEL_COLOR = (200, 200, 200)
DELAY_COLOR = (255, 100, 100)
ONTIME_COLOR = (100, 255, 100)
HEADER_COLOR = (160, 180, 220)
EXPORT_COLOR = (80, 150, 120)


class TrackLayout:
    def __init__(self, ox: int, oy: int, scale: float = 1.0):
        self.ox = ox
        self.oy = oy
        self.s = scale

        self.y_top = self._y(-50)
        self.y_jct_n = self._y(50)
        self.y_tor_n = self._y(130)
        self.y_tor_mid = self._y(240)
        self.y_tor_s = self._y(350)
        self.y_jct_s = self._y(420)
        self.y_bot = self._y(520)

        self.x_568 = self._x(-70)
        self.x_tor1 = self._x(-20)
        self.x_tor2 = self._x(25)
        self.x_main = self._x(0)

        self.x_tor3 = self._x(80)
        self.x_tor4 = self._x(130)

        self.dual_offset = max(int(8 * scale), 6)

        self.x_l73_far = self._x(200)
        self.y_l73_split = self._y(460)

        self.kop_ox = self._x(310)
        self.kop_oy = self._y(180)
        self.kop_track_spacing = int(50 * scale)
        self.kop_track_len = int(140 * scale)

    def _x(self, v):
        return self.ox + int(v * self.s)

    def _y(self, v):
        return self.oy + int(v * self.s)

    def path_tor(self, name):
        paths = {
            "tor1": [(self.x_main, self.y_jct_n), (self.x_tor1, self.y_tor_n), (self.x_tor1, self.y_tor_s), (self.x_main, self.y_jct_s)],
            "tor2": [(self.x_main, self.y_jct_n), (self.x_tor2, self.y_tor_n), (self.x_tor2, self.y_tor_s), (self.x_main, self.y_jct_s)],
            "tor3": [(self.x_main, self.y_jct_n), (self.x_tor3, self.y_tor_n), (self.x_tor3, self.y_tor_s), (self.x_main, self.y_jct_s)],
            "tor4": [(self.x_main, self.y_jct_n), (self.x_tor4, self.y_tor_n), (self.x_tor4, self.y_tor_s), (self.x_main, self.y_jct_s)],
            "568":  [(self.x_main, self.y_jct_n), (self.x_568, self.y_tor_n), (self.x_568, self.y_tor_s), (self.x_main, self.y_jct_s)],
        }
        return paths.get(name, [])

    def x_of_tor(self, name):
        m = {"tor1": self.x_tor1, "tor2": self.x_tor2, "tor3": self.x_tor3, "tor4": self.x_tor4, "568": self.x_568}
        return m.get(name, self.x_main)

    def path_approach_n(self, direction: str):
        dx = -self.dual_offset if direction == "in" else self.dual_offset
        return [(self.x_main + dx, self.y_top - 40), (self.x_main + dx, self.y_jct_n - 6),
                (self.x_main, self.y_jct_n)]

    def path_approach_s(self, direction: str):
        dx = self.dual_offset if direction == "in" else -self.dual_offset
        return [(self.x_main + dx, self.y_bot + 40), (self.x_main + dx, self.y_jct_s + 6),
                (self.x_main, self.y_jct_s)]

    def path_l73_approach(self, direction: str):
        dx_v = int(self.dual_offset * 1.5) if direction == "in" else -int(self.dual_offset * 1.5)
        dx_d = int(self.dual_offset * 1.0) if direction == "in" else -int(self.dual_offset * 1.0)
        dy_d = -int(self.dual_offset * 1.5) if direction == "in" else int(self.dual_offset * 1.5)
        return [(self.x_l73_far + dx_v, self.y_bot + 40),
                (self.x_l73_far + dx_v, self.y_l73_split + dy_d),
                (self.x_main + int(30 * self.s) + dx_d, self.y_jct_s + int(15 * self.s) + dy_d),
                (self.x_main, self.y_jct_s)]

    def path_kopalnia_branch(self):
        return [(self.x_main, self.y_jct_s), (self._x(140), self.y_jct_s - 40), (self.kop_ox - 30, self.kop_oy + 30)]

    def path_kopalnia_track(self, idx):
        y = self.kop_oy + idx * self.kop_track_spacing
        return [(self.kop_ox - 30, y), (self.kop_ox, y), (self.kop_ox + self.kop_track_len, y)]


class Renderer:
    def __init__(self, screen: pygame.Surface, layout: TrackLayout):
        self.screen = screen
        self.L = layout
        self.font_sm = pygame.font.SysFont("consolas", 12)
        self.font_md = pygame.font.SysFont("consolas", 14)
        self.font_lg = pygame.font.SysFont("consolas", 18, bold=True)
        self.font_title = pygame.font.SysFont("consolas", 20, bold=True)
        self.export_button_rect = None

    def draw_tracks(self):
        L = self.L

        pygame.draw.lines(self.screen, TRACK_COLOR, False, L.path_approach_n("in"), 2)
        pygame.draw.lines(self.screen, TRACK_COLOR, False, L.path_approach_n("out"), 2)
        pygame.draw.lines(self.screen, TRACK_COLOR, False, L.path_approach_s("in"), 2)
        pygame.draw.lines(self.screen, TRACK_COLOR, False, L.path_approach_s("out"), 2)

        pygame.draw.lines(self.screen, TRACK_568_COLOR, False, L.path_tor("568"), 2)

        for n in ("tor1", "tor2"): pygame.draw.lines(self.screen, TRACK_COLOR, False, L.path_tor(n), 3)
        for n in ("tor3", "tor4"): pygame.draw.lines(self.screen, TRACK_L73_COLOR, False, L.path_tor(n), 3)

        pygame.draw.lines(self.screen, TRACK_L73_COLOR, False, L.path_l73_approach("in"), 2)
        pygame.draw.lines(self.screen, TRACK_L73_COLOR, False, L.path_l73_approach("out"), 2)

        self._draw_platform("P1", L.x_tor1, L.x_tor2)
        self._draw_platform("P2", L.x_tor3, L.x_tor4)

        pygame.draw.circle(self.screen, WHITE, (L.x_main, L.y_jct_n), 6)
        pygame.draw.circle(self.screen, WHITE, (L.x_main, L.y_jct_s), 6)

        pygame.draw.lines(self.screen, TRACK_KOP_COLOR, False, L.path_kopalnia_branch(), 2)
        for i in range(3):
            pygame.draw.lines(self.screen, TRACK_KOP_COLOR, False, L.path_kopalnia_track(i), 3)

        self._label("568", L.x_568 - 26, L.y_tor_mid - 6, TRACK_568_COLOR)
        self._label("T1", L.x_tor1 - 6, L.y_tor_n - 18, LABEL_COLOR)
        self._label("T2", L.x_tor2 - 6, L.y_tor_n - 18, LABEL_COLOR)
        self._label("T3", L.x_tor3 - 6, L.y_tor_n - 18, TRACK_L73_COLOR)
        self._label("T4", L.x_tor4 - 6, L.y_tor_n - 18, TRACK_L73_COLOR)
        self._label("Gl.N", L.x_main + 12, L.y_jct_n - 6, LIGHT_GRAY)
        self._label("Gl.S", L.x_main + 12, L.y_jct_s - 6, LIGHT_GRAY)
        self._label_md("POLNOC", L.x_main - 28, L.y_top - 60, LABEL_COLOR)
        self._label_md("POLUDNIE", L.x_main - 32, L.y_bot + 45, LABEL_COLOR)
        self._label("L73", L.x_l73_far - 10, L.y_bot + 45, TRACK_L73_COLOR)
        self._label("L8", (L.x_tor1 + L.x_tor2) // 2 - 6, L.y_tor_s + 8, TRACK_COLOR)
        self._label("L73", (L.x_tor3 + L.x_tor4) // 2 - 8, L.y_tor_s + 8, TRACK_L73_COLOR)

        self._label_lg("KOPALNIA TRZUSKAWICA", L.kop_ox - 20, L.kop_oy - 50, TRACK_KOP_COLOR)
        for i in range(3):
            y = L.kop_oy + i * L.kop_track_spacing
            self._label(f"K{i}", L.kop_ox + L.kop_track_len + 8, y - 6, TRACK_KOP_COLOR)

    def _draw_platform(self, label, x_left, x_right):
        L = self.L
        margin = int(6 * L.s)
        px = x_left + margin
        pw = (x_right - x_left) - 2 * margin
        ph = int((L.y_tor_s - L.y_tor_n) * 0.7)
        py = L.y_tor_n + int((L.y_tor_s - L.y_tor_n) * 0.15)

        pygame.draw.rect(self.screen, PLATFORM_COLOR, (px, py, pw, ph))
        pygame.draw.rect(self.screen, PLATFORM_EDGE, (px, py, pw, ph), 1)

        stripe_gap = max(int(14 * L.s), 8)
        for sy in range(py + 4, py + ph - 4, stripe_gap):
            pygame.draw.line(self.screen, PLATFORM_STRIPE, (px + 2, sy), (px + pw - 3, sy), 1)

        surf = self.font_sm.render(label, True, (180, 185, 210))
        cx = px + pw // 2 - surf.get_width() // 2
        self.screen.blit(surf, (cx, py + ph + 3))

    def draw_signals(self, engine: SimulationEngine):
        L = self.L
        r = max(int(5 * L.s), 3)

        def _sig(x, y, is_red):
            pygame.draw.rect(self.screen, SIGNAL_DARK, (x - 3, y - 14, 6, 28))
            pygame.draw.circle(self.screen, SIGNAL_RED if is_red else SIGNAL_DARK, (x, y - 5), r)
            pygame.draw.circle(self.screen, SIGNAL_GREEN if not is_red else SIGNAL_DARK, (x, y + 7), r)

        _sig(L.x_main - 25, L.y_jct_n, engine.semafor_n_red)
        _sig(L.x_main - 25, L.y_jct_s, engine.semafor_s_red)
        _sig(L.x_main + 25, L.y_jct_s - 10, engine.semafor_kop_red)

        _sig(L.kop_ox - 25, L.kop_oy + 40, engine.semafor_kop_red)

    def _pos_angle_with_offset(self, path, t, offset_px):
        if not path: return (0, 0), 90.0

        lengths = []
        for i in range(len(path) - 1):
            dx = path[i + 1][0] - path[i][0]
            dy = path[i + 1][1] - path[i][1]
            lengths.append(math.sqrt(dx * dx + dy * dy))
        total_len = sum(lengths)

        if total_len == 0: return path[0], 90.0

        target_dist = t * total_len - offset_px

        if target_dist <= 0:
            dx = path[1][0] - path[0][0]
            dy = path[1][1] - path[0][1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 0:
                nx, ny = dx / dist, dy / dist
                out_x = path[0][0] + nx * target_dist
                out_y = path[0][1] + ny * target_dist
                angle = math.degrees(math.atan2(dy, dx))
                return (int(out_x), int(out_y)), angle
            else:
                return path[0], 90.0

        acc = 0
        for i, sl in enumerate(lengths):
            if acc + sl >= target_dist:
                if sl == 0: continue
                lt = (target_dist - acc) / sl
                x = path[i][0] + (path[i + 1][0] - path[i][0]) * lt
                y = path[i][1] + (path[i + 1][1] - path[i][1]) * lt
                dx = path[i + 1][0] - path[i][0]
                dy = path[i + 1][1] - path[i][1]
                angle = math.degrees(math.atan2(dy, dx))
                return (int(x), int(y)), angle
            acc += sl

        dx = path[-1][0] - path[-2][0]
        dy = path[-1][1] - path[-2][1]
        angle = math.degrees(math.atan2(dy, dx))
        return path[-1], angle

    def _queue_path(self, seg: str, train: Pociag):
        L = self.L
        if seg == "wait_jct_n":
            return L.path_approach_n("in")
        if seg == "wait_jct_s":
            return L.path_approach_s("in")
        if seg == "wait_jct_l73":
            return L.path_l73_approach("in")
        if seg == "wait_kop_branch":
            return [(L.x_main, L.y_jct_s), (L._x(140), L.y_jct_s - 40)]
        if seg == "wait_kop_track":
            return [(L._x(140), L.y_jct_s - 40), (L.kop_ox - 30, L.kop_oy + 30)]
        if seg == "wait_568_exit_s":
            tp = L.path_tor("568")
            return [tp[1], tp[2]]
        if seg == "wait_568_exit_n":
            tp = L.path_tor("568")
            return [tp[2], tp[1]]
        for tn in ("tor1", "tor2", "tor3", "tor4"):
            if seg == f"wait_exit_{tn}":
                tx = L.x_of_tor(tn)
                if train.kierunek == "Z_Polnocy":
                    return [(tx, L.y_tor_n), (tx, L.y_tor_s)]
                else:
                    return [(tx, L.y_tor_s), (tx, L.y_tor_n)]
        for i in range(3):
            if seg == f"wait_exit_kop_{i}":
                return list(reversed(L.path_kopalnia_track(i)))
        return None

    def _get_path_and_progress(self, vs: dict):
        L = self.L
        seg = vs["segment"]
        t0 = vs["t0"]
        dur = vs["duration"]
        now = vs.get("now", t0)
        raw_t = min(1.0, (now - t0) / dur) if dur > 0 else 1.0
        train = vs["train"]

        if seg == "approach_n":
            return L.path_approach_n("in"), raw_t
        if seg == "approach_s":
            return L.path_approach_s("in"), raw_t
        if seg == "approach_l73":
            return L.path_l73_approach("in"), raw_t
        if seg == "approach_kop":
            return L.path_kopalnia_branch(), raw_t

        for tn in ("tor1", "tor2", "tor3", "tor4"):
            if seg == f"enter_{tn}_from_n":
                tx = L.x_of_tor(tn)
                return [(L.x_main, L.y_jct_n), (tx, L.y_tor_n), (tx, L.y_tor_mid)], raw_t
            if seg == f"enter_{tn}_from_s":
                tx = L.x_of_tor(tn)
                return [(L.x_main, L.y_jct_s), (tx, L.y_tor_s), (tx, L.y_tor_mid)], raw_t

        for tn in ("tor1", "tor2", "tor3", "tor4"):
            if seg == f"at_{tn}":
                tx = L.x_of_tor(tn)
                if train.kierunek == "Z_Polnocy":
                    return [(tx, L.y_tor_n), (tx, L.y_tor_mid)], 1.0
                else:
                    return [(tx, L.y_tor_s), (tx, L.y_tor_mid)], 1.0

        for tn in ("tor1", "tor2", "tor3", "tor4"):
            if seg == f"move_{tn}_to_s":
                tx = L.x_of_tor(tn)
                return [(tx, L.y_tor_mid), (tx, L.y_tor_s)], raw_t
            if seg == f"cross_{tn}_to_s":
                tx = L.x_of_tor(tn)
                return [(tx, L.y_tor_s), (L.x_main, L.y_jct_s)], raw_t
            if seg == f"move_{tn}_to_n":
                tx = L.x_of_tor(tn)
                return [(tx, L.y_tor_mid), (tx, L.y_tor_n)], raw_t
            if seg == f"cross_{tn}_to_n":
                tx = L.x_of_tor(tn)
                return [(tx, L.y_tor_n), (L.x_main, L.y_jct_n)], raw_t
            if seg == f"exit_{tn}_to_n":
                tx = L.x_of_tor(tn)
                return [(tx, L.y_tor_mid), (tx, L.y_tor_n), (L.x_main, L.y_jct_n)], raw_t

        tp = L.path_tor("568")
        if seg == "enter_568_from_n": return [tp[0], tp[1]], raw_t
        if seg == "enter_568_from_s": return [tp[3], tp[2]], raw_t
        if seg == "on_568_ns": return [tp[1], tp[2]], raw_t
        if seg == "on_568_sn": return [tp[2], tp[1]], raw_t
        if seg == "cross_568_to_s": return [tp[2], tp[3]], raw_t
        if seg == "cross_568_to_n": return [tp[1], tp[0]], raw_t
        if seg == "exit_568_to_n": return [tp[1], tp[0]], raw_t

        for i in range(3):
            if seg == f"enter_kop_{i}":
                return L.path_kopalnia_track(i), raw_t
            if seg == f"loading_kop_{i}":
                return L.path_kopalnia_track(i), 1.0
            if seg == f"exit_kop_{i}":
                return list(reversed(L.path_kopalnia_track(i))), raw_t
        if seg == "depart_kop":
            return list(reversed(L.path_kopalnia_branch())), raw_t

        if seg == "depart_s": return list(reversed(L.path_approach_s("out"))), raw_t
        if seg == "depart_n": return list(reversed(L.path_approach_n("out"))), raw_t
        if seg == "depart_l73": return list(reversed(L.path_l73_approach("out"))), raw_t

        return [(L.x_main, L.y_tor_n), (L.x_main, L.y_tor_mid)], 1.0

    def _train_color(self, pociag: Pociag):
        if pociag.typ == "IC": return COLOR_IC
        if pociag.typ == "Towarowy": return COLOR_TOWAROWY
        return COLOR_REGIO

    def draw_train(self, pociag, path, t):
        color = self._train_color(pociag)
        pos, angle = self._pos_angle_with_offset(path, t, 0)

        s = self.L.s
        loco_w = int(20 * s)
        loco_h = int(8 * s)
        wagon_w = int(14 * s)
        wagon_h = int(6 * s)
        gap = int(3 * s)

        rad = math.radians(angle)
        dx = math.cos(rad)
        dy = math.sin(rad)

        self._draw_rotated_rect(pos, loco_w, loco_h, angle, color)

        n_w = min(pociag.liczba_wagonow, 12)
        for i in range(n_w):
            dist = (loco_w / 2 + wagon_w / 2 + gap) + i * (wagon_w + gap)
            wx = pos[0] - dx * dist
            wy = pos[1] - dy * dist

            if pociag.typ == "Towarowy" and pociag.wagony_stan:
                if i < len(pociag.wagony_stan):
                    wc = COLOR_WAGON_TOW_FULL if pociag.wagony_stan[i] else COLOR_WAGON_TOW_EMPTY
                else:
                    wc = COLOR_WAGON_TOW_EMPTY
            else:
                wc = COLOR_WAGON
            self._draw_rotated_rect((int(wx), int(wy)), wagon_w, wagon_h, angle, wc)

        label = f"{pociag.typ[0]}{pociag.id}"
        lsurf = self.font_sm.render(label, True, WHITE)
        self.screen.blit(lsurf, (pos[0] + 14, pos[1] - 14))

    def draw_queued_dot(self, pociag, pos):
        color = self._train_color(pociag)
        s = self.L.s
        size = max(int(9 * s), 7)
        rect = pygame.Rect(pos[0] - size // 2, pos[1] - size // 2, size, size)
        pygame.draw.rect(self.screen, color, rect)
        pygame.draw.rect(self.screen, WHITE, rect, 1)

        label = f"{pociag.typ[0]}{pociag.id}"
        lsurf = self.font_sm.render(label, True, WHITE)
        self.screen.blit(lsurf, (pos[0] + size // 2 + 3, pos[1] - 8))

    def _draw_rotated_rect(self, center, w, h, angle, color):
        rad = math.radians(angle)
        ca, sa = math.cos(rad), math.sin(rad)
        hw, hh = w / 2, h / 2
        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        pts = [(int(cx * ca - cy * sa + center[0]),
                int(cx * sa + cy * ca + center[1]))
               for cx, cy in corners]
        pygame.draw.polygon(self.screen, color, pts)
        pygame.draw.polygon(self.screen, WHITE, pts, 1)

    def draw_trains(self, engine: SimulationEngine):
        now = engine.env.now

        waiting_groups: dict = {}
        active_moving = []

        for tid, vs in list(engine.visual.items()):
            vs["now"] = now
            seg = vs["segment"]
            if seg.startswith("wait_"):
                waiting_groups.setdefault(seg, []).append(vs)
            else:
                active_moving.append(vs)

        for vs in active_moving:
            path, t = self._get_path_and_progress(vs)
            self.draw_train(vs["train"], path, t)

        for seg, vs_list in waiting_groups.items():
            vs_list.sort(key=lambda x: x["t0"])
            sample_train = vs_list[0]["train"]
            path = self._queue_path(seg, sample_train)
            if not path:
                continue

            spacing = int(18 * self.L.s)
            for idx, vs in enumerate(vs_list):
                offset = idx * spacing
                pos, _ = self._pos_angle_with_offset(path, 1.0, offset)
                self.draw_queued_dot(vs["train"], pos)

    def draw_trucks(self, engine: SimulationEngine):
        L = self.L
        loco_w = int(20 * L.s)
        wagon_w = int(14 * L.s)
        gap = int(3 * L.s)

        for truck in engine.trucks:
            idx = truck.track_idx
            y_track = L.kop_oy + idx * L.kop_track_spacing
            y = y_track + int(18 * L.s)

            dist = (loco_w / 2 + wagon_w / 2 + gap) + truck.wagon_idx * (wagon_w + gap)
            wagon_x = L.kop_ox + L.kop_track_len - dist

            if truck.progress <= 0.5:
                t = truck.progress / 0.5
                x = wagon_x + int((1.0 - t) * 60 * L.s)
            else:
                t = (truck.progress - 0.5) / 0.5
                x = wagon_x + int(t * 60 * L.s)

            if truck.action == "rozladunek":
                color = TRUCK_LOADED if truck.transfer_done else TRUCK_COLOR
            else:
                color = TRUCK_COLOR if truck.transfer_done else TRUCK_LOADED

            tw, th = int(14 * L.s), int(8 * L.s)
            pygame.draw.rect(self.screen, color, (x - tw // 2, y - th // 2, tw, th))
            pygame.draw.rect(self.screen, DARK_GRAY, (x + tw // 2, y - th // 2 + 1, 4, th - 2))

        for i in range(3):
            occ = engine.kopalnia_occupancy[i]
            y = L.kop_oy + i * L.kop_track_spacing - int(14 * L.s)
            pygame.draw.rect(self.screen, DARK_GRAY, (L.kop_ox, y, L.kop_track_len, 4))
            if occ:
                pygame.draw.rect(self.screen, COLOR_TOWAROWY, (L.kop_ox, y, L.kop_track_len, 4))

    def draw_panel(self, engine: SimulationEngine, speed_mult, idle_speed_mult, active_speed_mult, paused, auto_speed):
        sw = self.screen.get_width()
        panel_x = sw - 320
        panel_w = 310
        panel_y = 10
        panel_h = self.screen.get_height() - 20

        pygame.draw.rect(self.screen, PANEL_BG, (panel_x, panel_y, panel_w, panel_h))
        pygame.draw.rect(self.screen, GRAY, (panel_x, panel_y, panel_w, panel_h), 1)

        y = panel_y + 10
        x = panel_x + 10

        self._pt(self.font_title, "SITKOWKA NOWINY", x, y, WHITE)
        y += 26

        now = engine.env.now
        h, m = int(now // 60), int(now % 60)
        self._pt(self.font_md, f"Czas: {h:02d}:{m:02d}", x, y, LABEL_COLOR)
        y += 18

        if paused: state = "PAUZA"
        elif auto_speed:
            if engine.has_station_activity:
                state = f"AUTO (Akcja x{active_speed_mult:.1f})"
            else:
                state = f"AUTO (Czekanie x{idle_speed_mult:.1f})"
        else: state = f"RECZNY (Sztywne x{speed_mult:.1f})"

        self._pt(self.font_md, f"Tryb: {state}", x, y, LABEL_COLOR)
        y += 18

        if auto_speed:
            self._pt(self.font_sm, f"  [+/-] Czekanie: x{idle_speed_mult:.1f}", x, y, GRAY)
            y += 14
            self._pt(self.font_sm, f"  [Shift +/-] Akcja: x{active_speed_mult:.1f}", x, y, GRAY)
            y += 14

        y += 8
        self._pt(self.font_md, "ZASOBY STACJI", x, y, HEADER_COLOR)
        y += 16
        resources = [
            ("Gl.Polnocna", engine.semafor_n_red),
            ("Gl.Poludniowa", engine.semafor_s_red),
            ("Tor 1 (L8)", engine.track_busy("tor1")),
            ("Tor 2 (L8)", engine.track_busy("tor2")),
            ("Tor 3 (L73)", engine.track_busy("tor3")),
            ("Tor 4 (L73)", engine.track_busy("tor4")),
            ("Tor 568", engine.track_busy("568")),
            ("Szlak Kopalni", engine.track_busy("kop_szlak")),
        ]
        for name, busy in resources:
            c = SIGNAL_RED if busy else SIGNAL_GREEN
            pygame.draw.circle(self.screen, c, (x + 5, y + 6), 3)
            self._pt(self.font_sm, f"  {name}", x + 8, y, LABEL_COLOR)
            y += 14

        y += 4
        self._pt(self.font_md, "KOPALNIA", x, y, HEADER_COLOR)
        y += 16
        for i in range(3):
            occ = engine.kopalnia_occupancy[i]
            c = SIGNAL_RED if occ else SIGNAL_GREEN
            pygame.draw.circle(self.screen, c, (x + 5, y + 6), 3)
            self._pt(self.font_sm, f"  Tor K{i}", x + 8, y, LABEL_COLOR)
            y += 14

        y += 4
        self._pt(self.font_md, "AKTYWNE POCIAGI", x, y, HEADER_COLOR)
        y += 16
        active = sorted(engine.visual.values(), key=lambda v: v["train"].id)
        for vs in active[:8]:
            tr = vs["train"]
            c = self._train_color(tr)
            seg = vs["segment"][:20]
            self._pt(self.font_sm, f"#{tr.id:3d} {tr.typ:4s} {tr.linia:3s} {seg}", x, y, c)
            y += 13
            if y > panel_y + panel_h - 150:
                self._pt(self.font_sm, "...", x, y, GRAY)
                y += 13
                break

        y = panel_y + panel_h - 130
        self._pt(self.font_md, "STATYSTYKI", x, y, HEADER_COLOR)
        y += 16
        done = engine.pociagi_zakonczone
        total = len(engine.all_trains)
        self._pt(self.font_md, f"Obsluzono: {len(done)} / {total}", x, y, WHITE)
        y += 18
        delayed = [p for p in done if p.opoznienie > 0]
        dc = DELAY_COLOR if delayed else ONTIME_COLOR
        self._pt(self.font_sm, f"Opoznionych: {len(delayed)}", x, y, dc)
        y += 14
        if done:
            avg = sum(p.opoznienie for p in done) / len(done)
            mx = max(p.opoznienie for p in done)
            self._pt(self.font_sm, f"Sr: {avg:.1f}min  Max: {mx:.1f}min", x, y, LABEL_COLOR)
            y += 14
            avg_wait = sum(p.czas_oczekiwania_suma for p in done) / len(done)
            self._pt(self.font_sm, f"Sr.oczekiwanie: {avg_wait:.1f}min", x, y, LABEL_COLOR)
        y += 18

        btn = pygame.Rect(x, y, panel_w - 20, 26)
        self.export_button_rect = btn
        pygame.draw.rect(self.screen, EXPORT_COLOR, btn)
        pygame.draw.rect(self.screen, WHITE, btn, 1)
        surf = self.font_md.render("[X] Eksport do Excel", True, WHITE)
        self.screen.blit(surf, (btn.x + (btn.w - surf.get_width()) // 2, btn.y + 5))

    def draw_summary(self, engine: SimulationEngine, export_info: str = ""):
        sw, sh = self.screen.get_size()
        pw, ph = 480, 400
        px, py = (sw - pw) // 2, (sh - ph) // 2

        overlay = pygame.Surface((sw, sh))
        overlay.set_alpha(160)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        pygame.draw.rect(self.screen, EDIT_BG, (px, py, pw, ph))
        pygame.draw.rect(self.screen, LIGHT_GRAY, (px, py, pw, ph), 2)

        x = px + 25
        y = py + 25
        self._pt(self.font_title, "=== WYNIKI SYMULACJI ===", x, y, HEADER_COLOR)
        y += 40

        done = engine.pociagi_zakonczone
        total = len(done)
        all_expected = len(engine.all_trains)
        ic_count = sum(1 for p in done if p.typ == "IC")
        regio_count = sum(1 for p in done if p.typ == "Regio")
        tow_count = sum(1 for p in done if p.typ == "Towarowy")

        self._pt(self.font_md, f"Obsluzone pociagi: {total} / {all_expected}", x, y, WHITE)
        y += 25
        self._pt(self.font_md, f"- InterCity (IC): {ic_count}", x + 15, y, COLOR_IC)
        y += 20
        self._pt(self.font_md, f"- Regionalne (Regio): {regio_count}", x + 15, y, COLOR_REGIO)
        y += 20
        self._pt(self.font_md, f"- Towarowe (Kopalnia): {tow_count}", x + 15, y, COLOR_TOWAROWY)
        y += 30

        if total > 0:
            avg_delay = sum(p.opoznienie for p in done) / total
            max_delay = max(p.opoznienie for p in done)
            delayed_count = sum(1 for p in done if p.opoznienie > 0)
            avg_wait = sum(p.czas_oczekiwania_suma for p in done) / total
            self._pt(self.font_md, f"Srednie opoznienie:     {avg_delay:.2f} min", x, y, LABEL_COLOR)
            y += 22
            self._pt(self.font_md, f"Maksymalne opoznienie:  {max_delay:.2f} min", x, y, LABEL_COLOR)
            y += 22
            self._pt(self.font_md, f"Sredni czas oczekiwania:{avg_wait:.2f} min", x, y, LABEL_COLOR)
            y += 22
            self._pt(self.font_md, f"Pociagi opoznione:      {delayed_count} / {total}", x, y, LABEL_COLOR)
        else:
            self._pt(self.font_md, "Brak obsluzonych pociagow.", x, y, GRAY)

        y += 35
        if export_info:
            self._pt(self.font_sm, export_info, x, y, ONTIME_COLOR)
            y += 20
        self._pt(self.font_sm, "[X] Eksport  [R] Restart  [Q] Wyjscie", px + 80, py + ph - 30, LIGHT_GRAY)

    def _pt(self, font, text, x, y, color):
        self.screen.blit(font.render(text, True, color), (x, y))

    def _label(self, t, x, y, c):
        self._pt(self.font_sm, t, x, y, c)

    def _label_md(self, t, x, y, c):
        self._pt(self.font_md, t, x, y, c)

    def _label_lg(self, t, x, y, c):
        self._pt(self.font_lg, t, x, y, c)

    def draw_controls(self, show_editor):
        y = self.screen.get_height() - 28
        if show_editor: t = "[E] Zamknij  [G] Zastosuj  [ESC] Anuluj"
        else: t = "[SPACE] Pauza  [+/-] Pr.Czekania  [Shift+/-] Pr.Akcji  [A] Auto  [E] Edytor  [X] Eksport  [Q] Wyjscie"
        self._pt(self.font_sm, t, 10, y, LIGHT_GRAY)


class EditorPanel:
    def __init__(self, config: SimConfig):
        self.config = config
        self.visible = False
        self.font = pygame.font.SysFont("consolas", 13)
        self.font_lg = pygame.font.SysFont("consolas", 18, bold=True)
        self.fields = [
            ("L8 z Poludnia (ilosc)", "l8_south_count", 1, 50, 1, False),
            ("L8 z Polnocy (ilosc)", "l8_north_count", 1, 50, 1, False),
            ("L73 (ilosc)", "l73_count", 0, 50, 1, False),
            ("Towarowe (ilosc)", "freight_count", 0, 50, 1, False),
            ("Godzina start", "start_hour", 0, 23, 1, False),
            ("Godzina koniec", "end_hour", 1, 24, 1, False),
            ("Podjazd kopalnia [min]", "czas_podejscia_kopalnia", 0.1, 5.0, 0.1, True),
            ("Dojazd kopalnia [min]", "czas_dojazd_kopalnia", 0.2, 5.0, 0.2, True),
            ("Wyjazd kopalnia [min]", "czas_wyjazd_kopalnia", 0.2, 5.0, 0.2, True),
            ("Wagon: mu [min]", "czas_wagon_mu", 0.2, 10.0, 0.2, True),
            ("Wagon: sigma [min]", "czas_wagon_sigma", 0.0, 5.0, 0.1, True),
            ("Udzial tow. na polnoc", "freight_north_ratio", 0.0, 1.0, 0.1, True),
        ]
        self.buttons = []

    def toggle(self):
        self.visible = not self.visible

    def draw(self, screen):
        if not self.visible: return
        sw, sh = screen.get_size()
        pw, ph = 460, 40 + len(self.fields) * 32 + 80
        px = (sw - pw) // 2
        py = (sh - ph) // 2

        pygame.draw.rect(screen, EDIT_BG, (px, py, pw, ph))
        pygame.draw.rect(screen, LIGHT_GRAY, (px, py, pw, ph), 2)

        self.buttons.clear()
        y = py + 12
        x = px + 15

        screen.blit(self.font_lg.render("PARAMETRY SYMULACJI", True, WHITE), (x, y))
        y += 28

        for label, attr, vmin, vmax, step, is_float in self.fields:
            val = getattr(self.config, attr)
            screen.blit(self.font.render(f"{label}:", True, LABEL_COLOR), (x, y + 2))

            vx = px + pw - 130
            val_str = f"{val:5.2f}" if is_float else f"{val:4d}"
            screen.blit(self.font.render(val_str, True, WHITE), (vx + 25, y + 2))

            bm = pygame.Rect(vx, y, 22, 22)
            pygame.draw.rect(screen, BTN_COLOR, bm)
            pygame.draw.rect(screen, LIGHT_GRAY, bm, 1)
            screen.blit(self.font.render("-", True, WHITE), (vx + 7, y + 1))
            self.buttons.append((bm, attr, -step, vmin, vmax, is_float))

            bp = pygame.Rect(vx + 85, y, 22, 22)
            pygame.draw.rect(screen, BTN_COLOR, bp)
            pygame.draw.rect(screen, LIGHT_GRAY, bp, 1)
            screen.blit(self.font.render("+", True, WHITE), (vx + 91, y + 1))
            self.buttons.append((bp, attr, step, vmin, vmax, is_float))

            y += 32

        y += 8
        font_info = pygame.font.SysFont("consolas", 11)
        screen.blit(font_info.render("* Pociagi sa rozkladane rownomiernie w oknie czasu", True, GRAY), (x, y))
        y += 14
        screen.blit(font_info.render("* Udzial tow. na polnoc: czesc pociagow z kopalni jedzie dalej na N", True, GRAY), (x, y))

        y += 24
        ab = pygame.Rect(px + pw // 2 - 90, y, 180, 30)
        pygame.draw.rect(screen, (50, 120, 70), ab)
        pygame.draw.rect(screen, LIGHT_GRAY, ab, 1)
        surf = self.font.render("[G] Zastosuj & Reset", True, WHITE)
        screen.blit(surf, (ab.x + (180 - surf.get_width()) // 2, y + 6))

    def handle_click(self, pos):
        if not self.visible: return False
        for rect, attr, delta, vmin, vmax, is_float in self.buttons:
            if rect.collidepoint(pos):
                cur = getattr(self.config, attr)
                new_val = cur + delta
                new_val = max(vmin, min(vmax, new_val))
                if is_float:
                    new_val = round(new_val, 2)
                else:
                    new_val = int(new_val)
                setattr(self.config, attr, new_val)
                return True
        return False


def _export_current(engine: SimulationEngine) -> str:
    out_dir = "wyniki_symulacji"
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"symulacja_{ts}.xlsx")
    try:
        engine.export_to_excel(path)
        return f"Zapisano: {path}"
    except Exception as e:
        return f"Blad eksportu: {e}"


def run_visualization():
    pygame.init()

    info = pygame.display.Info()
    W = min(1500, info.current_w - 80)
    H = min(850, info.current_h - 80)
    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    pygame.display.set_caption("Symulacja Sitkowka Nowiny + Kopalnia Trzuskawica")

    clock = pygame.time.Clock()
    FPS = 60

    def make_layout(w, h):
        s = min(w / 1050, h / 720) * 0.85
        return TrackLayout(ox=int(w * 0.12), oy=int(h * 0.18), scale=s)

    layout = make_layout(W, H)
    renderer = Renderer(screen, layout)

    config = SimConfig()
    editor = EditorPanel(config)

    engine = create_simulation(use_excel=True, config=config)

    paused = False
    export_info = ""
    export_info_timer = 0.0

    idle_speed_mult = 120.0
    active_speed_mult = 1.0
    speed_mult = active_speed_mult
    auto_speed = True
    running = True

    while running:
        dt_real = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                mods = pygame.key.get_mods()
                if event.key == pygame.K_q:
                    if not editor.visible: running = False
                elif event.key == pygame.K_ESCAPE:
                    if editor.visible: editor.visible = False
                    else: running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    if auto_speed:
                        if mods & pygame.KMOD_SHIFT:
                            active_speed_mult = min(active_speed_mult * 1.5, 60.0)
                        else:
                            idle_speed_mult = min(idle_speed_mult * 1.5, 300.0)
                    else:
                        speed_mult = min(speed_mult * 1.5, 60.0)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    if auto_speed:
                        if mods & pygame.KMOD_SHIFT:
                            active_speed_mult = max(active_speed_mult / 1.5, 0.1)
                        else:
                            idle_speed_mult = max(idle_speed_mult / 1.5, 2.0)
                    else:
                        speed_mult = max(speed_mult / 1.5, 0.1)
                elif event.key == pygame.K_a:
                    auto_speed = not auto_speed
                elif event.key == pygame.K_e:
                    editor.toggle()
                    if editor.visible: paused = True
                elif event.key == pygame.K_r:
                    engine = create_simulation(use_excel=True, config=config)
                    paused = False
                    export_info = ""
                elif event.key == pygame.K_g:
                    engine = create_simulation(use_excel=False, config=config)
                    editor.visible = False
                    paused = False
                    export_info = ""
                elif event.key == pygame.K_x:
                    export_info = _export_current(engine)
                    export_info_timer = 5.0
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if editor.handle_click(event.pos):
                        pass
                    elif renderer.export_button_rect and renderer.export_button_rect.collidepoint(event.pos):
                        export_info = _export_current(engine)
                        export_info_timer = 5.0
            elif event.type == pygame.VIDEORESIZE:
                W, H = event.w, event.h
                screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
                layout = make_layout(W, H)
                renderer = Renderer(screen, layout)

        if auto_speed and not paused:
            if engine.has_station_activity:
                speed_mult = active_speed_mult
            else:
                speed_mult = idle_speed_mult

        if not paused and not engine.sim_finished:
            sim_dt = dt_real * speed_mult
            engine.step(sim_dt)
            engine.update_truck_progress()

        if export_info_timer > 0:
            export_info_timer -= dt_real
            if export_info_timer <= 0:
                export_info = ""

        screen.fill(BG_COLOR)

        gc = (38, 42, 48)
        for gx in range(0, W, 50): pygame.draw.line(screen, gc, (gx, 0), (gx, H))
        for gy in range(0, H, 50): pygame.draw.line(screen, gc, (0, gy), (W, gy))

        renderer.draw_tracks()
        renderer.draw_signals(engine)
        renderer.draw_trucks(engine)
        renderer.draw_trains(engine)
        renderer.draw_panel(engine, speed_mult, idle_speed_mult, active_speed_mult, paused, auto_speed)
        renderer.draw_controls(editor.visible)

        if export_info:
            surf = renderer.font_md.render(export_info, True, ONTIME_COLOR)
            screen.blit(surf, (10, H - 52))

        editor.draw(screen)

        if engine.sim_finished:
            renderer.draw_summary(engine, export_info)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    run_visualization()