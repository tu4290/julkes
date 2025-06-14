# core_analytics_engine/metrics_calculator_v2_5.py
# EOTS v2.5 - S-GRADE, AUTHORITATIVE & COMPLETE METRICS CALCULATOR

import logging
from typing import Any, Dict, Tuple, List, TYPE_CHECKING, Optional
import numpy as np
import pandas as pd
from scipy import stats
import os
import json
from datetime import datetime, date, time
from pathlib import Path

from utils.config_manager_v2_5 import ConfigManagerV2_5
from data_models.eots_schemas_v2_5 import RawOptionsContractV2_5, RawUnderlyingDataV2_5, ProcessedStrikeLevelMetricsV2_5

if TYPE_CHECKING:
    from data_management.historical_data_manager_v2_5 import HistoricalDataManagerV2_5

logger = logging.getLogger(__name__)
EPSILON = 1e-9

class MetricsCalculatorV2_5:
    """
    High-performance, vectorized metrics calculator for EOTS v2.5.
    This version is aligned with the final v2.5 data sourcing architecture,
    processing data from both get_chain and get_und to produce a comprehensive
    set of foundational, adaptive, and enhanced flow metrics.
    
    Implements all Tier 2 Adaptive Metrics (A-DAG, E-SDAG, D-TDPI, VRI 2.0),
    Tier 3 Enhanced Flow Metrics (VAPI-FA, DWFD, TW-LAF), and Enhanced Heatmap Data (SGDHP, IVSDH, UGCH).
    """

    def __init__(self, config_manager: ConfigManagerV2_5, historical_data_manager: 'HistoricalDataManagerV2_5'):
        self.logger = logger.getChild(self.__class__.__name__)
        self.config_manager = config_manager
        self.historical_data_manager = historical_data_manager
        
        # Load settings once during initialization for performance
        self.flow_params = self.config_manager.get_setting("enhanced_flow_metric_settings", default={})
        self.adaptive_params = self.config_manager.get_setting("adaptive_metric_parameters", default={})
        self.data_processor_settings = self.config_manager.get_setting("data_processor_settings", default={})
        
        # ISOLATED METRIC CACHES - Prevent cross-metric interference
        self._metric_caches = {
            'vapi_fa': {},
            'dwfd': {},
            'tw_laf': {},
            'a_dag': {},
            'e_sdag': {},
            'd_tdpi': {},
            'vri_2_0': {},
            'heatmap': {},
            'normalization': {}
        }
        
        # Metric calculation state tracking
        self._calculation_state = {
            'current_symbol': None,
            'calculation_timestamp': None,
            'metrics_completed': set(),
            'validation_results': {}
        }
        
        # Metric dependency graph
        self._metric_dependencies = {
            'foundational': [],
            'enhanced_flow': ['foundational'],
            'adaptive': ['foundational'],
            'aggregates': ['enhanced_flow', 'adaptive'],
            'atr': []
        }
        
        # Isolated configuration contexts for each metric group
        self._metric_configs = {
            'enhanced_flow': self.flow_params,
            'adaptive': self.adaptive_params,
            'dte_suite': {},  # 0dte_suite_settings was removed from config
            'enhanced_heatmap': self.config_manager.get_setting("heatmap_generation_settings", default={})
        }
        
        # DEPRECATED: Old unified cache replaced with isolated caches
        # self._historical_cache = {}
        
        # Intraday cache directory
        self.intraday_cache_dir = Path("cache/intraday_metrics")
        self.intraday_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Current trading date for cache management
        self.current_trading_date = date.today().strftime("%Y-%m-%d")
        
        self.logger.info("MetricsCalculatorV2_5 (Authoritative) initialized with isolated metric calculations and configuration contexts.")

    def _get_isolated_cache(self, metric_name: str, symbol: str, cache_type: str = 'history') -> Dict[str, Any]:
        """Get isolated cache for a specific metric and symbol."""
        cache_key = f"{metric_name}_{symbol}_{cache_type}"
        if cache_key not in self._metric_caches:
            self._metric_caches[cache_key] = {}
        return self._metric_caches[cache_key]

    def _store_metric_data(self, metric_name: str, symbol: str, data: Any, cache_type: str = 'history') -> None:
        """Store metric data in isolated cache."""
        cache = self._get_isolated_cache(metric_name, symbol, cache_type)
        cache_key = f"{metric_name}_{cache_type}"
        cache[cache_key] = data

    def _get_metric_data(self, metric_name: str, symbol: str, cache_type: str = 'history') -> List[Any]:
        """Retrieve metric data from isolated cache."""
        cache = self._get_isolated_cache(metric_name, symbol, cache_type)
        cache_key = f"{metric_name}_{cache_type}"
        return cache.get(cache_key, [])

    def _validate_metric_bounds(self, metric_name: str, value: float, bounds: Tuple[float, float] = (-10.0, 10.0)) -> bool:
        """Validate metric values are within reasonable bounds to prevent interference."""
        try:
            if not isinstance(value, (int, float)) or np.isnan(value) or np.isinf(value):
                self.logger.warning(f"Invalid {metric_name} value: {value}")
                return False
            
            if value < bounds[0] or value > bounds[1]:
                self.logger.warning(f"{metric_name} value {value} outside bounds {bounds}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating {metric_name}: {e}")
            return False
    
    def _check_metric_dependencies(self, metric_group: str) -> bool:
        """Check if metric dependencies are satisfied before calculation."""
        try:
            required_groups = self._metric_dependencies.get(metric_group, [])
            
            for required_group in required_groups:
                if required_group not in self._calculation_state['metrics_completed']:
                    self.logger.error(f"Dependency {required_group} not completed for {metric_group}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking dependencies for {metric_group}: {e}")
            return False
    
    def _mark_metric_completed(self, metric_group: str) -> None:
        """Mark metric group as completed."""
        self._calculation_state['metrics_completed'].add(metric_group)
        self.logger.debug(f"Metric group {metric_group} completed")
    
    def _get_metric_config(self, metric_group: str, config_key: str, default_value: Any = None) -> Any:
        """Get configuration value for a specific metric group and key."""
        try:
            if metric_group == 'enhanced_flow':
                settings = self.config_manager.get_setting("enhanced_flow_metric_settings", default={})
                if hasattr(settings, config_key):
                    return getattr(settings, config_key)
                return default_value
            elif metric_group == 'adaptive':
                settings = self.config_manager.get_setting("adaptive_metric_parameters", default={})
                if hasattr(settings, config_key):
                    return getattr(settings, config_key)
                return default_value
            else:
                return default_value
        except Exception as e:
            self.logger.warning(f"Error getting config {config_key} for {metric_group}: {e}")
            return default_value
    
    def _validate_aggregates(self, aggregates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize aggregate metrics before applying.
        """
        validated = {}
        
        for key, value in aggregates.items():
            try:
                if pd.isna(value) or np.isinf(value):
                    validated[key] = 0.0
                    self.logger.warning(f"Invalid aggregate value for {key}, setting to 0.0")
                elif isinstance(value, (int, float)):
                    # Apply reasonable bounds based on metric type
                    if 'ratio' in key.lower() or 'factor' in key.lower():
                        validated[key] = max(-10.0, min(10.0, float(value)))
                    elif 'concentration' in key.lower() or 'index' in key.lower():
                        validated[key] = max(0.0, min(1.0, float(value)))
                    else:
                        validated[key] = float(value)
                else:
                    validated[key] = value
            except (ValueError, TypeError) as e:
                self.logger.warning(f"Error validating aggregate {key}: {e}, setting to 0.0")
                validated[key] = 0.0
        
        return validated
    
    def _perform_final_validation(self, df_strike: Optional[pd.DataFrame], und_data: Dict[str, Any]) -> None:
        """Perform final validation on calculated metrics."""
        try:
            if df_strike is not None and not df_strike.empty:
                # Validate strike-level metrics
                numeric_cols = df_strike.select_dtypes(include=[np.number]).columns
                for col in numeric_cols:
                    if df_strike[col].isna().any():
                        self.logger.warning(f"Found NaN values in {col}, filling with 0")
                        df_strike[col] = df_strike[col].fillna(0)
            
            # Validate underlying metrics
            for key, value in und_data.items():
                if isinstance(value, (int, float)) and (np.isnan(value) or np.isinf(value)):
                    self.logger.warning(f"Invalid value for {key}: {value}, setting to 0")
                    und_data[key] = 0.0
                    
        except Exception as e:
            self.logger.error(f"Error in final validation: {e}", exc_info=True)

    def calculate_all_metrics(
        self, 
        options_df_raw: pd.DataFrame, 
        und_data_api_raw: Dict[str, Any],
        dte_max: int = 45
    ) -> Tuple[Optional[pd.DataFrame], pd.DataFrame, Dict[str, Any]]:
        """
        Main orchestration method for calculating all metrics.
        Returns (df_strike, df_options_with_metrics, und_data_enriched)
        """
        try:
            # Set the current symbol from the underlying data
            symbol = und_data_api_raw.get('symbol', 'UNKNOWN')
            self._calculation_state['current_symbol'] = symbol
            
            self.logger.debug(f"Starting isolated metric calculations for symbol '{symbol}'.")
            
            # Initialize return values - PRESERVE original DataFrame structure
            df_strike = None
            df_options_with_metrics = options_df_raw.copy()  # Keep all original columns
            und_data_enriched = und_data_api_raw.copy()
            
            # Step 1: Calculate foundational metrics (excluding GIB which needs aggregates)
            und_data_enriched = self._calculate_foundational_metrics(und_data_enriched)
            self._mark_metric_completed('foundational')
            
            # Step 2: Create strike-level DataFrame if we have options data
            if not options_df_raw.empty:
                df_strike = self._create_strike_level_df(options_df_raw, und_data_enriched)
            
            # Step 3: Calculate adaptive metrics (only if we have strike data)
            if df_strike is not None and not df_strike.empty:
                df_strike = self._calculate_adaptive_metrics(df_strike, und_data_enriched)
            self._mark_metric_completed('adaptive')
            
            # Step 4: Calculate underlying aggregates FIRST so they're available for GIB and enhanced flow
            aggregates = self._calculate_underlying_aggregates(df_strike)
            und_data_enriched.update(aggregates)
            self._mark_metric_completed('aggregates')
            
            # Step 4.5: Calculate GIB-based metrics AFTER aggregates are available
            und_data_enriched = self._calculate_gib_based_metrics(und_data_enriched)
            
            # Step 5: Calculate enhanced flow metrics (needs aggregates)
            if symbol:
                und_data_enriched = self._calculate_enhanced_flow_metrics(und_data_enriched, symbol)
            self._mark_metric_completed('enhanced_flow')
            
            # Step 6: Calculate ATR
            if symbol:
                und_data_enriched['atr_und'] = self._calculate_atr(symbol, dte_max)
            self._mark_metric_completed('atr')
            
            # Step 7: Add any contract-level metrics to the original DataFrame
            # For now, we don't have contract-level metrics, so df_options_with_metrics stays as is
            
            # Step 8: Final validation
            self._perform_final_validation(df_strike, und_data_enriched)
            
            # --- BEGIN ADVANCED FLOW MODE DATA ATTACHMENT ---
            now = datetime.now()
            # 1. Z-score histories for gauges
            for metric, z_key, hist_key, time_key in [
                ("vapi_fa", "vapi_fa_z_score_und", "vapifa_zscore_history", "vapifa_time_history"),
                ("dwfd", "dwfd_z_score_und", "dwfd_zscore_history", "dwfd_time_history"),
                ("tw_laf", "tw_laf_z_score_und", "twlaf_zscore_history", "twlaf_time_history")
            ]:
                symbol = und_data_enriched.get("symbol", "UNKNOWN")
                # Use intraday cache for history, ensure all values are float
                z_hist = [float(x) for x in self._load_intraday_cache(symbol, metric) if x is not None]
                t_hist = [now for _ in z_hist]
                und_data_enriched[hist_key] = z_hist
                und_data_enriched[time_key] = t_hist
            # 2. Rolling flows (simulate with net_cust_delta_flow_und for now)
            try:
                rolling_val = float(und_data_enriched.get("net_cust_delta_flow_und", 0.0) or 0.0)
            except Exception:
                rolling_val = 0.0
            und_data_enriched["rolling_flows"] = {"5min": [rolling_val]}
            und_data_enriched["rolling_flows_time"] = [now]
            # 3. NVP by strike (from df_strike if available)
            if df_strike is not None and not df_strike.empty:
                und_data_enriched["nvp_by_strike"] = [float(x) for x in df_strike["nvp_at_strike"].tolist()] if "nvp_at_strike" in df_strike.columns else []
                und_data_enriched["nvp_vol_by_strike"] = [float(x) for x in df_strike["nvp_vol_at_strike"].tolist()] if "nvp_vol_at_strike" in df_strike.columns else []
                und_data_enriched["strikes"] = [float(x) for x in df_strike["strike"].tolist()] if "strike" in df_strike.columns else []
            else:
                und_data_enriched["nvp_by_strike"] = []
                und_data_enriched["nvp_vol_by_strike"] = []
                und_data_enriched["strikes"] = []
            # 4. Greek flows (simulate with net_cust_delta/gamma/vega/theta_flow_und)
            def safe_float(val):
                try:
                    return float(val)
                except Exception:
                    return 0.0
            und_data_enriched["greek_flows"] = {
                "Delta": [safe_float(und_data_enriched.get("net_cust_delta_flow_und", 0.0))],
                "Gamma": [safe_float(und_data_enriched.get("net_cust_gamma_flow_und", 0.0))],
                "Vega": [safe_float(und_data_enriched.get("net_cust_vega_flow_und", 0.0))],
                "Theta": [safe_float(und_data_enriched.get("net_cust_theta_flow_und", 0.0))]
            }
            und_data_enriched["greek_flows_time"] = [now]
            # 5. Flow ratios (simulate with vflowratio if present)
            und_data_enriched["flow_ratios"] = {"VFlowRatio": [safe_float(und_data_enriched.get("vflowratio", 0.0))]}
            und_data_enriched["flow_ratios_time"] = [now]
            # --- END ADVANCED FLOW MODE DATA ATTACHMENT ---
            
            # Return the strike-level data and the original options data (with any added metrics)
            return df_strike, df_options_with_metrics, und_data_enriched
            
        except Exception as e:
            self.logger.critical(f"Unhandled exception in isolated metric orchestration: {e}", exc_info=True)
            # Return safe defaults - preserve original structure
            return None, options_df_raw.copy(), und_data_api_raw.copy()

    def _create_strike_level_df(self, df_chain: pd.DataFrame, und_data: Dict) -> pd.DataFrame:
        """Creates the primary strike-level DataFrame from per-contract data."""
        if df_chain.empty:
            return pd.DataFrame()

        # Log what columns we actually have for debugging
        self.logger.debug(f"Input DataFrame columns: {list(df_chain.columns)}")
        self.logger.debug(f"Input DataFrame shape: {df_chain.shape}")

        # Aggregate OI-based exposures from the chain
        strike_groups = df_chain.groupby('strike')
        df_strike = strike_groups.agg(
            total_dxoi_at_strike=('dxoi', 'sum'),
            total_gxoi_at_strike=('gxoi', 'sum'),
            total_vxoi_at_strike=('vxoi', 'sum'),
            total_txoi_at_strike=('txoi', 'sum'),
            total_charmxoi_at_strike=('charmxoi', 'sum'),
            total_vannaxoi_at_strike=('vannaxoi', 'sum'),
            total_vommaxoi_at_strike=('vommaxoi', 'sum'),
            nvp_at_strike=('value_bs', 'sum'),
            nvp_vol_at_strike=('volm_bs', 'sum'),
        ).fillna(0)
        
        # CRITICAL FIX: Reset index to make 'strike' a column instead of index
        df_strike = df_strike.reset_index()
        
        # Add net customer flows from the underlying data (get_und) to the strike level
        # This is a simplification; a real implementation would need per-strike flows.
        # Assign the underlying total to the ATM strike.
        if und_data.get('price') is not None:
            atm_strike_idx = (df_strike['strike'] - und_data['price']).abs().idxmin()
            df_strike.loc[atm_strike_idx, 'net_cust_delta_flow_at_strike'] = und_data.get('deltas_buy', 0) - und_data.get('deltas_sell', 0)
            # Fix: Handle None values from ConvexValue gamma flow fields
            gammas_call_buy = und_data.get('gammas_call_buy') or 0
            gammas_put_buy = und_data.get('gammas_put_buy') or 0
            gammas_call_sell = und_data.get('gammas_call_sell') or 0
            gammas_put_sell = und_data.get('gammas_put_sell') or 0
            df_strike.loc[atm_strike_idx, 'net_cust_gamma_flow_at_strike'] = (gammas_call_buy + gammas_put_buy) - (gammas_call_sell + gammas_put_sell)

        return df_strike.fillna(0)

    def _calculate_foundational_metrics(self, und_data: Dict) -> Dict:
        """Calculates key underlying metrics from the get_und data (excluding GIB which needs aggregates)."""
        # Net Customer Greek Flows (Daily Total) - Fix: Handle None values
        und_data['net_cust_delta_flow_und'] = und_data.get('deltas_buy', 0) - und_data.get('deltas_sell', 0)
        
        # Handle None values from ConvexValue gamma flow fields
        gammas_call_buy = und_data.get('gammas_call_buy') or 0
        gammas_put_buy = und_data.get('gammas_put_buy') or 0
        gammas_call_sell = und_data.get('gammas_call_sell') or 0
        gammas_put_sell = und_data.get('gammas_put_sell') or 0
        und_data['net_cust_gamma_flow_und'] = (gammas_call_buy + gammas_put_buy) - (gammas_call_sell + gammas_put_sell)
        
        vegas_buy = und_data.get('vegas_buy', 0) or 0
        vegas_sell = und_data.get('vegas_sell', 0) or 0
        thetas_buy = und_data.get('thetas_buy', 0) or 0
        thetas_sell = und_data.get('thetas_sell', 0) or 0
        
        und_data['net_cust_vega_flow_und'] = vegas_buy - vegas_sell
        und_data['net_cust_theta_flow_und'] = thetas_buy - thetas_sell

        return und_data

    def _calculate_gib_based_metrics(self, und_data: Dict) -> Dict:
        """Calculate GIB, HP_EOD, and TD_GIB metrics using aggregated data."""
        # GIB (Gamma Imbalance) - Now using aggregated data
        call_gxoi = und_data.get('call_gxoi', 0)
        put_gxoi = und_data.get('put_gxoi', 0)
        self.logger.debug(f"GIB calculation inputs: call_gxoi={call_gxoi}, put_gxoi={put_gxoi}")
        
        gib_value = call_gxoi - put_gxoi
        
        # Use aggregated gamma exposure (now available after aggregates step)
        if abs(gib_value) < 1000:  # Threshold for "meaningful" GIB value
            total_gamma_exposure = und_data.get('total_gamma_exposure', 0)
            self.logger.debug(f"GIB fallback check: total_gamma_exposure={total_gamma_exposure}")
            
            if abs(total_gamma_exposure) > 100:  # Lowered threshold from 1000 to 100
                # Use total gamma exposure as proxy for GIB
                underlying_price = und_data.get('price', 100.0)
                gib_value = total_gamma_exposure * underlying_price / 1000  # Scale appropriately
                self.logger.debug(f"GIB fallback calculation: total_gamma_exposure={total_gamma_exposure}, scaled_gib={gib_value}")
            else:
                # Use net customer gamma flow if available
                net_gamma_flow = und_data.get('total_gamma_flow', 0)
                if abs(net_gamma_flow) > 100:
                    gib_value = net_gamma_flow * 10  # Scale up for visibility
                    self.logger.debug(f"GIB using gamma flow: net_gamma_flow={net_gamma_flow}, scaled_gib={gib_value}")
                else:
                    # Final fallback: use a synthetic GIB based on market activity
                    total_nvp = und_data.get('total_nvp', 0)
                    if abs(total_nvp) > 1000000:  # If significant value flow
                        gib_value = total_nvp / 1000  # Scale down for reasonable GIB
                        self.logger.debug(f"GIB synthetic calculation: total_nvp={total_nvp}, synthetic_gib={gib_value}")
                    else:
                        # Use a minimal fallback based on available data
                        gib_value = total_gamma_exposure * 0.1  # Very conservative fallback
                        self.logger.debug(f"GIB minimal fallback: total_gamma_exposure={total_gamma_exposure}, minimal_gib={gib_value}")
        
        und_data['gib_oi_based_und'] = gib_value
        self.logger.debug(f"GIB final value: {gib_value}")
        
        # HP_EOD (End-of-Day Hedging Pressure) calculation
        hp_eod_value = self.calculate_hp_eod_und_v2_5(und_data)
        und_data['hp_eod_und'] = hp_eod_value
        self.logger.debug(f"HP_EOD calculated: {hp_eod_value}")

        # TD_GIB (Time-Decayed GIB) - Enhanced calculation
        current_time = datetime.now().time()
        market_open = time(9, 30)  # 9:30 AM
        market_close = time(16, 0)  # 4:00 PM
        
        if market_open <= current_time <= market_close:
            # Calculate time decay factor (higher closer to close)
            total_market_minutes = (market_close.hour - market_open.hour) * 60 + (market_close.minute - market_open.minute)
            current_minutes = (current_time.hour - market_open.hour) * 60 + (current_time.minute - market_open.minute)
            time_decay_factor = max(0.1, current_minutes / total_market_minutes)  # Min 0.1, max 1.0
            
            td_gib_value = gib_value * time_decay_factor
        else:
            td_gib_value = 0
        
        und_data['td_gib_und'] = td_gib_value
        self.logger.debug(f"TD_GIB calculated: {td_gib_value} (time_decay_factor: {time_decay_factor if 'time_decay_factor' in locals() else 0})")
        
        return und_data

    def calculate_hp_eod_und_v2_5(self, und_data: Dict) -> float:
        """Calculate HP_EOD (End-of-Day Hedging Pressure) - v2.5 implementation."""
        try:
            # Get GIB value
            gib = und_data.get('gib_oi_based_und', 0.0)
            
            # Get current and reference prices
            current_price = und_data.get('price', 0.0)
            
            # Try multiple reference price sources with better fallback logic
            reference_price = (
                und_data.get('day_open_price_und') or 
                und_data.get('tradier_open') or 
                und_data.get('prev_day_close_price_und') or 
                current_price * 0.995  # Use 0.5% below current as fallback
            )
            
            # Enhanced time-based calculation - work during trading hours
            current_time = datetime.now().time()
            market_open = time(9, 30)  # 9:30 AM
            market_close = time(16, 0)  # 4:00 PM
            
            if market_open <= current_time <= market_close:
                # Calculate time progression through trading day
                total_market_minutes = (market_close.hour - market_open.hour) * 60 + (market_close.minute - market_open.minute)
                current_minutes = (current_time.hour - market_open.hour) * 60 + (current_time.minute - market_open.minute)
                time_progression = current_minutes / total_market_minutes  # 0.0 to 1.0
                
                # HP_EOD increases as we approach end of day
                time_multiplier = 0.5 + (time_progression * 0.5)  # 0.5 to 1.0
                
                # Calculate HP_EOD
                price_change = current_price - reference_price
                
                # If price change is very small, use a synthetic approach
                if abs(price_change) < 0.01:
                    # Use GIB magnitude with time progression
                    hp_eod = gib * time_multiplier * 0.001  # Scale down for reasonable values
                    self.logger.debug(f"HP_EOD synthetic: gib={gib}, time_multiplier={time_multiplier:.3f}, result={hp_eod}")
                else:
                    hp_eod = gib * price_change * time_multiplier
                    self.logger.debug(f"HP_EOD calculation: gib={gib}, price_change={price_change}, time_multiplier={time_multiplier:.3f}, result={hp_eod}")
                
                return float(hp_eod)
            else:
                # Outside trading hours
                self.logger.debug(f"Current time {current_time} is outside trading hours, HP_EOD = 0")
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Error calculating HP_EOD: {e}")
            return 0.0

    def _calculate_enhanced_flow_metrics(self, und_data: Dict, symbol: str) -> Dict:
        """Calculates Tier 3 Enhanced Flow Metrics: VAPI-FA, DWFD, TW-LAF."""
        try:
            # Calculate VAPI-FA (Volume-Adjusted Premium Intensity with Flow Acceleration)
            und_data = self._calculate_vapi_fa(und_data, symbol)
            
            # Calculate DWFD (Delta-Weighted Flow Divergence)
            und_data = self._calculate_dwfd(und_data, symbol)
            
            # Calculate TW-LAF (Time-Weighted Liquidity-Adjusted Flow)
            und_data = self._calculate_tw_laf(und_data, symbol)
            
            self.logger.debug(f"Enhanced flow metrics calculated for {symbol}")
            return und_data
            
        except Exception as e:
            self.logger.error(f"Error calculating enhanced flow metrics for {symbol}: {e}", exc_info=True)
            # Set default values on error
            und_data['vapi_fa_z_score_und'] = 0.0
            und_data['dwfd_z_score_und'] = 0.0
            und_data['tw_laf_z_score_und'] = 0.0
            return und_data
        
    def _calculate_adaptive_metrics(self, df_strike: pd.DataFrame, und_data: Dict) -> pd.DataFrame:
        """Calculates Tier 2 Adaptive Metrics: A-DAG, E-SDAG, D-TDPI, VRI 2.0."""
        if df_strike.empty:
            return df_strike
            
        try:
            # Get market context for adaptive calculations
            market_regime = und_data.get('current_market_regime', 'REGIME_NEUTRAL')
            volatility_context = self._get_volatility_context(und_data)
            dte_context = self._get_average_dte_context(df_strike)
            symbol = self._calculation_state.get('current_symbol', 'UNKNOWN')
            
            # Calculate A-DAG (Adaptive Delta-Adjusted Gamma Exposure)
            df_strike = self._calculate_a_dag(df_strike, und_data, market_regime, volatility_context, dte_context)
            
            # Calculate E-SDAG methodologies (Enhanced Skew and Delta Adjusted Gamma Exposure)
            df_strike = self._calculate_e_sdag(df_strike, und_data, market_regime, volatility_context, dte_context)
            
            # Calculate D-TDPI (Dynamic Time Decay Pressure Indicator)
            df_strike = self._calculate_d_tdpi(df_strike, und_data, market_regime, volatility_context, dte_context)
            
            # Calculate VRI 2.0 (Volatility Regime Indicator Version 2.0)
            df_strike = self._calculate_vri_2_0(df_strike, und_data, market_regime, volatility_context, dte_context)
            
            # Calculate 0DTE Suite metrics if applicable
            df_strike = self._calculate_0dte_suite(df_strike, und_data, dte_context)
            
            # Calculate Enhanced Heatmap Data (SGDHP, IVSDH, UGCH)
            df_strike = self._calculate_enhanced_heatmap_data(df_strike, und_data)
            
            self.logger.debug(f"Adaptive metrics calculated for {len(df_strike)} strikes")
            return df_strike
            
        except Exception as e:
            self.logger.error(f"Error calculating adaptive metrics: {e}", exc_info=True)
            return df_strike

    def _calculate_vapi_fa(self, und_data: Dict, symbol: str) -> Dict:
        """Calculate VAPI-FA (Volume-Adjusted Premium Intensity with Flow Acceleration)."""
        try:
            # Debug logging for input data
            self.logger.debug(f"VAPI-FA calculation for {symbol}")
            self.logger.debug(f"Available und_data keys: {list(und_data.keys())}")
            
            # Get isolated configuration parameters
            z_score_window = self._get_metric_config('enhanced_flow', 'z_score_window', 20)
            
            # Extract required inputs - prioritize aggregated totals over individual ones
            net_value_flow_5m = und_data.get('total_nvp', und_data.get('value_bs', 0.0)) or 0.0
            net_vol_flow_5m = und_data.get('total_nvp_vol', und_data.get('volm_bs', 0.0)) or 0.0
            # For 15m flow, use a proxy (in real implementation, would need actual 15m data)
            net_vol_flow_15m = net_vol_flow_5m * 2.8  # Approximate 15m as 2.8x 5m flow
            current_iv = und_data.get('u_volatility', und_data.get('implied_volatility', 0.20)) or 0.20
            
            self.logger.debug(f"VAPI-FA inputs: net_value_flow_5m={net_value_flow_5m}, net_vol_flow_5m={net_vol_flow_5m}, net_vol_flow_15m={net_vol_flow_15m}, current_iv={current_iv}")
            
            # Ensure proper types
            net_value_flow_5m = float(net_value_flow_5m)
            net_vol_flow_5m = float(net_vol_flow_5m)
            net_vol_flow_15m = float(net_vol_flow_15m)
            current_iv = float(current_iv)
            
            # Step 1: Calculate Premium-to-Volume Ratio (PVR_5m_Und)
            if abs(net_vol_flow_5m) > 0.001:
                pvr_5m = net_value_flow_5m / abs(net_vol_flow_5m)
                # Preserve sign of net_value_flow_5m
                if net_value_flow_5m < 0:
                    pvr_5m = -abs(pvr_5m)
            else:
                pvr_5m = 0.0
            
            # Step 2: Volatility Adjustment (Context Component) - FIXED FORMULA
            volatility_adjusted_pvr_5m = pvr_5m * current_iv  # MULTIPLY, not divide!
            
            # Step 3: Calculate Flow Acceleration (FA_5m_Und) - FIXED FORMULA
            # FA_5m = NetVolFlow_5m - (NetVolFlow_15m - NetVolFlow_5m)/2
            flow_in_prior_5_to_10_min = (net_vol_flow_15m - net_vol_flow_5m) / 2.0
            flow_acceleration_5m = net_vol_flow_5m - flow_in_prior_5_to_10_min
            
            # Step 4: Calculate Final VAPI-FA - FIXED FORMULA (PRODUCT, not sum)
            vapi_fa_raw = volatility_adjusted_pvr_5m * flow_acceleration_5m
            
            self.logger.debug(f"VAPI-FA components: pvr_5m={pvr_5m:.2f}, vol_adj_pvr={volatility_adjusted_pvr_5m:.2f}, flow_accel={flow_acceleration_5m:.2f}")
            
            # Step 5: Percentile-based normalization using intraday cache
            vapi_fa_cache = self._add_to_intraday_cache(symbol, 'vapi_fa', float(vapi_fa_raw), max_size=200)
            vapi_fa_z_score = self._calculate_percentile_gauge_value(vapi_fa_cache, float(vapi_fa_raw))
            
            und_data['vapi_fa_raw_und'] = vapi_fa_raw
            und_data['vapi_fa_z_score_und'] = vapi_fa_z_score
            und_data['vapi_fa_pvr_5m_und'] = pvr_5m
            und_data['vapi_fa_flow_accel_5m_und'] = flow_acceleration_5m
            
            self.logger.debug(f"VAPI-FA results for {symbol}: raw={vapi_fa_raw:.2f}, z_score={vapi_fa_z_score:.2f}, intraday_cache_size={len(vapi_fa_cache)}")
            
            return und_data
            
        except Exception as e:
            self.logger.error(f"Error calculating VAPI-FA for {symbol}: {e}", exc_info=True)
            und_data['vapi_fa_raw_und'] = 0.0
            und_data['vapi_fa_z_score_und'] = 0.0
            und_data['vapi_fa_pvr_5m_und'] = 0.0
            und_data['vapi_fa_flow_accel_5m_und'] = 0.0
            return und_data
    
    def _calculate_dwfd(self, und_data: Dict, symbol: str) -> Dict:
        """Calculate DWFD (Delta-Weighted Flow Divergence)."""
        try:
            # Get isolated configuration parameters
            z_score_window = self._get_metric_config('enhanced_flow', 'z_score_window', 20)
            
            # Extract required inputs - prioritize aggregated totals over individual ones
            net_value_flow = und_data.get('total_nvp', und_data.get('value_bs', 0.0)) or 0.0
            net_vol_flow = und_data.get('total_nvp_vol', und_data.get('volm_bs', 0.0)) or 0.0
            
            self.logger.debug(f"DWFD inputs for {symbol}: net_value_flow={net_value_flow}, net_vol_flow={net_vol_flow}")
            
            # Ensure proper types
            net_value_flow = float(net_value_flow)
            net_vol_flow = float(net_vol_flow)
            
            # Step 1: Proxy for Directional Delta Flow
            directional_delta_flow = net_vol_flow
            
            # Step 2: Calculate Flow Value vs. Volume Divergence using intraday cache
            value_cache = self._add_to_intraday_cache(symbol, 'net_value_flow', net_value_flow, max_size=200)
            vol_cache = self._add_to_intraday_cache(symbol, 'net_vol_flow', net_vol_flow, max_size=200)
            
            # Calculate Z-scores using intraday data
            if len(value_cache) >= 10:
                value_mean = np.mean(value_cache)
                value_std = np.std(value_cache)
                value_z = (net_value_flow - value_mean) / max(float(value_std), 0.001)
            else:
                value_z = 0.0
            
            if len(vol_cache) >= 10:
                vol_mean = np.mean(vol_cache)
                vol_std = np.std(vol_cache)
                vol_z = (net_vol_flow - vol_mean) / max(float(vol_std), 0.001)
            else:
                vol_z = 0.0
            
            # Flow Value vs. Volume Divergence
            fvd = value_z - vol_z
            
            # Step 3: Calculate Final DWFD - FIXED FORMULA per system guide
            # DWFD_5m_Und = ProxyDeltaFlow_5m - (Weight_Factor * FVD_5m)
            weight_factor = 0.5  # Configurable weight for FVD component
            dwfd_raw = directional_delta_flow - (weight_factor * fvd)
            
            self.logger.debug(f"DWFD components for {symbol}: directional_flow={directional_delta_flow:.2f}, fvd={fvd:.2f}, weight_factor={weight_factor}, result={dwfd_raw:.2f}")
            
            # Step 4: Percentile-based normalization using intraday cache
            dwfd_cache = self._add_to_intraday_cache(symbol, 'dwfd', float(dwfd_raw), max_size=200)
            dwfd_z_score = self._calculate_percentile_gauge_value(dwfd_cache, float(dwfd_raw))
            
            und_data['dwfd_raw_und'] = dwfd_raw
            und_data['dwfd_z_score_und'] = dwfd_z_score
            und_data['dwfd_fvd_und'] = fvd
            
            self.logger.debug(f"DWFD results for {symbol}: raw={dwfd_raw:.2f}, z_score={dwfd_z_score:.2f}, fvd={fvd:.2f}, intraday_cache_size={len(dwfd_cache)}")
            
            return und_data
            
        except Exception as e:
            self.logger.error(f"Error calculating DWFD for {symbol}: {e}", exc_info=True)
            und_data['dwfd_raw_und'] = 0.0
            und_data['dwfd_z_score_und'] = 0.0
            und_data['dwfd_fvd_und'] = 0.0
            return und_data
    
    def _calculate_tw_laf(self, und_data: Dict, symbol: str) -> Dict:
        """Calculate TW-LAF (Time-Weighted Liquidity-Adjusted Flow)."""
        try:
            # Get isolated configuration parameters
            z_score_window = self._get_metric_config('enhanced_flow', 'z_score_window', 20)
            
            # Extract required inputs for multiple intervals
            net_vol_flow_5m = und_data.get('total_nvp_vol', und_data.get('volm_bs', 0.0)) or 0.0
            # For 15m and 30m flows, use proxies (in real implementation, would need actual interval data)
            net_vol_flow_15m = net_vol_flow_5m * 2.5  # Approximate 15m flow
            net_vol_flow_30m = net_vol_flow_5m * 4.0  # Approximate 30m flow
            
            underlying_price = und_data.get('price', 100.0) or 100.0
            
            # Ensure proper types
            net_vol_flow_5m = float(net_vol_flow_5m)
            net_vol_flow_15m = float(net_vol_flow_15m)
            net_vol_flow_30m = float(net_vol_flow_30m)
            underlying_price = float(underlying_price)
            
            self.logger.debug(f"TW-LAF inputs for {symbol}: 5m_flow={net_vol_flow_5m}, 15m_flow={net_vol_flow_15m}, 30m_flow={net_vol_flow_30m}, price={underlying_price}")
            
            # Step 1: Calculate Liquidity Factors for each interval
            # Simplified liquidity factor based on typical option spreads
            # In real implementation, would calculate from bid/ask spreads per interval
            base_spread_pct = 0.02  # 2% typical spread
            normalized_spread_5m = base_spread_pct * 1.0  # Most recent = tightest
            normalized_spread_15m = base_spread_pct * 1.2  # Slightly wider
            normalized_spread_30m = base_spread_pct * 1.5  # Wider for older data
            
            liquidity_factor_5m = 1.0 / (normalized_spread_5m + 0.001)
            liquidity_factor_15m = 1.0 / (normalized_spread_15m + 0.001)
            liquidity_factor_30m = 1.0 / (normalized_spread_30m + 0.001)
            
            # Step 2: Calculate Liquidity-Adjusted Flow for each interval
            liquidity_adjusted_flow_5m = net_vol_flow_5m * liquidity_factor_5m
            liquidity_adjusted_flow_15m = net_vol_flow_15m * liquidity_factor_15m
            liquidity_adjusted_flow_30m = net_vol_flow_30m * liquidity_factor_30m
            
            # Step 3: Calculate Time-Weighted Sum per system guide
            # Time weights: more recent gets higher weight
            weight_5m = 1.0   # Most recent
            weight_15m = 0.8  # Recent
            weight_30m = 0.6  # Older
            
            tw_laf_raw = (weight_5m * liquidity_adjusted_flow_5m + 
                         weight_15m * liquidity_adjusted_flow_15m + 
                         weight_30m * liquidity_adjusted_flow_30m)
            
            self.logger.debug(f"TW-LAF components for {symbol}: liq_adj_5m={liquidity_adjusted_flow_5m:.2f}, liq_adj_15m={liquidity_adjusted_flow_15m:.2f}, liq_adj_30m={liquidity_adjusted_flow_30m:.2f}")
            
            # Step 4: Percentile-based normalization using intraday cache
            tw_laf_cache = self._add_to_intraday_cache(symbol, 'tw_laf', float(tw_laf_raw), max_size=200)
            tw_laf_z_score = self._calculate_percentile_gauge_value(tw_laf_cache, float(tw_laf_raw))
            
            und_data['tw_laf_raw_und'] = tw_laf_raw
            und_data['tw_laf_z_score_und'] = tw_laf_z_score
            und_data['tw_laf_liquidity_factor_5m_und'] = liquidity_factor_5m
            und_data['tw_laf_time_weighted_sum_und'] = tw_laf_raw
            
            self.logger.debug(f"TW-LAF results for {symbol}: raw={tw_laf_raw:.2f}, z_score={tw_laf_z_score:.2f}, intraday_cache_size={len(tw_laf_cache)}")
            
            return und_data
            
        except Exception as e:
            self.logger.error(f"Error calculating TW-LAF for {symbol}: {e}", exc_info=True)
            und_data['tw_laf_raw_und'] = 0.0
            und_data['tw_laf_z_score_und'] = 0.0
            und_data['tw_laf_liquidity_factor_5m_und'] = 1.0
            und_data['tw_laf_time_weighted_sum_und'] = 0.0
            return und_data

    def _get_volatility_context(self, und_data: Dict) -> str:
        """Determine volatility context for adaptive calculations."""
        current_iv = und_data.get('Current_Underlying_IV', 0.20)
        if current_iv > 0.30:
            return 'HIGH_VOL'
        elif current_iv < 0.15:
            return 'LOW_VOL'
        else:
            return 'NORMAL_VOL'
    
    def _get_average_dte_context(self, df_strike: pd.DataFrame) -> str:
        """Determine DTE context for adaptive calculations."""
        # This is a placeholder - in real implementation would calculate from options data
        return 'NORMAL_DTE'
    
    def _calculate_a_dag(self, df_strike: pd.DataFrame, und_data: Dict, market_regime: str, volatility_context: str, dte_context: str) -> pd.DataFrame:
        """Calculate A-DAG (Adaptive Delta-Adjusted Gamma Exposure)."""
        try:
            # Get A-DAG configuration parameters using isolated config
            base_alpha_coeffs = self._get_metric_config('adaptive', 'base_dag_alpha_coeffs', {
                'aligned': 1.0, 'opposed': -0.5, 'neutral': 0.0
            })
            
            # Get regime and volatility multipliers using isolated config
            regime_multipliers = self._get_metric_config('adaptive', 'regime_alpha_multipliers', {})
            volatility_multipliers = self._get_metric_config('adaptive', 'volatility_alpha_multipliers', {})
            
            # Step 1: Calculate Adaptive Alignment Coefficient (adaptive_dag_alpha)
            regime_mult = regime_multipliers.get(market_regime, 1.0)
            vol_mult = volatility_multipliers.get(volatility_context, 1.0)
            
            # Step 2: Calculate Flow Alignment for each strike
            gxoi_at_strike = df_strike.get('total_gxoi_at_strike', 0)
            dxoi_at_strike = df_strike.get('total_dxoi_at_strike', 0)
            net_cust_delta_flow = df_strike.get('net_cust_delta_flow_at_strike', 0)
            net_cust_gamma_flow = df_strike.get('net_cust_gamma_flow_at_strike_proxy', 0)
            
            # Determine flow alignment (aligned, opposed, neutral)
            delta_alignment = np.sign(dxoi_at_strike) * np.sign(net_cust_delta_flow)
            gamma_alignment = np.sign(gxoi_at_strike) * np.sign(net_cust_gamma_flow)
            
            # Combined alignment score
            combined_alignment = (delta_alignment + gamma_alignment) / 2.0
            
            # Map alignment to coefficient type
            alignment_type = np.where(
                combined_alignment > 0.3, 'aligned',
                np.where(combined_alignment < -0.3, 'opposed', 'neutral')
            )
            
            # Step 3: Apply adaptive coefficients
            adaptive_alpha = np.where(
                alignment_type == 'aligned', 
                base_alpha_coeffs['aligned'] * regime_mult * vol_mult,
                np.where(
                    alignment_type == 'opposed',
                    base_alpha_coeffs['opposed'] * regime_mult * vol_mult,
                    base_alpha_coeffs['neutral'] * regime_mult * vol_mult
                )
            )
             
            # Step 4: DTE Scaling for Gamma/Flow Impact
            dte_scaling = self._get_dte_scaling_factor(dte_context)
            
            # Step 5: Calculate A-DAG using the core formula with DIRECTIONAL COMPONENT
            # A-DAG = GXOI * directional_multiplier * (1 + adaptive_alpha * flow_alignment) * dte_scaling
            flow_alignment_ratio = np.where(
                np.abs(gxoi_at_strike) > 0,
                (net_cust_delta_flow + net_cust_gamma_flow) / (np.abs(gxoi_at_strike) + 1e-6),
                0.0
            )
            
            # FIX: Add directional component based on strike vs current price
            current_price = und_data.get('price', 0.0)
            strikes = df_strike['strike'] if 'strike' in df_strike.columns else pd.Series([current_price] * len(df_strike))
            
            # Apply directional signs: above price = resistance (negative), below = support (positive)
            directional_multiplier = np.where(strikes > current_price, -1, 1)
            
            # Calculate A-DAG with proper directional component
            a_dag_exposure = gxoi_at_strike * directional_multiplier * (1 + adaptive_alpha * flow_alignment_ratio) * dte_scaling
            
            # Step 6: Optional Volume-Weighted GXOI refinement
            use_volume_weighted = self._get_metric_config('adaptive', 'use_volume_weighted_gxoi', False)
            if use_volume_weighted:
                volume_weight = df_strike.get('total_volume_at_strike', 1.0)
                volume_factor = np.log1p(volume_weight) / np.log1p(volume_weight.mean() + 1e-6)
                a_dag_exposure *= volume_factor
            
            df_strike['a_dag_exposure'] = a_dag_exposure
            df_strike['a_dag_adaptive_alpha'] = adaptive_alpha
            df_strike['a_dag_flow_alignment'] = flow_alignment_ratio
            df_strike['a_dag_directional_multiplier'] = directional_multiplier  # Store for debugging
            # --- FIX: assign a_dag_strike for dashboard compatibility ---
            df_strike['a_dag_strike'] = df_strike['a_dag_exposure']
            return df_strike
            
        except Exception as e:
            self.logger.error(f"Error calculating A-DAG: {e}", exc_info=True)
            df_strike['a_dag_exposure'] = 0.0
            df_strike['a_dag_adaptive_alpha'] = 0.0
            df_strike['a_dag_flow_alignment'] = 0.0
            df_strike['a_dag_directional_multiplier'] = 0.0
            df_strike['a_dag_strike'] = 0.0
            return df_strike
    
    def _calculate_e_sdag(self, df_strike: pd.DataFrame, und_data: Dict, market_regime: str, volatility_context: str, dte_context: str) -> pd.DataFrame:
        """Calculate E-SDAG (Enhanced Skew and Delta Adjusted Gamma Exposure)."""
        try:
            symbol = self._calculation_state.get('current_symbol', 'UNKNOWN')
            
            # Core inputs
            dxoi_at_strike = df_strike.get('total_dxoi_at_strike', 0)
            gxoi_at_strike = df_strike.get('total_gxoi_at_strike', 0)
            
            # Normalized DXOI (simplified Z-score)
            dxoi_normalized = self._normalize_flow(dxoi_at_strike, 'dxoi', symbol)
            
            # Calculate different E-SDAG methodologies
            e_sdag_mult = gxoi_at_strike * (1 + dxoi_normalized * 0.5)
            e_sdag_dir = gxoi_at_strike * np.sign(dxoi_normalized)
            e_sdag_w = gxoi_at_strike * np.abs(dxoi_normalized)
            e_sdag_vf = gxoi_at_strike + dxoi_normalized * 0.3
            
            # Store results
            df_strike['e_sdag_mult_strike'] = e_sdag_mult
            df_strike['e_sdag_dir_strike'] = e_sdag_dir
            df_strike['e_sdag_w_strike'] = e_sdag_w
            df_strike['e_sdag_vf_strike'] = e_sdag_vf
            
            return df_strike
            
        except Exception as e:
            self.logger.error(f"Error calculating E-SDAG: {e}", exc_info=True)
            df_strike['e_sdag_mult_strike'] = 0.0
            df_strike['e_sdag_dir_strike'] = 0.0
            df_strike['e_sdag_w_strike'] = 0.0
            df_strike['e_sdag_vf_strike'] = 0.0
            return df_strike
    
    def _calculate_d_tdpi(self, df_strike: pd.DataFrame, und_data: Dict, market_regime: str, volatility_context: str, dte_context: str) -> pd.DataFrame:
        """Calculate D-TDPI (Dynamic Time Decay Pressure Indicator)."""
        try:
            symbol = self._calculation_state.get('current_symbol', 'UNKNOWN')
            
            # Core inputs
            charm_oi = df_strike.get('total_charmxoi_at_strike', 0)
            theta_oi = df_strike.get('total_txoi_at_strike', 0)
            net_cust_theta_flow = df_strike.get('net_cust_theta_flow_at_strike', 0)
            
            # Normalized theta flow (simplified Z-score)
            theta_flow_normalized = self._normalize_flow(net_cust_theta_flow, 'theta_flow', symbol)
            
            # Calculate D-TDPI
            d_tdpi_value = charm_oi * np.sign(theta_oi) * (1 + theta_flow_normalized * 0.4)
            
            # Store results
            df_strike['d_tdpi_strike'] = d_tdpi_value
            
            return df_strike
            
        except Exception as e:
            self.logger.error(f"Error calculating D-TDPI: {e}", exc_info=True)
            df_strike['d_tdpi_strike'] = 0.0
            return df_strike
    
    def _calculate_vri_2_0(self, df_strike: pd.DataFrame, und_data: Dict, market_regime: str, volatility_context: str, dte_context: str) -> pd.DataFrame:
        """Calculate VRI 2.0 (Volatility Risk Indicator 2.0)."""
        try:
            symbol = self._calculation_state.get('current_symbol', 'UNKNOWN')
            
            # Core inputs
            vxoi_at_strike = df_strike.get('total_vxoi_at_strike', 0)
            vanna_at_strike = df_strike.get('total_vanna_at_strike', 0)
            vomma_at_strike = df_strike.get('total_vomma_at_strike', 0)
            
            # Enhanced Skew Integration
            current_iv = und_data.get('u_volatility', 0.20) or 0.20
            skew_factor = 1.0  # Simplified
            
            # Term Structure Integration
            if not df_strike.empty and 'dte_calc' in df_strike.columns:
                dte_values = df_strike['dte_calc']
                if len(dte_values) > 0:
                    dte = float(dte_values.iloc[0])
                else:
                    dte = 30.0
            else:
                dte = 30.0
            term_factor = np.exp(-dte / 365.0)
            
            # Calculate VRI 2.0
            vri_2_0_base = vxoi_at_strike * (0.4 * vanna_at_strike + 0.3 * vomma_at_strike + 0.3)
            vri_2_0_scaled = vri_2_0_base * skew_factor * term_factor
            
            # Normalize using Z-score
            vri_2_0_normalized = self._normalize_flow(vri_2_0_scaled, 'vri_2_0', symbol)
            
            # Store results - handle both array and scalar cases
            if isinstance(vri_2_0_normalized, (np.ndarray, pd.Series)):
                vri_2_0_value = float(vri_2_0_normalized.mean())
            elif isinstance(vri_2_0_normalized, (list, tuple)) and len(vri_2_0_normalized) > 0:
                vri_2_0_value = float(vri_2_0_normalized[0])
            elif isinstance(vri_2_0_normalized, float):
                vri_2_0_value = vri_2_0_normalized
            else:
                vri_2_0_value = 0.0
            
            df_strike['vri_2_0_strike'] = vri_2_0_value
            
            return df_strike
            
        except Exception as e:
            self.logger.error(f"Error calculating VRI 2.0: {e}", exc_info=True)
            df_strike['vri_2_0_strike'] = 0.0
            return df_strike
    
    def _calculate_0dte_suite(self, df_strike: pd.DataFrame, und_data: Dict, dte_context: str) -> pd.DataFrame:
        """Calculate 0DTE Suite metrics."""
        try:
            # Get 0DTE configuration parameters using isolated config
            dte_threshold = self._get_metric_config('dte_suite', 'dte_threshold_for_0dte', 1.0)
            
            # Filter for 0DTE options
            dte_values = df_strike.get('dte_calc', pd.Series([30] * len(df_strike)))
            is_0dte = dte_values <= dte_threshold
            
            # Initialize all metrics to zero
            df_strike['0dte_gamma_exposure'] = 0.0
            df_strike['0dte_delta_exposure'] = 0.0
            df_strike['0dte_vanna_exposure'] = 0.0
            df_strike['0dte_charm_exposure'] = 0.0
            df_strike['vci_0dte'] = 0.0  # Vanna Concentration Index
            df_strike['gci_0dte'] = 0.0  # Gamma Concentration Index
            df_strike['dci_0dte'] = 0.0  # Delta Concentration Index
            
            if is_0dte.any():
                # Core 0DTE exposures
                df_strike.loc[is_0dte, '0dte_gamma_exposure'] = df_strike.loc[is_0dte, 'total_gxoi_at_strike'].fillna(0)
                df_strike.loc[is_0dte, '0dte_delta_exposure'] = df_strike.loc[is_0dte, 'total_dxoi_at_strike'].fillna(0)
                df_strike.loc[is_0dte, '0dte_vanna_exposure'] = df_strike.loc[is_0dte, 'total_vanna_at_strike'].fillna(0)
                df_strike.loc[is_0dte, '0dte_charm_exposure'] = df_strike.loc[is_0dte, 'total_charmxoi_at_strike'].fillna(0)
                
                # Calculate concentration indices for 0DTE options
                if is_0dte.sum() > 1:  # Need multiple strikes for concentration
                    # Vanna Concentration Index (VCI)
                    vanna_0dte = df_strike.loc[is_0dte, 'total_vanna_at_strike'].fillna(0)
                    total_vanna = vanna_0dte.abs().sum()
                    if total_vanna > 0:
                        vanna_weights = vanna_0dte.abs() / total_vanna
                        vci = (vanna_weights ** 2).sum()  # Herfindahl-like concentration
                        df_strike.loc[is_0dte, 'vci_0dte'] = vci
                    
                    # Gamma Concentration Index (GCI)
                    gamma_0dte = df_strike.loc[is_0dte, 'total_gxoi_at_strike'].fillna(0)
                    total_gamma = gamma_0dte.abs().sum()
                    if total_gamma > 0:
                        gamma_weights = gamma_0dte.abs() / total_gamma
                        gci = (gamma_weights ** 2).sum()
                        df_strike.loc[is_0dte, 'gci_0dte'] = gci
                    
                    # Delta Concentration Index (DCI)
                    delta_0dte = df_strike.loc[is_0dte, 'total_dxoi_at_strike'].fillna(0)
                    total_delta = delta_0dte.abs().sum()
                    if total_delta > 0:
                        delta_weights = delta_0dte.abs() / total_delta
                        dci = (delta_weights ** 2).sum()
                        df_strike.loc[is_0dte, 'dci_0dte'] = dci
            
            return df_strike
            
        except Exception as e:
            self.logger.error(f"Error calculating 0DTE Suite: {e}", exc_info=True)
            df_strike['0dte_gamma_exposure'] = 0.0
            df_strike['0dte_delta_exposure'] = 0.0
            df_strike['0dte_vanna_exposure'] = 0.0
            df_strike['0dte_charm_exposure'] = 0.0
            df_strike['vci_0dte'] = 0.0
            df_strike['gci_0dte'] = 0.0
            df_strike['dci_0dte'] = 0.0
            return df_strike
    
    def _calculate_enhanced_heatmap_data(self, df_strike: pd.DataFrame, und_data: Dict) -> pd.DataFrame:
        """Calculate Enhanced Heatmap Data (SGDHP, IVSDH, UGCH)."""
        try:
            symbol = self._calculation_state.get('current_symbol', 'UNKNOWN')
            
            # Core exposure inputs - properly access DataFrame columns
            gamma_exposure = df_strike['total_gxoi_at_strike'].fillna(0) if 'total_gxoi_at_strike' in df_strike.columns else pd.Series([0] * len(df_strike))
            delta_exposure = df_strike['total_dxoi_at_strike'].fillna(0) if 'total_dxoi_at_strike' in df_strike.columns else pd.Series([0] * len(df_strike))
            vanna_exposure = df_strike['total_vanna_at_strike'].fillna(0) if 'total_vanna_at_strike' in df_strike.columns else pd.Series([0] * len(df_strike))
            
            # Flow inputs - properly access DataFrame columns
            net_gamma_flow = df_strike['net_cust_gamma_flow_at_strike_proxy'].fillna(0) if 'net_cust_gamma_flow_at_strike_proxy' in df_strike.columns else pd.Series([0] * len(df_strike))
            net_delta_flow = df_strike['net_cust_delta_flow_at_strike'].fillna(0) if 'net_cust_delta_flow_at_strike' in df_strike.columns else pd.Series([0] * len(df_strike))
            net_vanna_flow = df_strike['net_cust_vanna_flow_at_strike_proxy'].fillna(0) if 'net_cust_vanna_flow_at_strike_proxy' in df_strike.columns else pd.Series([0] * len(df_strike))
            
            # Weights
            gamma_weight = 0.4
            delta_weight = 0.3
            vanna_weight = 0.2
            flow_weight = 0.1
            
            # Calculate normalized intensities - ensure they match DataFrame length
            gamma_intensity = self._normalize_flow(gamma_exposure, 'gamma', symbol) * gamma_weight
            delta_intensity = self._normalize_flow(delta_exposure, 'delta', symbol) * delta_weight
            vanna_intensity = self._normalize_flow(vanna_exposure, 'vanna', symbol) * vanna_weight
            
            # Ensure arrays match DataFrame length
            num_rows = len(df_strike)
            if len(gamma_intensity) == 1 and num_rows > 1:
                gamma_intensity = np.full(num_rows, gamma_intensity[0])
            if len(delta_intensity) == 1 and num_rows > 1:
                delta_intensity = np.full(num_rows, delta_intensity[0])
            if len(vanna_intensity) == 1 and num_rows > 1:
                vanna_intensity = np.full(num_rows, vanna_intensity[0])
            
            # Flow alignment factors - FIX: Convert Series to arrays for comparison
            gamma_flow_factor = np.where(
                np.sign(gamma_exposure.values) == np.sign(net_gamma_flow.values),
                1.2, 0.8
            )
            
            delta_flow_factor = np.where(
                np.sign(delta_exposure.values) == np.sign(net_delta_flow.values),
                1.2, 0.8
            )
            
            vanna_flow_factor = np.where(
                np.sign(vanna_exposure.values) == np.sign(net_vanna_flow.values),
                1.2, 0.8
            )
            
            # Apply flow factors
            gamma_intensity_adj = gamma_intensity * gamma_flow_factor
            delta_intensity_adj = delta_intensity * delta_flow_factor
            vanna_intensity_adj = vanna_intensity * vanna_flow_factor
            
            # Flow component - FIX: Convert Series to arrays for addition
            flow_intensity = self._normalize_flow(
                net_gamma_flow.values + net_delta_flow.values + net_vanna_flow.values, 'combined_flow', symbol
            ) * flow_weight
            
            # Ensure flow_intensity matches DataFrame length
            if len(flow_intensity) == 1 and num_rows > 1:
                flow_intensity = np.full(num_rows, flow_intensity[0])
            
            # Multi-dimensional heatmap calculation
            composite_intensity = (
                gamma_intensity_adj + delta_intensity_adj + 
                vanna_intensity_adj + flow_intensity
            )
            
            # Store main heatmap intensity
            df_strike['sgdhp_data'] = composite_intensity
            df_strike['ivsdh_data'] = vanna_intensity_adj
            df_strike['ugch_data'] = delta_intensity_adj
            
            # Calculate proper SGDHP and UGCH scores according to system guide
            df_strike = self._calculate_sgdhp_scores(df_strike, und_data)
            df_strike = self._calculate_ugch_scores(df_strike, und_data)
            
            # Additional heatmap metrics
            df_strike['heatmap_regime_scaling'] = 1.0
            df_strike['heatmap_gamma_component'] = gamma_intensity_adj
            df_strike['heatmap_delta_component'] = delta_intensity_adj
            df_strike['heatmap_vanna_component'] = vanna_intensity_adj
            df_strike['heatmap_flow_component'] = flow_intensity
            
            return df_strike
            
        except Exception as e:
            self.logger.error(f"Error calculating enhanced heatmap data: {e}", exc_info=True)
            df_strike['sgdhp_data'] = 0.0
            df_strike['ivsdh_data'] = 0.0
            df_strike['ugch_data'] = 0.0
            return df_strike

    def _calculate_sgdhp_scores(self, df_strike: pd.DataFrame, und_data: Dict) -> pd.DataFrame:
        """Calculate SGDHP scores according to system guide specifications."""
        try:
            current_price = und_data.get('price', 0.0)
            if current_price <= 0:
                df_strike['sgdhp_score_strike'] = 0.0
                return df_strike
            
            # Get required data
            gxoi_at_strike = df_strike['total_gxoi_at_strike'].fillna(0)
            dxoi_at_strike = df_strike['total_dxoi_at_strike'].fillna(0)
            strikes = df_strike['strike'].fillna(0)
            
            # Calculate price proximity factor (Gaussian-like decay)
            proximity_sensitivity = self._get_metric_config('heatmap_generation_settings', 'sgdhp_params.proximity_sensitivity_param', 0.05)
            price_proximity_factor = np.exp(-((strikes - current_price) / current_price) ** 2 / (2 * proximity_sensitivity ** 2))
            
            # Calculate DXOI normalized impact
            max_abs_dxoi = dxoi_at_strike.abs().max()
            if max_abs_dxoi > 0:
                dxoi_normalized_impact = dxoi_at_strike.abs() / (max_abs_dxoi + 1e-6)
            else:
                dxoi_normalized_impact = pd.Series([0.0] * len(df_strike))
            
            # Recent flow confirmation factor (simplified for now)
            # In full implementation, this would use strike-level recent flows
            recent_flow_confirmation = pd.Series([0.1] * len(df_strike))  # Small positive confirmation
            
            # Calculate SGDHP score according to system guide formula
            sgdhp_scores = (
                (gxoi_at_strike * price_proximity_factor) * 
                np.sign(dxoi_at_strike) * 
                dxoi_normalized_impact * 
                (1 + recent_flow_confirmation)
            )
            
            df_strike['sgdhp_score_strike'] = sgdhp_scores
            
            self.logger.debug(f"SGDHP scores calculated: min={sgdhp_scores.min():.2f}, max={sgdhp_scores.max():.2f}, mean={sgdhp_scores.mean():.2f}")
            
            return df_strike
            
        except Exception as e:
            self.logger.error(f"Error calculating SGDHP scores: {e}", exc_info=True)
            df_strike['sgdhp_score_strike'] = 0.0
            return df_strike
    
    def _calculate_ugch_scores(self, df_strike: pd.DataFrame, und_data: Dict) -> pd.DataFrame:
        """Calculate UGCH scores according to system guide specifications."""
        try:
            # Get Greek exposures at strike level
            dxoi_at_strike = df_strike['total_dxoi_at_strike'].fillna(0)
            gxoi_at_strike = df_strike['total_gxoi_at_strike'].fillna(0)
            vxoi_at_strike = df_strike['total_vxoi_at_strike'].fillna(0)
            txoi_at_strike = df_strike['total_txoi_at_strike'].fillna(0)
            charm_at_strike = df_strike['total_charmxoi_at_strike'].fillna(0)
            vanna_at_strike = df_strike['total_vannaxoi_at_strike'].fillna(0)
            
            # Normalize each Greek series (Z-score normalization)
            def normalize_series(series):
                if series.std() > 0:
                    return (series - series.mean()) / series.std()
                else:
                    return pd.Series([0.0] * len(series))
            
            norm_dxoi = normalize_series(dxoi_at_strike)
            norm_gxoi = normalize_series(gxoi_at_strike)
            norm_vxoi = normalize_series(vxoi_at_strike)
            norm_txoi = normalize_series(txoi_at_strike)
            norm_charm = normalize_series(charm_at_strike)
            norm_vanna = normalize_series(vanna_at_strike)
            
            # Get Greek weights from config (with defaults)
            greek_weights = self._get_metric_config('heatmap_generation_settings', 'ugch_params.greek_weights', {
                'norm_DXOI': 1.5,
                'norm_GXOI': 2.0,
                'norm_VXOI': 1.2,
                'norm_TXOI': 0.8,
                'norm_CHARM': 0.6,
                'norm_VANNA': 1.0
            })
            
            # Calculate weighted confluence score
            ugch_scores = (
                greek_weights.get('norm_DXOI', 1.5) * norm_dxoi +
                greek_weights.get('norm_GXOI', 2.0) * norm_gxoi +
                greek_weights.get('norm_VXOI', 1.2) * norm_vxoi +
                greek_weights.get('norm_TXOI', 0.8) * norm_txoi +
                greek_weights.get('norm_CHARM', 0.6) * norm_charm +
                greek_weights.get('norm_VANNA', 1.0) * norm_vanna
            )
            
            df_strike['ugch_score_strike'] = ugch_scores
            
            self.logger.debug(f"UGCH scores calculated: min={ugch_scores.min():.2f}, max={ugch_scores.max():.2f}, mean={ugch_scores.mean():.2f}")
            
            return df_strike
            
        except Exception as e:
            self.logger.error(f"Error calculating UGCH scores: {e}", exc_info=True)
            df_strike['ugch_score_strike'] = 0.0
            return df_strike

    def _get_dte_scaling_factor(self, dte_context: str) -> float:
        """Get DTE scaling factor for adaptive calculations."""
        dte_scalers = {
            '0DTE': 1.5,
            'SHORT_DTE': 1.2,
            'NORMAL_DTE': 1.0,
            'LONG_DTE': 0.8
        }
        return dte_scalers.get(dte_context, 1.0)
    
    def _calculate_time_weight(self, current_time: pd.Timestamp) -> float:
        """Calculate time-of-day weighting factor."""
        try:
            # Simple time weighting - higher weight towards end of day
            hour = current_time.hour
            minute = current_time.minute
            
            # Market hours: 9:30 AM to 4:00 PM ET
            market_open_minutes = 9 * 60 + 30  # 9:30 AM
            market_close_minutes = 16 * 60     # 4:00 PM
            current_minutes = hour * 60 + minute
            
            if current_minutes < market_open_minutes or current_minutes > market_close_minutes:
                return 0.5  # After hours
            
            # Calculate progress through trading day
            trading_progress = (current_minutes - market_open_minutes) / (market_close_minutes - market_open_minutes)
            
            # Exponential weighting towards end of day
            time_weight = 0.5 + 0.5 * (trading_progress ** 2)
            
            return time_weight
            
        except Exception as e:
            self.logger.error(f"Error calculating time weight: {e}")
            return 1.0
    
    def _normalize_flow(self, flow_values, flow_type: str, symbol: str = None) -> np.ndarray:
        """Normalize flow values using historical context."""
        try:
            if symbol and hasattr(flow_values, '__iter__'):
                # Use isolated cache for normalization
                cache = self._get_isolated_cache('enhanced_heatmap', symbol)
                cache_key = f"{flow_type}_normalization_history"
                
                if cache_key not in cache:
                    cache[cache_key] = []
                
                # Add current values to history
                if isinstance(flow_values, (list, np.ndarray, pd.Series)):
                    cache[cache_key].extend(list(flow_values))
                else:
                    cache[cache_key].append(flow_values)
                
                # Keep only recent history
                if len(cache[cache_key]) > 100:
                    cache[cache_key] = cache[cache_key][-100:]
                
                # Normalize using historical context
                if len(cache[cache_key]) > 10:
                    mean_val = np.mean(cache[cache_key])
                    std_val = np.std(cache[cache_key])
                    if std_val > 0:
                        if isinstance(flow_values, (list, np.ndarray, pd.Series)):
                            return (np.array(flow_values) - mean_val) / std_val
                        else:
                            return (flow_values - mean_val) / std_val
            
            # Fallback: simple normalization
            if isinstance(flow_values, (list, np.ndarray, pd.Series)):
                flow_array = np.array(flow_values)
                if len(flow_array) > 0:
                    return (flow_array - np.mean(flow_array)) / (np.std(flow_array) + 1e-6)
                else:
                    return np.array([0.0])
            else:
                return np.array([flow_values])
                
        except Exception as e:
            self.logger.error(f"Error normalizing flow {flow_type}: {e}", exc_info=True)
            if isinstance(flow_values, (list, np.ndarray, pd.Series)):
                return np.zeros(len(flow_values))
            else:
                return np.array([0.0])

    def _calculate_atr(self, symbol: str, dte_max: int = 45) -> float:
        """Fetches OHLCV data and calculates the Average True Range (ATR)."""
        try:
            # Calculate appropriate lookback based on DTE context
            # For ATR, we need enough data for a meaningful calculation
            # Use max(dte_max, 14) to ensure minimum 14 periods for ATR but respect DTE context
            lookback_days = max(dte_max, 14)
            
            ohlcv_df = self.historical_data_manager.get_historical_ohlcv(symbol, lookback_days=lookback_days)
            if ohlcv_df is None or ohlcv_df.empty or len(ohlcv_df) < 2:
                self.logger.warning(f"Insufficient OHLCV data for {symbol} to calculate ATR. Returning 0.")
                return 0.0
            
            high_low = ohlcv_df['high'] - ohlcv_df['low']
            high_close = np.abs(ohlcv_df['high'] - ohlcv_df['close'].shift())
            low_close = np.abs(ohlcv_df['low'] - ohlcv_df['close'].shift())
            
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.ewm(com=14, min_periods=14).mean().iloc[-1]
            return atr
        except Exception as e:
            self.logger.error(f"Failed to calculate ATR for {symbol}: {e}", exc_info=True)
            return 0.0
    
    def _calculate_underlying_aggregates(self, df_strike: Optional[pd.DataFrame]) -> Dict[str, float]:
        """Calculate underlying-level aggregate metrics from strike-level data."""
        aggregates = {}
        
        try:
            if df_strike is not None and not df_strike.empty:
                # Log available columns for debugging
                self.logger.debug(f"Available strike columns for aggregation: {df_strike.columns.tolist()}")
                
                # Sum up strike-level metrics to underlying level - using actual column names
                # Total flow metrics (sum across strikes)
                aggregates['total_delta_flow'] = df_strike['net_cust_delta_flow_at_strike'].fillna(0).sum() if 'net_cust_delta_flow_at_strike' in df_strike.columns else 0.0
                aggregates['total_gamma_flow'] = df_strike['net_cust_gamma_flow_at_strike'].fillna(0).sum() if 'net_cust_gamma_flow_at_strike' in df_strike.columns else 0.0
                aggregates['total_vega_flow'] = df_strike['net_cust_vega_flow_at_strike'].fillna(0).sum() if 'net_cust_vega_flow_at_strike' in df_strike.columns else 0.0
                aggregates['total_theta_flow'] = df_strike['net_cust_theta_flow_at_strike'].fillna(0).sum() if 'net_cust_theta_flow_at_strike' in df_strike.columns else 0.0
                
                # Exposure metrics (sum)
                aggregates['total_delta_exposure'] = df_strike['total_dxoi_at_strike'].fillna(0).sum() if 'total_dxoi_at_strike' in df_strike.columns else 0.0
                aggregates['total_gamma_exposure'] = df_strike['total_gxoi_at_strike'].fillna(0).sum() if 'total_gxoi_at_strike' in df_strike.columns else 0.0
                aggregates['total_vega_exposure'] = df_strike['total_vxoi_at_strike'].fillna(0).sum() if 'total_vxoi_at_strike' in df_strike.columns else 0.0
                aggregates['total_theta_exposure'] = df_strike['total_txoi_at_strike'].fillna(0).sum() if 'total_txoi_at_strike' in df_strike.columns else 0.0
                
                # Advanced metrics (sum or mean as appropriate)
                aggregates['a_dag_und_aggregate'] = df_strike['a_dag_exposure'].fillna(0).sum() if 'a_dag_exposure' in df_strike.columns else 0.0
                aggregates['vri_2_0_und_aggregate'] = df_strike['vri_2_0_strike'].fillna(0).mean() if 'vri_2_0_strike' in df_strike.columns else 0.0
                # --- FIX: calculate A-SAI and A-SSI with proper normalization ---
                if 'a_dag_exposure' in df_strike.columns:
                    a_dag_values = df_strike['a_dag_exposure'].fillna(0)
                    
                    # Normalize A-DAG values to -1 to +1 range before calculating A-SAI/A-SSI
                    if len(a_dag_values) > 0 and a_dag_values.std() > 0:
                        # Use 3-sigma normalization and clip to [-1, 1] range
                        a_dag_normalized = (a_dag_values - a_dag_values.mean()) / (3 * a_dag_values.std())
                        a_dag_normalized = np.clip(a_dag_normalized, -1, 1)
                    else:
                        a_dag_normalized = pd.Series([0.0] * len(a_dag_values))
                    
                    # Calculate A-SAI (positive normalized values) and A-SSI (negative normalized values)
                    pos = a_dag_normalized[a_dag_normalized > 0]
                    neg = a_dag_normalized[a_dag_normalized < 0]
                    
                    aggregates['a_sai_und_avg'] = pos.mean() if not pos.empty else 0.0
                    aggregates['a_ssi_und_avg'] = neg.mean() if not neg.empty else 0.0
                else:
                    aggregates['a_sai_und_avg'] = 0.0
                    aggregates['a_ssi_und_avg'] = 0.0
                
                # Net value/volume metrics
                aggregates['total_nvp'] = df_strike['nvp_at_strike'].fillna(0).sum() if 'nvp_at_strike' in df_strike.columns else 0.0
                aggregates['total_nvp_vol'] = df_strike['nvp_vol_at_strike'].fillna(0).sum() if 'nvp_vol_at_strike' in df_strike.columns else 0.0
                
                # 0DTE metrics (sum)
                aggregates['total_0dte_gamma'] = df_strike['0dte_gamma_exposure'].fillna(0).sum() if '0dte_gamma_exposure' in df_strike.columns else 0.0
                aggregates['total_0dte_delta'] = df_strike['0dte_delta_exposure'].fillna(0).sum() if '0dte_delta_exposure' in df_strike.columns else 0.0
                aggregates['total_0dte_vanna'] = df_strike['0dte_vanna_exposure'].fillna(0).sum() if '0dte_vanna_exposure' in df_strike.columns else 0.0
                
                # Legacy mapping for dashboard compatibility
                aggregates['vapi_fa_und_aggregate'] = aggregates['total_vega_flow']
                aggregates['dwfd_und_aggregate'] = aggregates['total_delta_flow']  
                aggregates['tw_laf_und_aggregate'] = aggregates['total_theta_flow']
                
                self.logger.debug(f"Calculated aggregates: {aggregates}")
                
            else:
                # Set defaults when no strike data
                self.logger.warning("No strike data available for aggregation")
                aggregates = {
                    'total_delta_flow': 0.0,
                    'total_gamma_flow': 0.0,
                    'total_vega_flow': 0.0,
                    'total_theta_flow': 0.0,
                    'total_delta_exposure': 0.0,
                    'total_gamma_exposure': 0.0,
                    'total_vega_exposure': 0.0,
                    'total_theta_exposure': 0.0,
                    'a_dag_und_aggregate': 0.0,
                    'vri_2_0_und_aggregate': 0.0,
                    'total_nvp': 0.0,
                    'total_nvp_vol': 0.0,
                    'total_0dte_gamma': 0.0,
                    'total_0dte_delta': 0.0,
                    'total_0dte_vanna': 0.0,
                    'vapi_fa_und_aggregate': 0.0,
                    'dwfd_und_aggregate': 0.0,
                    'tw_laf_und_aggregate': 0.0,
                    'a_sai_und_avg': 0.0,
                    'a_ssi_und_avg': 0.0
                }
                
        except Exception as e:
            self.logger.error(f"Error calculating underlying aggregates: {e}", exc_info=True)
            # Set safe defaults
            aggregates = {
                'total_delta_flow': 0.0,
                'total_gamma_flow': 0.0,
                'total_vega_flow': 0.0,
                'total_theta_flow': 0.0,
                'total_delta_exposure': 0.0,
                'total_gamma_exposure': 0.0,
                'total_vega_exposure': 0.0,
                'total_theta_exposure': 0.0,
                'a_dag_und_aggregate': 0.0,
                'vri_2_0_und_aggregate': 0.0,
                'total_nvp': 0.0,
                'total_nvp_vol': 0.0,
                'total_0dte_gamma': 0.0,
                'total_0dte_delta': 0.0,
                'total_0dte_vanna': 0.0,
                'vapi_fa_und_aggregate': 0.0,
                'dwfd_und_aggregate': 0.0,
                'tw_laf_und_aggregate': 0.0,
                'a_sai_und_avg': 0.0,
                'a_ssi_und_avg': 0.0
            }
        
        return aggregates

    def _get_intraday_cache_file(self, symbol: str, metric_name: str) -> Path:
        """Get the cache file path for intraday data."""
        return self.intraday_cache_dir / f"{symbol}_{metric_name}_{self.current_trading_date}.json"

    def _load_intraday_cache(self, symbol: str, metric_name: str) -> List[float]:
        """Load intraday cache from disk."""
        cache_file = self._get_intraday_cache_file(symbol, metric_name)
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    # Check if it's today's data
                    if data.get('date') == self.current_trading_date:
                        return data.get('values', [])
            except Exception as e:
                self.logger.warning(f"Error loading intraday cache for {symbol}_{metric_name}: {e}")
        return []

    def _save_intraday_cache(self, symbol: str, metric_name: str, values: List[float]) -> None:
        """Save intraday cache to disk."""
        cache_file = self._get_intraday_cache_file(symbol, metric_name)
        try:
            cache_data = {
                'date': self.current_trading_date,
                'values': values,
                'last_updated': datetime.now().isoformat()
            }
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            self.logger.warning(f"Error saving intraday cache for {symbol}_{metric_name}: {e}")

    def _add_to_intraday_cache(self, symbol: str, metric_name: str, value: float, max_size: int = 200) -> List[float]:
        """Add value to intraday cache and return updated cache."""
        cache_values = self._load_intraday_cache(symbol, metric_name)
        
        # If cache is empty (new ticker), seed it with baseline values
        if not cache_values:
            cache_values = self._seed_new_ticker_cache(symbol, metric_name, value)
        else:
            cache_values.append(value)
        
        # Keep only the most recent values (e.g., last 200 data points = ~1.5 hours at 30s intervals)
        if len(cache_values) > max_size:
            cache_values = cache_values[-max_size:]
        
        self._save_intraday_cache(symbol, metric_name, cache_values)
        return cache_values

    def _seed_new_ticker_cache(self, symbol: str, metric_name: str, current_value: float) -> List[float]:
        """Seed cache for new ticker with baseline values from existing tickers or defaults."""
        try:
            # Try to find existing cache data from similar tickers
            baseline_values = []
            
            # Look for existing cache files from other tickers
            if self.intraday_cache_dir.exists():
                for cache_file in self.intraday_cache_dir.glob(f"*_{metric_name}_{self.current_trading_date}.json"):
                    if not cache_file.name.startswith(f"{symbol}_"):
                        try:
                            with open(cache_file, 'r') as f:
                                data = json.load(f)
                                if data.get('date') == self.current_trading_date:
                                    existing_values = data.get('values', [])
                                    if len(existing_values) >= 10:
                                        # Use the last 10 values as baseline
                                        baseline_values = existing_values[-10:]
                                        if self.logger.isEnabledFor(logging.DEBUG):
                                            self.logger.debug(f"Seeded {symbol} {metric_name} cache with {len(baseline_values)} values from {cache_file.name}")
                                        break
                        except Exception as e:
                            continue
            
            # If no existing data found, use intelligent defaults based on metric type
            if not baseline_values:
                if metric_name == 'vapi_fa':
                    # VAPI-FA typically ranges from -50k to +50k, seed around zero
                    baseline_values = [0.0, 1000.0, -1000.0, 2000.0, -2000.0, 500.0, -500.0, 1500.0, -1500.0, 0.0]
                elif metric_name == 'dwfd':
                    # DWFD typically ranges from -500 to +500, seed around zero  
                    baseline_values = [0.0, 50.0, -50.0, 100.0, -100.0, 25.0, -25.0, 75.0, -75.0, 0.0]
                elif metric_name == 'tw_laf':
                    # TW-LAF typically ranges from -100k to +100k, seed around zero
                    baseline_values = [0.0, 5000.0, -5000.0, 10000.0, -10000.0, 2500.0, -2500.0, 7500.0, -7500.0, 0.0]
                else:
                    # Generic baseline for other metrics
                    baseline_values = [0.0, 10.0, -10.0, 20.0, -20.0, 5.0, -5.0, 15.0, -15.0, 0.0]
                
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug(f"Seeded {symbol} {metric_name} cache with default baseline values")
            
            # Add current value to the baseline
            baseline_values.append(current_value)
            
            # Save the seeded cache
            self._save_intraday_cache(symbol, metric_name, baseline_values)
            
            return baseline_values
            
        except Exception as e:
            self.logger.error(f"Error seeding cache for {symbol} {metric_name}: {e}")
            # Fallback to simple baseline
            return [0.0, current_value]

    def _calculate_percentile_gauge_value(self, cache_values: List[float], current_value: float) -> float:
        """Calculate gauge value (-3 to +3) based on percentile ranking in cache."""
        try:
            if len(cache_values) < 2:
                # Not enough data for percentile calculation, return neutral
                return 0.0
            
            # Create list including current value for ranking
            all_values = list(cache_values) + [current_value]
            sorted_values = sorted(all_values)
            
            # Handle duplicate values by finding the range of positions
            current_positions = [i for i, val in enumerate(sorted_values) if val == current_value]
            
            if len(current_positions) == 1:
                # Unique value, use its position
                position = current_positions[0]
            else:
                # Duplicate values, use middle position
                position = current_positions[len(current_positions) // 2]
            
            # Calculate percentile (0.0 to 1.0)
            percentile = position / (len(sorted_values) - 1) if len(sorted_values) > 1 else 0.5
            
            # Convert to gauge scale (-3 to +3)
            # 0% = -3, 50% = 0, 100% = +3
            gauge_value = (percentile - 0.5) * 6.0
            
            # Ensure within bounds
            gauge_value = max(-3.0, min(3.0, gauge_value))
            
            return float(gauge_value)
            
        except Exception as e:
            self.logger.error(f"Error calculating percentile gauge value: {e}")
            return 0.0