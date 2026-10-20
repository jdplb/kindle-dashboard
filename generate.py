#!/usr/bin/env python3
"""Dashboard e-ink 800x600: tiempo y calidad del aire de Madrid (Open-Meteo, sin claves)."""
import datetime as dt
import math
import os
import sys
import time
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont


def env(name, default=""):
    v = os.environ.get(name, "")
    v = v.strip() if v else ""
    return v if v else default


W, H = 800, 600
TZ_NAME = env("TZ_NAME", "Europe/Madrid")
TZ = ZoneInfo(TZ_NAME)
LAT = float(env("LAT", "40.4168"))
LON = float(env("LON", "-3.7038"))
CITY = env("CITY_NAME", "Madrid")
ROTATE = int(env("ROTATE", "90"))
OUT_DIR = env("OUT_DIR", "site")
BASE = env("FILE_BASE", "dashboard")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# ------------------------------------------------------------------ fuentes
_fonts = {}


def font(size, bold=False):
    key = (size, bold)
    if key in _fonts:
        return _fonts[key]
    cands = ["DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold else ["DejaVuSans.ttf", "arial.ttf"]
    dirs = ["/usr/share/fonts/truetype/dejavu/", "C:/Windows/Fonts/", ""]
    f = None
    for d in dirs:
        for n in cands:
            try:
                f = ImageFont.truetype(d + n, size)
                break
            except OSError:
                continue
        if f:
            break
    if f is None:
        raise RuntimeError("No se encontró ninguna fuente TrueType")
    _fonts[key] = f
    return f


def fit(d, text, f, max_w):
    if d.textlength(text, font=f) <= max_w:
        return text
    while text and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


# ------------------------------------------------------------------ proveedores
def get_json(url, params, tries=3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                last = RuntimeError(f"HTTP {r.status_code}")
            else:
                r.raise_for_status()
                return r.json()
        except requests.RequestException as e:
            last = e
        if i < tries - 1:
            time.sleep(4 * (i + 1))
    raise last


def get_weather():
    return get_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": LAT, "longitude": LON,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                  "uv_index_max,sunrise,sunset"),
        "timezone": TZ_NAME, "forecast_days": 4,
    })


def get_air():
    return get_json("https://air-quality-api.open-meteo.com/v1/air-quality", {
        "latitude": LAT, "longitude": LON,
        "current": "european_aqi,pm2_5,pm10,ozone,nitrogen_dioxide",
        "timezone": TZ_NAME,
    })


# Para añadir una fuente nueva (p. ej. Notion): escribe get_notion() y regístrala aquí.
PROVIDERS = {"weather": get_weather, "air": get_air}


# ------------------------------------------------------------------ utilidades de datos
def wmo(code):
    if code == 0:
        return "Despejado", "sun"
    if code in (1, 2):
        return "Poco nuboso", "partly"
    if code == 3:
        return "Nublado", "cloud"
    if code in (45, 48):
        return "Niebla", "fog"
    if code in (51, 53, 55, 56, 57):
        return "Llovizna", "rain"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Lluvia", "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "Nieve", "snow"
    if code in (95, 96, 99):
        return "Tormenta", "storm"
    return "—", "cloud"


def aqi_label(v):
    for lim, txt in ((20, "Buena"), (40, "Aceptable"), (60, "Moderada"), (80, "Mala"), (100, "Muy mala")):
        if v <= lim:
            return txt
    return "Extrema"


def uv_label(v):
    for lim, txt in ((2, "Bajo"), (5, "Moderado"), (7, "Alto"), (10, "Muy alto")):
        if v <= lim:
            return txt
    return "Extremo"


def is_night(t, daily):
    try:
        i = daily["time"].index(t.date().isoformat())
        sr = dt.datetime.fromisoformat(daily["sunrise"][i])
        ss = dt.datetime.fromisoformat(daily["sunset"][i])
        return not (sr <= t <= ss)
    except (ValueError, KeyError, IndexError, TypeError):
        return False


# ------------------------------------------------------------------ iconos
def sun(d, cx, cy, s):
    r = s * 0.25
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    for i in range(8):
        a = math.radians(i * 45)
        d.line([cx + math.cos(a) * s * 0.35, cy + math.sin(a) * s * 0.35,
                cx + math.cos(a) * s * 0.50, cy + math.sin(a) * s * 0.50],
               fill=0, width=max(2, int(s / 14)))


def moon(d, cx, cy, s):
    r = s * 0.28
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    r2 = s * 0.24
    ox, oy = cx + 0.12 * s, cy - 0.08 * s
    d.ellipse([ox - r2, oy - r2, ox + r2, oy + r2], fill=255)


def cloud(d, cx, cy, s, fill):
    d.ellipse([cx - .55 * s, cy - .10 * s, cx - .10 * s, cy + .35 * s], fill=fill)
    d.ellipse([cx - .30 * s, cy - .38 * s, cx + .22 * s, cy + .14 * s], fill=fill)
    d.ellipse([cx + .00 * s, cy - .18 * s, cx + .55 * s, cy + .35 * s], fill=fill)
    d.rectangle([cx - .32 * s, cy + .05 * s, cx + .32 * s, cy + .35 * s], fill=fill)


def icon(d, kind, cx, cy, s, night=False):
    gray = 70
    lw = max(2, int(s / 14))
    if kind == "sun":
        (moon if night else sun)(d, cx, cy, s)
    elif kind == "partly":
        (moon if night else sun)(d, cx - .18 * s, cy - .18 * s, s * .8)
        cloud(d, cx + .05 * s, cy + .12 * s, s * 1.08, 255)
        cloud(d, cx + .05 * s, cy + .12 * s, s, gray)
    elif kind == "cloud":
        cloud(d, cx, cy, s, gray)
    elif kind == "fog":
        for i in range(4):
            y = cy - .3 * s + i * .22 * s
            d.line([cx - .5 * s, y, cx + .5 * s, y], fill=gray, width=max(2, int(s / 12)))
    else:
        cloud(d, cx, cy - .18 * s, s, gray)
        if kind == "rain":
            for i in range(4):
                x = cx - .35 * s + i * .23 * s
                d.line([x, cy + .28 * s, x - .08 * s, cy + .50 * s], fill=0, width=lw)
        elif kind == "snow":
            r = max(2, int(s / 20))
            for i in range(4):
                x = cx - .33 * s + i * .22 * s
                y = cy + .38 * s + (i % 2) * .08 * s
                d.ellipse([x - r, y - r, x + r, y + r], fill=0)
        else:
            d.polygon([(cx + .02 * s, cy + .12 * s), (cx - .14 * s, cy + .40 * s),
                       (cx - .02 * s, cy + .40 * s), (cx - .10 * s, cy + .62 * s),
                       (cx + .16 * s, cy + .32 * s), (cx + .04 * s, cy + .32 * s)], fill=0)


# ------------------------------------------------------------------ paneles
def panel_header(d, ctx):
    now = ctx["now"]
    d.rectangle([0, 0, W, 60], fill=0)
    titulo = f"{DIAS[now.weekday()].capitalize()} {now.day} de {MESES[now.month - 1]}"
    d.text((16, 30), titulo, font=font(30, True), fill=255, anchor="lm")
    d.text((W - 16, 30), CITY, font=font(22), fill=255, anchor="rm")


def panel_now(d, ctx):
    wx = ctx["data"]["weather"]
    cur, daily = wx["current"], wx["daily"]
    desc, kind = wmo(int(cur["weather_code"]))
    night = is_night(ctx["now"].replace(tzinfo=None), daily)
    icon(d, kind, 90, 150, 120, night)
    d.text((170, 130), f"{round(cur['temperature_2m'])}°", font=font(88, True), fill=0, anchor="lm")
    d.text((24, 238), desc, font=font(26, True), fill=0, anchor="lm")
    d.text((24, 270), f"Sensación térmica {round(cur['apparent_temperature'])}°", font=font(18), fill=0, anchor="lm")
    d.line([400, 60, 400, 298], fill=0, width=2)
    d.line([0, 298, W, 298], fill=0, width=2)


def panel_stats(d, ctx):
    wx = ctx["data"]["weather"]
    cur, daily = wx["current"], wx["daily"]
    air = ctx["data"].get("air")
    pp = daily["precipitation_probability_max"][0]
    uv = daily["uv_index_max"][0]
    aqi = None
    if air:
        aqi = air.get("current", {}).get("european_aqi")
    cells = [
        ("MÁX / MÍN HOY", f"{round(daily['temperature_2m_max'][0])}° / {round(daily['temperature_2m_min'][0])}°"),
        ("PROB. DE LLUVIA", f"{round(pp)}%" if pp is not None else "—"),
        ("VIENTO", f"{round(cur['wind_speed_10m'])} km/h"),
        ("HUMEDAD", f"{round(cur['relative_humidity_2m'])}%"),
        ("ÍNDICE UV (MÁX)", f"{round(uv)} · {uv_label(uv)}" if uv is not None else "—"),
        ("CALIDAD DEL AIRE", f"{round(aqi)} · {aqi_label(aqi)}" if aqi is not None else "—"),
        ("AMANECER", daily["sunrise"][0][11:16]),
        ("ATARDECER", daily["sunset"][0][11:16]),
    ]
    for i, (lab, val) in enumerate(cells):
        col, row = i % 2, i // 2
        x = 416 + col * 196
        y = 68 + row * 57
        d.text((x, y + 12), lab, font=font(13), fill=90, anchor="lm")
        d.text((x, y + 36), fit(d, val, font(22, True), 180), font=font(22, True), fill=0, anchor="lm")


def panel_hourly(d, ctx):
    wx = ctx["data"]["weather"]
    hourly, daily = wx["hourly"], wx["daily"]
    d.text((16, 312), "PRÓXIMAS HORAS", font=font(16, True), fill=0, anchor="lm")
    d.line([16, 324, W - 16, 324], fill=0, width=2)
    times = [dt.datetime.fromisoformat(t) for t in hourly["time"]]
    now_naive = ctx["now"].replace(tzinfo=None)
    start = next((i for i, t in enumerate(times) if t > now_naive), 0)
    idxs = [start + 2 * k for k in range(8) if start + 2 * k < len(times)]
    for k, i in enumerate(idxs):
        cx = 50 + k * 100
        t = times[i]
        _, kind = wmo(int(hourly["weather_code"][i]))
        d.text((cx, 346), f"{t.hour:02d}h", font=font(18, True), fill=0, anchor="mm")
        icon(d, kind, cx, 388, 44, is_night(t, daily))
        d.text((cx, 428), f"{round(hourly['temperature_2m'][i])}°", font=font(22, True), fill=0, anchor="mm")
        p = hourly["precipitation_probability"][i]
        if p is not None:
            d.text((cx, 448), f"{round(p)}%", font=font(14), fill=70, anchor="mm")


def panel_daily(d, ctx):
    daily = ctx["data"]["weather"]["daily"]
    d.text((16, 468), "PRÓXIMOS DÍAS", font=font(16, True), fill=0, anchor="lm")
    d.line([16, 480, W - 16, 480], fill=0, width=2)
    for n, i in enumerate((1, 2, 3)):
        x0 = 16 + n * 262
        day = dt.date.fromisoformat(daily["time"][i])
        _, kind = wmo(int(daily["weather_code"][i]))
        if n > 0:
            d.line([x0 - 8, 490, x0 - 8, 572], fill=170, width=1)
        icon(d, kind, x0 + 36, 532, 56)
        d.text((x0 + 80, 504), f"{DIAS[day.weekday()].capitalize()} {day.day}", font=font(20, True), fill=0, anchor="lm")
        d.text((x0 + 80, 530), f"{round(daily['temperature_2m_min'][i])}° / {round(daily['temperature_2m_max'][i])}°",
               font=font(20), fill=0, anchor="lm")
        pp = daily["precipitation_probability_max"][i]
        if pp is not None:
            d.text((x0 + 80, 554), f"Lluvia {round(pp)}%", font=font(15), fill=70, anchor="lm")


def panel_footer(d, ctx):
    now = ctx["now"]
    d.text((W - 16, 588), f"Actualizado {now.strftime('%d/%m %H:%M')} · Open-Meteo",
           font=font(13), fill=90, anchor="rm")


# Para añadir un panel nuevo (p. ej. tareas de Notion): escribe panel_xxx(d, ctx) y añádelo aquí.
PANELS = [panel_header, panel_now, panel_stats, panel_hourly, panel_daily, panel_footer]


# ------------------------------------------------------------------ salida
def save(img):
    os.makedirs(OUT_DIR, exist_ok=True)
    img = img.point(lambda p: (p // 16) * 17).convert("L")  # 16 niveles de gris
    img.save(os.path.join(OUT_DIR, f"{BASE}-preview.png"), optimize=True)
    k = img if ROTATE % 360 == 0 else img.rotate(ROTATE, expand=True)
    k.save(os.path.join(OUT_DIR, f"{BASE}.png"), optimize=True)
    open(os.path.join(OUT_DIR, ".nojekyll"), "w").close()
    print("OK preview", img.size, "kindle", k.size)


def err_text(e):
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return f"HTTP {e.response.status_code}"
    if isinstance(e, RuntimeError):
        return str(e)
    return type(e).__name__


def main():
    ctx = {"now": dt.datetime.now(TZ), "data": {}, "err": {}}
    for name, fn in PROVIDERS.items():
        try:
            ctx["data"][name] = fn()
        except Exception as e:
            ctx["err"][name] = err_text(e)
            print(f"Error en proveedor '{name}':", ctx["err"][name])
    if "weather" not in ctx["data"]:
        print("Sin datos del tiempo: no se publica nada nuevo.")
        sys.exit(1)
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    for panel in PANELS:
        panel(d, ctx)
    save(img)


if __name__ == "__main__":
    main()
