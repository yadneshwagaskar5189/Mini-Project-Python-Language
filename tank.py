"""
TANK STARS - 2 Player Hot-Seat Arcade Game (Upgraded)
=====================================================
Controls:
    A / D         - Drive tank left / right (uses fuel)
    LEFT / RIGHT  - Aim barrel
    SPACE (hold)  - Charge power, release to fire
    1 / 2 / 3     - Switch weapon (Shell / Bomb / Triple)
    ENTER         - Start / Restart
    ESC           - Quit

Each turn you get fuel to drive AND one shot. Driving uses fuel.
Firing ends your turn.

Requirements: pygame  (pip install pygame)
Run: python tank_stars.py
"""

import math
import random
import sys
import array

import pygame

# ---------- CONFIG ----------
WIDTH, HEIGHT = 1100, 650
FPS = 60

# Sky gradient (dawn / soft blue)
SKY_TOP = (60, 90, 150)
SKY_MID = (180, 130, 140)
SKY_BOTTOM = (240, 200, 170)

GROUND_COLOR = (95, 140, 75)
GROUND_DARK = (55, 90, 50)
GROUND_DIRT = (110, 80, 55)
GROUND_DIRT_DARK = (75, 50, 35)

P1_COLOR = (220, 70, 70)
P2_COLOR = (70, 130, 230)
TEXT_COLOR = (245, 245, 245)

GRAVITY = 0.35
MAX_POWER = 22.0
POWER_RATE = 0.45

FUEL_PER_TURN = 100
DRIVE_COST = 0.6           # fuel cost per pixel of movement
DRIVE_SPEED = 1.2          # pixels per frame while held
MAX_SLOPE = 30             # max climbable slope per pixel (px)

# ---------- INIT ----------
pygame.init()
pygame.mixer.pre_init(44100, -16, 1, 512)
try:
    pygame.mixer.init()
    SOUND_OK = True
except pygame.error:
    SOUND_OK = False

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Tank Stars")
clock = pygame.time.Clock()

font_sm = pygame.font.SysFont("arial", 16, bold=True)
font_md = pygame.font.SysFont("arial", 22, bold=True)
font_lg = pygame.font.SysFont("arial", 48, bold=True)
font_xl = pygame.font.SysFont("arial", 72, bold=True)


# ---------- PROCEDURAL SOUNDS ----------
def make_sound(freq=440, duration=0.15, volume=0.3, decay=True, noise=False):
    if not SOUND_OK:
        return None
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    buf = array.array("h")
    amp = int(32767 * volume)
    for i in range(n_samples):
        t = i / sample_rate
        env = (1.0 - i / n_samples) if decay else 1.0
        if noise:
            val = (random.random() * 2 - 1) * amp * env
        else:
            val = math.sin(2 * math.pi * freq * t) * amp * env
        buf.append(int(val))
    return pygame.mixer.Sound(buffer=buf.tobytes())


snd_fire = make_sound(220, 0.18, 0.35, noise=True)
snd_explode = make_sound(80, 0.45, 0.45, noise=True)
snd_charge = make_sound(330, 0.05, 0.15)
snd_hit = make_sound(150, 0.25, 0.4, noise=True)
snd_click = make_sound(660, 0.05, 0.2)
snd_engine = make_sound(110, 0.08, 0.15, noise=True)


def play(s):
    if s is not None:
        s.play()


# ---------- TERRAIN ----------
class Terrain:
    """Heightmap-based destructible terrain."""

    def __init__(self):
        self.heights = self._generate()
        # Cache for the rendered terrain surface (rebuilt when destroyed)
        self._surface = None
        self._dirty = True

    def _generate(self):
        heights = [0.0] * WIDTH
        base = HEIGHT - 140
        amp1, freq1 = 55, 0.004
        amp2, freq2 = 28, 0.011
        amp3, freq3 = 13, 0.025
        offset = random.uniform(0, 1000)
        for x in range(WIDTH):
            y = (base
                 - math.sin(x * freq1 + offset) * amp1
                 - math.sin(x * freq2 + offset * 1.3) * amp2
                 - math.sin(x * freq3 + offset * 0.7) * amp3)
            heights[x] = y
        return heights

    def height_at(self, x):
        x = int(max(0, min(WIDTH - 1, x)))
        return self.heights[x]

    def deform(self, cx, cy, radius):
        """Carve a crater into the terrain at (cx, cy) with given radius."""
        x0 = max(0, int(cx - radius))
        x1 = min(WIDTH, int(cx + radius))
        for x in range(x0, x1):
            dx = x - cx
            # circle equation: y_offset = sqrt(r^2 - dx^2) below the impact center
            inside = radius * radius - dx * dx
            if inside <= 0:
                continue
            dy = math.sqrt(inside)
            crater_top = cy - dy
            crater_bot = cy + dy
            # Lower the surface to at least crater_bot if the impact is at/above current ground
            if self.heights[x] < crater_bot:
                # If current surface sits inside the circle, push it down
                if self.heights[x] >= crater_top:
                    self.heights[x] = min(HEIGHT - 5, crater_bot)
        self._dirty = True

    def _build_surface(self):
        surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        # Build polygon for grass body
        points = [(x, self.heights[x]) for x in range(0, WIDTH, 2)]
        points.append((WIDTH, HEIGHT))
        points.append((0, HEIGHT))
        pygame.draw.polygon(surf, GROUND_COLOR, points)

        # Darker dirt body underneath
        dirt_band_top = [(x, self.heights[x] + 14) for x in range(0, WIDTH, 2)]
        dirt_band = list(dirt_band_top)
        dirt_band.append((WIDTH, HEIGHT))
        dirt_band.append((0, HEIGHT))
        pygame.draw.polygon(surf, GROUND_DIRT, dirt_band)

        # Even darker deep layer
        deep_top = [(x, self.heights[x] + 60) for x in range(0, WIDTH, 2)]
        deep = list(deep_top)
        deep.append((WIDTH, HEIGHT))
        deep.append((0, HEIGHT))
        pygame.draw.polygon(surf, GROUND_DIRT_DARK, deep)

        # Grass surface band (top 14px)
        grass_top = [(x, self.heights[x]) for x in range(0, WIDTH, 2)]
        grass_bot = [(x, self.heights[x] + 14) for x in range(WIDTH - 1, -1, -2)]
        pygame.draw.polygon(surf, GROUND_COLOR, grass_top + grass_bot)

        # Grass top highlight line
        if len(grass_top) > 1:
            pygame.draw.lines(surf, GROUND_DARK, False, grass_top, 2)
            # bright highlight
            highlight = [(x, y - 1) for (x, y) in grass_top]
            pygame.draw.lines(surf, (140, 190, 100), False, highlight, 1)

        # Scattered grass tufts
        for _ in range(120):
            x = random.randint(0, WIDTH - 1)
            y = self.heights[x]
            for i in range(3):
                pygame.draw.line(surf, (60, 110, 50),
                                 (x + i - 1, y),
                                 (x + i - 1, y - random.randint(2, 5)), 1)

        return surf

    def draw(self, target):
        if self._dirty or self._surface is None:
            self._surface = self._build_surface()
            self._dirty = False
        target.blit(self._surface, (0, 0))


# ---------- WEAPONS ----------
WEAPONS = [
    {"name": "Shell",  "key": "1", "radius": 4, "blast": 55,  "damage": 28, "count": 1, "spread": 0,  "color": (255, 220, 80)},
    {"name": "Bomb",   "key": "2", "radius": 7, "blast": 95,  "damage": 55, "count": 1, "spread": 0,  "color": (255, 100, 60)},
    {"name": "Triple", "key": "3", "radius": 3, "blast": 40,  "damage": 18, "count": 3, "spread": 8,  "color": (180, 240, 255)},
]


# ---------- TANK ----------
class Tank:
    def __init__(self, x, color, facing, name):
        self.x = float(x)
        self.color = color
        self.facing = facing  # 1 = right, -1 = left
        self.name = name
        self.health = 100
        self.angle = 45 if facing == 1 else 135
        self.weapon = 0
        self.alive = True
        self.fuel = FUEL_PER_TURN
        self.tread_offset = 0  # animates when driving

    def y(self, terrain):
        return terrain.height_at(self.x)

    def ground_angle(self, terrain):
        """Return the slope angle (radians) at the tank position so the body tilts."""
        x = int(self.x)
        x0 = max(0, x - 14)
        x1 = min(WIDTH - 1, x + 14)
        dy = terrain.height_at(x1) - terrain.height_at(x0)
        dx = x1 - x0
        return math.atan2(dy, dx)

    def adjust_angle(self, delta):
        self.angle = max(5, min(175, self.angle + delta))

    def cycle_weapon(self, idx):
        if 0 <= idx < len(WEAPONS):
            self.weapon = idx
            play(snd_click)

    def drive(self, direction, terrain, other_tank):
        """direction: -1 left, +1 right. Returns True if moved."""
        if self.fuel <= 0 or not self.alive:
            return False
        new_x = self.x + direction * DRIVE_SPEED
        # bounds
        if new_x < 25 or new_x > WIDTH - 25:
            return False
        # don't overlap the other tank
        if other_tank.alive and abs(new_x - other_tank.x) < 50:
            return False
        # don't climb impossible slopes
        old_h = terrain.height_at(self.x)
        new_h = terrain.height_at(new_x)
        if abs(new_h - old_h) > MAX_SLOPE:
            return False
        # update facing toward direction of travel for visual flair
        self.facing = direction
        moved = abs(new_x - self.x)
        self.x = new_x
        self.fuel = max(0, self.fuel - moved * DRIVE_COST)
        self.tread_offset = (self.tread_offset + direction * 2) % 9
        return True

    def barrel_tip(self, terrain):
        gy = self.y(terrain)
        ga = self.ground_angle(terrain)
        # Turret pivot sits on the body, tilted with the ground
        pivot_x = self.x - math.sin(ga) * 6
        pivot_y = gy - 18 - math.cos(ga) * 6 + 6  # ~ gy - 18
        rad = math.radians(self.angle)
        length = 30
        return ((pivot_x + math.cos(rad) * length,
                 pivot_y - math.sin(rad) * length),
                (pivot_x, pivot_y))

    def draw(self, surf, terrain, active=False):
        if not self.alive:
            return
        gy = self.y(terrain)
        ga = self.ground_angle(terrain)
        cx, cy = self.x, gy

        # ---- Shadow ----
        shadow = pygame.Surface((60, 12), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 110), (0, 0, 60, 12))
        surf.blit(shadow, (cx - 30, cy - 2))

        # We draw the chassis on a small surface so we can rotate it with the slope
        body = pygame.Surface((70, 40), pygame.SRCALPHA)
        bx, by = 35, 30  # local center

        # ---- Treads (bottom) ----
        tread_rect = pygame.Rect(bx - 24, by - 8, 48, 10)
        pygame.draw.rect(body, (35, 35, 40), tread_rect, border_radius=4)
        pygame.draw.rect(body, (15, 15, 20), tread_rect, 2, border_radius=4)
        # tread links (animated)
        for i in range(6):
            lx = bx - 22 + ((i * 9 + self.tread_offset) % 48)
            pygame.draw.rect(body, (60, 60, 70), (lx, by - 7, 5, 8), border_radius=1)
        # wheels
        for i in range(5):
            wx = bx - 18 + i * 9
            pygame.draw.circle(body, (50, 50, 55), (wx, by - 3), 4)
            pygame.draw.circle(body, (20, 20, 25), (wx, by - 3), 4, 1)
            pygame.draw.circle(body, (90, 90, 95), (wx, by - 3), 1)

        # ---- Hull ----
        hull = [
            (bx - 22, by - 10),
            (bx - 26, by - 18),
            (bx - 14, by - 24),
            (bx + 14, by - 24),
            (bx + 26, by - 18),
            (bx + 22, by - 10),
        ]
        pygame.draw.polygon(body, self.color, hull)
        # darker bottom shade
        shade = [
            (bx - 22, by - 10),
            (bx + 22, by - 10),
            (bx + 26, by - 18),
            (bx - 26, by - 18),
        ]
        dark_color = (max(0, self.color[0] - 60),
                      max(0, self.color[1] - 60),
                      max(0, self.color[2] - 60))
        pygame.draw.polygon(body, dark_color, shade)
        # top highlight
        light_color = (min(255, self.color[0] + 40),
                       min(255, self.color[1] + 40),
                       min(255, self.color[2] + 40))
        pygame.draw.line(body, light_color, (bx - 12, by - 23), (bx + 12, by - 23), 2)
        pygame.draw.polygon(body, (0, 0, 0), hull, 2)

        # rivets
        for px in (bx - 20, bx - 10, bx, bx + 10, bx + 20):
            pygame.draw.circle(body, (30, 30, 30), (px, by - 13), 1)

        # rotate the body to match ground slope
        rotated = pygame.transform.rotate(body, math.degrees(-ga))
        rrect = rotated.get_rect(center=(cx, cy - 14))
        surf.blit(rotated, rrect.topleft)

        # ---- Turret (drawn separately, doesn't tilt with ground except for pivot offset) ----
        pivot_x = cx - math.sin(ga) * 6
        pivot_y = cy - 18 - math.cos(ga) * 0  # keep simple
        # Turret base
        pygame.draw.circle(surf, dark_color, (int(pivot_x), int(pivot_y) + 1), 10)
        pygame.draw.circle(surf, self.color, (int(pivot_x), int(pivot_y)), 9)
        pygame.draw.circle(surf, (0, 0, 0), (int(pivot_x), int(pivot_y)), 9, 2)
        pygame.draw.circle(surf, light_color, (int(pivot_x - 2), int(pivot_y - 2)), 3)

        # ---- Barrel ----
        tip, base = self.barrel_tip(terrain)
        # outer dark
        pygame.draw.line(surf, (25, 25, 30), base, tip, 8)
        # inner color
        pygame.draw.line(surf, self.color, base, tip, 4)
        # muzzle
        pygame.draw.circle(surf, (25, 25, 30), (int(tip[0]), int(tip[1])), 4)
        pygame.draw.circle(surf, (60, 60, 60), (int(tip[0]), int(tip[1])), 2)

        # ---- Active indicator ----
        if active:
            arrow_y = cy - 60 + math.sin(pygame.time.get_ticks() * 0.008) * 4
            pygame.draw.polygon(surf, (255, 230, 80),
                                [(cx, arrow_y + 14),
                                 (cx - 9, arrow_y),
                                 (cx + 9, arrow_y)])
            pygame.draw.polygon(surf, (0, 0, 0),
                                [(cx, arrow_y + 14),
                                 (cx - 9, arrow_y),
                                 (cx + 9, arrow_y)], 2)


# ---------- PROJECTILE ----------
class Projectile:
    def __init__(self, x, y, vx, vy, weapon):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.weapon = weapon
        self.alive = True
        self.trail = []
        self.spin = 0

    def update(self, wind):
        self.trail.append((self.x, self.y))
        if len(self.trail) > 22:
            self.trail.pop(0)
        self.vx += wind * 0.02
        self.vy += GRAVITY
        self.x += self.vx
        self.y += self.vy
        self.spin += 0.4

    def draw(self, surf):
        # smoke trail
        for i, (tx, ty) in enumerate(self.trail):
            alpha = i / max(1, len(self.trail))
            r = int(1 + alpha * 4)
            shade = int(120 + alpha * 100)
            pygame.draw.circle(surf, (shade, shade, shade), (int(tx), int(ty)), r)
        # spark trail (weapon color)
        if self.trail:
            for i in range(max(0, len(self.trail) - 6), len(self.trail)):
                tx, ty = self.trail[i]
                r = 1 + (i - (len(self.trail) - 6))
                pygame.draw.circle(surf, self.weapon["color"], (int(tx), int(ty)), max(1, r))
        # projectile body
        c = self.weapon["color"]
        rad = self.weapon["radius"]
        pygame.draw.circle(surf, (40, 40, 40), (int(self.x), int(self.y)), rad + 3)
        pygame.draw.circle(surf, c, (int(self.x), int(self.y)), rad + 1)
        pygame.draw.circle(surf, (255, 255, 255),
                           (int(self.x - rad * 0.3), int(self.y - rad * 0.3)),
                           max(1, rad // 2))


# ---------- PARTICLES ----------
class Particle:
    def __init__(self, x, y, vx, vy, life, color, size, kind="fire"):
        self.x = x; self.y = y
        self.vx = vx; self.vy = vy
        self.life = life; self.max_life = life
        self.color = color; self.size = size
        self.kind = kind  # fire / smoke / debris / spark

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if self.kind == "smoke":
            self.vy -= 0.05
            self.vx *= 0.97
        elif self.kind == "debris":
            self.vy += 0.35
            self.vx *= 0.99
        else:
            self.vy += 0.15
            self.vx *= 0.97
        self.life -= 1

    def draw(self, surf):
        if self.life <= 0:
            return
        t = self.life / self.max_life
        if self.kind == "smoke":
            r = max(2, int(self.size * (2 - t)))
            shade = int(80 + t * 100)
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (shade, shade, shade, int(150 * t)), (r, r), r)
            surf.blit(s, (self.x - r, self.y - r))
        elif self.kind == "debris":
            pygame.draw.rect(surf, self.color,
                             (int(self.x), int(self.y), 3, 3))
        else:
            r = max(1, int(self.size * t))
            c = (
                min(255, int(self.color[0] * t + 60)),
                min(255, int(self.color[1] * t * 0.7 + 30)),
                min(255, int(self.color[2] * t * 0.4)),
            )
            pygame.draw.circle(surf, c, (int(self.x), int(self.y)), r)


def make_explosion(x, y, particles, big=False):
    n = 70 if big else 35
    for _ in range(n):
        ang = random.uniform(0, math.pi * 2)
        spd = random.uniform(2, 9 if big else 6)
        particles.append(Particle(
            x, y,
            math.cos(ang) * spd,
            math.sin(ang) * spd - 1,
            random.randint(25, 55),
            (255, random.randint(120, 220), 60),
            random.randint(3, 8 if big else 5),
            kind="fire"
        ))
    # smoke
    for _ in range(20 if big else 12):
        ang = random.uniform(0, math.pi * 2)
        spd = random.uniform(0.5, 2.5)
        particles.append(Particle(
            x, y,
            math.cos(ang) * spd,
            math.sin(ang) * spd - 0.5,
            random.randint(50, 90),
            (180, 180, 180),
            random.randint(6, 11),
            kind="smoke"
        ))
    # debris (dirt chunks)
    for _ in range(15 if big else 8):
        ang = random.uniform(-math.pi, 0)  # mostly upward
        spd = random.uniform(3, 8)
        particles.append(Particle(
            x, y,
            math.cos(ang) * spd,
            math.sin(ang) * spd,
            random.randint(40, 80),
            random.choice([(110, 80, 55), (75, 50, 35), (95, 70, 45)]),
            3,
            kind="debris"
        ))


# ---------- CLOUDS ----------
class Cloud:
    def __init__(self):
        self.x = random.uniform(0, WIDTH)
        self.y = random.uniform(40, 200)
        self.speed = random.uniform(0.1, 0.4)
        self.size = random.uniform(0.7, 1.6)
        self.layer = random.choice([0, 1])  # parallax

    def update(self, wind):
        self.x += self.speed + wind * 0.05 * (0.5 if self.layer == 0 else 1)
        if self.x > WIDTH + 120:
            self.x = -120
        if self.x < -120:
            self.x = WIDTH + 120

    def draw(self, surf):
        s = self.size
        alpha = 180 if self.layer == 0 else 230
        c = (255, 255, 255, alpha)
        cloud_surf = pygame.Surface((int(80 * s), int(50 * s)), pygame.SRCALPHA)
        cw, ch = cloud_surf.get_size()
        pygame.draw.circle(cloud_surf, c, (cw // 2, ch // 2 + 4), int(20 * s))
        pygame.draw.circle(cloud_surf, c, (cw // 2 + int(18 * s), ch // 2 + 8), int(16 * s))
        pygame.draw.circle(cloud_surf, c, (cw // 2 - int(18 * s), ch // 2 + 8), int(16 * s))
        pygame.draw.circle(cloud_surf, c, (cw // 2 + int(8 * s), ch // 2 - int(6 * s)), int(14 * s))
        surf.blit(cloud_surf, (self.x - cw // 2, self.y - ch // 2))


# ---------- MOUNTAINS (parallax) ----------
class MountainRange:
    def __init__(self, base_y, color, amplitude, freq, seed):
        self.base_y = base_y
        self.color = color
        self.amplitude = amplitude
        self.freq = freq
        self.seed = seed
        self.points = self._build()

    def _build(self):
        rng = random.Random(self.seed)
        pts = []
        x = 0
        while x <= WIDTH:
            y = self.base_y - rng.random() * self.amplitude
            pts.append((x, y))
            x += int(40 + rng.random() * 60)
        return pts

    def draw(self, surf):
        polygon = list(self.points) + [(WIDTH, HEIGHT), (0, HEIGHT)]
        pygame.draw.polygon(surf, self.color, polygon)


# ---------- BACKGROUND ----------
def draw_sky(surf):
    # 3-stop vertical gradient
    for y in range(HEIGHT):
        t = y / HEIGHT
        if t < 0.5:
            k = t / 0.5
            r = int(SKY_TOP[0] * (1 - k) + SKY_MID[0] * k)
            g = int(SKY_TOP[1] * (1 - k) + SKY_MID[1] * k)
            b = int(SKY_TOP[2] * (1 - k) + SKY_MID[2] * k)
        else:
            k = (t - 0.5) / 0.5
            r = int(SKY_MID[0] * (1 - k) + SKY_BOTTOM[0] * k)
            g = int(SKY_MID[1] * (1 - k) + SKY_BOTTOM[1] * k)
            b = int(SKY_MID[2] * (1 - k) + SKY_BOTTOM[2] * k)
        pygame.draw.line(surf, (r, g, b), (0, y), (WIDTH, y))


def draw_sun(surf, x, y):
    # glow halos
    for r, a in ((90, 30), (65, 50), (45, 80)):
        glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 230, 170, a), (r, r), r)
        surf.blit(glow, (x - r, y - r))
    pygame.draw.circle(surf, (255, 240, 200), (x, y), 32)
    pygame.draw.circle(surf, (255, 250, 230), (x, y), 22)


# ---------- HUD ----------
def draw_health_bar(surf, x, y, w, h, hp, color):
    pygame.draw.rect(surf, (0, 0, 0), (x - 2, y - 2, w + 4, h + 4), border_radius=4)
    pygame.draw.rect(surf, (60, 60, 60), (x, y, w, h), border_radius=3)
    fill = int(w * max(0, hp) / 100)
    if fill > 0:
        # gradient by health
        if hp > 60:
            c = color
        elif hp > 30:
            c = (240, 180, 60)
        else:
            c = (220, 60, 60)
        pygame.draw.rect(surf, c, (x, y, fill, h), border_radius=3)
    txt = font_sm.render(f"{int(max(0, hp))} HP", True, TEXT_COLOR)
    surf.blit(txt, (x + w // 2 - txt.get_width() // 2, y + h // 2 - txt.get_height() // 2))


def draw_fuel_bar(surf, x, y, w, h, fuel):
    pygame.draw.rect(surf, (0, 0, 0), (x - 2, y - 2, w + 4, h + 4), border_radius=4)
    pygame.draw.rect(surf, (40, 40, 40), (x, y, w, h), border_radius=3)
    fill = int(w * max(0, fuel) / FUEL_PER_TURN)
    if fill > 0:
        pygame.draw.rect(surf, (90, 200, 230), (x, y, fill, h), border_radius=3)
    txt = font_sm.render(f"FUEL {int(max(0, fuel))}", True, TEXT_COLOR)
    surf.blit(txt, (x + w // 2 - txt.get_width() // 2, y + h // 2 - txt.get_height() // 2))


def draw_wind(surf, wind):
    cx, cy = WIDTH // 2, 30
    bg = pygame.Surface((180, 36), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 150))
    surf.blit(bg, (cx - 90, cy - 18))
    label = font_sm.render("WIND", True, TEXT_COLOR)
    surf.blit(label, (cx - label.get_width() // 2, cy - 14))
    direction = 1 if wind >= 0 else -1
    strength = min(1.0, abs(wind) / 3.0)
    arrow_len = int(60 * strength)
    ay = cy + 6
    if arrow_len > 4:
        start_x = cx - arrow_len // 2 * direction
        end_x = cx + arrow_len // 2 * direction
        pygame.draw.line(surf, (255, 220, 80), (start_x, ay), (end_x, ay), 3)
        head = end_x
        pygame.draw.polygon(surf, (255, 220, 80),
                            [(head, ay),
                             (head - 8 * direction, ay - 5),
                             (head - 8 * direction, ay + 5)])
    else:
        calm = font_sm.render("calm", True, (200, 200, 200))
        surf.blit(calm, (cx - calm.get_width() // 2, ay - 6))


def draw_power_meter(surf, x, y, power):
    w, h = 180, 16
    pygame.draw.rect(surf, (0, 0, 0), (x - 2, y - 2, w + 4, h + 4), border_radius=4)
    pygame.draw.rect(surf, (40, 40, 40), (x, y, w, h), border_radius=3)
    fill = int(w * power / MAX_POWER)
    t = power / MAX_POWER
    color = (int(80 + 175 * t), int(220 - 180 * t), 60)
    pygame.draw.rect(surf, color, (x, y, fill, h), border_radius=3)
    label = font_sm.render("POWER", True, TEXT_COLOR)
    surf.blit(label, (x, y - 18))


def draw_weapon_panel(surf, tank, x, y):
    bg = pygame.Surface((200, 80), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 150))
    surf.blit(bg, (x - 8, y - 8))
    title = font_sm.render("WEAPON", True, TEXT_COLOR)
    surf.blit(title, (x, y - 4))
    for i, w in enumerate(WEAPONS):
        sel = (i == tank.weapon)
        col = (255, 230, 80) if sel else (180, 180, 180)
        line = f"[{w['key']}] {w['name']}"
        txt = font_sm.render(line, True, col)
        surf.blit(txt, (x, y + 16 + i * 16))


# ---------- GAME ----------
class Game:
    def __init__(self):
        self.state = "menu"
        self.reset()

    def reset(self):
        self.terrain = Terrain()
        x1 = random.randint(80, 220)
        x2 = random.randint(WIDTH - 220, WIDTH - 80)
        self.tanks = [
            Tank(x1, P1_COLOR, 1, "PLAYER 1"),
            Tank(x2, P2_COLOR, -1, "PLAYER 2"),
        ]
        self.tanks[0].fuel = FUEL_PER_TURN
        self.tanks[1].fuel = FUEL_PER_TURN
        self.turn = 0
        self.projectiles = []
        self.particles = []
        self.clouds = [Cloud() for _ in range(7)]
        self.mountains_far = MountainRange(HEIGHT - 280, (110, 120, 150), 80, 0.003, 1)
        self.mountains_mid = MountainRange(HEIGHT - 220, (90, 105, 130), 60, 0.005, 2)
        self.mountains_near = MountainRange(HEIGHT - 180, (70, 90, 110), 40, 0.008, 3)
        self.sun_pos = (WIDTH - 180, 130)
        self.wind = random.uniform(-3, 3)
        self.power = 0.0
        self.charging = False
        self.fired = False
        self.winner = None
        self.shake = 0
        self.engine_cooldown = 0

    def fire(self):
        tank = self.tanks[self.turn]
        tip, _ = tank.barrel_tip(self.terrain)
        weapon = WEAPONS[tank.weapon]
        for i in range(weapon["count"]):
            offset = (i - (weapon["count"] - 1) / 2) * weapon["spread"]
            ang = tank.angle + offset
            r = math.radians(ang)
            vx = math.cos(r) * self.power
            vy = -math.sin(r) * self.power
            self.projectiles.append(Projectile(tip[0], tip[1], vx, vy, weapon))
        # Muzzle flash
        for _ in range(15):
            a = math.radians(tank.angle) + random.uniform(-0.3, 0.3)
            sp = random.uniform(2, 6)
            self.particles.append(Particle(
                tip[0], tip[1],
                math.cos(a) * sp, -math.sin(a) * sp,
                random.randint(8, 18),
                (255, 220, 100), random.randint(2, 5), "fire"
            ))
        play(snd_fire)
        self.fired = True
        self.shake = max(self.shake, 6)
        self.power = 0
        self.charging = False

    def update(self):
        if self.state != "playing":
            return

        for c in self.clouds:
            c.update(self.wind)

        if self.charging and not self.fired:
            self.power = min(MAX_POWER, self.power + POWER_RATE)

        for p in self.projectiles[:]:
            p.update(self.wind)
            if p.x < -50 or p.x > WIDTH + 50 or p.y > HEIGHT + 200:
                self.projectiles.remove(p)
                continue
            if p.y >= self.terrain.height_at(p.x):
                self.explode(p)
                self.projectiles.remove(p)
                continue
            for t in self.tanks:
                if not t.alive:
                    continue
                tx, ty = t.x, t.y(self.terrain) - 15
                if (p.x - tx) ** 2 + (p.y - ty) ** 2 < 22 ** 2:
                    self.explode(p)
                    if p in self.projectiles:
                        self.projectiles.remove(p)
                    break

        for pt in self.particles[:]:
            pt.update()
            if pt.life <= 0:
                self.particles.remove(pt)

        if self.shake > 0:
            self.shake -= 1
        if self.engine_cooldown > 0:
            self.engine_cooldown -= 1

        if self.fired and not self.projectiles and not any(pt.life > 5 for pt in self.particles):
            for t in self.tanks:
                if t.health <= 0:
                    t.alive = False
            alive = [t for t in self.tanks if t.alive]
            if len(alive) <= 1:
                self.winner = alive[0] if alive else None
                self.state = "gameover"
            else:
                self.turn = 1 - self.turn
                self.tanks[self.turn].fuel = FUEL_PER_TURN
                self.fired = False
                self.wind = random.uniform(-3, 3)

    def explode(self, projectile):
        weapon = projectile.weapon
        x, y = projectile.x, projectile.y
        blast = weapon["blast"]
        damage = weapon["damage"]
        big = blast > 70
        play(snd_explode)
        make_explosion(x, y, self.particles, big=big)
        # Carve terrain
        self.terrain.deform(x, y, blast * 0.55)
        self.shake = 18 if big else 9
        for t in self.tanks:
            if not t.alive:
                continue
            tx, ty = t.x, t.y(self.terrain) - 15
            dist = math.hypot(tx - x, ty - y)
            if dist < blast:
                falloff = 1 - (dist / blast)
                dmg = damage * falloff
                t.health -= dmg
                if dmg > 5:
                    play(snd_hit)

    # ---------- DRAW ----------
    def draw(self, surf):
        offset_x = random.randint(-self.shake, self.shake) if self.shake > 0 else 0
        offset_y = random.randint(-self.shake, self.shake) if self.shake > 0 else 0

        world = pygame.Surface((WIDTH, HEIGHT))
        draw_sky(world)
        draw_sun(world, self.sun_pos[0], self.sun_pos[1])
        # parallax mountains back-to-front
        self.mountains_far.draw(world)
        # back clouds
        for c in self.clouds:
            if c.layer == 0:
                c.draw(world)
        self.mountains_mid.draw(world)
        self.mountains_near.draw(world)
        # front clouds
        for c in self.clouds:
            if c.layer == 1:
                c.draw(world)

        self.terrain.draw(world)

        for t in self.tanks:
            t.draw(world, self.terrain, active=(self.tanks[self.turn] is t and self.state == "playing"))

        # Aim trajectory preview for active tank
        if self.state == "playing" and not self.fired:
            tank = self.tanks[self.turn]
            tip, base = tank.barrel_tip(self.terrain)
            rad = math.radians(tank.angle)
            preview_power = self.power if self.charging else 9
            vx = math.cos(rad) * preview_power
            vy = -math.sin(rad) * preview_power
            x, y = tip
            for i in range(50):
                x += vx
                y += vy
                vy += GRAVITY
                vx += self.wind * 0.02
                if i % 2 == 0:
                    pygame.draw.circle(world, (255, 255, 255), (int(x), int(y)), 2)
                if y > self.terrain.height_at(x) or y > HEIGHT or x < 0 or x > WIDTH:
                    break

        for p in self.projectiles:
            p.draw(world)
        for pt in self.particles:
            pt.draw(world)

        surf.blit(world, (offset_x, offset_y))

        self.draw_hud(surf)
        if self.state == "menu":
            self.draw_menu(surf)
        elif self.state == "gameover":
            self.draw_gameover(surf)

    def draw_hud(self, surf):
        hud = pygame.Surface((WIDTH, 60), pygame.SRCALPHA)
        hud.fill((10, 15, 25, 180))
        surf.blit(hud, (0, 0))

        p1 = self.tanks[0]
        name1 = font_md.render(p1.name, True, P1_COLOR)
        surf.blit(name1, (20, 8))
        draw_health_bar(surf, 20, 32, 200, 18, p1.health, P1_COLOR)

        p2 = self.tanks[1]
        name2 = font_md.render(p2.name, True, P2_COLOR)
        surf.blit(name2, (WIDTH - 20 - name2.get_width(), 8))
        draw_health_bar(surf, WIDTH - 220, 32, 200, 18, p2.health, P2_COLOR)

        draw_wind(surf, self.wind)

        if self.state == "playing":
            tank = self.tanks[self.turn]
            draw_power_meter(surf, 20, HEIGHT - 32, self.power)
            ang_txt = font_md.render(f"Angle: {int(tank.angle)}°", True, TEXT_COLOR)
            surf.blit(ang_txt, (220, HEIGHT - 36))
            draw_fuel_bar(surf, 360, HEIGHT - 32, 180, 16, tank.fuel)
            draw_weapon_panel(surf, tank, WIDTH - 200, HEIGHT - 88)

            turn_txt = font_md.render(f"{tank.name}'s TURN", True, tank.color)
            tx_bg = pygame.Surface((turn_txt.get_width() + 24, 32), pygame.SRCALPHA)
            tx_bg.fill((0, 0, 0, 180))
            surf.blit(tx_bg, (WIDTH // 2 - turn_txt.get_width() // 2 - 12, 70))
            surf.blit(turn_txt, (WIDTH // 2 - turn_txt.get_width() // 2, 76))

            help_txt = font_sm.render(
                "A/D drive   ←/→ aim   SPACE hold to fire   1/2/3 weapon",
                True, (220, 220, 220))
            surf.blit(help_txt, (WIDTH // 2 - help_txt.get_width() // 2, HEIGHT - 22))

    def draw_menu(self, surf):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surf.blit(overlay, (0, 0))

        title = font_xl.render("TANK STARS", True, (255, 220, 80))
        # title shadow
        shadow = font_xl.render("TANK STARS", True, (40, 30, 0))
        surf.blit(shadow, (WIDTH // 2 - title.get_width() // 2 + 4, 134))
        surf.blit(title, (WIDTH // 2 - title.get_width() // 2, 130))
        sub = font_md.render("2-Player Hot-Seat Artillery", True, (220, 220, 220))
        surf.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 210))

        lines = [
            "A / D       Drive your tank (uses fuel)",
            "← / →       Aim your barrel",
            "SPACE       Hold to charge power, release to fire",
            "1 / 2 / 3   Switch weapon",
            "Watch the wind, mind the slopes!",
            "",
            "Press ENTER to begin",
        ]
        for i, line in enumerate(lines):
            color = (255, 230, 100) if "ENTER" in line else (230, 230, 230)
            t = font_md.render(line, True, color)
            surf.blit(t, (WIDTH // 2 - t.get_width() // 2, 280 + i * 32))

    def draw_gameover(self, surf):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surf.blit(overlay, (0, 0))

        if self.winner:
            msg = f"{self.winner.name} WINS!"
            color = self.winner.color
        else:
            msg = "DRAW!"
            color = (220, 220, 220)
        title = font_xl.render(msg, True, color)
        surf.blit(title, (WIDTH // 2 - title.get_width() // 2, 220))

        sub = font_md.render("Press ENTER to play again — ESC to quit",
                             True, (230, 230, 230))
        surf.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 320))

    # ---------- INPUT ----------
    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()
            if self.state == "menu":
                if e.key == pygame.K_RETURN:
                    self.reset()
                    self.state = "playing"
                    play(snd_click)
            elif self.state == "gameover":
                if e.key == pygame.K_RETURN:
                    self.reset()
                    self.state = "playing"
                    play(snd_click)
            elif self.state == "playing" and not self.fired:
                tank = self.tanks[self.turn]
                if e.key == pygame.K_1:
                    tank.cycle_weapon(0)
                elif e.key == pygame.K_2:
                    tank.cycle_weapon(1)
                elif e.key == pygame.K_3:
                    tank.cycle_weapon(2)
                elif e.key == pygame.K_SPACE and not self.charging:
                    self.charging = True
                    self.power = 4
        if e.type == pygame.KEYUP:
            if self.state == "playing" and not self.fired:
                if e.key == pygame.K_SPACE and self.charging:
                    self.fire()

    def handle_held_keys(self):
        if self.state != "playing" or self.fired:
            return
        keys = pygame.key.get_pressed()
        tank = self.tanks[self.turn]
        other = self.tanks[1 - self.turn]
        # Aim
        if keys[pygame.K_LEFT]:
            tank.adjust_angle(1.2)
        if keys[pygame.K_RIGHT]:
            tank.adjust_angle(-1.2)
        # Drive
        moved = False
        if keys[pygame.K_a]:
            moved = tank.drive(-1, self.terrain, other) or moved
        if keys[pygame.K_d]:
            moved = tank.drive(1, self.terrain, other) or moved
        if moved and self.engine_cooldown <= 0:
            play(snd_engine)
            self.engine_cooldown = 8


# ---------- MAIN LOOP ----------
def main():
    game = Game()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            game.handle_event(e)
        game.handle_held_keys()
        game.update()
        game.draw(screen)
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()