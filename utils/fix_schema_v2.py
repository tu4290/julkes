import json
import os

def fix_schema():
    # Change to config directory
    os.chdir(os.path.dirname(os.path.dirname(__file__)) + '/config')
    
    # Read the current schema
    with open('config.schema.v2_5.json', 'r', encoding='utf-8') as f:
        schema_text = f.read()
    
    # Clean up the text
    schema_text = schema_text.replace('\\', '/')  # Normalize path separators
    schema_text = schema_text.strip()  # Remove leading/trailing whitespace
    
    # Remove any extra whitespace and normalize
    schema_text = '\n'.join(line.strip() for line in schema_text.split('\n') if line.strip())
    
    # Fix JSON syntax issues
    schema_text = schema_text.replace(',,', ',')  # Remove duplicate commas
    schema_text = schema_text.replace(',}', '}')  # Remove trailing commas
    schema_text = schema_text.replace(',]', ']')  # Remove trailing commas
    
    # Try to load and validate
    try:
        schema = json.loads(schema_text)
        # Write back the validated schema
        with open('config.schema.v2_5.json', 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        print("Schema fixed successfully!")
    except json.JSONDecodeError as e:
        print(f"Error fixing schema: {e}")
        print("Schema content preview:")
        print(schema_text[:200])

if __name__ == "__main__":
    fix_schema()
