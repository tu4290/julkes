# dashboard_application/modes/advanced_flow_mode_v2_5.py
# EOTS v2.5 - S-GRADE, AUTHORITATIVE ADVANCED FLOW DISPLAY

import logging
from typing import Optional
from datetime import datetime # Added for timestamp type hint

import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc
import dash_bootstrap_components as dbc
import numpy as np

# EOTS v2.5 Imports
from data_models.eots_schemas_v2_5 import FinalAnalysisBundleV2_5 # ProcessedUnderlyingAggregatesV2_5 is part of this
from utils.config_manager_v2_5 import ConfigManagerV2_5
from dashboard_application.utils_dashboard_v2_5 import create_empty_figure, add_timestamp_annotation, add_bottom_right_timestamp_annotation, PLOTLY_TEMPLATE
from dashboard_application import ids

logger = logging.getLogger(__name__)

# --- Helper Function for Chart Generation ---

def _create_z_score_gauge(
    metric_name: str,
    z_score_value: Optional[float],
    symbol: str,
    component_id: str,
    config: ConfigManagerV2_5, # Added config manager
    timestamp: Optional[datetime] # Added timestamp for annotation
) -> html.Div:
    """A centralized helper to create the Z-Score gauge chart as a Div with about section."""

    adv_flow_settings = config.get_setting('visualization_settings.dashboard.advanced_flow_chart_settings', default={}) or {}
    gauge_specific_height_key = f"{metric_name.lower().replace(' ', '_').replace('-', '_')}_gauge_height" # e.g., vapi_fa_gauge_height
    fig_height = adv_flow_settings.get(gauge_specific_height_key, adv_flow_settings.get('default_gauge_height', 250))

    title_text = f"<b>{symbol}</b> - {metric_name}"

    # Type-safe and NA-safe check for z_score_value
    if z_score_value is None or (isinstance(z_score_value, float) and pd.isna(z_score_value)):
        fig = create_empty_figure(title=title_text, height=fig_height, reason=f"{metric_name} N/A")
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id=component_id, figure=fig)
    else:
        try:
            value = float(z_score_value)
        except Exception:
            value = 0.0
        context = get_metric_context(metric_name, value)
        hover_text = f"""
        <b>{symbol} - {metric_name}</b><br>
        Current Value: {value:.2f}<br>
        Range: -3 to +3<br>
        <b>Context:</b> {context}<br>
        <extra></extra>
        """
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=value,
            title={'text': metric_name, 'font': {'size': 18}}, # Gauge-internal title
            number={'font': {'size': 36}},
            gauge={
                'axis': {'range': [-3, 3], 'tickwidth': 1, 'tickcolor': "darkgrey"},
                'bar': {'color': "rgba(0,0,0,0)"},
                'steps': [
                    {'range': [-3.0, -2.0], 'color': adv_flow_settings.get("gauge_color_strong_neg", '#d62728')},
                    {'range': [-2.0, -0.5], 'color': adv_flow_settings.get("gauge_color_mild_neg", '#ff9896')},
                    {'range': [-0.5, 0.5], 'color': adv_flow_settings.get("gauge_color_neutral", '#aec7e8')},
                    {'range': [0.5, 2.0], 'color': adv_flow_settings.get("gauge_color_mild_pos", '#98df8a')},
                    {'range': [2.0, 3.0], 'color': adv_flow_settings.get("gauge_color_strong_pos", '#2ca02c')}
                ],
                'threshold': {
                    'line': {'color': adv_flow_settings.get("gauge_threshold_line_color", "white"), 'width': 5},
                    'thickness': 0.95, 'value': value
                }
            }
        ))
        # Add invisible scatter for custom hover
        fig.add_trace(go.Scatter(
            x=[0.5], y=[0.5],
            mode='markers',
            marker=dict(size=1, opacity=0),
            hovertemplate=hover_text,
            showlegend=False,
            name=""
        ))
        fig.update_layout(
            title={'text': title_text, 'y': 0.95, 'x': 0.5, 'xanchor': 'center', 'yanchor': 'top'}, # Main figure title
            height=fig_height,
            margin=adv_flow_settings.get("gauge_margin", {'t': 60, 'b': 40, 'l': 20, 'r': 20}), # Configurable margin, added more bottom margin for timestamp
            template=PLOTLY_TEMPLATE,
            showlegend=True
        )
        # Hide gridlines and axes for gauge charts
        fig.update_xaxes(showgrid=False, zeroline=False, visible=False)
        fig.update_yaxes(showgrid=False, zeroline=False, visible=False)
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id=component_id, figure=fig)

    # Use robust about blurbs
    about_blurb_map = {
        "VAPI-FA": ABOUT_VAPI_FA,
        "DWFD": ABOUT_DWFD,
        "TW-LAF": ABOUT_TW_LAF
    }
    about = make_about_section(about_blurb_map.get(metric_name, "See About for details."), component_id)
    return html.Div(about + [chart])

def _create_vapifa_historical_chart(und_data, symbol, config, timestamp) -> html.Div:
    """Create a Plotly time series chart for VAPI-FA Z-score history as a Div with about section."""
    # Attempt to extract VAPI-FA Z-score history from underlying data
    vapifa_hist = getattr(und_data, 'vapifa_zscore_history', None)
    time_hist = getattr(und_data, 'vapifa_time_history', None)
    if vapifa_hist is None or time_hist is None or len(vapifa_hist) == 0:
        fig = create_empty_figure(title=f"{symbol} - VAPI-FA Z-Score History", height=300, reason="No VAPI-FA history available")
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='vapifa-historical-chart', figure=fig)
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=time_hist,
            y=vapifa_hist,
            mode='lines+markers',
            name='VAPI-FA Z-Score',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=4),
            hovertemplate='Time: %{x}<br>VAPI-FA Z: %{y:.2f}<br>Context: ' + get_metric_context("VAPI-FA") + '<extra></extra>'
        ))
        fig.update_layout(
            title=f"{symbol} - VAPI-FA Z-Score History",
            xaxis_title="Time",
            yaxis_title="VAPI-FA Z-Score",
            height=300,
            template=PLOTLY_TEMPLATE,
            margin=dict(t=60, b=40, l=20, r=20),
            showlegend=True
        )
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='vapifa-historical-chart', figure=fig)
    about = make_about_section(ABOUT_VAPI_FA, 'vapifa-historical-chart')
    return html.Div(about + [chart])

def _create_dwfd_historical_chart(und_data, symbol, config, timestamp) -> html.Div:
    dwfd_hist = getattr(und_data, 'dwfd_zscore_history', None)
    time_hist = getattr(und_data, 'dwfd_time_history', None)
    if dwfd_hist is None or time_hist is None or len(dwfd_hist) == 0:
        fig = create_empty_figure(title=f"{symbol} - DWFD Z-Score History", height=300, reason="No DWFD history available")
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='dwfd-historical-chart', figure=fig)
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=time_hist,
            y=dwfd_hist,
            mode='lines+markers',
            name='DWFD Z-Score',
            line=dict(color='#ff7f0e', width=2),
            marker=dict(size=4),
            hovertemplate='Time: %{x}<br>DWFD Z: %{y:.2f}<br>Context: ' + get_metric_context("DWFD") + '<extra></extra>'
        ))
        fig.update_layout(
            title=f"{symbol} - DWFD Z-Score History",
            xaxis_title="Time",
            yaxis_title="DWFD Z-Score",
            height=300,
            template=PLOTLY_TEMPLATE,
            margin=dict(t=60, b=40, l=20, r=20),
            showlegend=True
        )
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='dwfd-historical-chart', figure=fig)
    about = make_about_section(ABOUT_DWFD, 'dwfd-historical-chart')
    return html.Div(about + [chart])

def _create_twlaf_historical_chart(und_data, symbol, config, timestamp) -> html.Div:
    twlaf_hist = getattr(und_data, 'twlaf_zscore_history', None)
    time_hist = getattr(und_data, 'twlaf_time_history', None)
    if twlaf_hist is None or time_hist is None or len(twlaf_hist) == 0:
        fig = create_empty_figure(title=f"{symbol} - TW-LAF Z-Score History", height=300, reason="No TW-LAF history available")
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='twlaf-historical-chart', figure=fig)
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=time_hist,
            y=twlaf_hist,
            mode='lines+markers',
            name='TW-LAF Z-Score',
            line=dict(color='#2ca02c', width=2),
            marker=dict(size=4),
            hovertemplate='Time: %{x}<br>TW-LAF Z: %{y:.2f}<br>Context: ' + get_metric_context("TW-LAF") + '<extra></extra>'
        ))
        fig.update_layout(
            title=f"{symbol} - TW-LAF Z-Score History",
            xaxis_title="Time",
            yaxis_title="TW-LAF Z-Score",
            height=300,
            template=PLOTLY_TEMPLATE,
            margin=dict(t=60, b=40, l=20, r=20),
            showlegend=True
        )
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='twlaf-historical-chart', figure=fig)
    about = make_about_section(ABOUT_TW_LAF, 'twlaf-historical-chart')
    return html.Div(about + [chart])

def _create_rolling_flows_chart(und_data, symbol, config, timestamp) -> html.Div:
    flows = getattr(und_data, 'rolling_flows', None)
    time_hist = getattr(und_data, 'rolling_flows_time', None)
    if flows is None or time_hist is None or not isinstance(flows, dict) or len(flows) == 0:
        fig = create_empty_figure(title=f"{symbol} - Rolling Net Signed Flows", height=300, reason="No rolling flows data available")
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='rolling-flows-chart', figure=fig)
    else:
        fig = go.Figure()
        for window, values in flows.items():
            # Defensive: ensure values is always a list/array
            if not isinstance(values, (list, tuple, pd.Series, np.ndarray)):
                values = [values]
            fig.add_trace(go.Scatter(
                x=time_hist,
                y=values,
                mode='lines',
                name=f'{window} Flow',
                hovertemplate=f'Time: %{{x}}<br>{window} Flow: %{{y:.2f}}<br>Context: ' + get_metric_context(f"{window} Flow") + '<extra></extra>'
            ))
        fig.update_layout(
            title=f"{symbol} - Rolling Net Signed Flows",
            xaxis_title="Time",
            yaxis_title="Net Signed Flow",
            height=300,
            template=PLOTLY_TEMPLATE,
            margin=dict(t=60, b=40, l=20, r=20)
        )
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='rolling-flows-chart', figure=fig)
    about = make_about_section(ABOUT_ROLLING_FLOWS, 'rolling-flows-chart')
    return html.Div(about + [chart])

def _create_nvp_charts(und_data, symbol, config, timestamp) -> html.Div:
    nvp = getattr(und_data, 'nvp_by_strike', None)
    nvp_vol = getattr(und_data, 'nvp_vol_by_strike', None)
    strikes = getattr(und_data, 'strikes', None)
    if nvp is None or nvp_vol is None or strikes is None or len(strikes) == 0:
        fig = create_empty_figure(title=f"{symbol} - NVP & NVP_Vol by Strike", height=300, reason="No NVP data available")
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='nvp-charts', figure=fig)
    else:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=strikes,
            y=nvp,
            name='NVP',
            marker_color='#9467bd',
            hovertemplate='Strike: %{x}<br>NVP: %{y:.2f}<br>Context: ' + get_metric_context("NVP") + '<extra></extra>'
        ))
        fig.add_trace(go.Bar(
            x=strikes,
            y=nvp_vol,
            name='NVP_Vol',
            marker_color='#8c564b',
            hovertemplate='Strike: %{x}<br>NVP_Vol: %{y:.2f}<br>Context: ' + get_metric_context("NVP_Vol") + '<extra></extra>'
        ))
        fig.update_layout(
            barmode='group',
            title=f"{symbol} - NVP & NVP_Vol by Strike",
            xaxis_title="Strike",
            yaxis_title="Value",
            height=300,
            template=PLOTLY_TEMPLATE,
            margin=dict(t=60, b=40, l=20, r=20)
        )
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='nvp-charts', figure=fig)
    about = make_about_section(ABOUT_NVP, 'nvp-charts')
    return html.Div(about + [chart])

def _create_greek_flows_charts(und_data, symbol, config, timestamp) -> html.Div:
    greek_flows = getattr(und_data, 'greek_flows', None)
    time_hist = getattr(und_data, 'greek_flows_time', None)
    if greek_flows is None or time_hist is None or not isinstance(greek_flows, dict) or len(greek_flows) == 0:
        fig = create_empty_figure(title=f"{symbol} - Net Customer Greek Flows", height=300, reason="No Greek flows data available")
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='greek-flows-charts', figure=fig)
    else:
        fig = go.Figure()
        for greek, values in greek_flows.items():
            fig.add_trace(go.Scatter(
                x=time_hist,
                y=values,
                mode='lines',
                name=f'{greek} Flow',
                hovertemplate=f'Time: %{{x}}<br>{greek} Flow: %{{y:.2f}}<br>Context: ' + get_metric_context(f"{greek} Flow") + '<extra></extra>'
            ))
        fig.update_layout(
            title=f"{symbol} - Net Customer Greek Flows",
            xaxis_title="Time",
            yaxis_title="Greek Flow",
            height=300,
            template=PLOTLY_TEMPLATE,
            margin=dict(t=60, b=40, l=20, r=20)
        )
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='greek-flows-charts', figure=fig)
    about = make_about_section(ABOUT_GREEK_FLOWS, 'greek-flows-charts')
    return html.Div(about + [chart])

def _create_flow_ratios_charts(und_data, symbol, config, timestamp) -> html.Div:
    ratios = getattr(und_data, 'flow_ratios', None)
    time_hist = getattr(und_data, 'flow_ratios_time', None)
    if ratios is None or time_hist is None or not isinstance(ratios, dict) or len(ratios) == 0:
        fig = create_empty_figure(title=f"{symbol} - Specialized Flow Ratios", height=300, reason="No flow ratios data available")
        if timestamp:
            fig = add_bottom_right_timestamp_annotation(fig, timestamp)
        chart = dcc.Graph(id='flow-ratios-charts', figure=fig)
    else:
        fig = go.Figure()
        for ratio, values in ratios.items():
            fig.add_trace(go.Scatter(
                x=time_hist,
                y=values,
                mode='lines',
                name=f'{ratio}',
                hovertemplate=f'Time: %{{x}}<br>{ratio}: %{{y:.2f}}<br>Context: ' + get_metric_context(f"{ratio}") + '<extra></extra>'
            ))
        fig.update_layout(
            title=f"{symbol} - Specialized Flow Ratios",
            xaxis_title="Time",
            yaxis_title="Ratio Value",
            height=300,
            template=PLOTLY_TEMPLATE,
            margin=dict(t=60, b=40, l=20, r=20)
        )
    if timestamp:
        fig = add_bottom_right_timestamp_annotation(fig, timestamp)
    chart = dcc.Graph(id='flow-ratios-charts', figure=fig)
    about = make_about_section(ABOUT_FLOW_RATIOS, 'flow-ratios-charts')
    return html.Div(about + [chart])

# --- About blurbs for each metric ---
ABOUT_VAPI_FA = dbc.Alert([
    html.B("🚀 VAPI-FA (Volatility-Adjusted Premium Intensity with Flow Acceleration): "),
    "This is your INSTITUTIONAL FLOW DETECTOR – it identifies when 'smart money' is aggressively positioning. VAPI-FA combines premium paid, volatility context, and flow acceleration to spot high-conviction trades. ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "Z-Score > +2 = AGGRESSIVE INSTITUTIONAL BUYING (very bullish). ",
    "Z-Score < -2 = AGGRESSIVE INSTITUTIONAL SELLING (very bearish). ",
    "Z-Score between -0.5 and +0.5 = Normal/retail flow (neutral). ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "SURGE ABOVE +2: Enter longs/calls on pullbacks – institutions are accumulating. ",
    "PLUNGE BELOW -2: Enter shorts/puts on rallies – institutions are distributing. ",
    "DIVERGENCE: If price rises but VAPI-FA falls = distribution into strength (bearish). If price falls but VAPI-FA rises = accumulation into weakness (bullish). ",
    "BEST SIGNALS: When VAPI-FA, DWFD, and TW-LAF all align in the same direction. ",
    "Watch for VAPI-FA to lead price by 5–30 minutes – institutions position BEFORE moves!"
], color="info", dismissable=False, className="mb-2")

ABOUT_DWFD = dbc.Alert([
    html.B("⚡ DWFD (Delta-Weighted Flow Divergence): "),
    "DWFD measures the conviction and divergence between value and volume flows, revealing when big players are making conviction-backed moves versus when flow is more passive or conflicted. ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "High positive DWFD = conviction-backed bullish flow (institutions buying with size and intent). ",
    "High negative DWFD = conviction-backed bearish flow (institutions selling with size and intent). ",
    "DWFD near zero = low conviction, choppy or indecisive market. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "DWFD surges above +2: Look for strong upside follow-through, especially if VAPI-FA and TW-LAF agree. ",
    "DWFD plunges below -2: Look for strong downside follow-through. ",
    "Divergence between DWFD and price: If price rises but DWFD falls, rally is suspect (potential reversal). ",
    "DWFD is best used as a confirmation tool for VAPI-FA and TW-LAF signals."
], color="info", dismissable=False, className="mb-2")

ABOUT_TW_LAF = dbc.Alert([
    html.B("📈 TW-LAF (Time-Weighted Liquidity-Adjusted Flow): "),
    "TW-LAF captures the persistence and quality of directional flow by weighting recent, high-liquidity flows more heavily. It helps distinguish between fleeting spikes and sustainable trends. ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "Sustained positive TW-LAF = reliable bullish trend, especially if supported by VAPI-FA and DWFD. ",
    "Sustained negative TW-LAF = reliable bearish trend. ",
    "Choppy or rapidly flipping TW-LAF = unstable trend, higher risk of reversal. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "TW-LAF rising and holding above +1: Add to longs, trend is strengthening. ",
    "TW-LAF falling and holding below -1: Add to shorts, trend is strengthening. ",
    "TW-LAF flattening at extremes: Trend exhaustion, prepare for reversal. ",
    "TW-LAF crossing zero: Major trend change signal."
], color="info", dismissable=False, className="mb-2")

ABOUT_ROLLING_FLOWS = dbc.Alert([
    html.B("💰 Rolling Net Signed Flows: "),
    "REAL-TIME MONEY FLOW – shows actual dollars flowing in (calls) vs out (puts) across multiple timeframes. The most direct measure of whether buyers or sellers are in control RIGHT NOW. ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "POSITIVE VALUES = Net call buying (bullish pressure). ",
    "NEGATIVE VALUES = Net put buying (bearish pressure). ",
    "MULTIPLE TIMEFRAMES ALIGNED = Strong directional conviction. ",
    "DIVERGING TIMEFRAMES = Mixed signals, potential reversal. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "ALL TIMEFRAMES POSITIVE: Strong bullish – buy dips aggressively. ",
    "ALL TIMEFRAMES NEGATIVE: Strong bearish – sell rallies aggressively. ",
    "SHORT-TERM FLIP: 5-min flips but 15/30 hold = temporary pullback/bounce. ",
    "CASCADING FLIPS: 5-min flips, then 15-min, then 30-min = major trend change. ",
    "MAGNITUDE MATTERS: Larger bars = more conviction, more reliable signal. ",
    "Best for: Timing exact entries/exits and confirming other flow signals."
], color="info", dismissable=False, className="mb-2")

ABOUT_NVP = dbc.Alert([
    html.B("🎯 NVP & NVP_Vol by Strike: "),
    "NET VALUE POSITIONING – shows where the BIG MONEY is concentrated at each strike. NVP = Net premium paid (dollar commitment). NVP_Vol = Net contracts (position size). ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "LARGE POSITIVE NVP = Heavy call buying at that strike (bullish above, support below). ",
    "LARGE NEGATIVE NVP = Heavy put buying at that strike (bearish below, resistance above). ",
    "NVP_Vol CONFIRMS NVP = Both high means real positioning, not just expensive trades. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "SUPPORT LEVELS: Large positive NVP below current price = buyers will defend. ",
    "RESISTANCE LEVELS: Large negative NVP above current price = sellers will defend. ",
    "BREAKOUT TARGETS: Strikes with highest absolute NVP often become magnets. ",
    "HEDGING ZONES: Massive NVP at round numbers often indicates hedging (fade moves there). ",
    "EVOLVING LEVELS: Watch NVP shift throughout day – shows changing battlegrounds. ",
    "COMBO SIGNAL: When NVP aligns with technical levels = VERY strong support/resistance!"
], color="info", dismissable=False, className="mb-2")

ABOUT_GREEK_FLOWS = dbc.Alert([
    html.B("🔬 Net Customer Greek Flows: "),
    "POSITIONING X-RAY – reveals what risks traders are taking on (or hedging against). Shows aggregate customer exposure to direction (Delta), convexity (Gamma), volatility (Vega), and time (Theta). ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "DELTA FLOW: Positive = bullish positioning, Negative = bearish positioning. ",
    "GAMMA FLOW: Positive = expecting big moves, Negative = expecting range-bound. ",
    "VEGA FLOW: Positive = buying volatility (expecting expansion), Negative = selling vol. ",
    "THETA FLOW: Negative = paying for time (directional bets), Positive = collecting time. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "ALIGNED GREEKS: Delta + Gamma + Vega all positive = expecting bullish breakout. ",
    "CONFLICTING GREEKS: Mixed signals = likely hedging, not directional. ",
    "GAMMA SURGE: Spike in gamma buying = big move expected (straddle opportunity). ",
    "VEGA DUMP: Heavy vega selling = volatility crush expected (sell premium). ",
    "REGIME PREDICTOR: Sustained Greek flow changes often precede regime shifts. ",
    "Watch for unusual Greek combinations – they reveal sophisticated positioning!"
], color="info", dismissable=False, className="mb-2")

ABOUT_FLOW_RATIOS = dbc.Alert([
    html.B("📐 Specialized Flow Ratios: "),
    "ADVANCED FLOW ANALYTICS – sophisticated ratios that reveal hidden market dynamics. These ratios normalize and compare different flow types to identify regime changes and anomalies. ",
    html.Br(), html.Br(),
    html.B("KEY RATIOS: "),
    "VFLOWRATIO: Value flow / Volume flow – High = paying up (urgent), Low = patient. ",
    "P/C RATIOS: Put/Call ratios by value, volume, etc. – sentiment indicators. ",
    "SMART/DUMB: Institutional vs retail flow ratios – follow the smart money. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "RATIO EXTREMES: Any ratio >2 SD from mean = potential opportunity. ",
    "RATIO DIVERGENCE: When ratios disagree = market confusion, volatility ahead. ",
    "TREND CONFIRMATION: Rising ratios in trend direction = trend strengthening. ",
    "REVERSAL SIGNALS: Ratio reversals often lead price reversals by 15–60 minutes. ",
    "BEST USE: Combine with primary flow metrics for confirmation and timing. ",
    "These are your 'early warning system' for market regime changes!"
], color="info", dismissable=False, className="mb-2")

# --- Main Layout Function ---

def create_layout(bundle, config):
    """
    Creates the complete layout for the "Advanced Flow Analysis" mode.
    This is the single entry point called by the callback manager.
    Accepts a FinalAnalysisBundleV2_5 and ConfigManagerV2_5, but omits type hints to allow for flexible return types (dbc.Alert or html.Div).
    """
    if not bundle or not hasattr(bundle, 'processed_data_bundle') or not bundle.processed_data_bundle or not hasattr(bundle.processed_data_bundle, 'underlying_data_enriched') or not bundle.processed_data_bundle.underlying_data_enriched:
        logger.warning("Advanced Flow data or underlying_data_enriched is not available. Cannot render mode.")
        return dbc.Alert("Advanced Flow data is not available. Cannot render mode.", color="warning", className="m-4")

    und_data = bundle.processed_data_bundle.underlying_data_enriched
    symbol = getattr(bundle, 'target_symbol', 'N/A')
    bundle_timestamp = getattr(bundle, 'bundle_timestamp', None)

    # Generate all components for this mode
    vapi_gauge = _create_z_score_gauge(
        "VAPI-FA", getattr(und_data, 'vapi_fa_z_score_und', None), symbol,
        ids.ID_VAPI_GAUGE, config, bundle_timestamp
    )
    dwfd_gauge = _create_z_score_gauge(
        "DWFD", getattr(und_data, 'dwfd_z_score_und', None), symbol,
        ids.ID_DWFD_GAUGE, config, bundle_timestamp
    )
    tw_laf_gauge = _create_z_score_gauge(
        "TW-LAF", getattr(und_data, 'tw_laf_z_score_und', None), symbol,
        ids.ID_TW_LAF_GAUGE, config, bundle_timestamp
    )
    vapifa_hist_chart = _create_vapifa_historical_chart(und_data, symbol, config, bundle_timestamp)
    dwfd_hist_chart = _create_dwfd_historical_chart(und_data, symbol, config, bundle_timestamp)
    twlaf_hist_chart = _create_twlaf_historical_chart(und_data, symbol, config, bundle_timestamp)
    rolling_flows_chart = _create_rolling_flows_chart(und_data, symbol, config, bundle_timestamp)
    nvp_charts = _create_nvp_charts(und_data, symbol, config, bundle_timestamp)
    greek_flows_charts = _create_greek_flows_charts(und_data, symbol, config, bundle_timestamp)
    flow_ratios_charts = _create_flow_ratios_charts(und_data, symbol, config, bundle_timestamp)

    # Assemble the layout using the generated components
    return html.Div(
        className="advanced-flow-mode-container",
        children=[
            dbc.Container(
                fluid=True,
                children=[
                    dbc.Row(
                        [
                            dbc.Col(html.Div([vapi_gauge]), md=12, lg=4, className="mb-4 gauge-column"),
                            dbc.Col(html.Div([dwfd_gauge]), md=12, lg=4, className="mb-4 gauge-column"),
                            dbc.Col(html.Div([tw_laf_gauge]), md=12, lg=4, className="mb-4 gauge-column"),
                        ],
                        className="mt-4 justify-content-center"
                    ),
                    dbc.Row([
                        dbc.Col(html.Div([vapifa_hist_chart]), width=12)
                    ], className="mt-4"),
                    dbc.Row([
                        dbc.Col(html.Div([dwfd_hist_chart]), width=12)
                    ], className="mt-4"),
                    dbc.Row([
                        dbc.Col(html.Div([twlaf_hist_chart]), width=12)
                    ], className="mt-4"),
                    dbc.Row([
                        dbc.Col(html.Div([rolling_flows_chart]), width=12)
                    ], className="mt-4"),
                    dbc.Row([
                        dbc.Col(html.Div([nvp_charts]), width=12)
                    ], className="mt-4"),
                    dbc.Row([
                        dbc.Col(html.Div([greek_flows_charts]), width=12)
                    ], className="mt-4"),
                    dbc.Row([
                        dbc.Col(html.Div([flow_ratios_charts]), width=12)
                    ], className="mt-4"),
                ]
            )
        ]
    )

# --- Helper for About Section ---
def make_about_section(blurb, component_id):
    about_button = dbc.Button(
        "ℹ️ About",
        id={"type": "about-toggle", "index": component_id},
        color="link",
        size="sm",
        className="p-0 text-muted mb-2",
        style={'font-size': '0.75em'}
    )
    about_collapse = dbc.Collapse(
        html.Small(blurb, className="text-muted d-block mb-2", style={'font-size': '0.75em'}),
        id={"type": "about-collapse", "index": component_id},
        is_open=False
    )
    return [about_button, about_collapse]

# --- Helper for Metric Context Tooltips ---
def get_metric_context(metric_name, value=None):
    # Add more detailed context as needed
    if metric_name == "VAPI-FA":
        return "Strong positive = high-conviction net buying; strong negative = net selling."
    if metric_name == "DWFD":
        return "High positive = conviction-backed bullish flow; high negative = bearish."
    if metric_name == "TW-LAF":
        return "Sustained positive = reliable bullish trend; negative = bearish."
    if metric_name == "Rolling Flows":
        return "Sustained positive = persistent buying; negative = selling."
    if metric_name == "NVP":
        return "Large positive = net customer buying (support); negative = selling (resistance)."
    if metric_name == "Greek Flows":
        return "Tracks daily aggregate customer positioning in Greeks."
    if metric_name == "Flow Ratios":
        return "Advanced ratios reveal nuanced shifts in flow composition."
    return "See About for details."