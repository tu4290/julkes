#!/usr/bin/env python3
"""
Script to inspect the .pyc file and extract class information
"""

import sys
import os
import inspect
import types

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # Import the module from the .pyc file
    import data_models.eots_schemas_v2_5 as schemas
    
    print("Module loaded successfully!")
    print(f"Module file: {schemas.__file__}")
    print(f"Module dict keys: {list(schemas.__dict__.keys())}")
    
    print("\nAll attributes (including private):")
    all_attrs = dir(schemas)
    for attr_name in sorted(all_attrs):
        attr = getattr(schemas, attr_name)
        print(f"  {attr_name}: {type(attr).__name__}")
    
    print("\nClasses found:")
    for name, obj in inspect.getmembers(schemas, inspect.isclass):
        print(f"\nClass: {name}")
        print(f"  Type: {type(obj)}")
        print(f"  Module: {obj.__module__}")
        print(f"  Bases: {[base.__name__ for base in obj.__bases__]}")
        
        # Try to get source or at least signature
        try:
            source = inspect.getsource(obj)
            print(f"  Source available: Yes ({len(source)} chars)")
        except:
            print(f"  Source available: No")
        
        # Get class attributes
        if hasattr(obj, '__annotations__'):
            print(f"  Annotations: {obj.__annotations__}")
        
        if hasattr(obj, '__dict__'):
            class_attrs = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
            if class_attrs:
                print(f"  Class attributes: {list(class_attrs.keys())}")
    
    print("\nFunctions found:")
    for name, obj in inspect.getmembers(schemas, inspect.isfunction):
        print(f"  Function: {name}")
    
except ImportError as e:
    print(f"Failed to import module: {e}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()