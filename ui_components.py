"""Static, accessible presentation components for the Footy-Scout interface."""

from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape
from typing import Any, Literal
from urllib.parse import urlparse

from valuation import per_90

Player = dict[str, Any]
ComparisonDirection = Literal["higher", "lower", "context"]


APP_CSS = """
<style>
  :root {
    --fs-canvas: #07111a;
    --fs-canvas-soft: #0a1620;
    --fs-surface: #0e1a26;
    --fs-surface-raised: #132331;
    --fs-surface-soft: #172a38;
    --fs-line: #263a49;
    --fs-line-strong: #365064;
    --fs-text: #f5f8fa;
    --fs-muted: #aab8c5;
    --fs-accent: #c5f54a;
    --fs-accent-ink: #101b08;
    --fs-player-a: #43d6c5;
    --fs-player-b: #ff9b5e;
    --fs-focus: #ffe08a;
    --fs-danger: #ff8585;
    --fs-radius-sm: 10px;
    --fs-radius-md: 16px;
    --fs-radius-lg: 24px;
  }

  html, body, [class*="st-"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }

  body { color: var(--fs-text); }

  [data-testid="stAppViewContainer"] {
    background:
      radial-gradient(circle at 88% 7%, rgba(67, 214, 197, .09), transparent 30rem),
      radial-gradient(circle at 18% 72%, rgba(197, 245, 74, .05), transparent 26rem),
      linear-gradient(145deg, var(--fs-canvas) 0%, var(--fs-canvas-soft) 100%);
  }

  [data-testid="stHeader"] { background: transparent; }
  [data-testid="stDecoration"],
  [data-testid="stToolbarActions"],
  [data-testid="stAppDeployButton"],
  #MainMenu { display: none; }
  footer { visibility: hidden; }

  [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"],
  [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] [data-testid="stIconMaterial"],
  [data-testid="stExpander"] [data-testid="stIconMaterial"] {
    width: 18px;
    font-size: 0 !important;
  }

  [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"]::after,
  [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] [data-testid="stIconMaterial"]::after,
  [data-testid="stExpander"] [data-testid="stIconMaterial"]::after {
    display: inline-block;
    color: var(--fs-muted);
    font-family: inherit;
    font-size: 1.2rem;
    font-weight: 800;
    line-height: 1;
  }

  [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"]::after,
  [data-testid="stExpander"] [data-testid="stIconMaterial"]::after { content: "›"; }
  [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] [data-testid="stIconMaterial"]::after { content: "‹"; }
  [data-testid="stExpander"] details[open] [data-testid="stIconMaterial"]::after { transform: rotate(90deg); }

  .block-container {
    max-width: 1240px;
    padding: 1.5rem 2rem 4rem;
  }

  h1 {
    color: var(--fs-text) !important;
    font-size: clamp(2.25rem, 5vw, 4rem) !important;
    line-height: .98 !important;
    letter-spacing: -.045em !important;
    margin: 2rem 0 .8rem !important;
  }

  h2, h3, h4 { color: var(--fs-text) !important; letter-spacing: -.02em; }
  p { color: var(--fs-text); }

  *:focus-visible {
    outline: 3px solid var(--fs-focus) !important;
    outline-offset: 3px !important;
  }

  [data-testid="stSidebar"] {
    background:
      linear-gradient(180deg, rgba(19, 35, 49, .48), transparent 14rem),
      #09151f;
    border-right: 1px solid var(--fs-line);
  }

  [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top: 1rem;
  }

  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3,
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] p {
    color: var(--fs-text);
  }

  [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
  [data-testid="stSidebar"] small {
    color: var(--fs-muted) !important;
  }

  [data-testid="stForm"] {
    border: 0;
    padding: 0;
  }

  [data-testid="stSidebar"] [data-baseweb="select"] > div,
  [data-testid="stSidebar"] [data-baseweb="input"] > div,
  [data-testid="stSidebar"] input {
    background: var(--fs-surface) !important;
    border-color: var(--fs-line) !important;
    color: var(--fs-text) !important;
  }

  [data-testid="stSidebar"] div[role="radiogroup"],
  [data-testid="stSidebar"] [data-testid="stSegmentedControl"] {
    background: var(--fs-surface);
    border: 1px solid var(--fs-line);
    border-radius: 12px;
    padding: 4px;
  }

  .stButton > button,
  .stDownloadButton > button,
  [data-testid="stFormSubmitButton"] > button {
    min-height: 46px;
    border-radius: 12px;
    font-weight: 750;
    transition: transform .16s ease, border-color .16s ease, background .16s ease;
  }

  button[kind="primary"],
  [data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: var(--fs-accent) !important;
    border-color: var(--fs-accent) !important;
    color: var(--fs-accent-ink) !important;
  }

  button[kind="primary"] p,
  [data-testid="stFormSubmitButton"] button[kind="primary"] p {
    color: var(--fs-accent-ink) !important;
  }

  .stButton > button:hover,
  .stDownloadButton > button:hover,
  [data-testid="stFormSubmitButton"] > button:hover {
    transform: translateY(-1px);
    border-color: var(--fs-accent) !important;
  }

  [data-testid="stExpander"] {
    background: rgba(19, 35, 49, .6);
    border: 1px solid var(--fs-line);
    border-radius: var(--fs-radius-md);
  }

  [data-testid="stAlert"] {
    border-radius: var(--fs-radius-md);
    border-width: 1px;
  }

  .fs-sidebar-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: .35rem 0 1.15rem;
    border-bottom: 1px solid var(--fs-line);
    margin-bottom: 1.3rem;
  }

  .fs-sidebar-mark,
  .fs-brand-mark {
    display: inline-grid;
    place-items: center;
    width: 42px;
    height: 42px;
    flex: 0 0 42px;
    border-radius: 12px;
    background: var(--fs-accent);
    color: var(--fs-accent-ink);
    font-weight: 900;
    letter-spacing: -.06em;
    box-shadow: 0 8px 30px rgba(197, 245, 74, .15);
  }

  .fs-sidebar-wordmark {
    display: block;
    color: var(--fs-text);
    font-size: .95rem;
    font-weight: 850;
    letter-spacing: .1em;
  }

  .fs-sidebar-tagline {
    display: block;
    color: var(--fs-muted);
    font-size: .72rem;
    margin-top: 2px;
  }

  .fs-step {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 1.15rem 0 .55rem;
  }

  .fs-step-number {
    display: inline-grid;
    place-items: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: rgba(197, 245, 74, .12);
    border: 1px solid rgba(197, 245, 74, .35);
    color: var(--fs-accent);
    font-size: .7rem;
    font-weight: 900;
  }

  .fs-step-copy strong {
    display: block;
    color: var(--fs-text);
    font-size: .82rem;
    letter-spacing: .04em;
    text-transform: uppercase;
  }

  .fs-step-copy span {
    display: block;
    color: var(--fs-muted);
    font-size: .7rem;
    margin-top: 1px;
  }

  .fs-ab-key {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin: .3rem 0 .8rem;
  }

  .fs-mini-key,
  .fs-side-label,
  .fs-lead-badge,
  .fs-edu-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 999px;
    font-size: .67rem;
    font-weight: 850;
    letter-spacing: .09em;
    text-transform: uppercase;
  }

  .fs-mini-key { color: var(--fs-muted); }
  .fs-mini-key::before {
    content: "";
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
  .fs-mini-key-a::before { background: var(--fs-player-a); }
  .fs-mini-key-b::before { background: var(--fs-player-b); }

  .fs-brand-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }

  .fs-brand-lockup {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .fs-brand-name {
    color: var(--fs-text);
    font-weight: 850;
    letter-spacing: .12em;
    text-transform: uppercase;
    font-size: .82rem;
  }

  .fs-source-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-height: 34px;
    padding: 0 12px;
    border: 1px solid var(--fs-line);
    border-radius: 999px;
    background: rgba(19, 35, 49, .72);
    color: var(--fs-muted);
    font-size: .7rem;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
  }

  .fs-source-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--fs-accent);
    box-shadow: 0 0 0 4px rgba(197, 245, 74, .09);
  }

  .fs-deck {
    max-width: 700px;
    color: var(--fs-muted);
    font-size: clamp(1rem, 2vw, 1.18rem);
    line-height: 1.65;
    margin: 0 0 2rem;
  }

  .fs-section-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 16px;
    margin: 2.25rem 0 1rem;
  }

  .fs-section-kicker {
    color: var(--fs-accent);
    font-size: .68rem;
    font-weight: 850;
    letter-spacing: .13em;
    text-transform: uppercase;
    margin-bottom: 5px;
  }

  .fs-section-title {
    color: var(--fs-text);
    font-size: clamp(1.45rem, 3vw, 1.8rem);
    font-weight: 800;
    letter-spacing: -.03em;
    line-height: 1.15;
    margin: 0;
  }

  .fs-section-note {
    color: var(--fs-muted);
    font-size: .8rem;
    max-width: 360px;
    text-align: right;
  }

  .fs-matchup-stage {
    position: relative;
    overflow: hidden;
    border: 1px solid var(--fs-line);
    border-radius: var(--fs-radius-lg);
    background:
      linear-gradient(120deg, rgba(67, 214, 197, .05), transparent 35%),
      linear-gradient(240deg, rgba(255, 155, 94, .05), transparent 35%),
      var(--fs-surface);
    box-shadow: 0 24px 70px rgba(0, 0, 0, .24);
  }

  .fs-stage-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(150px, .42fr) minmax(0, 1fr);
    align-items: stretch;
  }

  .fs-player-stage {
    min-width: 0;
    padding: clamp(22px, 4vw, 38px);
  }

  .fs-player-stage-a { border-top: 3px solid var(--fs-player-a); }
  .fs-player-stage-b { border-top: 3px solid var(--fs-player-b); }

  .fs-player-stage-top {
    display: flex;
    align-items: center;
    gap: 16px;
    min-width: 0;
  }

  .fs-avatar {
    display: grid;
    place-items: center;
    width: 82px;
    height: 82px;
    flex: 0 0 82px;
    overflow: hidden;
    border-radius: 50%;
    background: var(--fs-surface-raised);
    color: var(--fs-text);
    font-size: 1.35rem;
    font-weight: 900;
    letter-spacing: -.04em;
  }

  .fs-avatar-a { border: 2px solid var(--fs-player-a); box-shadow: 0 0 0 7px rgba(67, 214, 197, .07); }
  .fs-avatar-b { border: 2px solid var(--fs-player-b); box-shadow: 0 0 0 7px rgba(255, 155, 94, .07); }
  .fs-avatar img { width: 100%; height: 100%; object-fit: cover; }

  .fs-player-identity { min-width: 0; }
  .fs-side-label { padding: 5px 8px; margin-bottom: 7px; }
  .fs-side-label-a { color: var(--fs-player-a); background: rgba(67, 214, 197, .1); }
  .fs-side-label-b { color: var(--fs-player-b); background: rgba(255, 155, 94, .1); }

  .fs-player-name {
    color: var(--fs-text);
    font-size: clamp(1.35rem, 3vw, 1.75rem);
    font-weight: 820;
    letter-spacing: -.035em;
    line-height: 1.08;
    margin: 0;
    overflow-wrap: anywhere;
  }

  .fs-player-meta {
    color: var(--fs-muted);
    font-size: .82rem;
    margin-top: 6px;
    overflow-wrap: anywhere;
  }

  .fs-chip-row { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 20px; }
  .fs-chip {
    border: 1px solid var(--fs-line);
    border-radius: 999px;
    color: var(--fs-muted);
    background: rgba(255,255,255,.018);
    padding: 5px 9px;
    font-size: .69rem;
    font-weight: 700;
  }

  .fs-estimate { margin-top: 28px; }
  .fs-estimate-label {
    color: var(--fs-muted);
    font-size: .7rem;
    font-weight: 800;
    letter-spacing: .1em;
    text-transform: uppercase;
  }

  .fs-estimate-value {
    color: var(--fs-text);
    font-size: clamp(2.15rem, 5vw, 3rem);
    font-weight: 880;
    letter-spacing: -.055em;
    line-height: 1;
    margin-top: 7px;
    font-variant-numeric: tabular-nums;
  }

  .fs-estimate-range { color: var(--fs-muted); font-size: .75rem; margin-top: 9px; }

  .fs-versus {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 24px 14px;
    border-left: 1px solid var(--fs-line);
    border-right: 1px solid var(--fs-line);
    background: rgba(7, 17, 26, .38);
  }

  .fs-vs-mark {
    display: grid;
    place-items: center;
    width: 52px;
    height: 52px;
    border-radius: 50%;
    border: 1px solid var(--fs-line-strong);
    background: var(--fs-surface-raised);
    color: var(--fs-text);
    font-size: .72rem;
    font-weight: 900;
    letter-spacing: .12em;
  }

  .fs-gap-label {
    color: var(--fs-muted);
    font-size: .62rem;
    font-weight: 850;
    letter-spacing: .1em;
    text-transform: uppercase;
    margin-top: 20px;
  }

  .fs-gap-value {
    color: var(--fs-accent);
    font-size: 1.35rem;
    font-weight: 850;
    margin-top: 4px;
    font-variant-numeric: tabular-nums;
  }

  .fs-gap-copy { color: var(--fs-muted); font-size: .72rem; line-height: 1.4; margin-top: 7px; }

  .fs-overview,
  .fs-duel-panel,
  .fs-valuation-panel {
    border: 1px solid var(--fs-line);
    border-radius: var(--fs-radius-lg);
    background: rgba(14, 26, 38, .86);
  }

  .fs-overview { display: grid; grid-template-columns: 1fr 1px 1fr; }
  .fs-overview-divider { background: var(--fs-line); }
  .fs-overview-side { padding: 24px; min-width: 0; }
  .fs-overview-side-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 17px;
    color: var(--fs-muted);
    font-size: .72rem;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
  }

  .fs-overview-facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
  .fs-fact {
    min-width: 0;
    border-radius: var(--fs-radius-sm);
    background: var(--fs-surface-raised);
    padding: 13px;
  }
  .fs-fact-value {
    display: block;
    color: var(--fs-text);
    font-size: 1.15rem;
    font-weight: 820;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }
  .fs-fact-label { display: block; color: var(--fs-muted); font-size: .66rem; margin-top: 4px; }
  .fs-rating-rail { display:block; height:3px; background:#263a49; border-radius:99px; margin-top:8px; overflow:hidden; }
  .fs-rating-rail i { display:block; height:100%; border-radius:99px; }
  .fs-overview-a .fs-rating-rail i { background: var(--fs-player-a); }
  .fs-overview-b .fs-rating-rail i { background: var(--fs-player-b); }

  .fs-insights { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .fs-insight-card {
    border: 1px solid var(--fs-line);
    border-radius: var(--fs-radius-md);
    background: rgba(19, 35, 49, .6);
    padding: 17px;
    min-width: 0;
  }
  .fs-insight-label { color: var(--fs-muted); font-size: .65rem; font-weight: 850; letter-spacing: .1em; text-transform: uppercase; }
  .fs-insight-winner { color: var(--fs-text); font-size: .95rem; font-weight: 800; margin-top: 8px; overflow-wrap: anywhere; }
  .fs-insight-detail { color: var(--fs-muted); font-size: .72rem; margin-top: 5px; line-height: 1.45; }

  .fs-duel-panel { overflow: hidden; }
  .fs-duel-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  .fs-duel-table caption { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
  .fs-duel-table td, .fs-duel-table th { padding: 13px 18px; border-bottom: 1px solid rgba(38, 58, 73, .72); }
  .fs-duel-table tr:last-child td, .fs-duel-table tr:last-child th { border-bottom: 0; }
  .fs-duel-group th {
    padding: 14px 18px 8px;
    background: rgba(7, 17, 26, .28);
    color: var(--fs-accent);
    font-size: .64rem;
    font-weight: 900;
    letter-spacing: .12em;
    text-transform: uppercase;
    text-align: left;
  }
  .fs-duel-side { width: 38%; }
  .fs-duel-metric { width: 24%; text-align: center; color: var(--fs-text); font-size: .76rem; font-weight: 750; }
  .fs-duel-hint { display:block; color:var(--fs-muted); font-size:.55rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin-top:2px; }
  .fs-duel-value-row { display:flex; align-items:center; gap:8px; }
  .fs-duel-side-a .fs-duel-value-row { justify-content:flex-end; }
  .fs-duel-side-b .fs-duel-value-row { justify-content:flex-start; }
  .fs-duel-value { color:var(--fs-muted); font-size:.8rem; font-weight:760; font-variant-numeric:tabular-nums; min-width:38px; }
  .fs-duel-value.is-leading { color:var(--fs-text); }
  .fs-lead-badge { color:var(--fs-accent); font-size:.52rem; }
  .fs-bar-track { display:flex; align-items:center; width:100%; max-width:170px; height:6px; background:#1b2d3b; border-radius:99px; overflow:hidden; }
  .fs-duel-side-a .fs-bar-track { justify-content:flex-end; }
  .fs-bar { display:block; height:100%; min-width:0; border-radius:99px; }
  .fs-bar-a { background:var(--fs-player-a); }
  .fs-bar-b { background:var(--fs-player-b); }

  .fs-valuation-panel { padding: clamp(20px, 4vw, 30px); }
  .fs-valuation-method { display:grid; grid-template-columns:minmax(0,1fr) minmax(130px,.55fr) minmax(0,1fr); gap:18px; align-items:center; padding:18px 0; border-bottom:1px solid var(--fs-line); }
  .fs-valuation-method:last-of-type { border-bottom:0; }
  .fs-method-side { min-width:0; }
  .fs-method-side-b { text-align:right; }
  .fs-method-value { color:var(--fs-text); font-size:1.1rem; font-weight:820; font-variant-numeric:tabular-nums; }
  .fs-method-track { display:flex; width:100%; height:7px; margin-top:8px; background:#1b2d3b; border-radius:99px; overflow:hidden; }
  .fs-method-side-a .fs-method-track { justify-content:flex-start; }
  .fs-method-side-b .fs-method-track { justify-content:flex-end; }
  .fs-method-copy { text-align:center; }
  .fs-method-name { color:var(--fs-text); font-size:.82rem; font-weight:820; }
  .fs-method-description { color:var(--fs-muted); font-size:.64rem; margin-top:3px; }
  .fs-edu-badge { color:var(--fs-accent); background:rgba(197,245,74,.08); border:1px solid rgba(197,245,74,.2); padding:5px 8px; }
  .fs-spread-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:18px; }
  .fs-spread-card { background:var(--fs-surface-raised); border-radius:var(--fs-radius-sm); padding:14px; color:var(--fs-muted); font-size:.72rem; }
  .fs-spread-card strong { display:block; color:var(--fs-text); font-size:.92rem; margin-top:4px; font-variant-numeric:tabular-nums; }

  .st-key-export_tray {
    margin-top: 2.25rem;
    padding: clamp(18px, 4vw, 28px);
    border: 1px solid var(--fs-line);
    border-radius: var(--fs-radius-lg);
    background: linear-gradient(120deg, rgba(197,245,74,.06), transparent 36%), var(--fs-surface);
  }
  .st-key-export_tray h3 { margin-top:0; }
  .st-key-export_tray p { color:var(--fs-muted); }
  .st-key-export_tray [data-testid="stDownloadButton"] button { width:100%; }

  @media (max-width: 900px) {
    .block-container { padding-left: 1.25rem; padding-right: 1.25rem; }
    .fs-stage-grid { grid-template-columns: 1fr; }
    .fs-versus { border:0; border-top:1px solid var(--fs-line); border-bottom:1px solid var(--fs-line); padding:18px; }
    .fs-vs-mark { width:42px; height:42px; }
    .fs-gap-label { margin-top:10px; }
    .fs-overview { grid-template-columns:1fr; }
    .fs-overview-divider { height:1px; }
    .fs-overview-facts { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .fs-insights { grid-template-columns:1fr; }
    .fs-valuation-method { grid-template-columns:1fr; gap:10px; }
    .fs-method-copy { order:-1; text-align:left; }
    .fs-method-side-b { text-align:left; }
    .fs-method-side-b .fs-method-track { justify-content:flex-start; }
  }

  @media (max-width: 640px) {
    .block-container { padding: 1rem 1rem 3rem; }
    [data-testid="stExpandSidebarButton"] {
      position: fixed;
      top: 14px;
      right: 14px;
      z-index: 1000;
      width: 38px;
      height: 38px;
      border: 1px solid var(--fs-line);
      border-radius: 10px;
      background: rgba(19,35,49,.94);
    }
    h1 { margin-top:1.45rem !important; }
    .fs-brand-row { align-items:flex-start; }
    .fs-source-badge { width:100%; justify-content:center; }
    .fs-section-head { align-items:flex-start; flex-direction:column; gap:6px; }
    .fs-section-note { text-align:left; }
    .fs-player-stage-top { align-items:flex-start; }
    .fs-avatar { width:68px; height:68px; flex-basis:68px; }
    .fs-estimate-value { font-size:2.1rem; }
    .fs-duel-table td, .fs-duel-table th { padding:11px 8px; }
    .fs-duel-side { width:35%; }
    .fs-duel-metric { width:30%; font-size:.68rem; }
    .fs-bar-track { display:none; }
    .fs-duel-value-row { justify-content:center !important; }
    .fs-lead-badge { display:none; }
    .fs-spread-grid { grid-template-columns:1fr; }
    .st-key-export_tray [data-testid="stHorizontalBlock"] { flex-direction:column; }
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { scroll-behavior:auto !important; transition:none !important; animation:none !important; }
  }
</style>
"""


@dataclass(frozen=True)
class MetricSpec:
    group: str
    label: str
    key: str
    decimals: int = 0
    rate: bool = False
    direction: ComparisonDirection = "higher"
    hint: str = ""


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def display_number(value: Any, decimals: int = 0) -> str:
    number = _number(value)
    if number is None:
        return "—"
    return f"{number:,.{decimals}f}" if decimals else f"{number:,.0f}"


def _initials(name: Any) -> str:
    words = [word for word in str(name or "Player").replace("-", " ").split() if word]
    return "".join(word[0] for word in words[:2]).upper() or "P"


def _safe_photo_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


def included_items(player: Player, plural_key: str, fallback_key: str) -> str:
    values = player.get(plural_key)
    if isinstance(values, list) and values:
        return ", ".join(str(value) for value in values)
    return str(player.get(fallback_key) or "Unknown")


def sidebar_brand_html() -> str:
    return """
    <div class="fs-sidebar-brand">
      <span class="fs-sidebar-mark" aria-hidden="true">FS</span>
      <span>
        <span class="fs-sidebar-wordmark">Footy-Scout</span>
        <span class="fs-sidebar-tagline">Matchup intelligence</span>
      </span>
    </div>
    """


def sidebar_step_html(number: int, title: str, detail: str) -> str:
    return (
        '<div class="fs-step">'
        f'<span class="fs-step-number">{number}</span>'
        '<span class="fs-step-copy">'
        f"<strong>{escape(title)}</strong><span>{escape(detail)}</span>"
        "</span></div>"
    )


def player_key_html() -> str:
    return """
    <div class="fs-ab-key" aria-label="Player color key">
      <span class="fs-mini-key fs-mini-key-a">Player A</span>
      <span class="fs-mini-key fs-mini-key-b">Player B</span>
    </div>
    """


def masthead_html(source_note: str) -> str:
    return f"""
    <div class="fs-brand-row">
      <div class="fs-brand-lockup">
        <span class="fs-brand-mark" aria-hidden="true">FS</span>
        <span class="fs-brand-name">Footy-Scout</span>
      </div>
      <span class="fs-source-badge">
        <span class="fs-source-dot" aria-hidden="true"></span>
        {escape(source_note)}
      </span>
    </div>
    """


def section_header_html(kicker: str, title: str, note: str = "") -> str:
    note_html = f'<div class="fs-section-note">{escape(note)}</div>' if note else ""
    return f"""
    <div class="fs-section-head">
      <div>
        <div class="fs-section-kicker">{escape(kicker)}</div>
        <h2 class="fs-section-title">{escape(title)}</h2>
      </div>
      {note_html}
    </div>
    """


def _avatar_html(player: Player, side: str) -> str:
    name = str(player.get("name") or "Unknown player")
    photo_url = _safe_photo_url(player.get("photo"))
    if photo_url:
        content = (
            f'<img src="{escape(photo_url, quote=True)}" '
            f'alt="Portrait of {escape(name, quote=True)}">'
        )
    else:
        content = f'<span aria-hidden="true">{escape(_initials(name))}</span>'
    return f'<div class="fs-avatar fs-avatar-{side}">{content}</div>'


def _player_stage_html(
    player: Player,
    values: dict[str, float],
    blended: float,
    side: str,
) -> str:
    name = str(player.get("name") or "Unknown player")
    low, high = min(values.values()), max(values.values())
    chips = [
        f"Season {player.get('season') or '—'}",
        str(player.get("scope") or player.get("league") or "Competition unavailable"),
    ]
    chip_html = "".join(
        f'<span class="fs-chip">{escape(chip)}</span>' for chip in chips
    )
    return f"""
    <article class="fs-player-stage fs-player-stage-{side}" aria-label="Player {side.upper()}: {escape(name)}">
      <div class="fs-player-stage-top">
        {_avatar_html(player, side)}
        <div class="fs-player-identity">
          <span class="fs-side-label fs-side-label-{side}">Player {side.upper()}</span>
          <h3 class="fs-player-name">{escape(name)}</h3>
          <div class="fs-player-meta">{escape(str(player.get('team') or 'Unknown team'))} · {escape(str(player.get('position') or 'Unknown position'))}</div>
        </div>
      </div>
      <div class="fs-chip-row">{chip_html}</div>
      <div class="fs-estimate">
        <div class="fs-estimate-label">Blended estimate</div>
        <div class="fs-estimate-value">€{blended:,.2f}M</div>
        <div class="fs-estimate-range">Method range €{low:,.2f}M–€{high:,.2f}M</div>
      </div>
    </article>
    """


def matchup_html(
    players: list[Player],
    valuations: list[dict[str, float]],
    blended_values: list[float],
) -> str:
    margin = abs(blended_values[0] - blended_values[1])
    if margin < 0.005:
        gap_copy = "Estimates are level"
    else:
        leader_index = 0 if blended_values[0] > blended_values[1] else 1
        side = "A" if leader_index == 0 else "B"
        gap_copy = (
            f"Player {side} · {players[leader_index].get('name', 'Player')} leads"
        )
    return f"""
    <section class="fs-matchup-stage" aria-label="Player matchup">
      <div class="fs-stage-grid">
        {_player_stage_html(players[0], valuations[0], blended_values[0], 'a')}
        <div class="fs-versus" aria-label="Comparison result">
          <span class="fs-vs-mark" aria-hidden="true">VS</span>
          <span class="fs-gap-label">Valuation gap</span>
          <strong class="fs-gap-value">€{margin:,.2f}M</strong>
          <span class="fs-gap-copy">{escape(gap_copy)}</span>
        </div>
        {_player_stage_html(players[1], valuations[1], blended_values[1], 'b')}
      </div>
    </section>
    """


def _fact_html(label: str, value: str, rating: float | None, side: str) -> str:
    rail = ""
    if rating is not None:
        width = min(max(rating * 10.0, 0.0), 100.0)
        rail = (
            '<span class="fs-rating-rail" aria-hidden="true">'
            f'<i style="width:{width:.1f}%"></i></span>'
        )
    return f"""
    <div class="fs-fact">
      <span class="fs-fact-value">{escape(value)}</span>
      <span class="fs-fact-label">{escape(label)}</span>
      {rail}
    </div>
    """


def _overview_side_html(player: Player, side: str) -> str:
    rating = _number(player.get("rating"))
    facts = (
        _fact_html("Age", display_number(player.get("age")), None, side)
        + _fact_html("Appearances", display_number(player.get("games")), None, side)
        + _fact_html("Minutes", display_number(player.get("minutes")), None, side)
        + _fact_html("Season rating", display_number(rating, 2), rating, side)
    )
    return f"""
    <div class="fs-overview-side fs-overview-{side}">
      <div class="fs-overview-side-head">
        <span class="fs-side-label fs-side-label-{side}">{side.upper()}</span>
        {escape(str(player.get('name') or 'Player'))}
      </div>
      <div class="fs-overview-facts">{facts}</div>
    </div>
    """


def overview_html(players: list[Player]) -> str:
    return f"""
    <section class="fs-overview" aria-label="Season overview">
      {_overview_side_html(players[0], 'a')}
      <div class="fs-overview-divider" aria-hidden="true"></div>
      {_overview_side_html(players[1], 'b')}
    </section>
    """


def performance_specs(players: list[Player]) -> list[MetricSpec]:
    specs = [
        MetricSpec("Usage", "Appearances", "games", direction="context"),
        MetricSpec("Usage", "Minutes", "minutes", direction="context"),
        MetricSpec("Usage", "Season rating", "rating", decimals=2),
        MetricSpec("Attack", "Goals", "goals"),
        MetricSpec("Attack", "Goals / 90", "goals", decimals=2, rate=True),
        MetricSpec("Attack", "Assists", "assists"),
        MetricSpec("Attack", "Assists / 90", "assists", decimals=2, rate=True),
    ]
    positions = " ".join(
        str(player.get("position") or "").lower() for player in players
    )
    has_defensive_data = any(
        (_number(player.get("tackles")) or 0) > 0
        or (_number(player.get("interceptions")) or 0) > 0
        for player in players
    )
    if has_defensive_data or any(
        role in positions for role in ("defender", "midfielder")
    ):
        specs.extend(
            [
                MetricSpec(
                    "Out of possession",
                    "Tackles / 90",
                    "tackles",
                    decimals=2,
                    rate=True,
                ),
                MetricSpec(
                    "Out of possession",
                    "Interceptions / 90",
                    "interceptions",
                    decimals=2,
                    rate=True,
                ),
            ]
        )
    if any(player.get("clean_sheets") is not None for player in players):
        specs.append(MetricSpec("Out of possession", "Clean sheets", "clean_sheets"))
    if "goalkeeper" in positions:
        specs.extend(
            [
                MetricSpec("Goalkeeping", "Saves / 90", "saves", decimals=2, rate=True),
                MetricSpec(
                    "Goalkeeping",
                    "Goals conceded / 90",
                    "conceded",
                    decimals=2,
                    rate=True,
                    direction="lower",
                    hint="Lower is better",
                ),
            ]
        )
    return specs


def metric_value(player: Player, spec: MetricSpec) -> float | None:
    raw = _number(player.get(spec.key))
    if raw is None:
        return None
    if not spec.rate:
        return raw
    minutes = _number(player.get("minutes"))
    if minutes is None or minutes <= 0:
        return None
    return per_90(raw, minutes)


def _leader_indexes(
    values: list[float | None], direction: ComparisonDirection
) -> set[int]:
    if direction == "context" or any(value is None for value in values):
        return set()
    first, second = values
    if first is None or second is None or abs(first - second) < 0.005:
        return set()
    if direction == "lower":
        return {0 if first < second else 1}
    return {0 if first > second else 1}


def _duel_side_html(
    value: float | None,
    width: float,
    decimals: int,
    side: str,
    leading: bool,
) -> str:
    lead = '<span class="fs-lead-badge">Lead</span>' if leading else ""
    leading_class = " is-leading" if leading else ""
    bar = (
        ""
        if value is None
        else f'<span class="fs-bar fs-bar-{side}" style="width:{width:.1f}%"></span>'
    )
    value_text = display_number(value, decimals)
    if side == "a":
        content = f'{lead}<span class="fs-duel-value{leading_class}">{value_text}</span><span class="fs-bar-track" aria-hidden="true">{bar}</span>'
    else:
        content = f'<span class="fs-bar-track" aria-hidden="true">{bar}</span><span class="fs-duel-value{leading_class}">{value_text}</span>{lead}'
    return f'<td class="fs-duel-side fs-duel-side-{side}"><div class="fs-duel-value-row">{content}</div></td>'


def performance_duel_html(players: list[Player]) -> str:
    rows: list[str] = []
    current_group = ""
    for spec in performance_specs(players):
        if spec.group != current_group:
            rows.append(
                f'<tr class="fs-duel-group"><th colspan="3">{escape(spec.group)}</th></tr>'
            )
            current_group = spec.group
        values = [metric_value(player, spec) for player in players]
        measured = [value for value in values if value is not None]
        scale = max(measured, default=0.0)
        widths = [
            0.0 if value is None or scale <= 0 else value / scale * 100.0
            for value in values
        ]
        leaders = _leader_indexes(values, spec.direction)
        hint = (
            f'<span class="fs-duel-hint">{escape(spec.hint)}</span>'
            if spec.hint
            else ""
        )
        rows.append(
            "<tr>"
            + _duel_side_html(values[0], widths[0], spec.decimals, "a", 0 in leaders)
            + f'<th scope="row" class="fs-duel-metric">{escape(spec.label)}{hint}</th>'
            + _duel_side_html(values[1], widths[1], spec.decimals, "b", 1 in leaders)
            + "</tr>"
        )
    return f"""
    <section class="fs-duel-panel" aria-label="Performance duel">
      <table class="fs-duel-table">
        <caption>Side-by-side season performance for Player A and Player B</caption>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


def _insight_html(label: str, players: list[Player], spec: MetricSpec) -> str:
    values = [metric_value(player, spec) for player in players]
    if any(value is None for value in values):
        winner = "Insufficient data"
        detail = "This signal is not available for both players."
    elif abs(values[0] - values[1]) < 0.005:
        winner = "Level signal"
        detail = f"Both players record {display_number(values[0], spec.decimals)}."
    else:
        leader = 0 if values[0] > values[1] else 1
        side = "A" if leader == 0 else "B"
        difference = abs(values[0] - values[1])
        winner = f"Player {side} · {players[leader].get('name', 'Player')}"
        detail = f"Leads by {display_number(difference, spec.decimals)} in {spec.label.lower()}."
    return f"""
    <article class="fs-insight-card">
      <div class="fs-insight-label">{escape(label)}</div>
      <div class="fs-insight-winner">{escape(winner)}</div>
      <div class="fs-insight-detail">{escape(detail)}</div>
    </article>
    """


def insights_html(players: list[Player]) -> str:
    cards = [
        _insight_html(
            "Goal threat", players, MetricSpec("", "goals / 90", "goals", 2, True)
        ),
        _insight_html(
            "Chance creation",
            players,
            MetricSpec("", "assists / 90", "assists", 2, True),
        ),
        _insight_html(
            "Form signal", players, MetricSpec("", "season rating", "rating", 2)
        ),
    ]
    return f'<section class="fs-insights" aria-label="Quick comparison insights">{"".join(cards)}</section>'


def valuation_lab_html(
    players: list[Player], valuations: list[dict[str, float]]
) -> str:
    method_names = list(valuations[0])
    overall_max = (
        max(value for result in valuations for value in result.values()) or 1.0
    )
    descriptions = {
        "Heuristic": "Bounded role model",
        "Demo ML": "Constrained synthetic model",
    }
    methods: list[str] = []
    for method in method_names:
        left = valuations[0][method]
        right = valuations[1][method]
        left_width = left / overall_max * 100.0
        right_width = right / overall_max * 100.0
        methods.append(
            f"""
            <div class="fs-valuation-method">
              <div class="fs-method-side fs-method-side-a">
                <div class="fs-method-value">€{left:,.2f}M</div>
                <div class="fs-method-track" aria-hidden="true"><span class="fs-bar fs-bar-a" style="width:{left_width:.1f}%"></span></div>
              </div>
              <div class="fs-method-copy">
                <div class="fs-method-name">{escape(method)}</div>
                <div class="fs-method-description">{escape(descriptions.get(method, 'Illustrative method'))}</div>
              </div>
              <div class="fs-method-side fs-method-side-b">
                <div class="fs-method-value">€{right:,.2f}M</div>
                <div class="fs-method-track" aria-hidden="true"><span class="fs-bar fs-bar-b" style="width:{right_width:.1f}%"></span></div>
              </div>
            </div>
            """
        )
    spreads = [max(values.values()) - min(values.values()) for values in valuations]
    return f"""
    <section class="fs-valuation-panel" aria-label="Valuation model comparison">
      {''.join(methods)}
      <div class="fs-spread-grid">
        <div class="fs-spread-card">Player A · {escape(str(players[0].get('name') or 'Player'))}<strong>€{spreads[0]:,.2f}M method spread</strong></div>
        <div class="fs-spread-card">Player B · {escape(str(players[1].get('name') or 'Player'))}<strong>€{spreads[1]:,.2f}M method spread</strong></div>
      </div>
    </section>
    """
