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
    else:
        print("ERROR: Could not find window._initialData in the HTML file")
        sys.exit(1)


def main():

    html_file = sys.argv[1] if len(
        sys.argv) > 1 else r".\TEST_DATA\test-1-ind.htm"

    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    if output_file is None:
        # Generate output filename from input filename
        base = os.path.splitext(os.path.basename(html_file))[0]

    output_file = os.path.join(os.path.dirname(html_file) or ".", f"{base}_initial_data.json")

    extract_json_data_ind(html_file, output_file)

    # Your primary code logic goes here
    print("Hello from the main function!")

if __name__ == "__main__":
    main()