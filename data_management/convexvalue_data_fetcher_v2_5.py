# data_management/convexvalue_data_fetcher_v2_5.py
# EOTS v2.5 - SENTRY-APPROVED, CANONICAL V2.5.3 IMPLEMENTATION (FIXED FOR CONVEXVALUE API)

import logging
import os
from datetime import datetime, date
from typing import Any, Dict, List, Tuple, Optional
import asyncio
import concurrent.futures

# Import ConvexValue Python API
from convexlib.api import ConvexApi

from utils.config_manager_v2_5 import ConfigManagerV2_5
from data_models.eots_schemas_v2_5 import RawOptionsContractV2_5, RawUnderlyingDataCombinedV2_5

logger = logging.getLogger(__name__)

# --- CANONICAL PARAMETER LISTS (UNABRIDGED) ---
# As provided by Prime Operator. This is the ground truth.
UNDERLYING_REQUIRED_PARAMS: List[str] = [
    "price", "volatility", "day_volume", "call_gxoi", "put_gxoi",
    "gammas_call_buy", "gammas_call_sell", "gammas_put_buy", "gammas_put_sell",
    "deltas_call_buy", "deltas_call_sell", "deltas_put_buy", "deltas_put_sell",
    "vegas_call_buy", "vegas_call_sell", "vegas_put_buy", "vegas_put_sell",
    "thetas_call_buy", "thetas_call_sell", "thetas_put_buy", "thetas_put_sell",
    "call_vxoi", "put_vxoi", "value_bs", "volm_bs", "deltas_buy", "deltas_sell",
    "vegas_buy", "vegas_sell", "thetas_buy", "thetas_sell", "volm_call_buy",
    "volm_put_buy", "volm_call_sell", "volm_put_sell", "value_call_buy",
    "value_put_buy", "value_call_sell", "value_put_sell", "vflowratio",
    "dxoi", "gxoi", "vxoi", "txoi", "call_dxoi", "put_dxoi"
]

OPTIONS_CHAIN_REQUIRED_PARAMS: List[str] = [
  "price", "volatility", "multiplier", "oi", "delta", "gamma", "theta", "vega",
  "vanna", "vomma", "charm", "dxoi", "gxoi", "vxoi", "txoi", "vannaxoi", "vommaxoi", "charmxoi",
  "dxvolm", "gxvolm", "vxvolm", "txvolm", "vannaxvolm", "vommaxvolm", "charmxvolm",
  "value_bs", "volm_bs", "deltas_buy", "deltas_sell", "gammas_buy", "gammas_sell",
  "vegas_buy", "vegas_sell", "thetas_buy", "thetas_sell",
  "valuebs_5m", "volmbs_5m", "valuebs_15m", "volmbs_15m",
  "valuebs_30m", "volmbs_30m", "valuebs_60m", "volmbs_60m",
  "volm", "volm_buy", "volm_sell", "value_buy", "value_sell"
]


class ConvexValueDataFetcherV2_5:
    """
    Data fetcher for ConvexValue using the official Python API library.
    Replaces the incorrect web API implementation with proper ConvexValue integration.
    """
    def __init__(self, config_manager: ConfigManagerV2_5):
        self.logger = logger.getChild(self.__class__.__name__)
        self.config_manager = config_manager
        self.timeout = self.config_manager.get_setting("data_fetcher_settings.timeout", 30.0)
        self.email = os.getenv("CONVEX_EMAIL")
        self.password = os.getenv("CONVEX_PASSWORD")
        
        # Initialize ConvexValue API client
        self.convex_api = None
        self.authenticated = False
        
        if not self.email or not self.password:
            self.logger.warning("ConvexValue email or password not found in environment variables. API calls will fail.")
        else:
            try:
                # Initialize ConvexValue API with credentials
                # Use "pro" or "live" depending on your subscription
                self.convex_api = ConvexApi(self.email, self.password, "pro")
                self.authenticated = True
                self.logger.info("✅ ConvexValue API client initialized successfully")
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize ConvexValue API: {str(e)}")
                self.authenticated = False
        
        self.logger.info("ConvexValueDataFetcherV2_5 initialized.")

    def _convert_underlying_to_model(self, symbol: str, raw_data: Any) -> Optional[RawUnderlyingDataCombinedV2_5]:
        """Convert ConvexValue underlying data to our internal model."""
        try:
            # ConvexValue API can return data in different formats
            # Handle both dict format and direct list format
            if isinstance(raw_data, dict):
                if 'data' not in raw_data or not raw_data['data']:
                    self.logger.error(f"No data returned for underlying {symbol}")
                    return None
                data_rows = raw_data['data']
            elif isinstance(raw_data, list):
                data_rows = raw_data
            else:
                self.logger.error(f"Unexpected data format for underlying {symbol}: {type(raw_data)}")
                return None
            
            # Extract the data row for our symbol
            symbol_data = None
            
            for row in data_rows:
                if row and len(row) > 0:
                    # Try exact match first
                    if str(row[0]).upper() == symbol.upper():
                        symbol_data = row
                        break
                    # Try partial match for different symbol formats
                    elif symbol.upper() in str(row[0]).upper() or str(row[0]).upper() in symbol.upper():
                        symbol_data = row
                        break
            
            if not symbol_data:
                self.logger.error(f"Symbol {symbol} not found in underlying data. Available: {[row[0] if row and len(row) > 0 else 'None' for row in data_rows[:3]]}")
                return None
            
            # Map the data to our parameter names
            # The order matches the params we requested
            param_values = {}
            for i, param in enumerate(UNDERLYING_REQUIRED_PARAMS):
                if i + 1 < len(symbol_data):  # +1 because first element is symbol
                    value = symbol_data[i + 1]
                    # Convert None values to 0 for numeric calculations
                    if value is None:
                        param_values[param] = 0.0
                    else:
                        param_values[param] = float(value) if isinstance(value, (int, float, str)) and str(value).replace('.', '').replace('-', '').isdigit() else 0.0
                else:
                    param_values[param] = 0.0
            
            # Create the model
            model_data = {
                'symbol': symbol,
                'timestamp': datetime.now(),
                **param_values
            }
            
            return RawUnderlyingDataCombinedV2_5(**model_data)
            
        except Exception as e:
            self.logger.error(f"Error converting underlying data for {symbol}: {str(e)}")
            return None

    def _convert_chain_to_models(self, symbol: str, raw_data: Any) -> List[RawOptionsContractV2_5]:
        """Convert ConvexValue options chain data to our internal models."""
        try:
            contracts = []
            
            # Handle both dict format and direct list format
            if isinstance(raw_data, dict):
                if 'data' not in raw_data or not raw_data['data']:
                    self.logger.warning(f"No options chain data returned for {symbol}")
                    return contracts
                data_rows = raw_data['data']
            elif isinstance(raw_data, list):
                data_rows = raw_data
            else:
                self.logger.warning(f"Unexpected chain data format for {symbol}: {type(raw_data)}")
                return contracts
            
            # ConvexValue returns chain data as rows: [symbol, expiration, strike, kind, ...params]
            for row in data_rows:
                try:
                    if len(row) < 4:
                        continue
                    
                    contract_symbol = row[0]
                    expiration = row[1]
                    strike = row[2]
                    opt_kind = row[3]
                    
                    # Map remaining values to parameters
                    param_values = {}
                    for i, param in enumerate(OPTIONS_CHAIN_REQUIRED_PARAMS):
                        if i + 4 < len(row):  # +4 because first 4 elements are metadata
                            value = row[i + 4]
                            # Convert None values to 0 for numeric calculations
                            if value is None:
                                param_values[param] = 0.0
                            else:
                                param_values[param] = float(value) if isinstance(value, (int, float, str)) and str(value).replace('.', '').replace('-', '').isdigit() else 0.0
                        else:
                            param_values[param] = 0.0
                    
                    # Calculate days to expiration
                    from datetime import datetime
                    try:
                        exp_datetime = datetime.strptime(expiration, '%Y-%m-%d')
                        current_datetime = datetime.now()
                        dte_calc = (exp_datetime - current_datetime).days
                    except:
                        dte_calc = 0  # Default if calculation fails
                    
                    # Create contract model
                    contract_data = {
                        'contract_symbol': contract_symbol,
                        'strike': float(strike) if strike else 0.0,
                        'opt_kind': opt_kind,
                        'dte_calc': dte_calc,  # Required field!
                        # Map ConvexValue fields to schema fields with explicit field mapping
                        'open_interest': param_values.get('oi', 0.0),
                        'iv': param_values.get('volatility', 0.0),
                        'raw_price': param_values.get('price', 0.0),
                        'delta_contract': param_values.get('delta', 0.0),
                        'gamma_contract': param_values.get('gamma', 0.0),
                        'theta_contract': param_values.get('theta', 0.0),
                        'vega_contract': param_values.get('vega', 0.0),
                        'vanna_contract': param_values.get('vanna', 0.0),
                        'vomma_contract': param_values.get('vomma', 0.0),
                        'charm_contract': param_values.get('charm', 0.0),
                        # Explicit mapping for critical OI-based Greeks
                        'dxoi': param_values.get('dxoi', 0.0),
                        'gxoi': param_values.get('gxoi', 0.0),
                        'vxoi': param_values.get('vxoi', 0.0),
                        'txoi': param_values.get('txoi', 0.0),
                        'vannaxoi': param_values.get('vannaxoi', 0.0),
                        'vommaxoi': param_values.get('vommaxoi', 0.0),
                        'charmxoi': param_values.get('charmxoi', 0.0),
                        # Flow data
                        'value_bs': param_values.get('value_bs', 0.0),
                        'volm_bs': param_values.get('volm_bs', 0.0),
                        'volm': param_values.get('volm', 0.0),
                        # Rolling flows
                        'valuebs_5m': param_values.get('valuebs_5m', 0.0),
                        'volmbs_5m': param_values.get('volmbs_5m', 0.0),
                        'valuebs_15m': param_values.get('valuebs_15m', 0.0),
                        'volmbs_15m': param_values.get('volmbs_15m', 0.0),
                        'valuebs_30m': param_values.get('valuebs_30m', 0.0),
                        'volmbs_30m': param_values.get('volmbs_30m', 0.0),
                        'valuebs_60m': param_values.get('valuebs_60m', 0.0),
                        'volmbs_60m': param_values.get('volmbs_60m', 0.0),
                        # Additional parameters from the schema
                        **{k: v for k, v in param_values.items() if k not in [
                            'oi', 'volatility', 'price', 'delta', 'gamma', 'theta', 'vega',
                            'vanna', 'vomma', 'charm', 'dxoi', 'gxoi', 'vxoi', 'txoi',
                            'vannaxoi', 'vommaxoi', 'charmxoi', 'value_bs', 'volm_bs', 'volm',
                            'valuebs_5m', 'volmbs_5m', 'valuebs_15m', 'volmbs_15m',
                            'valuebs_30m', 'volmbs_30m', 'valuebs_60m', 'volmbs_60m'
                        ]}
                    }
                    
                    contract = RawOptionsContractV2_5(**contract_data)
                    contracts.append(contract)
                    
                except Exception as e:
                    self.logger.warning(f"Error parsing contract row: {str(e)}")
                    continue
            
            self.logger.info(f"Successfully converted {len(contracts)} contracts for {symbol}")
            return contracts
            
        except Exception as e:
            self.logger.error(f"Error converting chain data for {symbol}: {str(e)}")
            return []

    async def fetch_chain_and_underlying(self, session, symbol: str, dte_min: int = 0, dte_max: int = 45, price_range_percent: int = 20) -> Tuple[Optional[List[RawOptionsContractV2_5]], Optional[RawUnderlyingDataCombinedV2_5]]:
        """
        Fetch both options chain and underlying data for a symbol using ConvexValue API.
        Note: session parameter is kept for compatibility but not used with ConvexValue API.
        
        Args:
            session: Kept for compatibility (not used)
            symbol: The ticker symbol to fetch data for
            dte_min: Minimum days to expiration filter
            dte_max: Maximum days to expiration filter
            price_range_percent: Strike price range percentage around current price
        """
        if not self.authenticated or not self.convex_api:
            self.logger.error("ConvexValue API not authenticated or initialized")
            return None, None
        
        executor = None
        try:
            self.logger.info(f"🔄 Fetching ConvexValue data for {symbol} with DTE range [{dte_min}, {dte_max}] and price range ±{price_range_percent}%...")
            
            # Fetch underlying data in thread executor (since ConvexValue API is synchronous)
            underlying_data = None
            try:
                self.logger.debug(f"Requesting underlying data for {symbol}")
                
                # Run synchronous ConvexValue API call in thread executor
                def fetch_underlying():
                    if self.convex_api is not None:
                        return self.convex_api.get_und(
                            symbols=[symbol], 
                            params=UNDERLYING_REQUIRED_PARAMS
                        )
                    return None
                
                loop = asyncio.get_event_loop()
                executor = concurrent.futures.ThreadPoolExecutor()
                und_response = await loop.run_in_executor(executor, fetch_underlying)
                
                underlying_data = self._convert_underlying_to_model(symbol, und_response)
                if underlying_data:
                    self.logger.info(f"✅ Successfully fetched underlying data for {symbol}")
                else:
                    self.logger.warning(f"⚠️ No underlying data returned for {symbol}")
            except Exception as e:
                self.logger.error(f"❌ Error fetching underlying data for {symbol}: {str(e)}")
            
            # Fetch options chain data in thread executor
            chain_data = None
            try:
                self.logger.debug(f"Requesting options chain for {symbol} with DTE range [{dte_min}, {dte_max}] and price range ±{price_range_percent}%")
                
                def fetch_chain():
                    if self.convex_api is not None:
                        # Convert price range percentage to decimal (e.g., 20% -> 0.20)
                        price_range_decimal = price_range_percent / 100.0
                        
                        # Calculate number of expirations to fetch based on DTE range
                        # For now, we'll fetch more expirations and filter later
                        # ConvexValue API doesn't directly support DTE filtering, so we'll get more data and filter
                        max_expirations = min(10, max(3, (dte_max // 7) + 1))  # Estimate based on weekly expirations
                        
                        self.logger.info(f"🔍 ConvexValue API call: symbol={symbol}, exps={max_expirations}, rng={price_range_decimal}")
                        
                        return self.convex_api.get_chain_as_rows(
                            symbol,
                            params=OPTIONS_CHAIN_REQUIRED_PARAMS,
                            exps=list(range(1, max_expirations + 1)),  # Get multiple expirations
                            rng=price_range_decimal  # Use control panel price range
                        )
                    return None
                
                loop = asyncio.get_event_loop()
                if executor is None:
                    executor = concurrent.futures.ThreadPoolExecutor()
                chain_response = await loop.run_in_executor(executor, fetch_chain)
                
                # Convert and filter the chain data
                all_chain_data = self._convert_chain_to_models(symbol, {'data': chain_response})
                
                # Filter by DTE range if we have data
                if all_chain_data:
                    chain_data = [
                        contract for contract in all_chain_data 
                        if dte_min <= contract.dte_calc <= dte_max
                    ]
                    
                    self.logger.info(f"✅ Successfully fetched {len(all_chain_data)} total contracts, {len(chain_data)} after DTE filtering [{dte_min}, {dte_max}] for {symbol}")
                else:
                    self.logger.warning(f"⚠️ No options chain data returned for {symbol}")
                    chain_data = []
            except Exception as e:
                self.logger.error(f"❌ Error fetching options chain for {symbol}: {str(e)}")
                chain_data = []
            
            return chain_data, underlying_data
            
        except Exception as e:
            self.logger.error(f"❌ Critical error in ConvexValue data fetch for {symbol}: {str(e)}")
            return None, None
        finally:
            # CRITICAL FIX: Properly shutdown ThreadPoolExecutor to prevent 'futures after interpreter shutdown'
            if executor is not None:
                try:
                    executor.shutdown(wait=True, cancel_futures=True)
                except Exception as cleanup_error:
                    self.logger.warning(f"Error during executor cleanup: {cleanup_error}")

    # Legacy method for compatibility
    async def authenticate(self, session) -> bool:
        """Legacy authentication method for compatibility."""
        return self.authenticated