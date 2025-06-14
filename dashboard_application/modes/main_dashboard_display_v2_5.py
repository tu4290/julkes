# EOTS v2.5 - S-GRADE, AUTHORITATIVE MAIN DASHBOARD DISPLAY

import logging
from typing import List, Optional, Any, Union, Tuple
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
import numpy as np

from dashboard_application import ids
from dashboard_application.utils_dashboard_v2_5 import create_empty_figure, PLOTLY_TEMPLATE, add_timestamp_annotation
from data_models.eots_schemas_v2_5 import FinalAnalysisBundleV2_5, ProcessedUnderlyingAggregatesV2_5, ActiveRecommendationPayloadV2_5, ProcessedStrikeLevelMetricsV2_5
from utils.config_manager_v2_5 import ConfigManagerV2_5

logger = logging.getLogger(__name__)

# --- Helper Functions for Component Generation ---

def _get_gauge_interpretation(value: float, metric_name: str) -> Tuple[str, str]:
    """Returns (synopsis, interpretation) for gauge values."""
    if metric_name in ["VAPI-FA", "DWFD", "TW-LAF"]:
        # Flow metrics
        if value >= 2:
            return ("Strong bullish flow momentum", "Strong Bullish Signal")
        elif value >= 1:
            return ("Moderate bullish flow", "Moderate Bullish Signal")
        elif value >= -1:
            return ("Neutral/mixed flow", "Neutral/Mixed Signal")
        elif value >= -2:
            return ("Bearish flow momentum", "Moderate Bearish Signal")
        else:
            return ("Strong bearish flow momentum", "Strong Bearish Signal")
    elif metric_name == "GIB OI-Based":
        # Gamma Imbalance
        if value > 5000:
            return ("Dealers long gamma (market stable)", "High Dealer Long Gamma (Price Stability)")
        elif value > 1000:
            return ("Moderate dealer long gamma", "Dealer Long Gamma (Some Stability)")
        elif value > 0:
            return ("Slight dealer long gamma", "Dealer Long Gamma (Some Stability)")
        elif value > -1000:
            return ("Slight dealer short gamma", "Dealer Short Gamma (Some Volatility)")
        elif value > -5000:
            return ("Moderate dealer short gamma", "Dealer Short Gamma (Some Volatility)")
        else:
            return ("Dealers short gamma (market volatile)", "High Dealer Short Gamma (High Volatility)")
    elif metric_name in ["TD-GIB", "HP-EOD"]:
        if value > 0:
            return ("Buying/positive pressure expected", "Positive Pressure Expected")
        else:
            return ("Selling/negative pressure expected", "Negative Pressure Expected")
    else:
        return (f"Value: {value:.2f}", f"Value: {value:.2f}")

def _get_heatmap_interpretation(value: float, metric_name: str) -> str:
    """Returns interpretation text for heatmap values."""
    if metric_name == "SGDHP":
        if value > 50:
            return "Very Strong Support/Resistance Level"
        elif value > 20:
            return "Strong Support/Resistance Level"
        elif value > 5:
            return "Moderate Support/Resistance Level"
        else:
            return "Weak Support/Resistance Level"
    elif metric_name == "UGCH":
        if value > 5:
            return "Very High Greek Confluence"
        elif value > 2:
            return "High Greek Confluence"
        elif value > 0:
            return "Moderate Greek Confluence"
        elif value > -2:
            return "Low Greek Confluence"
        else:
            return "Very Low Greek Confluence"
    else:
        return f"Value: {value:.2f}"

def _get_dashboard_settings(config: ConfigManagerV2_5) -> dict:
    """Get dashboard settings with proper fallbacks"""
    try:
        dashboard_config = config.config.visualization_settings.dashboard
        return dashboard_config.get("main_dashboard_settings", {})
    except Exception as e:
        logger.warning(f"Failed to load dashboard settings: {e}")
        return {}

def _create_regime_display(und_data: ProcessedUnderlyingAggregatesV2_5, config: ConfigManagerV2_5) -> dbc.Card:
    """Creates the market regime display card."""
    main_dash_settings = _get_dashboard_settings(config)
    regime_settings = main_dash_settings.get("regime_display", {})
    regime_title = regime_settings.get("title", "Market Regime")
    
    # Chart blurb for user guidance - now in collapsible section
    regime_blurb = dbc.Alert([
        html.B("🧠 Market Regime Engine: "),
        "Analyzes current market conditions using multiple metrics. Helps determine optimal strategy types and risk parameters. ",
        "Green = Bullish conditions, Red = Bearish conditions, Yellow = Transitional/Unclear. ",
        html.Br(), html.Br(),
        html.B("💡 TRADING INSIGHTS: "),
        "BULLISH: Favor trend-following, long-biased strategies. ",
        "BEARISH: Favor short-biased, defensive strategies. ",
        "TRANSITION: Reduce size, use mean-reversion or neutral strategies. ",
        "Regime shifts often precede major market moves – watch for color changes!"
    ], color="info", dismissable=False, className="mb-2", style={'font-size': '0.95em'})

    card_body_children: List[Union[html.H6, dbc.Alert, html.Small, dbc.Collapse, dbc.Button]] = [
        html.H6(f"{regime_title}", className="card-title text-muted text-center"),
        dbc.Button(
            "ℹ️ About", 
            id="regime-about-toggle", 
            color="link", 
            size="sm", 
            className="p-0 text-muted",
            style={'font-size': '0.75em'}
        ),
        dbc.Collapse(
            regime_blurb,
            id="regime-about-collapse",
            is_open=False
        )
    ]

    if not und_data or not hasattr(und_data, 'current_market_regime_v2_5'):
        card_body_children.append(dbc.Alert("Regime data unavailable.", color="info", className="mt-2"))
    else:
        regime = und_data.current_market_regime_v2_5 or "UNKNOWN"
        
        # Color mapping for different regimes
        if "BULL" in regime.upper() or "POSITIVE" in regime.upper():
            alert_color = "success"
        elif "BEAR" in regime.upper() or "NEGATIVE" in regime.upper():
            alert_color = "danger"
        elif "UNCLEAR" in regime.upper() or "TRANSITION" in regime.upper():
            alert_color = "warning"
        else:
            alert_color = "info"
        
        card_body_children.append(
            dbc.Alert(regime.replace("_", " ").title(), color=alert_color, className="mt-2 text-center")
        )

    return dbc.Card(dbc.CardBody(card_body_children))

def _create_flow_gauge(
    metric_name: str,
    value: Optional[float],
    component_id: str,
    config: ConfigManagerV2_5,
    timestamp: Optional[datetime],
    symbol: str
) -> html.Div:
    """Creates a flow gauge for enhanced flow metrics (VAPI-FA, DWFD, TW-LAF)."""
    main_dash_settings = _get_dashboard_settings(config)
    flow_gauge_settings = main_dash_settings.get("flow_gauge", {})
    fig_height = flow_gauge_settings.get("height", 200)
    
    # Chart blurbs for user guidance
    gauge_blurbs = {
        "VAPI-FA": "📈 Volatility-Adjusted Premium Intensity with Flow Acceleration: Measures premium flow momentum adjusted for volatility. +3 = Strong bullish flow, -3 = Strong bearish flow. Use for trend confirmation.",
        "DWFD": "⚖️ Delta-Weighted Flow Divergence: Detects when smart money flows diverge from price action. +3 = Bullish divergence, -3 = Bearish divergence. Use for reversal signals.",
        "TW-LAF": "⏰ Time-Weighted Liquidity-Adjusted Flow: Tracks sustained flow patterns across multiple timeframes. +3 = Sustained bullish pressure, -3 = Sustained bearish pressure. Use for trend strength."
    }
    
    blurb_text = gauge_blurbs.get(metric_name, f"{metric_name} flow analysis")
    gauge_title_text = f"{metric_name}"  # Just the metric name to prevent overlapping
    indicator_title_text = f"{metric_name}"

    if value is None or pd.isna(value):
        fig = create_empty_figure(title=gauge_title_text, height=fig_height, reason="Data N/A")
    else:
        synopsis, interpretation = _get_gauge_interpretation(float(value), metric_name)
        hover_text = f"""
        <b>{symbol} - {metric_name}</b><br>
        Current Value: {float(value):.2f}<br>
        Range: -3 to +3<br>
        <b>Quick Synopsis:</b> {synopsis}<br>
        Interpretation: {interpretation}<br>
        <extra></extra>
        """
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=float(value),
            title={'text': indicator_title_text, 'font': {'size': flow_gauge_settings.get("indicator_font_size", 14)}},
            number={'font': {'size': flow_gauge_settings.get("number_font_size", 20)}},
            gauge={
                'axis': {'range': [-3, 3], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "rgba(0,0,0,0)"},
                'steps': [
                    {'range': [-3, -2], 'color': '#d62728'},
                    {'range': [-2, -1], 'color': '#ff9896'},
                    {'range': [-1, 1], 'color': '#aec7e8'},
                    {'range': [1, 2], 'color': '#98df8a'},
                    {'range': [2, 3], 'color': '#2ca02c'}
                ],
                'threshold': {
                    'line': {'color': flow_gauge_settings.get("threshold_line_color", "white"), 'width': 3},
                    'thickness': 0.8, 'value': float(value)
                }
            }
        ))
        
        # Add invisible scatter point for custom hover
        fig.add_trace(go.Scatter(
            x=[0.5], y=[0.5],
            mode='markers',
            marker=dict(size=1, opacity=0),
            hovertemplate=hover_text,
            showlegend=False,
            name=""
        ))
        fig.update_layout(
            height=fig_height,  # Normal height without extra space for blurb
            margin=flow_gauge_settings.get("margin", {'t': 30, 'b': 30, 'l': 15, 'r': 15}),  # Reduced top margin since no main title
            template=PLOTLY_TEMPLATE,
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        # Remove grid lines from gauge charts
        fig.update_xaxes(showgrid=False, zeroline=False, visible=False)
        fig.update_yaxes(showgrid=False, zeroline=False, visible=False)

    if timestamp:
        fig = add_timestamp_annotation(fig, timestamp)

    # Create the graph with collapsible about section
    graph_component = dcc.Graph(id=component_id, figure=fig)
    
    # Create collapsible about section
    about_blurb_map = {
        "VAPI-FA": ABOUT_VAPI_FA,
        "DWFD": ABOUT_DWFD,
        "TW-LAF": ABOUT_TW_LAF
    }
    about_blurb = about_blurb_map.get(metric_name, ABOUT_VAPI_FA)
    about_button = dbc.Button(
        "ℹ️ About", 
        id={"type": "about-toggle", "index": component_id}, 
        color="link", 
        size="sm", 
        className="p-0 text-muted mb-2",
        style={'font-size': '0.75em'}
    )
    about_collapse = dbc.Collapse(
        about_blurb,
        id={"type": "about-collapse", "index": component_id},
        is_open=False
    )
    
    return html.Div([
        about_button,
        about_collapse,
        graph_component
    ])

def _create_recommendations_table(
    recommendations: List[ActiveRecommendationPayloadV2_5],
    config: ConfigManagerV2_5,
    timestamp: Optional[datetime],
    symbol: str
) -> dbc.Card:
    """Creates the display for the ATIF recommendations table using dash_table.DataTable."""
    main_dash_settings = _get_dashboard_settings(config)
    table_settings = main_dash_settings.get("recommendations_table", {})
    max_rationale_len = table_settings.get('max_rationale_length', 50)
    table_title = table_settings.get("title", "ATIF Recommendations")

    card_body_children: List[Union[html.H4, dbc.Alert, dash_table.DataTable, html.Small]] = [
        html.H4(table_title)
    ]

    if not recommendations:
        card_body_children.append(dbc.Alert("No active recommendations.", color="info", className="mt-2"))
    else:
        data_for_table = []
        for reco in recommendations:
            rationale = reco.target_rationale
            if rationale and len(rationale) > max_rationale_len:
                rationale = rationale[:max_rationale_len] + '...'

            data_for_table.append({
                'Strategy': reco.strategy_type,
                'Bias': reco.trade_bias,
                'Conviction': f"{reco.atif_conviction_score_at_issuance:.2f}",
                'Status': reco.status,
                'Entry': f"{reco.entry_price_initial:.2f}" if reco.entry_price_initial is not None else "N/A",
                'Stop': f"{reco.stop_loss_current:.2f}" if reco.stop_loss_current is not None else "N/A",
                'Target 1': f"{reco.target_1_current:.2f}" if reco.target_1_current is not None else "N/A",
                'Rationale': rationale
            })

        table_component = dash_table.DataTable(
            id=f"{ids.ID_RECOMMENDATIONS_TABLE}-{symbol.lower()}",
            columns=[{"name": i, "id": i} for i in data_for_table[0].keys()] if data_for_table else [],
            data=data_for_table,
            style_cell=table_settings.get("style_cell", {'textAlign': 'left', 'padding': '5px', 'minWidth': '80px', 'width': 'auto', 'maxWidth': '200px'}),
            style_header=table_settings.get("style_header", {'backgroundColor': 'rgb(30, 30, 30)', 'fontWeight': 'bold', 'color': 'white'}),
            style_data=table_settings.get("style_data", {'backgroundColor': 'rgb(50, 50, 50)', 'color': 'white'}),
            style_as_list_view=True,
            page_size=table_settings.get("page_size", 5),
            sort_action="native",
            filter_action="native",
        )
        card_body_children.append(table_component)

    if timestamp:
        ts_format = config.config.visualization_settings.dashboard.get("timestamp_format", '%Y-%m-%d %H:%M:%S %Z')
        timestamp_text = f"Last updated: {timestamp.strftime(ts_format)}"
        card_body_children.append(html.Small(timestamp_text, className="text-muted d-block mt-2 text-end"))

    return dbc.Card(dbc.CardBody(card_body_children))

def _create_gib_gauge(
    metric_name: str,
    value: Optional[float],
    component_id: str,
    config: ConfigManagerV2_5,
    timestamp: Optional[datetime],
    symbol: str,
    is_dollar_value: bool = False
) -> html.Div:
    """Creates a GIB gauge for gamma imbalance metrics."""
    main_dash_settings = _get_dashboard_settings(config)
    gib_gauge_settings = main_dash_settings.get("gib_gauge", {})
    fig_height = gib_gauge_settings.get("height", 200)
    
    # Chart blurbs for user guidance
    gib_blurbs = {
        "GIB OI-Based": "🎯 Gamma Imbalance Barometer: Measures net gamma exposure from open interest. Positive = Dealers long gamma (price stability), Negative = Dealers short gamma (volatility). Use for volatility forecasting.",
        "TD-GIB": "⏰ Time-Decay Adjusted GIB: GIB adjusted for time decay effects. Shows how gamma imbalance evolves toward expiration. Higher values = Stronger pin risk. Use for EOD positioning.",
        "HP-EOD": "🔚 End-of-Day Hedging Pressure: Predicts hedging flows into market close. Positive = Buying pressure expected, Negative = Selling pressure expected. Use for EOD trade timing."
    }
    
    blurb_text = gib_blurbs.get(metric_name, f"{metric_name} gamma analysis")
    gauge_title_text = f"{metric_name}"  # Just the metric name to prevent overlapping
    indicator_title_text = metric_name

    if value is None or pd.isna(value):
        fig = create_empty_figure(title=gauge_title_text, height=fig_height, reason="Data N/A")
    else:
        # Dynamic scaling based on value type
        if is_dollar_value:
            # For HP_EOD (dollar values)
            abs_val = abs(float(value))
            if abs_val > 50000:
                axis_range = [-100000, 100000]
            elif abs_val > 10000:
                axis_range = [-50000, 50000]
            else:
                axis_range = [-10000, 10000]
            
            steps = gib_gauge_settings.get("steps_dollar", [
                {'range': [axis_range[0], axis_range[0]*0.5], 'color': '#d62728'},
                {'range': [axis_range[0]*0.5, axis_range[0]*0.1], 'color': '#ff9896'},
                {'range': [axis_range[0]*0.1, axis_range[1]*0.1], 'color': '#aec7e8'},
                {'range': [axis_range[1]*0.1, axis_range[1]*0.5], 'color': '#98df8a'},
                {'range': [axis_range[1]*0.5, axis_range[1]], 'color': '#2ca02c'}
            ])
        elif metric_name == "GIB OI-Based":
            # For GIB (large values)
            abs_val = abs(float(value))
            if abs_val > 50000:
                axis_range = [-100000, 100000]
            elif abs_val > 10000:
                axis_range = [-50000, 50000]
            else:
                axis_range = [-10000, 10000]
                
            steps = gib_gauge_settings.get("steps_gib", [
                {'range': [axis_range[0], axis_range[0]*0.5], 'color': '#d62728'},
                {'range': [axis_range[0]*0.5, axis_range[0]*0.1], 'color': '#ff9896'},
                {'range': [axis_range[0]*0.1, axis_range[1]*0.1], 'color': '#aec7e8'},
                {'range': [axis_range[1]*0.1, axis_range[1]*0.5], 'color': '#98df8a'},
                {'range': [axis_range[1]*0.5, axis_range[1]], 'color': '#2ca02c'}
            ])
        else:
            axis_range = gib_gauge_settings.get("axis_range", [-1, 1])
            steps = gib_gauge_settings.get("steps", [
                {'range': [-1, -0.5], 'color': '#d62728'},
                {'range': [-0.5, -0.1], 'color': '#ff9896'},
                {'range': [-0.1, 0.1], 'color': '#aec7e8'},
                {'range': [0.1, 0.5], 'color': '#98df8a'},
                {'range': [0.5, 1], 'color': '#2ca02c'}
            ])

        synopsis, interpretation = _get_gauge_interpretation(float(value), metric_name)
        hover_text = f"""
        <b>{symbol} - {metric_name}</b><br>
        Current Value: {float(value):,.0f}<br>
        Range: {axis_range[0]:,} to {axis_range[1]:,}<br>
        <b>Quick Synopsis:</b> {synopsis}<br>
        Interpretation: {interpretation}<br>
        <extra></extra>
        """
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=float(value),
            title={'text': indicator_title_text, 'font': {'size': gib_gauge_settings.get("indicator_font_size", 14)}},
            number={'font': {'size': gib_gauge_settings.get("number_font_size", 20)}},
            gauge={
                'axis': {'range': axis_range, 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "rgba(0,0,0,0)"},
                'steps': steps,
                'threshold': {
                    'line': {'color': gib_gauge_settings.get("threshold_line_color", "white"), 'width': 3},
                    'thickness': 0.8, 'value': float(value)
                }
            }
        ))
        
        # Add invisible scatter point for custom hover
        fig.add_trace(go.Scatter(
            x=[0.5], y=[0.5],
            mode='markers',
            marker=dict(size=1, opacity=0),
            hovertemplate=hover_text,
            showlegend=False,
            name=""
        ))
        fig.update_layout(
            height=fig_height,  # Normal height without extra space for blurb
            margin=gib_gauge_settings.get("margin", {'t': 30, 'b': 30, 'l': 15, 'r': 15}),  # Reduced top margin since no main title
            template=PLOTLY_TEMPLATE,
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        # Remove grid lines from gauge charts
        fig.update_xaxes(showgrid=False, zeroline=False, visible=False)
        fig.update_yaxes(showgrid=False, zeroline=False, visible=False)

    if timestamp:
        fig = add_timestamp_annotation(fig, timestamp)

    # Create the graph with collapsible about section
    graph_component = dcc.Graph(id=component_id, figure=fig)
    
    # Create collapsible about section
    about_blurb_map = {
        "GIB OI-Based": ABOUT_GIB,
        "TD-GIB": ABOUT_TD_GIB,
        "HP-EOD": ABOUT_HP_EOD
    }
    about_blurb = about_blurb_map.get(metric_name, ABOUT_GIB)
    about_button = dbc.Button(
        "ℹ️ About", 
        id={"type": "about-toggle", "index": component_id}, 
        color="link", 
        size="sm", 
        className="p-0 text-muted mb-2",
        style={'font-size': '0.75em'}
    )
    about_collapse = dbc.Collapse(
        about_blurb,
        id={"type": "about-collapse", "index": component_id},
        is_open=False
    )
    
    return html.Div([
        about_button,
        about_collapse,
        graph_component
    ])

def _create_mini_heatmap(
    metric_name: str,
    strike_data: List[ProcessedStrikeLevelMetricsV2_5],
    metric_field: str,
    component_id: str,
    config: ConfigManagerV2_5,
    timestamp: Optional[datetime],
    symbol: str,
    current_price: Optional[float]
) -> html.Div:
    """Creates a mini-heatmap for strike-level metrics like SGDHP and UGCH."""
    main_dash_settings = _get_dashboard_settings(config)
    heatmap_settings = main_dash_settings.get("mini_heatmap", {})
    fig_height = heatmap_settings.get("height", 150)
    
    # Chart blurbs for user guidance
    chart_blurbs = {
        "SGDHP": "🎯 Super Gamma-Delta Hedging Pressure: Shows strikes where market makers defend prices most aggressively. Cyan = Strong positive pressure (support), Magenta = Strong negative pressure (resistance). Use for dynamic S/R levels.",
        "UGCH": "⚡ Ultimate Greek Confluence: Highlights strikes where ALL Greeks (Delta, Gamma, Vega, Theta, Charm, Vanna) align. Higher values = stronger structural significance. Use for high-conviction strike selection."
    }
    
    blurb_text = chart_blurbs.get(metric_name, f"{metric_name} strike-level analysis")
    heatmap_title_text = f"{metric_name} Mini-Heatmap"  # Just the metric name to prevent overlapping

    if not strike_data or current_price is None:
        fig = create_empty_figure(title=heatmap_title_text, height=fig_height, reason="Data N/A")
    else:
        price_range = current_price * 0.05
        relevant_strikes = []
        values = []
        
        for strike_info in strike_data:
            if abs(strike_info.strike - current_price) <= price_range:
                metric_value = getattr(strike_info, metric_field, None)
                if metric_value is not None and pd.notna(metric_value):
                    relevant_strikes.append(strike_info.strike)
                    values.append(metric_value)
        
        if not relevant_strikes:
            fig = create_empty_figure(title=heatmap_title_text, height=fig_height, reason="No ATM/NTM Data")
        else:
            sorted_data = sorted(zip(relevant_strikes, values))
            strikes, vals = zip(*sorted_data)
            
            # Custom color scheme for SGDHP: Cyan-Magenta gradient
            if metric_name == "SGDHP":
                colorscale = [
                    [0.0, '#FF00FF'],    # Magenta for negative (strong resistance)
                    [0.2, '#FF66FF'],    # Light magenta
                    [0.4, '#CCCCCC'],    # Neutral gray
                    [0.6, '#66FFFF'],    # Light cyan  
                    [1.0, '#00FFFF']     # Cyan for positive (strong support)
                ]
            else:
                # Keep default for UGCH
                colorscale = heatmap_settings.get("colorscale", "RdYlGn")
            
            # Create custom hover template for heatmap
            hover_template = (
                f"<b>{symbol} - {metric_name}</b><br>"
                "Strike: $%{x:,.0f}<br>"
                f"Current Price: ${current_price:,.2f}<br>"
                "Distance: $%{customdata[2]:,.2f} (%{customdata[3]:.1f}%)<br>"
                f"{metric_name} Value: %{{z:.2f}}<br>"
                "Interpretation: %{customdata[4]}<br>"
                "<extra></extra>"
            )
            
            # Prepare custom data for hover
            custom_data = []
            for strike, val in zip(strikes, vals):
                distance_from_current = abs(strike - current_price)
                pct_from_current = (distance_from_current / current_price) * 100
                interpretation = _get_heatmap_interpretation(val, metric_name)
                custom_data.append([strike, val, distance_from_current, pct_from_current, interpretation])
            
            fig = go.Figure(data=go.Heatmap(
                z=[vals],
                x=strikes,
                y=[metric_name],
                colorscale=colorscale,
                showscale=True,
                colorbar=dict(len=0.5, thickness=10),
                hovertemplate=hover_template,
                customdata=[custom_data]
            ))
            
            fig.update_layout(
                title={'text': heatmap_title_text, 'y':0.85, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top', 'font': {'size': 12}},
                height=fig_height,  # Normal height without extra space for blurb
                margin=heatmap_settings.get("margin", {'t': 60, 'b': 30, 'l': 40, 'r': 40}),  # Increased top margin for title
                template=PLOTLY_TEMPLATE,
                xaxis_title="Strike",
                yaxis_title="",
                showlegend=False
            )

    if timestamp:
        fig = add_timestamp_annotation(fig, timestamp)

    # Create the graph with collapsible about section
    graph_component = dcc.Graph(id=component_id, figure=fig)
    
    # Create collapsible about section
    about_blurb_map = {
        "SGDHP": ABOUT_SGDHP,
        "UGCH": ABOUT_UGCH
    }
    about_blurb = about_blurb_map.get(metric_name, ABOUT_SGDHP)
    about_button = dbc.Button(
        "ℹ️ About", 
        id={"type": "about-toggle", "index": component_id}, 
        color="link", 
        size="sm", 
        className="p-0 text-muted mb-2",
        style={'font-size': '0.75em'}
    )
    about_collapse = dbc.Collapse(
        about_blurb,
        id={"type": "about-collapse", "index": component_id},
        is_open=False
    )
    
    return html.Div([
        about_button,
        about_collapse,
        graph_component
    ])

def _create_ticker_context_summary(
    ticker_context_dict: Optional[Any],
    config: ConfigManagerV2_5,
    timestamp: Optional[datetime],
    symbol: str
) -> dbc.Card:
    """Creates the ticker context summary display."""
    main_dash_settings = _get_dashboard_settings(config)
    context_settings = main_dash_settings.get("ticker_context", {})
    context_title = context_settings.get("title", "Ticker Context")

    card_body_children: List[Union[html.H6, dbc.Alert, dbc.Badge, html.Small]] = [
        html.H6(context_title, className="card-title text-muted text-center")
    ]

    if not ticker_context_dict:
        card_body_children.append(dbc.Alert("No context data available.", color="info", className="mt-2"))
    else:
        context_flags = []
        
        if hasattr(ticker_context_dict, 'is_0dte') and ticker_context_dict.is_0dte:
            context_flags.append(f"{symbol}: 0DTE")
        if hasattr(ticker_context_dict, 'is_1dte') and ticker_context_dict.is_1dte:
            context_flags.append(f"{symbol}: 1DTE")
        if hasattr(ticker_context_dict, 'active_intraday_session') and ticker_context_dict.active_intraday_session:
            context_flags.append(f"Session: {ticker_context_dict.active_intraday_session}")
        if hasattr(ticker_context_dict, 'vix_spy_price_divergence_strong_negative') and ticker_context_dict.vix_spy_price_divergence_strong_negative:
            context_flags.append("Pattern: VIX_DIVERGENCE_ACTIVE")
        if hasattr(ticker_context_dict, 'is_fomc_meeting_day') and ticker_context_dict.is_fomc_meeting_day:
            context_flags.append("Event: FOMC_DAY")
        if hasattr(ticker_context_dict, 'earnings_approaching_flag') and ticker_context_dict.earnings_approaching_flag:
            context_flags.append("Event: EARNINGS_APPROACHING")
        
        if context_flags:
            for flag in context_flags:
                card_body_children.append(
                    dbc.Badge(flag, color="primary", className="me-1 mb-1")
                )
        else:
            card_body_children.append(
                html.Small("No significant context flags active.", className="text-muted")
            )

    if timestamp:
        ts_format = config.config.visualization_settings.dashboard.get("timestamp_format", '%Y-%m-%d %H:%M:%S %Z')
        timestamp_text = f"Last updated: {timestamp.strftime(ts_format)}"
        card_body_children.append(html.Small(timestamp_text, className="text-muted d-block mt-2 text-end"))

    return dbc.Card(dbc.CardBody(card_body_children))

# --- Enhanced About blurbs for each metric ---
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
], color="info", dismissable=False, className="mb-2", style={'font-size': '0.95em'})

ABOUT_DWFD = dbc.Alert([
    html.B("⚖️ DWFD (Delta-Weighted Flow Divergence): "),
    "This is your FLOW REVERSAL RADAR – it detects when smart money flows diverge from price action. DWFD highlights when institutions are buying into weakness or selling into strength. ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "+2 or higher = Strong bullish divergence (buying into weakness). ",
    "-2 or lower = Strong bearish divergence (selling into strength). ",
    "Between -0.5 and +0.5 = No significant divergence. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "BULLISH DIVERGENCE: Price down, DWFD up = buy reversal setups. ",
    "BEARISH DIVERGENCE: Price up, DWFD down = short reversal setups. ",
    "BEST SIGNALS: When DWFD and VAPI-FA both show strong divergence. ",
    "DWFD often leads price reversals by 10–60 minutes."
], color="info", dismissable=False, className="mb-2", style={'font-size': '0.95em'})

ABOUT_TW_LAF = dbc.Alert([
    html.B("⏰ TW-LAF (Time-Weighted Liquidity-Adjusted Flow): "),
    "This is your TREND STRENGTH METER – it tracks sustained flow patterns across multiple timeframes. TW-LAF shows whether bullish or bearish pressure is building and persisting. ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "+2 or higher = Sustained bullish pressure (trend likely to continue). ",
    "-2 or lower = Sustained bearish pressure (trend likely to continue down). ",
    "Between -0.5 and +0.5 = Choppy/neutral. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "SUSTAINED BULLISH: TW-LAF > 2 for 30+ min = ride the trend long. ",
    "SUSTAINED BEARISH: TW-LAF < -2 for 30+ min = ride the trend short. ",
    "CHOP: TW-LAF oscillates near zero = fade extremes, avoid trend trades. ",
    "BEST SIGNALS: When TW-LAF, VAPI-FA, and DWFD all align."
], color="info", dismissable=False, className="mb-2", style={'font-size': '0.95em'})

ABOUT_GIB = dbc.Alert([
    html.B("🎯 GIB OI-Based (Gamma Imbalance Barometer): "),
    "This is your VOLATILITY FORECASTER – it measures net gamma exposure from open interest. Positive = Dealers long gamma (price stability), Negative = Dealers short gamma (volatility). ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "> 10,000 = Dealers very long gamma (expect low volatility, mean reversion). ",
    "< -10,000 = Dealers very short gamma (expect high volatility, large moves). ",
    "Between -1,000 and +1,000 = Neutral, market can move either way. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "LONG GAMMA: Favor range trades, fade breakouts. ",
    "SHORT GAMMA: Favor breakout trades, use wide stops. ",
    "GIB FLIPS: When GIB crosses zero, expect regime change."
], color="info", dismissable=False, className="mb-2", style={'font-size': '0.95em'})

ABOUT_TD_GIB = dbc.Alert([
    html.B("⏰ TD-GIB (Time-Decay Adjusted Gamma Imbalance): "),
    "This is your PIN RISK METER – it shows how gamma imbalance evolves toward expiration. Higher values = Stronger pin risk. Use for EOD positioning. ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "+10,000 or higher = Strong pin risk, expect price to gravitate to key strikes. ",
    "-10,000 or lower = Strong anti-pin, expect price to move away from key strikes. ",
    "Between -2,000 and +2,000 = Low pin risk. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "PIN RISK: Use for EOD trades, favor iron condors/butterflies near pin strikes. ",
    "ANTI-PIN: Favor directional trades away from key strikes."
], color="info", dismissable=False, className="mb-2", style={'font-size': '0.95em'})

ABOUT_HP_EOD = dbc.Alert([
    html.B("🔚 HP-EOD (End-of-Day Hedging Pressure): "),
    "This is your EOD FLOW FORECAST – predicts hedging flows into market close. Positive = Buying pressure expected, Negative = Selling pressure expected. ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "+50,000 or higher = Strong EOD buying pressure. ",
    "-50,000 or lower = Strong EOD selling pressure. ",
    "Between -10,000 and +10,000 = Neutral. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "EOD BUYING: Favor long trades into the close. ",
    "EOD SELLING: Favor short trades into the close. ",
    "HP-EOD FLIPS: When HP-EOD crosses zero, expect reversal risk."
], color="info", dismissable=False, className="mb-2", style={'font-size': '0.95em'})

ABOUT_SGDHP = dbc.Alert([
    html.B("🎯 SGDHP (Super Gamma-Delta Hedging Pressure): "),
    "This is your DYNAMIC SUPPORT/RESISTANCE MAP – shows strikes where market makers defend prices most aggressively. Cyan = Strong positive pressure (support), Magenta = Strong negative pressure (resistance). ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "CYAN BARS = Support zones, price likely to bounce. ",
    "MAGENTA BARS = Resistance zones, price likely to reject. ",
    "BAR HEIGHT = Strength of defense. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "MULTIPLE CYAN LEVELS BELOW = Bullish structure. ",
    "MULTIPLE MAGENTA LEVELS ABOVE = Bearish structure. ",
    "BREAKOUTS: When price breaks through a strong level, expect acceleration."
], color="info", dismissable=False, className="mb-2", style={'font-size': '0.95em'})

ABOUT_UGCH = dbc.Alert([
    html.B("⚡ UGCH (Ultimate Greek Confluence Heatmap): "),
    "This is your HIGH-CONVICTION STRIKE FINDER – highlights strikes where ALL Greeks (Delta, Gamma, Vega, Theta, Charm, Vanna) align. Higher values = stronger structural significance. ",
    html.Br(), html.Br(),
    html.B("HOW TO READ: "),
    "HIGH VALUES = All Greeks aligned, high conviction. ",
    "LOW VALUES = Mixed signals, low conviction. ",
    html.Br(), html.Br(),
    html.B("💡 TRADING INSIGHTS: "),
    "HIGH UGCH: Use these strikes for spreads, butterflies, and high-probability trades. ",
    "LOW UGCH: Avoid these strikes for major positions."
], color="info", dismissable=False, className="mb-2", style={'font-size': '0.95em'})

# --- Main Layout Function ---

def create_layout(bundle: FinalAnalysisBundleV2_5, config: ConfigManagerV2_5) -> html.Div:
    """Creates the complete layout for the Main Dashboard mode."""
    if not bundle or not bundle.processed_data_bundle:
        return html.Div(dbc.Alert("Analysis data is not available. Cannot render Main Dashboard.", color="danger"))

    # Extract data for convenience
    processed_data = bundle.processed_data_bundle
    und_data = processed_data.underlying_data_enriched
    strike_data = processed_data.strike_level_data_with_metrics
    symbol = bundle.target_symbol or "Unknown"
    bundle_timestamp = bundle.bundle_timestamp
    current_price = und_data.price if und_data else None

    return html.Div(
        id=ids.ID_MAIN_DASHBOARD_CONTAINER,
        children=[
            dbc.Container(
                fluid=True,
                children=[
                    # Row 1: Market Regime and Flow Metrics
                    dbc.Row([
                        dbc.Col(_create_regime_display(und_data, config), md=6, lg=3, className="mb-4"),
                        dbc.Col(_create_flow_gauge("VAPI-FA", und_data.vapi_fa_z_score_und, ids.ID_VAPI_GAUGE, config, bundle_timestamp, symbol), md=6, lg=3, className="mb-4"),
                        dbc.Col(_create_flow_gauge("DWFD", und_data.dwfd_z_score_und, ids.ID_DWFD_GAUGE, config, bundle_timestamp, symbol), md=6, lg=3, className="mb-4"),
                        dbc.Col(_create_flow_gauge("TW-LAF", und_data.tw_laf_z_score_und, ids.ID_TW_LAF_GAUGE, config, bundle_timestamp, symbol), md=6, lg=3, className="mb-4"),
                    ], className="mt-3"),
                    # Row 2: GIB Gauges and HP_EOD
                    dbc.Row([
                        dbc.Col(_create_gib_gauge("GIB OI-Based", und_data.gib_oi_based_und, f"{ids.ID_GIB_GAUGE}-oi", config, bundle_timestamp, symbol), md=6, lg=4, className="mb-4"),
                        dbc.Col(_create_gib_gauge("TD-GIB", und_data.td_gib_und, f"{ids.ID_GIB_GAUGE}-td", config, bundle_timestamp, symbol, is_dollar_value=False), md=6, lg=4, className="mb-4"),
                        dbc.Col(_create_gib_gauge("HP-EOD", und_data.hp_eod_und, f"{ids.ID_HP_EOD_GAUGE}", config, bundle_timestamp, symbol, is_dollar_value=True), md=6, lg=4, className="mb-4"),
                    ], className="mt-3"),
                    # Row 3: Mini-Heatmaps (System Guide Requirements)
                    dbc.Row([
                        dbc.Col(_create_mini_heatmap("SGDHP", strike_data, "sgdhp_score_strike", "sgdhp-mini-heatmap", config, bundle_timestamp, symbol, current_price), md=6, lg=6, className="mb-4"),
                        dbc.Col(_create_mini_heatmap("UGCH", strike_data, "ugch_score_strike", "ugch-mini-heatmap", config, bundle_timestamp, symbol, current_price), md=6, lg=6, className="mb-4"),
                    ], className="mt-3"),
                    # Row 4: Recommendations Table and Ticker Context
                    dbc.Row([
                        dbc.Col(_create_recommendations_table(bundle.active_recommendations_v2_5, config, bundle_timestamp, symbol), md=12, lg=8, className="mb-4"),
                        dbc.Col(_create_ticker_context_summary(und_data.ticker_context_dict_v2_5, config, bundle_timestamp, symbol), md=12, lg=4, className="mb-4"),
                    ], className="mt-3"),
                ]
            )
        ]
    )