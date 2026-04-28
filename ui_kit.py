"""Futuristic UI primitives for AqueLyst OS.

All functions render directly to the active Streamlit container via st.markdown.
The visual language is deliberately consistent across pages — dark cyan-accented
heroes, monospace ◢ section headers, glass cards. This file is the source of
truth for that vocabulary so individual pages don't redefine it.
"""

import base64
from datetime import datetime
from functools import lru_cache
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:
    _ET = None

import streamlit as st


def now_et():
    """Eastern time (handles DST automatically — EST in winter, EDT in summer).
    Falls back to local time if zoneinfo unavailable."""
    if _ET is not None:
        return datetime.now(_ET)
    return datetime.now()


_LOGO_PATH = Path(__file__).parent / "assets" / "aquelyst-logo.png"


@lru_cache(maxsize=1)
def _logo_data_uri():
    """Read the official AqueLyst logo PNG once, encode as base64 data URI so
    it can be inlined inside any HTML string. Returns None if file missing —
    callers fall back to the inline SVG wordmark."""
    try:
        if not _LOGO_PATH.exists():
            return None
        with open(_LOGO_PATH, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


_PULSE_KEYFRAMES_INJECTED = False


def _ensure_pulse_animation():
    """Inject the @keyframes aqp-pulse rule once per session — used by status
    pills and accent dots throughout the OS."""
    global _PULSE_KEYFRAMES_INJECTED
    if _PULSE_KEYFRAMES_INJECTED:
        return
    st.markdown("""
    <style>
        @keyframes aqp-pulse {
            0%,100% { opacity: 1; transform: scale(1); }
            50%     { opacity: 0.45; transform: scale(0.92); }
        }
        @keyframes aqp-spin {
            from { transform: rotate(0deg); }
            to   { transform: rotate(360deg); }
        }
    </style>
    """, unsafe_allow_html=True)
    _PULSE_KEYFRAMES_INJECTED = True


def page_hero(title, subtitle="", stats=None, eyebrow="AQUELYST OS",
              chips=None):
    """Render a futuristic dark page hero.

    Args:
        title: HTML-allowed heading. Wrap accent words in
               `<span style='background:linear-gradient(135deg,#06b6d4,#a3e635);
               -webkit-background-clip:text;-webkit-text-fill-color:transparent;
               background-clip:text'>X</span>` for cyan gradient.
        subtitle: Description below title (HTML allowed).
        stats: Optional list of dicts: [{'label':'X','value':'5','color':'#06b6d4'}].
                Renders as a vertical-divider stat strip on the right.
        eyebrow: Mono uppercase strip at top — defaults to 'AQUELYST OS'.
        chips: Optional list of (text, color) tuples for small pill chips
                rendered below the subtitle.
    """
    _ensure_pulse_animation()
    _now = now_et()
    now_time = _now.strftime("%H:%M ET")
    today_short = _now.strftime("%a · %d %b %Y").upper()

    stats_html = ""
    if stats:
        parts = []
        for i, s in enumerate(stats):
            color = s.get('color', '#e2e8f0')
            parts.append(
                f"<div style='text-align:right;padding:0 0.3rem'>"
                f"<div style='font-family:JetBrains Mono,monospace;font-size:1.5rem;"
                f"font-weight:700;color:{color};line-height:1'>{s['value']}</div>"
                f"<div style='font-size:0.62rem;color:#64748b;text-transform:uppercase;"
                f"letter-spacing:0.10em;font-weight:600;margin-top:0.3rem'>"
                f"{s['label']}</div></div>"
            )
            if i < len(stats) - 1:
                parts.append(
                    "<div style='width:1px;height:34px;"
                    "background:linear-gradient(180deg,transparent,#06b6d4,transparent)'></div>"
                )
        stats_html = (
            f"<div style='display:flex;gap:1.0rem;align-items:center'>"
            f"{''.join(parts)}</div>"
        )

    chips_html = ""
    if chips:
        chip_parts = []
        for text, color in chips:
            chip_parts.append(
                f"<span style='display:inline-flex;align-items:center;"
                f"padding:0.25rem 0.7rem;border-radius:999px;"
                f"background:rgba(15,23,42,0.55);"
                f"border:1px solid {color}55;color:{color};"
                f"font-family:JetBrains Mono,monospace;font-size:0.66rem;"
                f"font-weight:700;letter-spacing:0.10em;text-transform:uppercase'>"
                f"{text}</span>"
            )
        chips_html = (
            f"<div style='display:flex;gap:0.4rem;margin-top:0.85rem;"
            f"flex-wrap:wrap'>{''.join(chip_parts)}</div>"
        )

    subtitle_html = (
        f"<div style='color:#94a3b8;margin-top:0.5rem;font-size:0.92rem;"
        f"line-height:1.45;max-width:680px'>{subtitle}</div>"
        if subtitle else ""
    )

    st.markdown(f"""
    <div style='position:relative;
                background:linear-gradient(135deg,#0a0f1c 0%,#0f172a 55%,#0a1f24 100%);
                border-radius:18px;padding:1.5rem 2.0rem;margin-bottom:1.4rem;
                border:1px solid rgba(6,182,212,0.20);
                box-shadow:0 10px 30px rgba(6,182,212,0.06),
                            inset 0 1px 0 rgba(255,255,255,0.04);
                overflow:hidden'>
        <div style='position:absolute;inset:0;pointer-events:none;
                    background-image:
                        radial-gradient(circle at 12% 0%, rgba(6,182,212,0.10) 0%, transparent 40%),
                        radial-gradient(circle at 100% 100%, rgba(26,95,63,0.10) 0%, transparent 42%),
                        linear-gradient(rgba(6,182,212,0.04) 1px, transparent 1px),
                        linear-gradient(90deg, rgba(6,182,212,0.04) 1px, transparent 1px);
                    background-size: auto, auto, 32px 32px, 32px 32px'></div>
        <div style='position:relative;display:flex;justify-content:space-between;
                    align-items:center;font-family:JetBrains Mono,monospace;
                    font-size:0.66rem;letter-spacing:0.22em;color:#64748b;
                    text-transform:uppercase;margin-bottom:1.0rem;font-weight:700'>
            <span>◢ {eyebrow}</span>
            <span>{today_short} · {now_time}</span>
        </div>
        <div style='position:relative;display:flex;justify-content:space-between;
                    align-items:flex-end;flex-wrap:wrap;gap:1.4rem'>
            <div style='min-width:0;flex:1'>
                <div style='font-size:2rem;font-weight:700;color:#e2e8f0;
                            letter-spacing:-0.02em;line-height:1.05'>
                    {title}
                </div>
                {subtitle_html}
                {chips_html}
            </div>
            {stats_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


def section_header(label, accent='#06b6d4'):
    """Cyan-accented section divider with monospace ◢ marker."""
    st.markdown(f"""
    <div style='display:flex;align-items:center;gap:0.8rem;margin:1.4rem 0 0.7rem'>
        <div style='font-family:JetBrains Mono,monospace;font-size:0.68rem;
                    letter-spacing:0.20em;color:#475569;text-transform:uppercase;
                    font-weight:700'>◢ {label}</div>
        <div style='flex:1;height:1px;background:linear-gradient(90deg,
                    {accent}55 0%, {accent}00 100%)'></div>
    </div>
    """, unsafe_allow_html=True)


def status_pill_html(text, status='ok', mono=True):
    """Return HTML for a compact status pill with pulsing dot.

    status: 'ok' (green), 'warn' (amber), 'error' (red), 'info' (cyan), 'muted' (gray)
    """
    colors = {
        'ok': '#10b981', 'warn': '#f59e0b', 'error': '#ef4444',
        'info': '#06b6d4', 'muted': '#64748b',
    }
    color = colors.get(status, '#64748b')
    pulse = (f"<span style='display:inline-block;width:6px;height:6px;"
             f"border-radius:50%;background:{color};"
             f"box-shadow:0 0 8px {color};animation:aqp-pulse 2s infinite;"
             f"margin-right:0.5rem'></span>")
    font_family = "JetBrains Mono,monospace" if mono else "Inter,sans-serif"
    transform = "uppercase" if mono else "none"
    return (f"<span style='display:inline-flex;align-items:center;"
            f"padding:0.25rem 0.75rem;border-radius:999px;"
            f"background:rgba(15,23,42,0.04);border:1px solid {color}33;"
            f"color:{color};font-family:{font_family};"
            f"font-size:0.68rem;font-weight:700;letter-spacing:0.10em;"
            f"text-transform:{transform}'>{pulse}{text}</span>")


def glass_card(content_html, accent='#06b6d4', padding='1.4rem 1.8rem'):
    """Render a glass panel with subtle accent border + inner content as HTML."""
    st.markdown(f"""
    <div style='position:relative;
                background:linear-gradient(135deg,
                    rgba({_hex_to_rgb(accent)},0.06) 0%,
                    rgba(15,23,42,0.02) 100%);
                border:1px solid {accent}40;
                border-radius:14px;padding:{padding};
                margin-bottom:1.0rem;
                box-shadow:0 4px 24px rgba({_hex_to_rgb(accent)},0.06)'>
        {content_html}
    </div>
    """, unsafe_allow_html=True)


def empty_state(icon, title, body, accent='#06b6d4'):
    """Glass empty-state panel with icon, title, body."""
    st.markdown(f"""
    <div style='position:relative;text-align:center;
                background:linear-gradient(135deg,
                    rgba({_hex_to_rgb(accent)},0.05) 0%,
                    rgba(15,23,42,0.02) 100%);
                border:1px dashed {accent}55;
                border-radius:14px;padding:2.5rem 2rem;
                margin-bottom:1.0rem'>
        <div style='font-size:2.2rem;opacity:0.85'>{icon}</div>
        <div style='font-size:1.05rem;font-weight:700;color:#0f172a;
                    margin-top:0.6rem;letter-spacing:-0.01em'>{title}</div>
        <div style='color:#475569;font-size:0.9rem;margin-top:0.35rem;
                    max-width:480px;margin-left:auto;margin-right:auto'>{body}</div>
    </div>
    """, unsafe_allow_html=True)


def _hex_to_rgb(hex_color):
    """'#06b6d4' -> '6,182,212' for use in rgba()."""
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = ''.join(c*2 for c in h)
    return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"


# ============================================================================
# AqueLyst brand wordmark — inline SVG/HTML recreation of the company logo.
# Cyan "Aque" + lime "Lyst" with the molecular dot/curve mark on the left,
# rendered in Playfair Display serif. No image file required — pure vector.
# ============================================================================
def brand_wordmark(size='md', show_subtitle=False, on_dark=False, with_mark=True):
    """Render the AqueLyst logo as an HTML string (returned, not printed).

    If the official logo PNG exists at assets/aquelyst-logo.png it's used as
    a data URI — pixel-perfect match to the marketing logo. Otherwise falls
    back to a vector SVG/HTML recreation (cyan 'Aque' + lime 'Lyst' in
    Playfair Display + molecular dot mark).

    Args:
        size: 'sm' (24px), 'md' (40px), 'lg' (72px), 'xl' (104px)
        show_subtitle: show "ODOR ELIMINATING TECHNOLOGY" tagline below
                        (only honored on the inline-SVG fallback — official
                        PNG already includes it as part of the artwork)
        on_dark: True if rendering on a dark surface — adapts subtitle color
        with_mark: include the molecular dot pattern (inline-SVG fallback only)
    """
    sizes = {'sm': 24, 'md': 40, 'lg': 72, 'xl': 104}
    font_px = sizes.get(size, 40)

    # Use the official logo PNG when available — that's the real wordmark
    data_uri = _logo_data_uri()
    if data_uri:
        # Original PNG aspect ratio is ~2800:1200 ≈ 2.33:1. Height ladder maps
        # to font_px so visual weight matches inline-SVG fallback.
        height_px = {
            'sm': 32,
            'md': 56,
            'lg': 96,
            'xl': 140,
        }.get(size, 56)
        return (
            f'<img src="{data_uri}" alt="AqueLyst" '
            f'style="height:{height_px}px;width:auto;vertical-align:middle;'
            f'display:inline-block" />'
        )

    # Fallback: inline SVG/HTML recreation (works without the asset file)
    mark_px = int(font_px * 1.5)

    # Molecular dot pattern — cyan + lime dots scattered along a swirling
    # path, mimicking the company logo's dotted swirl
    mark_html = ""
    if with_mark:
        mark_html = (
            f'<svg width="{mark_px}" height="{mark_px}" viewBox="0 0 60 60" '
            'style="vertical-align:middle;flex-shrink:0;display:inline-block">'
            '<path d="M 6 16 Q 18 10 24 22 T 14 38 Q 22 46 36 42 Q 48 38 50 26"'
            ' stroke="#a3e635" stroke-width="1" fill="none" opacity="0.45"/>'
            '<circle cx="6"  cy="16" r="2.4" fill="#a3e635"/>'
            '<circle cx="13" cy="11" r="1.8" fill="#06b6d4"/>'
            '<circle cx="19" cy="16" r="3.0" fill="#a3e635"/>'
            '<circle cx="24" cy="22" r="2.0" fill="#06b6d4"/>'
            '<circle cx="14" cy="28" r="2.6" fill="#a3e635"/>'
            '<circle cx="9"  cy="34" r="1.8" fill="#06b6d4"/>'
            '<circle cx="14" cy="38" r="3.2" fill="#a3e635"/>'
            '<circle cx="22" cy="44" r="2.0" fill="#06b6d4"/>'
            '<circle cx="30" cy="40" r="2.4" fill="#a3e635"/>'
            '<circle cx="36" cy="42" r="1.8" fill="#06b6d4"/>'
            '<circle cx="44" cy="36" r="2.6" fill="#a3e635"/>'
            '<circle cx="50" cy="26" r="2.0" fill="#06b6d4"/>'
            '<circle cx="42" cy="22" r="1.6" fill="#a3e635"/>'
            '<circle cx="36" cy="14" r="2.0" fill="#06b6d4"/>'
            '<circle cx="29" cy="9"  r="1.6" fill="#a3e635"/>'
            '</svg>'
        )

    tm_html = (
        f'<sup style="font-family:Inter,sans-serif;font-size:{int(font_px*0.22)}px;'
        f'color:#06b6d4;font-weight:600;margin-left:2px;'
        f'background:#06b6d4;color:#fff;padding:0 4px;border-radius:50%;'
        f'display:inline-block;width:{int(font_px*0.30)}px;'
        f'height:{int(font_px*0.30)}px;line-height:{int(font_px*0.30)}px;'
        f'text-align:center;vertical-align:super">TM</sup>'
        if size in ('lg', 'xl') else
        f'<sup style="font-family:Inter,sans-serif;font-size:{int(font_px*0.30)}px;'
        f'color:#06b6d4;font-weight:500;margin-left:1px;vertical-align:super">™</sup>'
    )

    subtitle_html = ""
    if show_subtitle:
        sub_color = '#94a3b8' if on_dark else '#64748b'
        sub_size = max(8, int(font_px * 0.16))
        subtitle_html = (
            f'<div style="font-family:Inter,sans-serif;font-size:{sub_size}px;'
            f'color:{sub_color};letter-spacing:0.22em;font-weight:600;'
            f'text-transform:uppercase;margin-top:{max(2,int(font_px*0.05))}px;'
            f'line-height:1">ODOR ELIMINATING TECHNOLOGY</div>'
        )

    return (
        f'<div style="display:inline-flex;align-items:center;gap:0.5rem;'
        f'line-height:1">'
        f'{mark_html}'
        f'<div style="display:inline-block">'
        f'<div style="font-family:\'Playfair Display\',Georgia,\'Times New Roman\',serif;'
        f'font-size:{font_px}px;font-weight:700;letter-spacing:-0.01em;'
        f'line-height:1;white-space:nowrap">'
        f'<span style="color:#06b6d4">Aque</span>'
        f'<span style="color:#a3e635">Lyst</span>'
        f'{tm_html}'
        f'</div>'
        f'{subtitle_html}'
        f'</div></div>'
    )


def render_brand_wordmark(size='md', show_subtitle=False, on_dark=False, with_mark=True):
    """Render the wordmark directly to the active Streamlit container."""
    st.markdown(brand_wordmark(size=size, show_subtitle=show_subtitle,
                                on_dark=on_dark, with_mark=with_mark),
                 unsafe_allow_html=True)
