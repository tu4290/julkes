# core_analytics_engine/market_regime_engine_v2_5.py
# EOTS v2.5 - S-GRADE PRODUCTION HARDENED & OPTIMIZED ARTIFACT

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from data_models.eots_schemas_v2_5 import ProcessedUnderlyingAggregatesV2_5, MarketRegimeEngineSettings
from utils.config_manager_v2_5 import ConfigManagerV2_5

logger = logging.getLogger(__name__)

class MarketRegimeEngineV2_5:
    """Determines market regime based on configuration-driven rules."""
    
    def __init__(self, config_manager: ConfigManagerV2_5):
        """
        Initialize the MarketRegimeEngineV2_5.

        Args:
            config_manager: The system's configuration manager
        """
        self.logger = logging.getLogger(__name__)
        self.config_manager = config_manager
        
        # Get settings from config manager
        self.settings = self.config_manager.get_setting("market_regime_engine_settings")
        if not self.settings:
            raise ValueError("FATAL: market_regime_engine_settings not found in configuration.")
            
        # Access regime rules from the Pydantic model
        self.regime_rules = self.settings.regime_rules
        self.evaluation_order = self.settings.regime_evaluation_order
        self.default_regime = self.settings.default_regime
        
        self.logger.info("MarketRegimeEngineV2_5 initialized.")
        
    def determine_regime(self, metrics: Dict[str, float]) -> str:
        """Determine the current market regime based on metrics."""
        try:
            # Evaluate each regime in order
            for regime in self.evaluation_order:
                if self._evaluate_regime(regime, metrics):
                    return regime
                    
            return self.default_regime
            
        except Exception as e:
            self.logger.error(f"Error determining market regime: {e}", exc_info=True)
            return self.default_regime
            
    def _evaluate_regime(self, regime: str, metrics: Dict[str, float]) -> bool:
        """Evaluate if the current metrics match a specific regime's rules."""
        try:
            rules = self.regime_rules.get(regime, {})
            if not rules:
                return False
                
            # Check each rule
            for metric, threshold in rules.items():
                if metric not in metrics:
                    return False
                    
                value = metrics[metric]
                
                # Handle different types of comparisons
                if metric.endswith('_gt'):
                    if value <= threshold:
                        return False
                elif metric.endswith('_lt'):
                    if value >= threshold:
                        return False
                elif metric.endswith('_abs_lt'):
                    if abs(value) >= threshold:
                        return False
                        
            return True
            
        except Exception as e:
            self.logger.error(f"Error evaluating regime {regime}: {e}", exc_info=True)
            return False

    def _parse_metric_key(self, key: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Parse a metric key into its components."""
        try:
            # Split the key into base metric and selector
            parts = key.split('@', 1)
            base_metric = parts[0]
            selector = parts[1] if len(parts) > 1 else None
            
            # Parse any aggregation
            agg = None
            if selector and selector.startswith('[AGG='):
                agg = selector[5:-1]
                selector = None
                
            return base_metric, selector, agg
            
        except Exception as e:
            self.logger.error(f"Error parsing metric key {key}: {e}", exc_info=True)
            return key, None, None

    def determine_market_regime(self, 
                                und_data: ProcessedUnderlyingAggregatesV2_5, 
                                df_strike: pd.DataFrame, 
                                df_chain: pd.DataFrame) -> str:
        """
        Determines the current market regime by evaluating rules in the specified order.
        """
        if not all(isinstance(arg, (ProcessedUnderlyingAggregatesV2_5, pd.DataFrame)) for arg in [und_data, df_strike, df_chain]):
            self.logger.error("Invalid input types to determine_market_regime. Falling back to default.")
            return self.default_regime

        self.logger.debug(f"Determining market regime for {und_data.symbol}...")
        
        # Dynamic thresholds are now expected to be an attribute of the und_data object
        dynamic_thresholds = getattr(und_data, 'dynamic_thresholds', {})

        for regime_name in self.evaluation_order:
            rule_block = self.regime_rules.get(regime_name)
            if not rule_block or not isinstance(rule_block, dict):
                self.logger.warning(f"Skipping malformed or missing rule block for regime '{regime_name}'.")
                continue

            try:
                if self._evaluate_condition_block(rule_block, und_data, df_strike, df_chain, dynamic_thresholds):
                    self.logger.info(f"Market regime matched: {regime_name}")
                    return regime_name
            except Exception as e:
                self.logger.error(f"Unhandled exception during evaluation of regime '{regime_name}': {e}", exc_info=True)
                continue

        self.logger.info(f"No regime rules matched. Falling back to default: {self.default_regime}")
        return self.default_regime

    def _evaluate_condition_block(self, block: Dict, und_data: ProcessedUnderlyingAggregatesV2_5, df_strike: pd.DataFrame, df_chain: pd.DataFrame, thresholds: Dict) -> bool:
        """A condition block is TRUE only if ALL its conditions are TRUE (AND logic)."""
        for key, target_value in block.items():
            if key == "_any_of":
                if not any(self._evaluate_condition_block(sub_block, und_data, df_strike, df_chain, thresholds) for sub_block in target_value):
                    return False
                continue

            metric_name, selector, operator = self._parse_metric_key(key)
            if not operator:
                self.logger.warning(f"Rule key '{key}' has no valid operator. Condition fails.")
                return False
            
            context = getattr(und_data, 'ticker_context_dict_v2_5', {}) or {}
            if metric_name in context:
                if not self._check_special_condition(metric_name, target_value, context, operator):
                    return False
                continue

            resolved_target = thresholds.get(target_value.split(':')[1]) if isinstance(target_value, str) and target_value.startswith("dynamic_threshold:") else target_value
            actual_value = self._resolve_metric_value(metric_name, selector, und_data, df_strike, df_chain)
            
            if actual_value is None:
                self.logger.debug(f"Metric '{key}' resolved to None. Condition fails.")
                return False 
            
            if not self._perform_comparison(actual_value, operator, resolved_target):
                return False
        return True

    def _resolve_metric_value(self, metric: str, selector: Optional[str], und_data: ProcessedUnderlyingAggregatesV2_5, df_strike: pd.DataFrame, df_chain: pd.DataFrame) -> Any:
        """Resolves a metric's value, handling complex selectors and aggregations."""
        try:
            if not selector:
                return getattr(und_data, metric, None)

            if df_strike.empty and not selector.startswith('[AGG='): return None

            if selector.startswith('[AGG='):
                agg_type = selector[5:-1]
                if metric not in df_strike.columns: return None
                return getattr(df_strike[metric], agg_type, lambda: None)()
            
            if selector.startswith('[PERCENTILE='):
                percentile = float(selector[12:-1])
                if metric not in df_strike.columns: return None
                return df_strike[metric].quantile(percentile / 100.0)

            if und_data.price is None: return None
            
            if selector == '@ATM':
                if not pd.api.types.is_numeric_dtype(df_strike.index): return None
                # Calculate absolute differences using pandas Series
                strike_diffs = pd.Series(df_strike.index - und_data.price)
                target_strike = strike_diffs.abs().idxmin()
                return df_strike.loc[target_strike].get(metric)

            # Additional selectors can be added here
            return None
        except (AttributeError, KeyError, IndexError, ValueError, TypeError) as e:
            self.logger.warning(f"Could not resolve metric key '{metric}{selector or ''}': {e}", exc_info=True)
            return None
            
    def _check_special_condition(self, context_key: str, target_value: Any, context: Dict, operator: str) -> bool:
        """Data-driven evaluation of flags in the ticker context dictionary."""
        actual_value = context.get(context_key)
        if actual_value is None: return False
        return self._perform_comparison(actual_value, operator, target_value)

    def _perform_comparison(self, actual: Any, op: str, target: Any) -> bool:
        """Performs the actual comparison between a metric's value and its target."""
        try:
            if op == "_lt": return actual < target
            if op == "_gt": return actual > target
            if op == "_lte": return actual <= target
            if op == "_gte": return actual >= target
            if op == "_eq": return actual == target
            if op == "_neq": return actual != target
            if op == "_abs_gt": return abs(actual) > target
            if op == "_abs_lt": return abs(actual) < target
            if op == "_in_list": return actual in target
            if op == "_contains": return isinstance(actual, str) and target in actual
        except (TypeError, ValueError):
            # This can happen if comparing incompatible types, e.g., number and None
            return False
        return False