#!/usr/bin/env python3
"""
PYDANTIC COMPLIANCE FIX SCRIPT
EOTS v2.5 - Emergency Repair for Dictionary-Style Access Issues

This script identifies and fixes all .get() method calls that should be 
Pydantic attribute access in the core analytics engine.
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PydanticComplianceFixer:
    """Fixes Pydantic compliance issues across the codebase."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.core_analytics_path = self.project_root / "core_analytics_engine"
        
        # Patterns to identify problematic code
        self.problematic_patterns = [
            r'\.get\(',  # Dictionary-style .get() calls
            r'config\.get\(',  # Config dictionary access
            r'settings\.get\(',  # Settings dictionary access
            r'reco_config\.get\(',  # Recommendation config dictionary access
        ]
        
        # Known Pydantic model mappings
        self.pydantic_mappings = {
            'TickerContextAnalyzerSettings': {
                'lookback_days': 'lookback_days',
                'correlation_window': 'correlation_window',
                'volatility_windows': 'volatility_windows',
                'volume_threshold': 'volume_threshold',
                'use_yahoo_finance': 'use_yahoo_finance',
                'yahoo_finance_rate_limit_seconds': 'yahoo_finance_rate_limit_seconds'
            },
            'AdaptiveTradeIdeaFrameworkSettings': {
                'strategy_specificity_rules': 'strategy_specificity_rules',
                'signal_integration_params': 'signal_integration_params',
                'conviction_mapping_params': 'conviction_mapping_params'
            },
            'SystemSettings': {
                'signal_activation': 'signal_activation'
            }
        }
        
    def scan_files(self) -> Dict[str, List[Tuple[int, str]]]:
        """Scan all Python files in core analytics engine for problematic patterns."""
        issues = {}
        
        for py_file in self.core_analytics_path.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
                
            file_issues = []
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    
                for line_num, line in enumerate(lines, 1):
                    for pattern in self.problematic_patterns:
                        if re.search(pattern, line):
                            file_issues.append((line_num, line.strip()))
                            
                if file_issues:
                    issues[str(py_file)] = file_issues
                    
            except Exception as e:
                logger.error(f"Error scanning {py_file}: {e}")
                
        return issues
    
    def generate_fix_recommendations(self, issues: Dict[str, List[Tuple[int, str]]]) -> Dict[str, List[str]]:
        """Generate specific fix recommendations for each file."""
        recommendations = {}
        
        for file_path, file_issues in issues.items():
            file_name = Path(file_path).name
            file_recommendations = []
            
            file_recommendations.append(f"=== PYDANTIC COMPLIANCE FIXES FOR {file_name} ===")
            file_recommendations.append("")
            
            # Group issues by type
            config_gets = []
            settings_gets = []
            general_gets = []
            
            for line_num, line in file_issues:
                if 'config.get(' in line:
                    config_gets.append((line_num, line))
                elif 'settings.get(' in line:
                    settings_gets.append((line_num, line))
                elif '.get(' in line:
                    general_gets.append((line_num, line))
            
            # Generate specific recommendations
            if config_gets:
                file_recommendations.append("1. CONFIG.GET() FIXES:")
                file_recommendations.append("   Replace with isinstance() check and direct attribute access:")
                file_recommendations.append("   ```python")
                file_recommendations.append("   if isinstance(config, PydanticModelType):")
                file_recommendations.append("       value = config.attribute_name")
                file_recommendations.append("   else:")
                file_recommendations.append("       value = config.get('attribute_name', default)")
                file_recommendations.append("   ```")
                file_recommendations.append("")
                
            if settings_gets:
                file_recommendations.append("2. SETTINGS.GET() FIXES:")
                file_recommendations.append("   Replace with hasattr() check and getattr():")
                file_recommendations.append("   ```python")
                file_recommendations.append("   if hasattr(settings, '__fields__'):")
                file_recommendations.append("       value = getattr(settings, 'attribute_name', default)")
                file_recommendations.append("   else:")
                file_recommendations.append("       value = settings.get('attribute_name', default)")
                file_recommendations.append("   ```")
                file_recommendations.append("")
            
            if general_gets:
                file_recommendations.append("3. GENERAL .GET() FIXES:")
                file_recommendations.append("   Review each case individually - may be legitimate dictionary access")
                file_recommendations.append("")
            
            # List specific lines that need fixing
            file_recommendations.append("SPECIFIC LINES TO FIX:")
            for line_num, line in file_issues:
                file_recommendations.append(f"   Line {line_num}: {line}")
            
            file_recommendations.append("")
            recommendations[file_path] = file_recommendations
            
        return recommendations
    
    def create_fix_template(self, file_path: str) -> str:
        """Create a template fix for a specific file."""
        file_name = Path(file_path).name
        
        if "ticker_context_analyzer" in file_name:
            return self._create_ticker_context_fix()
        elif "signal_generator" in file_name:
            return self._create_signal_generator_fix()
        elif "recommendation_logic" in file_name:
            return self._create_recommendation_logic_fix()
        elif "trade_parameter_optimizer" in file_name:
            return self._create_trade_parameter_optimizer_fix()
        else:
            return self._create_generic_fix()
    
    def _create_ticker_context_fix(self) -> str:
        return """
# TICKER CONTEXT ANALYZER PYDANTIC FIX
def __init__(self, config: Union[TickerContextAnalyzerSettings, Dict[str, Any]]):
    if isinstance(config, TickerContextAnalyzerSettings):
        # Direct Pydantic attribute access
        self.lookback_days = config.lookback_days
        self.correlation_window = config.correlation_window
        self.volatility_windows = config.volatility_windows
        self.volume_threshold = config.volume_threshold
        self.use_yahoo_finance = config.use_yahoo_finance
        self.yahoo_finance_rate_limit = config.yahoo_finance_rate_limit_seconds
    else:
        # Dictionary fallback
        self.lookback_days = config.get('lookback_days', 252)
        self.correlation_window = config.get('correlation_window', 60)
        self.volatility_windows = config.get('volatility_windows', [1, 5, 20])
        self.volume_threshold = config.get('volume_threshold', 1000000)
        self.use_yahoo_finance = config.get('use_yahoo_finance', False)
        self.yahoo_finance_rate_limit = config.get('yahoo_finance_rate_limit_seconds', 2.0)
"""
    
    def _create_signal_generator_fix(self) -> str:
        return """
# SIGNAL GENERATOR PYDANTIC FIX
def __init__(self, config_manager: ConfigManagerV2_5):
    self.config_manager = config_manager
    system_settings = config_manager.config.system_settings
    
    # Pydantic attribute access
    if hasattr(system_settings, 'signal_activation'):
        self.activation = system_settings.signal_activation
    else:
        self.activation = {"EnableAllSignals": True}
"""
    
    def _create_recommendation_logic_fix(self) -> str:
        return """
# RECOMMENDATION LOGIC PYDANTIC FIX
def _get_conviction_modifiers_config(self):
    # Check if reco_config is Pydantic model
    if hasattr(self.reco_config, '__fields__'):
        return getattr(self.reco_config, 'conviction_modifiers', {})
    else:
        return self.reco_config.get("conviction_modifiers", {})

def _get_star_thresholds_config(self):
    if hasattr(self.reco_config, '__fields__'):
        return getattr(self.reco_config, 'star_thresholds', {})
    else:
        return self.reco_config.get("star_thresholds", {})
"""
    
    def _create_trade_parameter_optimizer_fix(self) -> str:
        return """
# TRADE PARAMETER OPTIMIZER PYDANTIC FIX
def _get_setting_value(self, key: str, default):
    if hasattr(self.settings, '__fields__'):
        return getattr(self.settings, key, default)
    else:
        return self.settings.get(key, default)

# Usage:
sl_mult = self._get_setting_value("target_atr_stop_loss_multiplier", 1.5)
t1_mult = self._get_setting_value("t1_mult_no_sr", 1.0)
t2_mult = self._get_setting_value("t2_mult_no_sr", 2.0)
"""
    
    def _create_generic_fix(self) -> str:
        return """
# GENERIC PYDANTIC COMPLIANCE FIX
def _safe_get_config_value(self, config_obj, key: str, default=None):
    '''Safely get value from either Pydantic model or dictionary'''
    if hasattr(config_obj, '__fields__'):
        # Pydantic model
        return getattr(config_obj, key, default)
    else:
        # Dictionary
        return config_obj.get(key, default)
"""

def main():
    """Main execution function."""
    logger.info("🔍 Starting Pydantic Compliance Analysis...")
    
    # Initialize fixer
    project_root = os.getcwd()  # Assumes script is run from project root
    fixer = PydanticComplianceFixer(project_root)
    
    # Scan for issues
    logger.info("📁 Scanning core analytics engine files...")
    issues = fixer.scan_files()
    
    if not issues:
        logger.info("✅ No Pydantic compliance issues found!")
        return
    
    # Generate recommendations
    logger.info(f"⚠️  Found issues in {len(issues)} files")
    recommendations = fixer.generate_fix_recommendations(issues)
    
    # Write comprehensive report
    report_path = Path(project_root) / "pydantic_compliance_report.md"
    with open(report_path, 'w') as f:
        f.write("# PYDANTIC COMPLIANCE CRISIS REPORT\n")
        f.write("## EOTS v2.5 - Emergency Repair Documentation\n\n")
        f.write(f"**Total Files with Issues:** {len(issues)}\n")
        f.write(f"**Total Issues Found:** {sum(len(file_issues) for file_issues in issues.values())}\n\n")
        
        f.write("## CRITICAL ISSUES BY FILE\n\n")
        for file_path, file_recommendations in recommendations.items():
            for line in file_recommendations:
                f.write(line + "\n")
            f.write("\n" + "="*80 + "\n\n")
        
        f.write("## SYSTEMATIC FIX APPROACH\n\n")
        f.write("1. **IMMEDIATE**: Fix core analytics engine components\n")
        f.write("2. **SECONDARY**: Fix dashboard and utility components\n")
        f.write("3. **VALIDATION**: Run comprehensive tests\n")
        f.write("4. **VERIFICATION**: Ensure no regression in functionality\n\n")
        
        f.write("## TEMPLATE FIXES\n\n")
        for file_path in issues.keys():
            f.write(f"### {Path(file_path).name}\n")
            f.write("```python\n")
            f.write(fixer.create_fix_template(file_path))
            f.write("\n```\n\n")
    
    logger.info(f"📋 Comprehensive report written to: {report_path}")
    
    # Print summary
    print("\n" + "="*80)
    print("🚨 PYDANTIC COMPLIANCE CRISIS SUMMARY")
    print("="*80)
    print(f"Files with issues: {len(issues)}")
    print(f"Total issues: {sum(len(file_issues) for file_issues in issues.values())}")
    print("\nMost problematic files:")
    
    sorted_issues = sorted(issues.items(), key=lambda x: len(x[1]), reverse=True)
    for file_path, file_issues in sorted_issues[:5]:
        print(f"  {Path(file_path).name}: {len(file_issues)} issues")
    
    print(f"\n📋 Full report: {report_path}")
    print("="*80)

if __name__ == "__main__":
    main() 