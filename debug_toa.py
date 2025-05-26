#!./.venv/bin/python

import re
import sys

def debug_toa(text):
    """Debug the Table of Authorities boundary detection logic."""
    lines = text.split('\n')
    
    # Original complex pattern
    complex_dot_re = re.compile(r'\.{3,}\s*\d+(?:[,\s]+\d+)*\s*$')
    
    # Simple pattern
    simple_dot_re = re.compile(r'\.{5,}\s*\d')
    
    print("Analyzing each line for dot leader patterns...")
    print("Line  | Cplx | Smpl | Content")
    print("-" * 80)
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        has_complex_pattern = bool(complex_dot_re.search(stripped))
        has_simple_pattern = bool(simple_dot_re.search(stripped))
        
        status = f"{i+1:4} | {'✓' if has_complex_pattern else '✗'} | {'✓' if has_simple_pattern else '✗'} | {stripped[:60]}"
        print(status + ("..." if len(stripped) > 60 else ""))
        
        # If patterns disagree, show details
        if has_complex_pattern != has_simple_pattern:
            if has_simple_pattern:
                print(f"  SIMPLE ONLY: Line matches only with simple pattern")
                match = simple_dot_re.search(stripped)
                print(f"  Matched part: '{match.group(0)}'")
            else:
                print(f"  COMPLEX ONLY: Line matches only with complex pattern")
                match = complex_dot_re.search(stripped)
                print(f"  Matched part: '{match.group(0)}'")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: debug_toa.py <text_file>")
        sys.exit(1)
        
    with open(sys.argv[1], 'r') as f:
        text = f.read()
    
    debug_toa(text) 