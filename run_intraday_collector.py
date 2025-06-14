import time
from datetime import datetime, time as dtime
import logging
import shutil
from pathlib import Path
import json

from utils.config_manager_v2_5 import ConfigManagerV2_5
from data_management.database_manager_v2_5 import DatabaseManagerV2_5
from data_management.historical_data_manager_v2_5 import HistoricalDataManagerV2_5
from data_management.performance_tracker_v2_5 import PerformanceTrackerV2_5
from core_analytics_engine.metrics_calculator_v2_5 import MetricsCalculatorV2_5
from data_management.initial_processor_v2_5 import InitialDataProcessorV2_5
from core_analytics_engine.market_regime_engine_v2_5 import MarketRegimeEngineV2_5
from core_analytics_engine.signal_generator_v2_5 import SignalGeneratorV2_5
from core_analytics_engine.adaptive_trade_idea_framework_v2_5 import AdaptiveTradeIdeaFrameworkV2_5
from core_analytics_engine.trade_parameter_optimizer_v2_5 import TradeParameterOptimizerV2_5
from core_analytics_engine.its_orchestrator_v2_5 import ITSOrchestratorV2_5

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IntradayCollector")

def is_market_open():
    now = datetime.now().time()
    return dtime(9, 30) <= now <= dtime(16, 0)

def build_orchestrator():
    config_manager = ConfigManagerV2_5()
    db_manager = DatabaseManagerV2_5(db_config={})
    historical_data_manager = HistoricalDataManagerV2_5(config_manager, db_manager)
    performance_tracker = PerformanceTrackerV2_5(config_manager)
    metrics_calculator = MetricsCalculatorV2_5(config_manager, historical_data_manager)
    initial_processor = InitialDataProcessorV2_5(config_manager, metrics_calculator)
    market_regime_engine = MarketRegimeEngineV2_5(config_manager)
    signal_generator = SignalGeneratorV2_5(config_manager)
    adaptive_trade_idea_framework = AdaptiveTradeIdeaFrameworkV2_5(config_manager, performance_tracker)
    trade_parameter_optimizer = TradeParameterOptimizerV2_5(config_manager)
    orchestrator = ITSOrchestratorV2_5(
        config_manager,
        historical_data_manager,
        performance_tracker,
        metrics_calculator,
        initial_processor,
        market_regime_engine,
        signal_generator,
        adaptive_trade_idea_framework,
        trade_parameter_optimizer
    )
    return orchestrator

def main():
    config_manager = ConfigManagerV2_5()
    collector_cfg = config_manager.config.intraday_collector_settings
    watched_tickers = collector_cfg.watched_tickers
    gauge_metrics = collector_cfg.metrics
    cache_dir = Path(collector_cfg.cache_dir)
    collection_interval = collector_cfg.collection_interval_seconds
    market_open = collector_cfg.market_open_time
    market_close = collector_cfg.market_close_time
    reset_at_eod = collector_cfg.reset_at_eod
    calibration_threshold = getattr(collector_cfg, 'calibration_threshold', 25)
    calibrated_pairs = set()

    logger.info(f"Loaded intraday collector config: {collector_cfg}")

    def clear_intraday_cache():
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Intraday cache cleared for new trading day.")
        calibrated_pairs.clear()

    orchestrator = build_orchestrator()
    last_reset_date = None
    while True:
        today = datetime.now().date()
        if last_reset_date != today:
            clear_intraday_cache()
            last_reset_date = today
        if is_market_open():
            for symbol in watched_tickers:
                try:
                    logger.info(f"Processing {symbol}...")
                    bundle = orchestrator.run_full_analysis_cycle(symbol)
                    logger.info(f"Completed {symbol}.")
                    # Extract enriched underlying data
                    und_data = None
                    if bundle and hasattr(bundle, 'processed_data_bundle') and bundle.processed_data_bundle is not None:
                        und_data = getattr(bundle.processed_data_bundle, 'underlying_data_enriched', None)
                        if und_data is not None and hasattr(und_data, 'model_dump'):
                            und_data = und_data.model_dump()
                    if not und_data:
                        logger.warning(f"No underlying data for {symbol}, skipping metric collection.")
                        continue
                    today = datetime.now().strftime('%Y-%m-%d')
                    for metric in gauge_metrics:
                        value = und_data.get(metric, None)
                        if value is None:
                            logger.warning(f"Metric {metric} missing for {symbol}.")
                            continue
                        # Always store as a list for histories/arrays, wrap scalars
                        if isinstance(value, (list, tuple)):
                            values = list(value)
                        elif isinstance(value, dict):
                            # For dicts (e.g., rolling_flows, greek_flows, flow_ratios), store as-is
                            values = value
                        else:
                            values = [value]
                        cache_file = cache_dir / f"{symbol}_{metric}_{today}.json"
                        try:
                            cache_data = {
                                'date': today,
                                'values': values,
                                'last_updated': datetime.now().isoformat()
                            }
                            with open(cache_file, 'w') as f:
                                json.dump(cache_data, f)
                            sample_count = len(values) if isinstance(values, list) else (len(values) if hasattr(values, '__len__') else 1)
                            pair_key = (symbol, metric)
                            if sample_count >= calibration_threshold and pair_key not in calibrated_pairs:
                                logger.info(f"Metric for {symbol} ({metric}) is now fully calibrated with {sample_count} samples.")
                                calibrated_pairs.add(pair_key)
                        except Exception as e:
                            logger.warning(f"Could not store/check calibration for {symbol} {metric}: {e}")
                except Exception as e:
                    logger.error(f"Error processing {symbol}: {e}")
            time.sleep(collection_interval)
        else:
            logger.info("Market closed. Sleeping until next check.")
            time.sleep(60 * 10)  # Sleep 10 minutes when market is closed

if __name__ == "__main__":
    main() 