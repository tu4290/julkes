# core_analytics_engine/signal_generator_v2_5.py
# EOTS v2.5 - S-GRADE PRODUCTION HARDENED ARTIFACT

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np

from data_models.eots_schemas_v2_5 import ProcessedDataBundleV2_5, SignalPayloadV2_5, ProcessedUnderlyingAggregatesV2_5
from utils.config_manager_v2_5 import ConfigManagerV2_5


logger = logging.getLogger(__name__)
EPSILON = 1e-9

class SignalGeneratorV2_5:
    """
    Generates discrete, scored trading signals based on a fully processed data bundle.
    This hardened version ensures production-grade resilience through robust error
    handling and employs vectorized logic where possible for maximum performance.
    """

    def __init__(self, config_manager: ConfigManagerV2_5):
        """
        Initializes the SignalGeneratorV2_5.

        Args:
            config_manager (ConfigManagerV2_5): The system's configuration manager,
                providing access to signal_generator_settings_v2_5.
        """

        self.logger = logger.getChild(self.__class__.__name__)
        

        self.config_manager = config_manager
        
        self.settings = self.config_manager.get_setting("signal_generator_settings_v2_5", default={})
        if not self.settings: # Log if settings are empty, as it might affect signal generation
            self.logger.warning("signal_generator_settings_v2_5 not found or empty in configuration. Using default behaviors.")

        # PYDANTIC COMPLIANCE FIX: Check if settings is Pydantic model or dict
        if hasattr(self.settings, '__dict__') and hasattr(self.settings, '__fields__'):
            # Pydantic model - access attributes directly
            self.activation = getattr(self.settings, 'signal_activation', {"EnableAllSignals": True})
        else:
            # Dictionary-style access for backward compatibility
            self.activation = (self.settings.get("signal_activation", {"EnableAllSignals": True}) 
                             if hasattr(self.settings, 'get') 
                             else getattr(self.settings, 'signal_activation', {"EnableAllSignals": True}))
        
        self.logger.info("SignalGeneratorV2_5 initialized with activation settings.")

    def generate_all_signals(self, bundle: ProcessedDataBundleV2_5) -> Dict[str, List[SignalPayloadV2_5]]:
        """
        Orchestrates the generation of all signal categories, passing the full data
        bundle to the specialized methods.
        """
        if not isinstance(bundle, ProcessedDataBundleV2_5):
            self.logger.error("generate_all_signals received an invalid data bundle type. Returning empty signals dict.")
            return {}

        if not bundle.underlying_data_enriched or not bundle.underlying_data_enriched.symbol:
             self.logger.error("Underlying data or symbol missing in bundle. Cannot generate signals.")
             return {}


        regime = getattr(bundle.underlying_data_enriched, 'current_market_regime_v2_5', 'UNKNOWN') # Default to UNKNOWN
        signals: Dict[str, List[SignalPayloadV2_5]] = {
            'directional': [], 'volatility': [], 'time_decay': [],
            'complex': [], 'v2_5_enhanced_flow': []
        }
        
        enable_all = self.activation.get("EnableAllSignals", False)

        # Create DataFrames once for performance
        # Ensure strike_level_data_with_metrics is not None before list comprehension
        strike_metrics_list = bundle.strike_level_data_with_metrics or []
        df_strike = pd.DataFrame([s.model_dump() for s in strike_metrics_list])
        if not df_strike.empty:
            df_strike.set_index('strike', inplace=True, drop=False)
        else:
            self.logger.debug("Strike level metrics data is empty or None. df_strike will be empty.")


        if enable_all or self.activation.get("v2_5_enhanced_flow_signals", False):
            signals['v2_5_enhanced_flow'] = self._generate_v2_5_enhanced_flow_signals(bundle.underlying_data_enriched, regime)
        
        if enable_all or self.activation.get("directional_signals", False):
            signals['directional'] = self._generate_directional_signals(bundle, regime, df_strike)

        if enable_all or self.activation.get("volatility_signals", False):
            signals['volatility'] = self._generate_volatility_signals(bundle, regime, df_strike)

        if enable_all or self.activation.get("time_decay_signals", False):
            signals['time_decay'] = self._generate_time_decay_signals(bundle, regime, df_strike)

        if enable_all or self.activation.get("complex_signals", False):
            signals['complex'] = self._generate_complex_signals(bundle, regime, df_strike)


        total_signals_generated = sum(len(v) for v in signals.values())
        self.logger.info(f"Signal generation complete for {bundle.underlying_data_enriched.symbol}. Found {total_signals_generated} total signals.")
        return signals

    # --- Stub Methods for Future Signal Categories ---
    def _generate_directional_signals(self, bundle: ProcessedDataBundleV2_5, regime: str, df_strike: pd.DataFrame) -> List[SignalPayloadV2_5]:
        self.logger.warning(f"Signal generation for 'directional' category for {bundle.underlying_data_enriched.symbol} is not yet implemented. Returning empty list.")
        return []

    def _generate_volatility_signals(self, bundle: ProcessedDataBundleV2_5, regime: str, df_strike: pd.DataFrame) -> List[SignalPayloadV2_5]:
        self.logger.warning(f"Signal generation for 'volatility' category for {bundle.underlying_data_enriched.symbol} is not yet implemented. Returning empty list.")
        return []

    def _generate_time_decay_signals(self, bundle: ProcessedDataBundleV2_5, regime: str, df_strike: pd.DataFrame) -> List[SignalPayloadV2_5]:
        self.logger.warning(f"Signal generation for 'time_decay' category for {bundle.underlying_data_enriched.symbol} is not yet implemented. Returning empty list.")
        return []

    def _generate_complex_signals(self, bundle: ProcessedDataBundleV2_5, regime: str, df_strike: pd.DataFrame) -> List[SignalPayloadV2_5]:
        self.logger.warning(f"Signal generation for 'complex' category for {bundle.underlying_data_enriched.symbol} is not yet implemented. Returning empty list.")
        return []

    # --- Existing Implemented Signal Category ---
    def _generate_v2_5_enhanced_flow_signals(self, und_data: ProcessedUnderlyingAggregatesV2_5, regime: str) -> List[SignalPayloadV2_5]:
        """Generates underlying-level signals from Tier 3 flow metrics."""
        signals = []
        if not isinstance(und_data, ProcessedUnderlyingAggregatesV2_5):
            self.logger.error("Invalid und_data provided to _generate_v2_5_enhanced_flow_signals.")
            return []

        try:
            params = self._get_v2_5_enhanced_flow_signals_params()
            regime_params = params.get("regime_thresholds", {}).get(regime, params.get("default_thresholds", {}))

            # VAPI-FA Signal
            vapi_z = und_data.vapi_fa_z_score_und
            vapi_thresh = regime_params.get("vapi_fa_z_thresh", 2.0) # Default threshold if not in config
            if vapi_z is not None and abs(vapi_z) > vapi_thresh:
                signals.append(self._create_signal_payload(
                    und_data, "VAPI-FA_Momentum_Surge", vapi_z, regime,
                    details={"vapi_z_score": vapi_z, "threshold": vapi_thresh}
                ))
            
            # DWFD Signal
            dwfd_z = und_data.dwfd_z_score_und
            dwfd_thresh = regime_params.get("dwfd_z_thresh", 2.0) # Default threshold
            if dwfd_z is not None and abs(dwfd_z) > dwfd_thresh:
                signals.append(self._create_signal_payload(
                    und_data, "DWFD_Smart_Money_Flow", dwfd_z, regime,
                    details={"dwfd_z_score": dwfd_z, "threshold": dwfd_thresh}
                ))
            
            # TW-LAF Signal
            tw_laf_z = und_data.tw_laf_z_score_und
            tw_laf_thresh = regime_params.get("tw_laf_z_thresh", 1.5) # Default threshold
            if tw_laf_z is not None and abs(tw_laf_z) > tw_laf_thresh:
                signals.append(self._create_signal_payload(
                    und_data, "TW-LAF_Sustained_Trend", tw_laf_z, regime,
                    details={"tw_laf_z_score": tw_laf_z, "threshold": tw_laf_thresh}
                ))

            return signals
        except (KeyError, AttributeError, TypeError) as e: # Added TypeError
            self.logger.error(f"Failed to generate v2.5 enhanced flow signals for {und_data.symbol if und_data else 'UNKNOWN'} due to data/config issue: {e}", exc_info=True)
            return []
        except Exception as e_unhandled: # Catch any other unhandled exceptions
             self.logger.error(f"Unhandled exception in _generate_v2_5_enhanced_flow_signals for {und_data.symbol if und_data else 'UNKNOWN'}: {e_unhandled}", exc_info=True)
             return []

    def _get_v2_5_enhanced_flow_signals_params(self):
        """Get parameters for v2.5 enhanced flow signals."""
        # PYDANTIC COMPLIANCE FIX: Check if settings is Pydantic model or dict
        if hasattr(self.settings, '__dict__') and hasattr(self.settings, '__fields__'):
            # Pydantic model - access attributes directly
            return getattr(self.settings, 'v2_5_enhanced_flow_signals', {})
        else:
            # Dictionary-style access for backward compatibility
            return self.settings.get("v2_5_enhanced_flow_signals", {})

    def _create_signal_payload(self, und_data: ProcessedUnderlyingAggregatesV2_5, name: str, strength: float, regime: str, strike: Optional[float] = None, details: Optional[Dict] = None) -> SignalPayloadV2_5:
        """Helper to construct the SignalPayloadV2_5 Pydantic model."""
        direction = "Neutral"
        if strength > EPSILON: # Using EPSILON for float comparison
            direction = "Bullish"
        elif strength < -EPSILON: # Using EPSILON
            direction = "Bearish"

        # Determine signal type based on name (case-insensitive check)
        name_upper = name.upper()
        signal_type = "Complex" # Default
        if any(k in name_upper for k in ["VAPI", "DWFD", "TW-LAF", "FLOW"]):
            signal_type = "Flow_Momentum"
        elif any(k in name_upper for k in ["MSPI", "SDAG", "DIRECTIONAL"]):
            signal_type = "Directional"
        elif any(k in name_upper for k in ["VOLATILITY", "VRI"]):
            signal_type = "Volatility"
        elif any(k in name_upper for k in ["DECAY", "PIN", "TDPI"]):
            signal_type = "Time_Decay"
        else:
            self.logger.debug(f"Signal '{name}' did not match specific type keywords, defaulting to '{signal_type}'.")


        return SignalPayloadV2_5(
            signal_id=f"sig_{uuid.uuid4().hex[:8]}",
            signal_name=name,
            symbol=und_data.symbol if und_data and und_data.symbol else "UNKNOWN", # Ensure symbol is present
            timestamp=datetime.now(), # Consider using bundle timestamp if consistency is key
            signal_type=signal_type,
            direction=direction,
            strength_score=float(np.clip(strength, -5.0, 5.0)), # Ensure float and clip
            strike_impacted=strike,
            regime_at_signal_generation=regime,
            supporting_metrics=details or {}
        )