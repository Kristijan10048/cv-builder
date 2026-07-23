import re
import json
import sys
import os

def extract_json_data_ind(html_file, output_file):
    """Extract JSON data from saved HTML file."""

    with open(html_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract the JSON object from window._initialData
    match = re.search(r'window\._initialData=(\{.*?\});', content, re.DOTALL)

    if match:
        json_str = match.group(1)
        data = json.loads(json_str)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Successfully extracted JSON to {output_file}")
        print(f"Top-level keys: {list(data.keys())}")
        return data
    else:
        print("ERROR: Could not find window._initialData in the HTML file")
        sys.exit(1)


def is_url(value):
    """Check if a string value looks like a URL."""
    if not isinstance(value, str):
        return False
    return value.startswith(("http://", "https://", "ftp://", "ftps://"))


def remove_null_values(data):
    """Recursively remove null (None) values and URLs from a dictionary or list."""
    if isinstance(data, dict):
        return {
            k: remove_null_values(v)
            for k, v in data.items()
            if v is not None and not is_url(v)
        }
    elif isinstance(data, list):
        return [remove_null_values(item) for item in data if item is not None and not is_url(item)]
    else:
        return data


def remove_null_json(input_file, output_file):
    """Load JSON from input file, remove null values, and save to output file."""

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    cleaned_data = remove_null_values(data)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully saved cleaned JSON to {output_file}")
    return cleaned_data


def main():

    html_file = sys.argv[1] if len(
        sys.argv) > 1 else r".\TEST_DATA\test-1-ind.htm"

    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    if output_file is None:
        # Generate output filename from input filename
        base = os.path.splitext(os.path.basename(html_file))[0]

    output_file = os.path.join(os.path.dirname(html_file) or ".", f"{base}_initial_data.json")

    extract_json_data_ind(html_file, output_file)

    # Remove null values and save to pass1 file
    pass1_output = os.path.join(
        os.path.dirname(output_file) or ".",
        os.path.splitext(os.path.basename(output_file))[0] + "_pass1.json"
    )
    remove_null_json(output_file, pass1_output)

    # Your primary code logic goes here
    print("Hello from the main function!")

if __name__ == "__main__":
    main()