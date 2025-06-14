#!/usr/bin/env python3
import json
import jsonschema

def quick_validate():
    try:
        with open('config/config.schema.v2_5.json', 'r') as f:
            schema = json.load(f)
        
        with open('config/config_v2_5.json', 'r') as f:
            config = json.load(f)
        
        jsonschema.validate(config, schema)
        print("✅ Config is valid!")
        return True
        
    except jsonschema.ValidationError as e:
        print(f"❌ Validation Error: {e.message}")
        print(f"Failed at path: {' -> '.join(str(p) for p in e.absolute_path)}")
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    quick_validate()