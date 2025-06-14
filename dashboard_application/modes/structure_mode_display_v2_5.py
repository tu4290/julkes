# dashboard_application/modes/structure_mode_display_v2_5.py
# EOTS v2.5 - S-GRADE, AUTHORITATIVE STRUCTURE MODE DISPLAY

import logging
from typing import Dict, Optional
import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
import pdb
from datetime import datetime

from dashboard_application import ids
from dashboard_application.utils_dashboard_v2_5 import create_empty_figure, add_timestamp_annotation, add_price_line, PLOTLY_TEMPLATE, add_bottom_right_timestamp_annotation
from data_models.eots_schemas_v2_5 import FinalAnalysisBundleV2_5
from utils.config_manager_v2_5 import ConfigManagerV2_5

logger = logging.getLogger(__name__)

# --- Helper Function for Chart Generation ---

def _generate_a_mspi_profile_chart(bundle: FinalAnalysisBundleV2_5, config: ConfigManagerV2_5) -> dcc.Graph:
    """
    Generates the primary visualization for Structure Mode: the Adaptive MSPI profile.
    This chart shows the synthesized structural pressure across different strikes.
    """
    chart_name = "Adaptive MSPI Profile"
    fig_height = config.get_setting("visualization_settings.dashboard.structure_mode_settings.mspi_chart_height", default=600)
    
    try:
        strike_data = bundle.processed_data_bundle.strike_level_data_with_metrics
        if not strike_data:
            return dcc.Graph(figure=create_empty_figure(chart_name, fig_height, "Strike level data not available."))

        df_strike = pd.DataFrame([s.model_dump() for s in strike_data])
        
        # A-MSPI is a summary score calculated at the underlying level, but its components are at strike level.
        # For this visualization, we will use a key component like 'a_dag_strike' as the primary bar chart.
        # A true A-MSPI chart might be a single gauge or an overlay of its components.
        metric_to_plot = 'a_dag_strike' # Using A-DAG as the main visual for structural pressure
        
        if df_strike.empty or metric_to_plot not in df_strike.columns:
            return dcc.Graph(figure=create_empty_figure(chart_name, fig_height, f"'{metric_to_plot}' data not found."))

        df_plot = df_strike.dropna(subset=['strike', metric_to_plot]).sort_values('strike')
        
        colors = ['#d62728' if x < 0 else '#2ca02c' for x in df_plot[metric_to_plot]]

        fig = go.Figure(data=[go.Bar(
            x=df_plot['strike'],
            y=df_plot[metric_to_plot],
            name='A-DAG',
            marker_color=colors,
            hovertemplate='Strike: %{x}<br>A-DAG: %{y:,.2f}<extra></extra>'
        )])

        current_price = bundle.processed_data_bundle.underlying_data_enriched.price
        
        fig.update_layout(
            title_text=f"<b>{bundle.target_symbol}</b> - {chart_name} (using A-DAG)",
            height=fig_height,
            template=PLOTLY_TEMPLATE,
            xaxis_title="Strike Price",
            yaxis_title="Adaptive Delta-Adjusted Gamma (A-DAG)",
            showlegend=False,
            barmode='relative',
            xaxis={'type': 'category'} # Treat strikes as categories for clear separation
        )
        add_price_line(fig, current_price, orientation='vertical', line_width=2, line_color='white')
        add_bottom_right_timestamp_annotation(fig, bundle.bundle_timestamp)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Strike-level DataFrame shape: {df_strike.shape}")
            logger.debug(f"Strike-level DataFrame columns: {df_strike.columns}")
            logger.debug(f"Strike-level DataFrame head:\n{df_strike.head()}")
            logger.debug(f"Strike values: {df_strike['strike'].tolist()}")

    except Exception as e:
        logger.error(f"Error creating {chart_name}: {e}", exc_info=True)
        fig = create_empty_figure(chart_name, fig_height, f"Error: {e}")

    return dcc.Graph(figure=fig)

def _about_section(text, component_id):
    return [
        dbc.Button(
            "ℹ️ About", id={"type": "about-toggle", "index": component_id}, color="link", size="sm", className="p-0 text-muted mb-2", style={'font-size': '0.75em'}
        ),
        dbc.Collapse(
            dbc.Alert(text, color="info", className="mb-2", style={'font-size': '0.95em'}),
            id={"type": "about-collapse", "index": component_id},
            is_open=False
        )
    ]

# --- Chart Stubs ---
def _generate_amspi_heatmap(bundle, config):
    chart_name = "A-MSPI Heatmap (SGDHP Score)"
    fig_height = config.get_setting("visualization_settings.dashboard.structure_mode_settings.sgdhp_chart_height", default=400)
    try:
        strike_data = bundle.processed_data_bundle.strike_level_data_with_metrics
        if not strike_data:
            logger.warning("[A-MSPI Heatmap] No strike data available.")
            return html.Div(_about_section(
                "🎯 A-MSPI Heatmap (Adaptive Market Structure Pressure Index): This is your PRIMARY structural view showing where dealers are positioned to provide support or resistance. "
                "GREEN bars = SUPPORT zones where dealers will likely buy to hedge (price floors). "
                "RED bars = RESISTANCE zones where dealers will likely sell to hedge (price ceilings). "
                "INTENSITY shows strength - darker colors mean stronger levels. "
                "CURRENT PRICE LINE shows where we are relative to these zones. "
                "💡 TRADING INSIGHT: Look for price to 'bounce' off strong green support or 'reject' at red resistance. "
                "When price breaks through a strong level with volume, expect acceleration in that direction as dealers are forced to re-hedge. "
                "Multiple green levels below = bullish structure. Multiple red levels above = bearish structure. "
                "This chart updates in real-time as options flow changes dealer positioning!", 
                "amspi-heatmap"
            ) + [
                dbc.Alert("No strike level data available.", color="warning", className="mb-2"),
                dcc.Graph(figure=create_empty_figure(chart_name, fig_height, "Strike level data not available."))
            ])
        df_strike = pd.DataFrame([s.model_dump() for s in strike_data])
        metric_to_plot = 'sgdhp_score_strike'
        if df_strike.empty or metric_to_plot not in df_strike.columns:
            logger.warning(f"[A-MSPI Heatmap] '{metric_to_plot}' data not found in DataFrame columns: {df_strike.columns}")
            return html.Div(_about_section(
                "🎯 A-MSPI Heatmap (Adaptive Market Structure Pressure Index): This is your PRIMARY structural view showing where dealers are positioned to provide support or resistance. "
                "GREEN bars = SUPPORT zones where dealers will likely buy to hedge (price floors). "
                "RED bars = RESISTANCE zones where dealers will likely sell to hedge (price ceilings). "
                "INTENSITY shows strength - darker colors mean stronger levels. "
                "CURRENT PRICE LINE shows where we are relative to these zones. "
                "💡 TRADING INSIGHT: Look for price to 'bounce' off strong green support or 'reject' at red resistance. "
                "When price breaks through a strong level with volume, expect acceleration in that direction as dealers are forced to re-hedge. "
                "Multiple green levels below = bullish structure. Multiple red levels above = bearish structure. "
                "This chart updates in real-time as options flow changes dealer positioning!", 
                "amspi-heatmap"
            ) + [
                dbc.Alert(f"'{metric_to_plot}' data not found.", color="warning", className="mb-2"),
                dcc.Graph(figure=create_empty_figure(chart_name, fig_height, f"'{metric_to_plot}' data not found."))
            ])
        df_plot = df_strike.dropna(subset=['strike', metric_to_plot]).sort_values('strike')
        colors = df_plot[metric_to_plot].apply(lambda x: '#2ca02c' if x > 0 else '#d62728')
        fig = go.Figure(data=[go.Bar(
            x=df_plot['strike'],
            y=df_plot[metric_to_plot],
            marker_color=colors,
            name='SGDHP',
            hovertemplate='Strike: %{x}<br>SGDHP Score: %{y:,.2f}<extra></extra>'
        )])
        current_price = bundle.processed_data_bundle.underlying_data_enriched.price
        fig.update_layout(
            title_text=f"<b>{bundle.target_symbol}</b> - {chart_name}",
            height=fig_height,
            template=PLOTLY_TEMPLATE,
            xaxis_title="Strike Price",
            yaxis_title="SGDHP Score (Support/Resistance Intensity)",
            showlegend=False,
            xaxis={'type': 'linear', 'automargin': True},
            margin=dict(l=60, r=30, t=60, b=60)
        )
        add_price_line(fig, current_price, orientation='vertical', width=2, color='white')
        add_bottom_right_timestamp_annotation(fig, bundle.bundle_timestamp)
        return html.Div(_about_section(
            "🎯 A-MSPI Heatmap (Adaptive Market Structure Pressure Index): This is your PRIMARY structural view showing where dealers are positioned to provide support or resistance. "
            "GREEN bars = SUPPORT zones where dealers will likely buy to hedge (price floors). "
            "RED bars = RESISTANCE zones where dealers will likely sell to hedge (price ceilings). "
            "INTENSITY shows strength - darker colors mean stronger levels. "
            "CURRENT PRICE LINE shows where we are relative to these zones. "
            "💡 TRADING INSIGHT: Look for price to 'bounce' off strong green support or 'reject' at red resistance. "
            "When price breaks through a strong level with volume, expect acceleration in that direction as dealers are forced to re-hedge. "
            "Multiple green levels below = bullish structure. Multiple red levels above = bearish structure. "
            "This chart updates in real-time as options flow changes dealer positioning!", 
            "amspi-heatmap"
        ) + [dcc.Graph(figure=fig)])
    except Exception as e:
        logger.error(f"Error creating {chart_name}: {e}", exc_info=True)
        return html.Div(_about_section(
            "🎯 A-MSPI Heatmap (Adaptive Market Structure Pressure Index): This is your PRIMARY structural view showing where dealers are positioned to provide support or resistance. "
            "GREEN bars = SUPPORT zones where dealers will likely buy to hedge (price floors). "
            "RED bars = RESISTANCE zones where dealers will likely sell to hedge (price ceilings). "
            "INTENSITY shows strength - darker colors mean stronger levels. "
            "CURRENT PRICE LINE shows where we are relative to these zones. "
            "💡 TRADING INSIGHT: Look for price to 'bounce' off strong green support or 'reject' at red resistance. "
            "When price breaks through a strong level with volume, expect acceleration in that direction as dealers are forced to re-hedge. "
            "Multiple green levels below = bullish structure. Multiple red levels above = bearish structure. "
            "This chart updates in real-time as options flow changes dealer positioning!", 
            "amspi-heatmap"
        ) + [
            dbc.Alert(f"Error: {e}", color="danger", className="mb-2"),
            dcc.Graph(figure=create_empty_figure(chart_name, fig_height, f"Error: {e}"))
        ])

def _generate_esdag_charts(bundle, config):
    chart_name = "E-SDAG Methodology Components"
    fig_height = config.get_setting("visualization_settings.dashboard.structure_mode_settings.esdag_chart_height", default=350)
    try:
        strike_data = bundle.processed_data_bundle.strike_level_data_with_metrics
        if not strike_data:
            logger.warning("[E-SDAG] No strike data available.")
            return html.Div(_about_section(
                "📊 E-SDAG Components (Enhanced Structural Delta-Adjusted Gamma): These 4 lines show DIFFERENT METHODS of calculating dealer hedging pressure, each capturing unique market dynamics. "
                "MULTIPLICATIVE (Blue) = Traditional gamma * delta interaction - shows basic hedging needs. "
                "DIRECTIONAL (Orange) = Factors in whether dealers are long/short gamma - shows hedging direction. "
                "WEIGHTED (Green) = Adjusts for volume and open interest - shows 'real' vs theoretical pressure. "
                "VOL FLOW (Red) = Incorporates volatility and flow - shows dynamic hedging adjustments. "
                "💡 TRADING INSIGHT: When ALL 4 lines AGREE (all positive or all negative) at a strike = VERY HIGH CONVICTION level. "
                "DIVERGENCE between lines = uncertainty, potential for volatility. "
                "Watch for lines CROSSING zero = hedging flip points where dealer behavior changes. "
                "The line with the LARGEST magnitude often leads price action. "
                "Use the legend to toggle lines and focus on specific methodologies!",
                "esdag-charts"
            ) + [
                dbc.Alert("No strike level data available.", color="warning", className="mb-2"),
                dcc.Graph(figure=create_empty_figure(chart_name, fig_height, "Strike level data not available."))
            ])
        df_strike = pd.DataFrame([s.model_dump() for s in strike_data])
        components = [
            ("Multiplicative", 'e_sdag_mult_strike', '#1f77b4'),
            ("Directional", 'e_sdag_dir_strike', '#ff7f0e'),
            ("Weighted", 'e_sdag_w_strike', '#2ca02c'),
            ("Vol Flow", 'e_sdag_vf_strike', '#d62728')
        ]
        fig = go.Figure()
        for label, col, color in components:
            if col in df_strike.columns:
                fig.add_trace(go.Scatter(
                    x=df_strike['strike'],
                    y=df_strike[col],
                    mode='lines+markers',
                    name=label,
                    line=dict(color=color),
                    hovertemplate=f'Strike: %{{x}}<br>{label}: %{{y:,.2f}}<extra></extra>'
                ))
        current_price = bundle.processed_data_bundle.underlying_data_enriched.price
        fig.update_layout(
            title_text=f"<b>{bundle.target_symbol}</b> - {chart_name}",
            height=fig_height,
            template=PLOTLY_TEMPLATE,
            xaxis_title="Strike Price",
            yaxis_title="E-SDAG Component Value",
            showlegend=True,
            xaxis={'type': 'linear', 'automargin': True},
            margin=dict(l=60, r=30, t=60, b=60)
        )
        add_price_line(fig, current_price, orientation='vertical', width=2, color='white')
        add_bottom_right_timestamp_annotation(fig, bundle.bundle_timestamp)
        return html.Div(_about_section(
            "📊 E-SDAG Components (Enhanced Structural Delta-Adjusted Gamma): These 4 lines show DIFFERENT METHODS of calculating dealer hedging pressure, each capturing unique market dynamics. "
            "MULTIPLICATIVE (Blue) = Traditional gamma * delta interaction - shows basic hedging needs. "
            "DIRECTIONAL (Orange) = Factors in whether dealers are long/short gamma - shows hedging direction. "
            "WEIGHTED (Green) = Adjusts for volume and open interest - shows 'real' vs theoretical pressure. "
            "VOL FLOW (Red) = Incorporates volatility and flow - shows dynamic hedging adjustments. "
            "💡 TRADING INSIGHT: When ALL 4 lines AGREE (all positive or all negative) at a strike = VERY HIGH CONVICTION level. "
            "DIVERGENCE between lines = uncertainty, potential for volatility. "
            "Watch for lines CROSSING zero = hedging flip points where dealer behavior changes. "
            "The line with the LARGEST magnitude often leads price action. "
            "Use the legend to toggle lines and focus on specific methodologies!",
            "esdag-charts"
        ) + [dcc.Graph(figure=fig)])
    except Exception as e:
        logger.error(f"Error creating {chart_name}: {e}", exc_info=True)
        return html.Div(_about_section(
            "📊 E-SDAG Components (Enhanced Structural Delta-Adjusted Gamma): These 4 lines show DIFFERENT METHODS of calculating dealer hedging pressure, each capturing unique market dynamics. "
            "MULTIPLICATIVE (Blue) = Traditional gamma * delta interaction - shows basic hedging needs. "
            "DIRECTIONAL (Orange) = Factors in whether dealers are long/short gamma - shows hedging direction. "
            "WEIGHTED (Green) = Adjusts for volume and open interest - shows 'real' vs theoretical pressure. "
            "VOL FLOW (Red) = Incorporates volatility and flow - shows dynamic hedging adjustments. "
            "💡 TRADING INSIGHT: When ALL 4 lines AGREE (all positive or all negative) at a strike = VERY HIGH CONVICTION level. "
            "DIVERGENCE between lines = uncertainty, potential for volatility. "
            "Watch for lines CROSSING zero = hedging flip points where dealer behavior changes. "
            "The line with the LARGEST magnitude often leads price action. "
            "Use the legend to toggle lines and focus on specific methodologies!",
            "esdag-charts"
        ) + [
            dbc.Alert(f"Error: {e}", color="danger", className="mb-2"),
            dcc.Graph(figure=create_empty_figure(chart_name, fig_height, f"Error: {e}"))
        ])

def _generate_adag_strike_chart(bundle, config):
    chart_name = "A-DAG by Strike"
    fig_height = config.get_setting("visualization_settings.dashboard.structure_mode_settings.adag_chart_height", default=350)
    try:
        strike_data = bundle.processed_data_bundle.strike_level_data_with_metrics
        if not strike_data:
            logger.warning("[A-DAG] No strike data available.")
            return html.Div(_about_section(
                "📈 A-DAG by Strike (Adaptive Delta-Adjusted Gamma): This shows the NET DIRECTIONAL PRESSURE at each strike after adapting to current market conditions. "
                "GREEN bars = NET BUYING pressure expected (support). "
                "RED bars = NET SELLING pressure expected (resistance). "
                "BAR HEIGHT = Magnitude of expected dealer hedging activity. "
                "This is MORE ADVANCED than regular gamma exposure because it: "
                "1) Adapts to market regime (trending vs ranging), "
                "2) Incorporates recent flow alignment, "
                "3) Adjusts for time decay effects. "
                "💡 TRADING INSIGHT: The LARGEST bars (positive or negative) are your KEY LEVELS for the day. "
                "Price tends to 'MAGNETIZE' toward large positive A-DAG strikes (dealer buying). "
                "Price tends to 'REJECT' from large negative A-DAG strikes (dealer selling). "
                "When A-DAG flips from positive to negative (or vice versa) = MAJOR INFLECTION POINT. "
                "In trending markets, trade WITH the A-DAG direction. In ranging markets, FADE extreme A-DAG levels.",
                "adag-strike-chart"
            ) + [
                dbc.Alert("No strike level data available.", color="warning", className="mb-2"),
                dcc.Graph(figure=create_empty_figure(chart_name, fig_height, "Strike level data not available."))
            ])
        df_strike = pd.DataFrame([s.model_dump() for s in strike_data])
        metric_to_plot = 'a_dag_strike'
        if df_strike.empty or metric_to_plot not in df_strike.columns:
            logger.warning(f"[A-DAG] '{metric_to_plot}' data not found in DataFrame columns: {df_strike.columns}")
            return html.Div(_about_section(
                "📈 A-DAG by Strike (Adaptive Delta-Adjusted Gamma): This shows the NET DIRECTIONAL PRESSURE at each strike after adapting to current market conditions. "
                "GREEN bars = NET BUYING pressure expected (support). "
                "RED bars = NET SELLING pressure expected (resistance). "
                "BAR HEIGHT = Magnitude of expected dealer hedging activity. "
                "This is MORE ADVANCED than regular gamma exposure because it: "
                "1) Adapts to market regime (trending vs ranging), "
                "2) Incorporates recent flow alignment, "
                "3) Adjusts for time decay effects. "
                "💡 TRADING INSIGHT: The LARGEST bars (positive or negative) are your KEY LEVELS for the day. "
                "Price tends to 'MAGNETIZE' toward large positive A-DAG strikes (dealer buying). "
                "Price tends to 'REJECT' from large negative A-DAG strikes (dealer selling). "
                "When A-DAG flips from positive to negative (or vice versa) = MAJOR INFLECTION POINT. "
                "In trending markets, trade WITH the A-DAG direction. In ranging markets, FADE extreme A-DAG levels.",
                "adag-strike-chart"
            ) + [
                dbc.Alert(f"'{metric_to_plot}' data not found.", color="warning", className="mb-2"),
                dcc.Graph(figure=create_empty_figure(chart_name, fig_height, f"'{metric_to_plot}' data not found."))
            ])
        df_plot = df_strike.dropna(subset=['strike', metric_to_plot]).sort_values('strike')
        # logger.info(f"Processed {len(df_plot)} strikes for {bundle.target_symbol}")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Processed {len(df_plot)} strikes for {bundle.target_symbol}")
        if df_plot.empty or df_plot[metric_to_plot].isnull().all():
            logger.warning("[A-DAG] All A-DAG values are missing or None.")
            return html.Div(_about_section(
                "📈 A-DAG by Strike (Adaptive Delta-Adjusted Gamma): This shows the NET DIRECTIONAL PRESSURE at each strike after adapting to current market conditions. "
                "GREEN bars = NET BUYING pressure expected (support). "
                "RED bars = NET SELLING pressure expected (resistance). "
                "BAR HEIGHT = Magnitude of expected dealer hedging activity. "
                "This is MORE ADVANCED than regular gamma exposure because it: "
                "1) Adapts to market regime (trending vs ranging), "
                "2) Incorporates recent flow alignment, "
                "3) Adjusts for time decay effects. "
                "💡 TRADING INSIGHT: The LARGEST bars (positive or negative) are your KEY LEVELS for the day. "
                "Price tends to 'MAGNETIZE' toward large positive A-DAG strikes (dealer buying). "
                "Price tends to 'REJECT' from large negative A-DAG strikes (dealer selling). "
                "When A-DAG flips from positive to negative (or vice versa) = MAJOR INFLECTION POINT. "
                "In trending markets, trade WITH the A-DAG direction. In ranging markets, FADE extreme A-DAG levels.",
                "adag-strike-chart"
            ) + [
                dbc.Alert("All A-DAG values are missing or None.", color="warning", className="mb-2"),
                dcc.Graph(figure=create_empty_figure(chart_name, fig_height, "All A-DAG values are missing or None."))
            ])
        colors = ['#d62728' if x < 0 else '#2ca02c' for x in df_plot[metric_to_plot]]
        fig = go.Figure(data=[go.Bar(
            x=df_plot['strike'],
            y=df_plot[metric_to_plot],
            name='A-DAG',
            marker_color=colors,
            hovertemplate='Strike: %{x}<br>A-DAG: %{y:,.2f}<extra></extra>'
        )])
        current_price = bundle.processed_data_bundle.underlying_data_enriched.price
        fig.update_layout(
            title_text=f"<b>{bundle.target_symbol}</b> - {chart_name}",
            height=fig_height,
            template=PLOTLY_TEMPLATE,
            xaxis_title="Strike Price",
            yaxis_title="A-DAG Value",
            showlegend=False,
            xaxis={'type': 'linear', 'automargin': True},
            margin=dict(l=60, r=30, t=60, b=60)
        )
        add_price_line(fig, current_price, orientation='vertical', width=2, color='white')
        add_bottom_right_timestamp_annotation(fig, bundle.bundle_timestamp)
        return html.Div(_about_section(
            "📈 A-DAG by Strike (Adaptive Delta-Adjusted Gamma): This shows the NET DIRECTIONAL PRESSURE at each strike after adapting to current market conditions. "
            "GREEN bars = NET BUYING pressure expected (support). "
            "RED bars = NET SELLING pressure expected (resistance). "
            "BAR HEIGHT = Magnitude of expected dealer hedging activity. "
            "This is MORE ADVANCED than regular gamma exposure because it: "
            "1) Adapts to market regime (trending vs ranging), "
            "2) Incorporates recent flow alignment, "
            "3) Adjusts for time decay effects. "
            "💡 TRADING INSIGHT: The LARGEST bars (positive or negative) are your KEY LEVELS for the day. "
            "Price tends to 'MAGNETIZE' toward large positive A-DAG strikes (dealer buying). "
            "Price tends to 'REJECT' from large negative A-DAG strikes (dealer selling). "
            "When A-DAG flips from positive to negative (or vice versa) = MAJOR INFLECTION POINT. "
            "In trending markets, trade WITH the A-DAG direction. In ranging markets, FADE extreme A-DAG levels.",
            "adag-strike-chart"
        ) + [dcc.Graph(figure=fig)])
    except Exception as e:
        logger.error(f"Error creating {chart_name}: {e}", exc_info=True)
        return html.Div(_about_section(
            "📈 A-DAG by Strike (Adaptive Delta-Adjusted Gamma): This shows the NET DIRECTIONAL PRESSURE at each strike after adapting to current market conditions. "
            "GREEN bars = NET BUYING pressure expected (support). "
            "RED bars = NET SELLING pressure expected (resistance). "
            "BAR HEIGHT = Magnitude of expected dealer hedging activity. "
            "This is MORE ADVANCED than regular gamma exposure because it: "
            "1) Adapts to market regime (trending vs ranging), "
            "2) Incorporates recent flow alignment, "
            "3) Adjusts for time decay effects. "
            "💡 TRADING INSIGHT: The LARGEST bars (positive or negative) are your KEY LEVELS for the day. "
            "Price tends to 'MAGNETIZE' toward large positive A-DAG strikes (dealer buying). "
            "Price tends to 'REJECT' from large negative A-DAG strikes (dealer selling). "
            "When A-DAG flips from positive to negative (or vice versa) = MAJOR INFLECTION POINT. "
            "In trending markets, trade WITH the A-DAG direction. In ranging markets, FADE extreme A-DAG levels.",
            "adag-strike-chart"
        ) + [
            dbc.Alert(f"Error: {e}", color="danger", className="mb-2"),
            dcc.Graph(figure=create_empty_figure(chart_name, fig_height, f"Error: {e}"))
        ])

def _generate_asai_assi_charts(bundle, config):
    chart_name = "A-SAI & A-SSI (Aggregate Structural Indexes)"
    fig_height = config.get_setting("visualization_settings.dashboard.structure_mode_settings.asai_assi_chart_height", default=350)
    try:
        und_data = bundle.processed_data_bundle.underlying_data_enriched
        # [A-SAI/A-SSI] underlying_data_enriched: ...
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"[A-SAI/A-SSI] underlying_data_enriched: {und_data}")
        # logger.info(f"[A-SAI/A-SSI] underlying_data_enriched received for {getattr(und_data, 'symbol', 'N/A')}")
        asai = getattr(und_data, 'a_sai_und_avg', None)
        assi = getattr(und_data, 'a_ssi_und_avg', None)
        # logger.info(f"[A-SAI/A-SSI] a_sai_und_avg: {asai}, a_ssi_und_avg: {assi}")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"[A-SAI/A-SSI] a_sai_und_avg: {asai}, a_ssi_und_avg: {assi}")
        fig = go.Figure()
        missing = []
        if asai is not None:
            fig.add_trace(go.Indicator(
                mode="gauge+number",
                value=asai,
                title={"text": "A-SAI (Support Aggregate Index)"},
                gauge={"axis": {"range": [-1, 1]}, "bar": {"color": "#2ca02c"}},
                domain={"row": 0, "column": 0}
            ))
        else:
            missing.append("A-SAI (Support Aggregate Index)")
        if assi is not None:
            fig.add_trace(go.Indicator(
                mode="gauge+number",
                value=assi,
                title={"text": "A-SSI (Resistance Aggregate Index)"},
                gauge={"axis": {"range": [-1, 1]}, "bar": {"color": "#d62728"}},
                domain={"row": 0, "column": 1}
            ))
        else:
            missing.append("A-SSI (Resistance Aggregate Index)")
        fig.update_layout(
            title_text=f"<b>{bundle.target_symbol}</b> - {chart_name}",
            height=fig_height,
            template=PLOTLY_TEMPLATE,
            grid={"rows": 1, "columns": 2, "pattern": "independent"},
            margin=dict(l=60, r=30, t=60, b=60)
        )
        add_bottom_right_timestamp_annotation(fig, bundle.bundle_timestamp)
        warning = dbc.Alert(f"Missing: {', '.join(missing)}" if missing else None, color="warning", className="mb-2") if missing else None
        return html.Div(_about_section(
            "🎚️ A-SAI & A-SSI Gauges (Adaptive Support/Resistance Aggregate Indexes): These gauges show the OVERALL MARKET STRUCTURE at a glance. "
            "A-SAI (GREEN gauge) = Aggregate SUPPORT strength index (-1 to +1). "
            "A-SSI (RED gauge) = Aggregate RESISTANCE strength index (-1 to +1). "
            "POSITIVE A-SAI = Strong support structure below current price (bullish). "
            "NEGATIVE A-SSI = Strong resistance structure above current price (bearish). "
            "BOTH NEAR ZERO = Balanced/neutral structure. "
            "💡 TRADING INSIGHT: These are your 'MARKET STRUCTURE COMPASS'. "
            "A-SAI > 0.5 = VERY BULLISH structure, dips are buying opportunities. "
            "A-SSI < -0.5 = VERY BEARISH structure, rallies are selling opportunities. "
            "When BOTH are extreme (SAI > 0.7, SSI < -0.7) = RANGE-BOUND market, fade extremes. "
            "When they FLIP (SAI goes negative or SSI goes positive) = MAJOR STRUCTURE CHANGE, potential trend reversal! "
            "These update throughout the day as options flow shifts the structural balance.",
            "asai-assi-charts"
        ) + ([warning] if warning else []) + [dcc.Graph(figure=fig)])
    except Exception as e:
        logger.error(f"Error creating {chart_name}: {e}", exc_info=True)
        return html.Div(_about_section(
            "🎚️ A-SAI & A-SSI Gauges (Adaptive Support/Resistance Aggregate Indexes): These gauges show the OVERALL MARKET STRUCTURE at a glance. "
            "A-SAI (GREEN gauge) = Aggregate SUPPORT strength index (-1 to +1). "
            "A-SSI (RED gauge) = Aggregate RESISTANCE strength index (-1 to +1). "
            "POSITIVE A-SAI = Strong support structure below current price (bullish). "
            "NEGATIVE A-SSI = Strong resistance structure above current price (bearish). "
            "BOTH NEAR ZERO = Balanced/neutral structure. "
            "💡 TRADING INSIGHT: These are your 'MARKET STRUCTURE COMPASS'. "
            "A-SAI > 0.5 = VERY BULLISH structure, dips are buying opportunities. "
            "A-SSI < -0.5 = VERY BEARISH structure, rallies are selling opportunities. "
            "When BOTH are extreme (SAI > 0.7, SSI < -0.7) = RANGE-BOUND market, fade extremes. "
            "When they FLIP (SAI goes negative or SSI goes positive) = MAJOR STRUCTURE CHANGE, potential trend reversal! "
            "These update throughout the day as options flow shifts the structural balance.",
            "asai-assi-charts"
        ) + [
            dbc.Alert(f"Error: {e}", color="danger", className="mb-2"),
            dcc.Graph(figure=create_empty_figure(chart_name, fig_height, f"Error: {e}"))
        ])

def _generate_key_level_table(bundle, config):
    chart_name = "Key Level Identifier Table"
    try:
        key_levels = bundle.key_levels_data_v2_5
        # [Key Levels Table] key_levels_data_v2_5: ...
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"[Key Levels Table] key_levels_data_v2_5: {key_levels}")
            logger.debug(f"[Key Levels Table] key_levels timestamp: {getattr(key_levels, 'timestamp', 'N/A')}")
            logger.debug(f"[Key Levels Table] supports count: {len(getattr(key_levels, 'supports', []))}")
            logger.debug(f"[Key Levels Table] resistances count: {len(getattr(key_levels, 'resistances', []))}")
            logger.debug(f"[Key Levels Table] pin_zones count: {len(getattr(key_levels, 'pin_zones', []))}")
            logger.debug(f"[Key Levels Table] vol_triggers count: {len(getattr(key_levels, 'vol_triggers', []))}")
            logger.debug(f"[Key Levels Table] major_walls count: {len(getattr(key_levels, 'major_walls', []))}")
        
        # Check if key levels data is stale
        key_levels_timestamp = getattr(key_levels, 'timestamp', None)
        if key_levels_timestamp:
            time_diff = datetime.now() - key_levels_timestamp
            if time_diff.total_seconds() > 300:  # 5 minutes
                logger.warning(f"[Key Levels Table] Data appears stale - timestamp: {key_levels_timestamp}, age: {time_diff}")
        
        # logger.info(f"[Key Levels Table] key_levels_data_v2_5 received for {getattr(bundle, 'target_symbol', 'N/A')}")
        rows = []
        for category, levels in [
            ("Support", getattr(key_levels, 'supports', [])),
            ("Resistance", getattr(key_levels, 'resistances', [])),
            ("Pin Zone", getattr(key_levels, 'pin_zones', [])),
            ("Vol Trigger", getattr(key_levels, 'vol_triggers', [])),
            ("Major Wall", getattr(key_levels, 'major_walls', [])),
        ]:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[Key Levels Table] Processing {category}: {len(levels)} levels")
            for i, lvl in enumerate(levels):
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"[Key Levels Table] {category}[{i}]: price={getattr(lvl, 'level_price', 'N/A')}, conviction={getattr(lvl, 'conviction_score', 'N/A')}")
                rows.append({
                    "Type": category,
                    "Price": getattr(lvl, 'level_price', '-'),
                    "Conviction": getattr(lvl, 'conviction_score', '-'),
                    "Metrics": ", ".join(getattr(lvl, 'contributing_metrics', [])) if getattr(lvl, 'contributing_metrics', None) else "-"
                })
        
        if not rows:
            logger.warning("[Key Levels Table] No key levels found in any category.")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[Key Levels Table] Raw key_levels object: {key_levels}")
                logger.debug(f"[Key Levels Table] key_levels type: {type(key_levels)}")
                logger.debug(f"[Key Levels Table] key_levels attributes: {dir(key_levels) if key_levels else 'None'}")
            return html.Div(_about_section(
                "🎯 Key Level Identifier Table: This table shows ALL CRITICAL PRICE LEVELS identified by the system's advanced algorithms. "
                "TYPES: Support (price floor), Resistance (price ceiling), Pin Zone (magnetic price), Vol Trigger (volatility expansion), Major Wall (massive OI). "
                "CONVICTION SCORE (0-1): Higher = stronger level. Above 0.7 = VERY HIGH conviction. "
                "METRICS: Shows which calculations identified this level (technical, options-based, flow-based). "
                "💡 TRADING INSIGHT: These are your BATTLE LINES for the day. "
                "SUPPORT levels = Where to buy/cover shorts, place stops below. "
                "RESISTANCE levels = Where to sell/short, place stops above. "
                "PIN ZONES = Price will gravitate here, especially near expiration. Great for iron condors/butterflies. "
                "VOL TRIGGERS = Breakout/breakdown points. Break = volatility expansion. Use for straddle/strangle entries. "
                "MAJOR WALLS = Extreme levels that rarely break. Use for credit spread strikes. "
                "Sort by CONVICTION to focus on the strongest levels. Filter by TYPE for specific strategies. "
                "These levels are DYNAMIC and update as market structure evolves!",
                "key-level-table"
            ) + [
                dbc.Alert("No key levels identified.", color="warning", className="mb-2"),
                html.Div("No key levels identified.", className="text-muted mb-2")
            ])
        
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"[Key Levels Table] Generated {len(rows)} table rows")
        
        df = pd.DataFrame(rows)
        table = dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in df.columns],
            data=df.to_dict('records'),
            style_cell={'textAlign': 'left', 'padding': '5px', 'minWidth': '80px', 'width': 'auto', 'maxWidth': '200px'},
            style_header={'backgroundColor': 'rgb(30, 30, 30)', 'fontWeight': 'bold', 'color': 'white'},
            style_data={'backgroundColor': 'rgb(50, 50, 50)', 'color': 'white'},
            style_as_list_view=True,
            page_size=10,
            sort_action="native",
            filter_action="native",
        )
        return html.Div(_about_section(
            "🎯 Key Level Identifier Table: This table shows ALL CRITICAL PRICE LEVELS identified by the system's advanced algorithms. "
            "TYPES: Support (price floor), Resistance (price ceiling), Pin Zone (magnetic price), Vol Trigger (volatility expansion), Major Wall (massive OI). "
            "CONVICTION SCORE (0-1): Higher = stronger level. Above 0.7 = VERY HIGH conviction. "
            "METRICS: Shows which calculations identified this level (technical, options-based, flow-based). "
            "💡 TRADING INSIGHT: These are your BATTLE LINES for the day. "
            "SUPPORT levels = Where to buy/cover shorts, place stops below. "
            "RESISTANCE levels = Where to sell/short, place stops above. "
            "PIN ZONES = Price will gravitate here, especially near expiration. Great for iron condors/butterflies. "
            "VOL TRIGGERS = Breakout/breakdown points. Break = volatility expansion. Use for straddle/strangle entries. "
            "MAJOR WALLS = Extreme levels that rarely break. Use for credit spread strikes. "
            "Sort by CONVICTION to focus on the strongest levels. Filter by TYPE for specific strategies. "
            "These levels are DYNAMIC and update as market structure evolves!",
            "key-level-table"
        ) + [table])
    except Exception as e:
        logger.error(f"Error creating {chart_name}: {e}", exc_info=True)
        return html.Div(_about_section(
            "🎯 Key Level Identifier Table: This table shows ALL CRITICAL PRICE LEVELS identified by the system's advanced algorithms. "
            "TYPES: Support (price floor), Resistance (price ceiling), Pin Zone (magnetic price), Vol Trigger (volatility expansion), Major Wall (massive OI). "
            "CONVICTION SCORE (0-1): Higher = stronger level. Above 0.7 = VERY HIGH conviction. "
            "METRICS: Shows which calculations identified this level (technical, options-based, flow-based). "
            "💡 TRADING INSIGHT: These are your BATTLE LINES for the day. "
            "SUPPORT levels = Where to buy/cover shorts, place stops below. "
            "RESISTANCE levels = Where to sell/short, place stops above. "
            "PIN ZONES = Price will gravitate here, especially near expiration. Great for iron condors/butterflies. "
            "VOL TRIGGERS = Breakout/breakdown points. Break = volatility expansion. Use for straddle/strangle entries. "
            "MAJOR WALLS = Extreme levels that rarely break. Use for credit spread strikes. "
            "Sort by CONVICTION to focus on the strongest levels. Filter by TYPE for specific strategies. "
            "These levels are DYNAMIC and update as market structure evolves!",
            "key-level-table"
        ) + [
            dbc.Alert(f"Error: {e}", color="danger", className="mb-2"),
            html.Div(f"Error: {e}", className="text-danger mb-2")
        ])

# --- Main Layout Function ---
def create_layout(bundle: FinalAnalysisBundleV2_5, config: ConfigManagerV2_5) -> html.Div:
    """
    Creates the complete layout for the "Structure & Dealer Positioning" mode.
    This is the single entry point called by the callback manager.
    """
    # --- DIAGNOSTIC LOGGING ---
    try:
        logger.info(f"[StructureMode] Bundle type: {type(bundle)}")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"[StructureMode] Bundle keys: {list(bundle.__dict__.keys()) if hasattr(bundle, '__dict__') else 'N/A'}")
        pdb = getattr(bundle, 'processed_data_bundle', None)
        if pdb:
            contracts = getattr(pdb, 'options_data_with_metrics', [])
            strikes = getattr(pdb, 'strike_level_data_with_metrics', [])
            # logger.info(f"Processed {len(contracts)} contracts, {len(strikes)} strikes for {bundle.target_symbol}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Processed {len(contracts)} contracts, {len(strikes)} strikes for {bundle.target_symbol}")
            if strikes and logger.isEnabledFor(logging.DEBUG):
                first_row = strikes[0].model_dump() if hasattr(strikes[0], 'model_dump') else str(strikes[0])
                logger.debug(f"[StructureMode] First strike row: {first_row}")
            elif not strikes:
                logger.info("[StructureMode] No strike data present.")
        else:
            logger.info("[StructureMode] No processed_data_bundle in bundle.")
    except Exception as e:
        logger.error(f"[StructureMode] Diagnostic logging failed: {e}", exc_info=True)

    warnings = []
    if not bundle or not getattr(bundle, 'processed_data_bundle', None):
        warnings.append("Structural data is not available. Cannot render Structure Mode.")
    else:
        strike_data = getattr(bundle.processed_data_bundle, 'strike_level_data_with_metrics', None)
        if not strike_data:
            warnings.append("Strike level data not available.")

    chart_blocks = [
        _generate_amspi_heatmap(bundle, config),
        _generate_esdag_charts(bundle, config),
        _generate_adag_strike_chart(bundle, config),
        _generate_asai_assi_charts(bundle, config),
        _generate_key_level_table(bundle, config)
    ]

    return html.Div([
        dbc.Container([
            html.H2("Structure & Dealer Positioning", className="mb-4 mt-2"),
            *([dbc.Alert(w, color="warning", className="mb-2")] for w in warnings),
            dbc.Row([
                dbc.Col(block, width=12, className="mb-4") for block in chart_blocks
            ])
        ], fluid=True)
    ])