# dashboard_application/app_main.py
# EOTS v2.5 - S-GRADE, AUTHORITATIVE APPLICATION ENTRY POINT (REFACTORED)

import logging
import atexit
import sys

from dash.dash import Dash
import dash_bootstrap_components as dbc

# --- [START] EOTS V2.5 CORE IMPORTS (CORRECTED) ---
# All imports are now absolute from the project root, which is added to sys.path
# by the runner script. This resolves all ModuleNotFoundError issues.
from utils.config_manager_v2_5 import ConfigManagerV2_5
from data_management.database_manager_v2_5 import DatabaseManagerV2_5
from data_management.historical_data_manager_v2_5 import HistoricalDataManagerV2_5
from data_management.performance_tracker_v2_5 import PerformanceTrackerV2_5
from data_management.initial_processor_v2_5 import InitialDataProcessorV2_5
from core_analytics_engine.metrics_calculator_v2_5 import MetricsCalculatorV2_5
from core_analytics_engine.market_regime_engine_v2_5 import MarketRegimeEngineV2_5
from core_analytics_engine.signal_generator_v2_5 import SignalGeneratorV2_5
from core_analytics_engine.adaptive_trade_idea_framework_v2_5 import AdaptiveTradeIdeaFrameworkV2_5
from core_analytics_engine.trade_parameter_optimizer_v2_5 import TradeParameterOptimizerV2_5
from core_analytics_engine.its_orchestrator_v2_5 import ITSOrchestratorV2_5

# EOTS V2.5 Dashboard Imports (also now absolute)
from dashboard_application import layout_manager_v2_5
from dashboard_application import callback_manager_v2_5
from dashboard_application import utils_dashboard_v2_5
# --- [END] EOTS V2.5 CORE IMPORTS (CORRECTED) ---


def main():
    """
    Initializes and runs the EOTS v2.5 Dash application.
    This function encapsulates the entire application lifecycle, ensuring
    correct dependency injection and robust initialization.
    """
    # --- 1. System Configuration & Logging ---
    # Logging is configured by the runner script. We get the logger for this module.
    logger = logging.getLogger(__name__)

    try:
        # Initialize configuration
        config_manager = ConfigManagerV2_5()
        config_manager.load_config()
        logger.info("Configuration loaded successfully by the application core.")
    except (FileNotFoundError, ValueError) as e:
        logger.critical(f"FATAL: Could not load or validate configuration. System cannot start. Error: {e}", exc_info=True)
        sys.exit(1)
        
    # Initialize dashboard-specific utilities (e.g., global plotly template)
    utils_dashboard_v2_5.initialize_dashboard_utils(config_manager)

    # --- 2. Backend Component Initialization (Dependency Hierarchy) ---
    logger.info("Initializing backend components...")

    db_settings = config_manager.config.database_settings.model_dump() if config_manager.config.database_settings else {}
    if not db_settings:
        logger.warning("Database settings not found in configuration. DB functionality will be stubbed.")
    
    # Initialize database manager
    db_manager = DatabaseManagerV2_5(db_settings)
    atexit.register(db_manager.close_connection)

    # Initialize core components first
    performance_tracker = PerformanceTrackerV2_5(config_manager)
    historical_data_manager = HistoricalDataManagerV2_5(config_manager, db_manager)
    metrics_calculator = MetricsCalculatorV2_5(config_manager, historical_data_manager)
    market_regime_engine = MarketRegimeEngineV2_5(config_manager)
    
    # Initialize analytics components
    signal_generator = SignalGeneratorV2_5(config_manager)
    trade_parameter_optimizer = TradeParameterOptimizerV2_5(config_manager)
    adaptive_trade_idea_framework = AdaptiveTradeIdeaFrameworkV2_5(config_manager, performance_tracker)
    
    # Initialize processing components
    initial_processor = InitialDataProcessorV2_5(config_manager, metrics_calculator)
    
    logger.info("Initializing Master Orchestrator...")
    orchestrator = ITSOrchestratorV2_5(
        config_manager=config_manager,
        historical_data_manager=historical_data_manager,
        performance_tracker=performance_tracker,
        metrics_calculator=metrics_calculator,
        market_regime_engine=market_regime_engine,
        signal_generator=signal_generator,
        trade_parameter_optimizer=trade_parameter_optimizer,
        adaptive_trade_idea_framework=adaptive_trade_idea_framework,
        initial_processor=initial_processor
    )
    logger.info("All backend components and orchestrator initialized.")

    # --- 3. Dash Application Setup ---
    logger.info("Setting up Dash application...")
    app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
    app.title = "EOTS v2.5 Apex Predator"

    # Pass the config_manager instance to the layout and callback functions
    app.layout = layout_manager_v2_5.create_master_layout(config_manager)
    callback_manager_v2_5.register_v2_5_callbacks(app, orchestrator, config_manager)
    logger.info("Dashboard layout created and callbacks registered.")

    # --- 4. Application Execution ---
    logger.info("Starting EOTS v2.5 Apex Predator Dashboard...")
    # PRODUCTION MODE: debug=False prevents auto-reloading and process multiplication
    # use_reloader=False explicitly disables the Werkzeug reloader
    # threaded=True enables multi-threading for better performance
    app.run(
        debug=False,
        host='0.0.0.0', 
        port='8050',
        use_reloader=False,
        threaded=True
    )

# Note: The if __name__ == '__main__' block is intentionally omitted,
# as this script is not meant to be run directly. It is called by the
# main runner script in the project root.