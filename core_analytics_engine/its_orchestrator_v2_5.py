# core_analytics_engine/its_orchestrator_v2_5.py
# EOTS v2.5 - S-GRADE, AUTHORITATIVE MASTER ORCHESTRATOR

import logging
import asyncio
from datetime import datetime
from typing import Dict, Optional, Any, List, NamedTuple, Union
import pandas as pd
import aiohttp
from pydantic import ValidationError as PydanticValidationError

# EOTS V2.5 Data Contracts
from data_models.eots_schemas_v2_5 import (
    UnprocessedDataBundleV2_5, ProcessedDataBundleV2_5, FinalAnalysisBundleV2_5, EOTSConfigV2_5,
    RawUnderlyingDataCombinedV2_5, KeyLevelsDataV2_5, SignalPayloadV2_5,
    ATIFStrategyDirectivePayloadV2_5, ActiveRecommendationPayloadV2_5, TradeParametersV2_5,
    KeyLevelV2_5
)

# EOTS V2.5 Core Components
from utils.config_manager_v2_5 import ConfigManagerV2_5

from data_management.convexvalue_data_fetcher_v2_5 import ConvexValueDataFetcherV2_5
from data_management.tradier_data_fetcher_v2_5 import TradierDataFetcherV2_5
from data_management.initial_processor_v2_5 import InitialDataProcessorV2_5
from data_management.historical_data_manager_v2_5 import HistoricalDataManagerV2_5
from core_analytics_engine.metrics_calculator_v2_5 import MetricsCalculatorV2_5
from core_analytics_engine.market_regime_engine_v2_5 import MarketRegimeEngineV2_5
from core_analytics_engine.signal_generator_v2_5 import SignalGeneratorV2_5
from core_analytics_engine.adaptive_trade_idea_framework_v2_5 import AdaptiveTradeIdeaFrameworkV2_5
from core_analytics_engine.trade_parameter_optimizer_v2_5 import TradeParameterOptimizerV2_5
# NOTE: TickerContextAnalyzer and KeyLevelIdentifier would be imported here once created.

logger = logging.getLogger(__name__)

class DataFetchResult(NamedTuple):
    bundle: Optional[UnprocessedDataBundleV2_5]
    historical_data: Optional[pd.DataFrame]
    status: str  # 'success', 'partial', 'failed'
    errors: list
    messages: list

class ITSOrchestratorV2_5:
    """
    Main orchestrator for the EOTS v2.5. Controls the entire analysis pipeline
    from data ingestion to final output, enforcing strict data contracts.
    Enhanced for comprehensive data processing.
    """
    def __init__(self, config_manager: ConfigManagerV2_5, historical_data_manager: HistoricalDataManagerV2_5, performance_tracker: Any,
                 metrics_calculator: MetricsCalculatorV2_5, initial_processor: InitialDataProcessorV2_5,
                 market_regime_engine: MarketRegimeEngineV2_5, signal_generator: SignalGeneratorV2_5,
                 adaptive_trade_idea_framework: AdaptiveTradeIdeaFrameworkV2_5,
                 trade_parameter_optimizer: TradeParameterOptimizerV2_5):
        """Initializes the orchestrator with all subordinate components injected."""

        self.logger = logger.getChild(self.__class__.__name__)
        self.logger.info("Initializing ITSOrchestratorV2_5...")

        # Store injected dependencies
        self.config_manager = config_manager
        self.historical_data_manager = historical_data_manager
        self.performance_tracker = performance_tracker
        self.metrics_calculator = metrics_calculator
        self.initial_processor = initial_processor
        self.market_regime_engine = market_regime_engine
        self.signal_generator = signal_generator
        self.adaptive_trade_idea_framework = adaptive_trade_idea_framework
        self.trade_parameter_optimizer = trade_parameter_optimizer

        # Instantiate components not requiring complex dependency chains
        self.convexvalue_fetcher = ConvexValueDataFetcherV2_5(config_manager)
        self.tradier_fetcher = TradierDataFetcherV2_5(config_manager)
        from .key_level_identifier_v2_5 import KeyLevelIdentifierV2_5
        self.key_level_identifier = KeyLevelIdentifierV2_5(
            config=config_manager.config.key_level_identifier_settings
        )
        
        from .ticker_context_analyzer_v2_5 import TickerContextAnalyzerV2_5
        self.ticker_context_analyzer = TickerContextAnalyzerV2_5(
            config=dict(config_manager.config.ticker_context_analyzer_settings)
        )

        # State Management
        self.active_recommendations: List[ActiveRecommendationPayloadV2_5] = []
        self.current_symbol_being_managed: Optional[str] = None
        self._latest_bundle: Optional[FinalAnalysisBundleV2_5] = None
        

        
        self.logger.info("ITSOrchestratorV2_5 initialized successfully with all components.")

    def get_latest_analysis_bundle(self) -> Optional[FinalAnalysisBundleV2_5]:
        """Public method for the dashboard to retrieve the last computed bundle."""
        return self._latest_bundle

    def run_full_analysis_cycle(self, symbol: str, dte_min: int = 0, dte_max: int = 45, price_range_percent: int = 20) -> Optional[FinalAnalysisBundleV2_5]:
        """
        Executes the complete 12-step analysis pipeline for a given symbol.
        
        Args:
            symbol: The ticker symbol to analyze
            dte_min: Minimum days to expiration filter
            dte_max: Maximum days to expiration filter  
            price_range_percent: Strike price range percentage around current price
            
        Returns:
            FinalAnalysisBundleV2_5 containing all analysis results, or None if failed
        """
        self.logger.info(f"---|> Starting Analysis Cycle for '{symbol}' with DTE range [{dte_min}, {dte_max}] and price range ±{price_range_percent}% <|---")
        
        try:
            # Reset active recommendations if symbol changed
            if self.current_symbol_being_managed != symbol:
                self.logger.info(f"Symbol context changed to '{symbol}'. Resetting active recommendations.")
                self.active_recommendations = []
                self.current_symbol_being_managed = symbol

            self.logger.info(f"---|> Starting Full Analysis Cycle for '{symbol}'...")

            # Add except clause at end of try block
            # 1. DATA FUSION: Fetch raw data from all sources
            self.logger.info(f"🔄 STEP 1: Starting data fetch for {symbol}...")
            
            raw_data_bundle, historical_data, status, errors, messages = self._fetch_and_fuse_data(symbol, dte_min, dte_max, price_range_percent)
            if not raw_data_bundle:
                self.logger.error(f"❌ STEP 1 FAILED: No raw data bundle returned for {symbol}. Status: {status}. Errors: {errors}")
                return None
            
            if status == 'partial':
                self.logger.warning(f"⚠️ PARTIAL DATA: {messages}")
                raw_data_bundle.errors.extend(errors)
            elif status == 'failed':
                self.logger.error(f"❌ DATA FETCH FAILED: {errors}")
                return None
            
            self.logger.info(f"✅ STEP 1 SUCCESS: Raw data bundle created for {symbol}")

            # 2. METRIC CALCULATION: Process raw data and compute all metrics
            self.logger.info(f"🔄 STEP 2: Processing data and calculating metrics for {symbol}...")

            
            processed_data_bundle = self.initial_processor.process_data_and_calculate_metrics(raw_data_bundle, dte_max)
            


            # Create DataFrames once for performance - FIX: Proper Pydantic model conversion
            df_underlying = pd.DataFrame([processed_data_bundle.underlying_data_enriched.model_dump()])
            
            # CRITICAL FIX: Convert Pydantic models to DataFrame properly
            if processed_data_bundle.strike_level_data_with_metrics:
                # Convert list of Pydantic models to list of dicts first
                strike_dicts = [strike_model.model_dump() for strike_model in processed_data_bundle.strike_level_data_with_metrics]
                df_strike = pd.DataFrame(strike_dicts)
                # self.logger.info(f"✅ Strike data converted: {len(df_strike)} strikes")
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug(f"✅ Strike data converted: {len(df_strike)} strikes")
            else:
                self.logger.warning(f"No strike-level data available for {symbol}")
                df_strike = pd.DataFrame(columns=['strike'])
            
            # CRITICAL FIX: Safe index setting with proper data
            if not df_strike.empty and 'strike' in df_strike.columns:
                # self.logger.info(f"✅ Strike data OK: {len(df_strike)} strikes for {symbol}")
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug(f"✅ Strike data OK: {len(df_strike)} strikes for {symbol}")
                try:
                    df_strike.set_index('strike', inplace=True, drop=False)
                    self.logger.debug(f"✅ Strike index set successfully")
                except Exception as e:
                    self.logger.error(f"Failed to set strike index: {e}")
                    df_strike = pd.DataFrame(columns=['strike'])
            else:
                if df_strike.empty:
                    self.logger.warning(f"Strike DataFrame is empty for {symbol}")
                else:
                    self.logger.error(f"CRITICAL: 'strike' column missing from strike data for {symbol}")
                    self.logger.error(f"Available columns: {list(df_strike.columns)}")
                # Create minimal dummy DataFrame to prevent downstream errors  
                df_strike = pd.DataFrame(columns=['strike'])
            
            # Convert options data similarly
            if processed_data_bundle.options_data_with_metrics:
                options_dicts = [opt_model.model_dump() for opt_model in processed_data_bundle.options_data_with_metrics]
                df_chain = pd.DataFrame(options_dicts)
            else:
                df_chain = pd.DataFrame()
            
            # 3. CONTEXTUALIZATION: Get Ticker-Specific Context
            self.logger.info(f"🔄 STEP 3: Analyzing ticker context for {symbol}...")
            ticker_context_analysis = self.ticker_context_analyzer.analyze_ticker_context(
                symbol=symbol,
                price_data=df_underlying,
                options_data=df_strike
            )
            # Only assign if type matches expected
            if hasattr(processed_data_bundle.underlying_data_enriched, 'ticker_context_dict_v2_5'):
                processed_data_bundle.underlying_data_enriched.ticker_context_dict_v2_5 = ticker_context_analysis if isinstance(ticker_context_analysis, type(processed_data_bundle.underlying_data_enriched.ticker_context_dict_v2_5)) else None
            
            # 4. DYNAMIC THRESHOLDS: Resolve dynamic thresholds for this cycle
            self.logger.info(f"🔄 STEP 4: Resolving dynamic thresholds for {symbol}...")
            dynamic_thresholds = self._resolve_dynamic_thresholds(symbol, ticker_context_analysis)
            # Not assigning to processed_data_bundle.underlying_data_enriched.dynamic_thresholds as it's not a field

            # 5. MARKET REGIME: Classify the market state
            self.logger.info(f"🔄 STEP 5: Determining market regime for {symbol}...")

            
            market_regime = self.market_regime_engine.determine_market_regime(
                und_data=processed_data_bundle.underlying_data_enriched,
                df_strike=df_strike,
                df_chain=df_chain
            )
            processed_data_bundle.underlying_data_enriched.current_market_regime_v2_5 = market_regime
            

            
            self.logger.info(f"Market Regime classified as: {market_regime}")

            # 6. KEY LEVEL IDENTIFICATION: Identify critical support/resistance levels
            self.logger.info(f"🔄 STEP 6: Identifying key levels for {symbol}...")

            # Use historical data if available, otherwise create minimal DataFrame from current price
            if historical_data is not None and not historical_data.empty:
                price_data_for_levels = historical_data
                self.logger.info(f"Using historical data for key levels: {len(price_data_for_levels)} rows")
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"[Key Levels] Historical data columns: {price_data_for_levels.columns.tolist()}")
                    logger.debug(f"[Key Levels] Historical data date range: {price_data_for_levels.index[0]} to {price_data_for_levels.index[-1]}")
                    logger.debug(f"[Key Levels] Historical data sample:\n{price_data_for_levels.tail(3)}")
            else:
                # Fallback: create minimal DataFrame from current underlying data
                current_price = processed_data_bundle.underlying_data_enriched.price or 0.0
                price_data_for_levels = pd.DataFrame({
                    'close': [current_price],
                    'high': [current_price * 1.01],
                    'low': [current_price * 0.99],
                    'volume': [1000000]
                })
                self.logger.warning(f"No historical data available, using current price for key levels")
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"[Key Levels] Fallback data: {price_data_for_levels}")
            
            # Debug options data being passed
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[Key Levels] Options data type: {type(df_strike)}")
                logger.debug(f"[Key Levels] Options data shape: {df_strike.shape if hasattr(df_strike, 'shape') else 'N/A'}")
                logger.debug(f"[Key Levels] Options data columns: {df_strike.columns.tolist() if hasattr(df_strike, 'columns') else 'N/A'}")
                if hasattr(df_strike, 'shape') and df_strike.shape[0] > 0:
                    logger.debug(f"[Key Levels] Options data sample:\n{df_strike.head(3)}")
            
            # Call key level identifier with debugging
            self.logger.info(f"[Key Levels] Calling identify_key_levels for {symbol}...")
            key_level_analysis = self.key_level_identifier.identify_key_levels(
                symbol=symbol,
                price_data=price_data_for_levels,
                options_data=df_strike
            )
            
            # Debug the raw analysis results
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[Key Levels] Raw analysis type: {type(key_level_analysis)}")
                logger.debug(f"[Key Levels] Raw analysis timestamp: {getattr(key_level_analysis, 'timestamp', 'N/A')}")
                logger.debug(f"[Key Levels] Raw analysis current_price: {getattr(key_level_analysis, 'current_price', 'N/A')}")
                logger.debug(f"[Key Levels] Raw key_levels count: {len(getattr(key_level_analysis, 'key_levels', []))}")
                logger.debug(f"[Key Levels] Raw gamma_walls count: {len(getattr(key_level_analysis, 'gamma_walls', []))}")
                logger.debug(f"[Key Levels] Raw pivot_points count: {len(getattr(key_level_analysis, 'pivot_points', []))}")
                
                # Log individual levels
                for i, level in enumerate(getattr(key_level_analysis, 'key_levels', [])):
                    logger.debug(f"[Key Levels] Level {i}: price={getattr(level, 'price', 'N/A')}, type={getattr(level, 'level_type', 'N/A')}, confidence={getattr(level, 'confidence', 'N/A')}")
            
            # Convert KeyLevelAnalysis to KeyLevelsDataV2_5
            supports = [KeyLevelV2_5(
                level_price=getattr(kl, 'price', 0.0),
                level_type=getattr(kl, 'level_type', ''),
                conviction_score=getattr(kl, 'confidence', 0.0),
                contributing_metrics=[],
                source_identifier=None
            ) for kl in getattr(key_level_analysis, 'key_levels', []) if getattr(kl, 'level_type', '') == 'support']
            resistances = [KeyLevelV2_5(
                level_price=getattr(kl, 'price', 0.0),
                level_type=getattr(kl, 'level_type', ''),
                conviction_score=getattr(kl, 'confidence', 0.0),
                contributing_metrics=[],
                source_identifier=None
            ) for kl in getattr(key_level_analysis, 'key_levels', []) if getattr(kl, 'level_type', '') == 'resistance']
            pin_zones = [KeyLevelV2_5(
                level_price=getattr(kl, 'price', 0.0),
                level_type=getattr(kl, 'level_type', ''),
                conviction_score=getattr(kl, 'confidence', 0.0),
                contributing_metrics=[],
                source_identifier=None
            ) for kl in getattr(key_level_analysis, 'pivot_points', [])]
            vol_triggers = []
            major_walls = [KeyLevelV2_5(
                level_price=getattr(kl, 'price', 0.0),
                level_type=getattr(kl, 'level_type', ''),
                conviction_score=getattr(kl, 'confidence', 0.0),
                contributing_metrics=[],
                source_identifier=None
            ) for kl in getattr(key_level_analysis, 'gamma_walls', [])]
            
            # Debug the converted levels
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[Key Levels] Converted supports: {len(supports)}")
                logger.debug(f"[Key Levels] Converted resistances: {len(resistances)}")
                logger.debug(f"[Key Levels] Converted pin_zones: {len(pin_zones)}")
                logger.debug(f"[Key Levels] Converted major_walls: {len(major_walls)}")
                
                for i, support in enumerate(supports):
                    logger.debug(f"[Key Levels] Support {i}: {support.level_price}")
                for i, resistance in enumerate(resistances):
                    logger.debug(f"[Key Levels] Resistance {i}: {resistance.level_price}")
            
            key_levels = KeyLevelsDataV2_5(
                supports=supports,
                resistances=resistances,
                pin_zones=pin_zones,
                vol_triggers=vol_triggers,
                major_walls=major_walls,
                timestamp=getattr(key_level_analysis, 'timestamp', datetime.now())
            )
            
            self.logger.info(f"[Key Levels] Final key levels created with timestamp: {key_levels.timestamp}")
            


            # 7. SIGNAL GENERATION: Generate scored signals
            self.logger.info(f"🔄 STEP 7: Generating signals for {symbol}...")

            
            signals = self.signal_generator.generate_all_signals(processed_data_bundle)
            


            # 8. ATIF - NEW IDEAS: Formulate new trade directives
            self.logger.info(f"🔄 STEP 8: Generating trade directives for {symbol}...")

            
            new_directives = self.adaptive_trade_idea_framework.generate_trade_directives(
                processed_data=processed_data_bundle,
                scored_signals=signals,
                key_levels=key_levels
            )
            


            # 9. TPO: Optimize parameters for new ideas
            self.logger.info(f"🔄 STEP 9: Optimizing trade parameters for {symbol}...")

            
            newly_parameterized_recos = [
                self.trade_parameter_optimizer.optimize_parameters_for_directive(d, processed_data_bundle, key_levels)
                for d in new_directives
            ]
            newly_parameterized_recos = [reco for reco in newly_parameterized_recos if reco is not None]
            


            # 10. ATIF - MANAGE ACTIVE: Manage lifecycle of existing recommendations
            self.logger.info(f"🔄 STEP 10: Managing active recommendations for {symbol}...")

            
            current_price = processed_data_bundle.underlying_data_enriched.price or 0.0
            self._manage_active_recommendations(current_price)
            

            
            # 11. STATE UPDATE: Add new recommendations to the active list
            self.logger.info(f"🔄 STEP 11: Updating recommendation state for {symbol}...")
            self.active_recommendations.extend(newly_parameterized_recos)
            
            # 12. BUNDLE FINALIZATION: Assemble the final output
            self.logger.info(f"🔄 STEP 12: Finalizing analysis bundle for {symbol}...")
            
            final_bundle = FinalAnalysisBundleV2_5(
                processed_data_bundle=processed_data_bundle,
                key_levels_data_v2_5=key_levels,
                scored_signals_v2_5=signals,
                active_recommendations_v2_5=self.active_recommendations,
                bundle_timestamp=datetime.now(),
                target_symbol=symbol,
                system_status_messages=[]
            )
            
            self._latest_bundle = final_bundle # Cache the latest bundle
            self.logger.info(f"✅ 12-step analysis pipeline completed for {symbol}")
            self.logger.info(f"---|> Analysis Cycle for '{symbol}' COMPLETE. <|---")
            return final_bundle

        except Exception as e:
            self.logger.critical(f"FATAL ERROR during analysis cycle for '{symbol}': {e}", exc_info=True)
            return None

    def _resolve_dynamic_thresholds(self, symbol: str, ticker_context) -> Dict[str, Any]:
        """Resolves dynamic thresholds based on current market conditions."""
        base_thresholds = {
            'volatility_threshold': 0.25,
            'volume_threshold': 1000,
            'price_movement_threshold': 0.02,
            'gamma_threshold': 0.1,
            'vanna_threshold': 0.05
        }
        
        # Adjust based on ticker context
        if hasattr(ticker_context, 'volatility_profile'):
            vol_regime = ticker_context.volatility_profile.vol_regime
            if vol_regime == 'high':
                base_thresholds['volatility_threshold'] *= 1.5
                base_thresholds['price_movement_threshold'] *= 1.3
            elif vol_regime == 'low':
                base_thresholds['volatility_threshold'] *= 0.7
                base_thresholds['price_movement_threshold'] *= 0.8
        
        if hasattr(ticker_context, 'ticker_profile'):
            liquidity_tier = ticker_context.ticker_profile.liquidity_tier
            if liquidity_tier == 'low':
                base_thresholds['volume_threshold'] *= 0.5
            elif liquidity_tier == 'high':
                base_thresholds['volume_threshold'] *= 2.0
        
        return base_thresholds

    async def fetch_and_fuse_data_async(self, symbol: str, dte_min: int, dte_max: int, price_range_percent: int) -> DataFetchResult:
        """Async: Fetches data from ConvexValue and Tradier, returns structured result."""
        errors = []
        messages = []
        status = 'success'
        bundle = None
        historical_df = None
        try:
            async with aiohttp.ClientSession() as cv_session:
                async with self.tradier_fetcher as tradier_session:
                    # Calculate appropriate historical lookback based on DTE settings
                    # For key levels and technical analysis, we need sufficient history
                    # Use max(dte_max * 2, 5) to ensure adequate data but respect DTE context
                    historical_lookback_days = max(dte_max * 2, 5)
                    
                    cv_task = self.convexvalue_fetcher.fetch_chain_and_underlying(cv_session, symbol, dte_min, dte_max, price_range_percent)
                    tradier_quote_task = tradier_session.fetch_underlying_quote(symbol)
                    tradier_history_task = tradier_session.fetch_historical_data(symbol, days=historical_lookback_days)
                    cv_result, tradier_quote_result, tradier_history_result = await asyncio.gather(cv_task, tradier_quote_task, tradier_history_task, return_exceptions=True)
            # ConvexValue
            cv_failed = False
            if isinstance(cv_result, Exception):
                errors.append(f"ConvexValue fetch failed: {cv_result}")
                cv_failed = True
            elif cv_result is None or not isinstance(cv_result, tuple) or len(cv_result) != 2:
                errors.append(f"ConvexValue returned invalid data format")
                cv_failed = True
            else:
                cv_options, cv_underlying = cv_result
                if not cv_failed and isinstance(cv_result, tuple) and len(cv_result) == 2:
                    if cv_underlying and hasattr(cv_underlying, 'model_dump'):
                        cv_underlying_dict = cv_underlying.model_dump()
                        advanced_metrics = ['call_gxoi', 'put_gxoi', 'dxoi', 'gxoi', 'vxoi', 'txoi', 'deltas_buy', 'deltas_sell', 'gammas_buy', 'gammas_sell']
                        for metric in advanced_metrics:
                            if metric in cv_underlying_dict and cv_underlying_dict[metric] is not None:
                                cv_underlying_dict[metric] = cv_underlying_dict[metric]
                    final_underlying_model = RawUnderlyingDataCombinedV2_5(**cv_underlying_dict)
                    bundle = UnprocessedDataBundleV2_5(
                        options_contracts=(cv_options if not cv_failed and isinstance(cv_options, list) else []),
                        underlying_data=final_underlying_model,
                        fetch_timestamp=datetime.now(),
                        errors=errors
                    )
                else:
                    cv_options = []
            # Tradier
            tradier_failed = False
            if isinstance(tradier_quote_result, Exception):
                errors.append(f"Tradier quote fetch failed: {tradier_quote_result}")
                tradier_failed = True
            elif not tradier_quote_result:
                errors.append(f"Tradier returned no underlying data")
                tradier_failed = True
            # Historical
            if isinstance(tradier_history_result, Exception):
                messages.append(f"Tradier history fetch failed: {tradier_history_result}. Historical data will be missing.")
            elif isinstance(tradier_history_result, dict) and 'data' in tradier_history_result:
                historical_df = pd.DataFrame(tradier_history_result['data'])
                if 'date' in historical_df.columns:
                    historical_df['date'] = pd.to_datetime(historical_df['date'])
                    historical_df.set_index('date', inplace=True)
            # Status logic
            if cv_failed and tradier_failed:
                status = 'failed'
                messages.append('Both ConvexValue and Tradier fetches failed.')
                return DataFetchResult(None, None, status, errors, messages)
            elif cv_failed or tradier_failed:
                status = 'partial'
                messages.append('Partial data: One or more sources failed. Some metrics may be unavailable.')
            # Build bundle if possible
            if not tradier_failed:
                tradier_underlying = tradier_quote_result
                if tradier_underlying is not None and not isinstance(tradier_underlying, (Exception, BaseException)):
                    final_underlying_dict = tradier_underlying.model_dump()
                    if not cv_failed and cv_result:
                        cv_options, cv_underlying = cv_result
                        if cv_underlying and hasattr(cv_underlying, 'model_dump'):
                            cv_underlying_dict = cv_underlying.model_dump()
                            advanced_metrics = ['call_gxoi', 'put_gxoi', 'dxoi', 'gxoi', 'vxoi', 'txoi', 'deltas_buy', 'deltas_sell', 'gammas_buy', 'gammas_sell']
                            for metric in advanced_metrics:
                                if metric in cv_underlying_dict and cv_underlying_dict[metric] is not None:
                                    final_underlying_dict[metric] = cv_underlying_dict[metric]
                    final_underlying_model = RawUnderlyingDataCombinedV2_5(**final_underlying_dict)
                    bundle = UnprocessedDataBundleV2_5(
                        options_contracts=(cv_options if not cv_failed and isinstance(cv_options, list) else []),
                        underlying_data=final_underlying_model,
                        fetch_timestamp=datetime.now(),
                        errors=errors
                    )
            return DataFetchResult(bundle, historical_df, status, errors, messages)
        except Exception as e:
            errors.append(f"Critical error in fetch_and_fuse_data_async: {e}")
            status = 'failed'
            return DataFetchResult(None, None, status, errors, messages)

    def _fetch_and_fuse_data(self, symbol: str, dte_min: int, dte_max: int, price_range_percent: int) -> tuple[Optional[UnprocessedDataBundleV2_5], Optional[pd.DataFrame], str, list, list]:
        """Sync wrapper for async fetch, returns bundle, historical, status, errors, messages."""
        try:
            # CRITICAL FIX: Use get_or_create_event_loop to prevent event loop conflicts
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is already running, create a new task
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self.fetch_and_fuse_data_async(symbol, dte_min, dte_max, price_range_percent))
                        result = future.result(timeout=60)
                else:
                    result = asyncio.run(self.fetch_and_fuse_data_async(symbol, dte_min, dte_max, price_range_percent))
            except RuntimeError:
                # No event loop exists, create one
                result = asyncio.run(self.fetch_and_fuse_data_async(symbol, dte_min, dte_max, price_range_percent))
            
            return result.bundle, result.historical_data, result.status, result.errors, result.messages
        except Exception as e:
            return None, None, 'failed', [f'Exception in sync wrapper: {e}'], []

    def _manage_active_recommendations(self, current_price: float):
        """Manages the lifecycle of active recommendations."""
        if not self.active_recommendations:
            return

        recos_to_keep = []
        for reco in self.active_recommendations:
            # Check for standard SL/TP hits first
            if reco.status.startswith("ACTIVE"):
                management_directive = self.adaptive_trade_idea_framework.get_management_directive(reco, current_price)
                if management_directive and management_directive.action == "EXIT":
                    reco.status = f"EXITED_ATIF_{management_directive.reason}"
                    reco.exit_timestamp = datetime.now()
                    reco.exit_price = current_price # Approximate exit price
                    self.performance_tracker.record_recommendation_outcome(reco)
                    self.logger.info(f"ATIF directed EXIT for {reco.recommendation_id} due to {management_directive.reason}.")
                    continue # Do not add back to active list
                # Logic for other directives (ADJUST_STOPLOSS, etc.) would go here
            
            recos_to_keep.append(reco)
        
        self.active_recommendations = recos_to_keep

    def _calculate_atr(self, symbol: str, dte_max: int = 45):
        lookback_days = max(dte_max, 14)  # Respect DTE but ensure minimum for ATR
        ohlcv_df = self.historical_data_manager.get_historical_ohlcv(symbol, lookback_days=lookback_days)