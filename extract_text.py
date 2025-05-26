#!./.venv/bin/python
import sys
import os
from eyecite_extractor import extract_text_from_pdf, normalize_whitespace

def extract_text(pdf_path):
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    text = extract_text_from_pdf(pdf_path)
    with open(f'{base_name}_extracted.txt', 'w') as f:
        f.write(text)

    cleaned = normalize_whitespace(text)
    with open(f'{base_name}_cleaned.txt', 'w') as f:
        f.write(cleaned)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: extract_text.py <pdf_path>')
        sys.exit(1)
    extract_text(sys.argv[1])
    base_name = os.path.splitext(os.path.basename(sys.argv[1]))[0]
    print(f'Extraction complete. Check {base_name}_extracted.txt and {base_name}_cleaned.txt')