#!/usr/bin/env python3
"""
Quick configuration validation test
"""

import json
import sys
from pathlib import Path

try:
    # Load the configuration file
    config_path = Path("config/config_v2_5.json")
    
    with open(config_path, 'r') as f:
        config_data = json.load(f)
    
    print("✅ JSON parsing successful!")
    print(f"📊 Configuration has {len(config_data)} top-level sections:")
    
    for section_name in config_data.keys():
        print(f"  - {section_name}")
    
    # Try importing the Pydantic model
    try:
        sys.path.insert(0, str(Path.cwd()))
        from data_models.eots_schemas_v2_5 import EOTSConfigV2_5
        
        # Validate against Pydantic model
        validated_config = EOTSConfigV2_5(**config_data)
        
        print("\n🎯 Pydantic validation successful!")
        print("✅ Configuration is now compatible with the system!")
        
    except ImportError as e:
        print(f"\n⚠️  Could not import Pydantic model: {e}")
        print("JSON structure looks good, but Pydantic validation skipped.")
    except Exception as e:
        print(f"\n❌ Pydantic validation failed: {e}")
        print(f"Error type: {type(e).__name__}")
        
except FileNotFoundError as e:
    print(f"❌ Configuration file not found: {e}")
except json.JSONDecodeError as e:
    print(f"❌ JSON parsing error: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    print(f"Error type: {type(e).__name__}")