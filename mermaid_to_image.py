#!./.venv/bin/python

import os
import re
import subprocess
import tempfile
import base64
import urllib.request
import urllib.parse
from PIL import Image
import io
import time
import requests
import sys
from typing import List, Tuple, Optional
import json
import argparse
import mermaid as md
from mermaid.graph import Graph

def extract_mermaid_diagrams(markdown_content):
    """Extract mermaid diagrams from markdown content and replace with image references."""
    pattern = r'```mermaid\n(.*?)\n```'
    diagrams = []
    
    def replace_diagram(match):
        diagram_content = match.group(1)
        diagram_id = f"diagram_{len(diagrams)}"
        diagrams.append((diagram_id, diagram_content))
        return f"![{diagram_id}]({diagram_id}.png)"
    
    modified_content = re.sub(pattern, replace_diagram, markdown_content, flags=re.DOTALL)
    return modified_content, diagrams

def generate_diagram_image(mermaid_code: str, output_path: str, method: str = 'puppeteer', theme: str = 'default', background_color: str = 'white') -> bool:
    """Generate a diagram image from Mermaid code.
    
    Args:
        mermaid_code: The Mermaid diagram code
        output_path: Path to save the generated image
        method: Method to use for generation ('mmdc', 'online', 'puppeteer', or 'mermaid-py')
        theme: Theme to use for the diagram
        background_color: Background color for the diagram
        
    Returns:
        True if generation was successful, False otherwise
    """
    if method == 'mermaid-py':
        try:
            # Use mermaid-py library
            diagram = Graph('diagram', mermaid_code)
            render = md.Mermaid(diagram)
            
            # Get the PNG image directly
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name
            
            render.to_png(temp_path)
            
            # Check if file was generated and copy it to destination
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with open(temp_path, 'rb') as src, open(output_path, 'wb') as dst:
                    dst.write(src.read())
                os.unlink(temp_path)  # Clean up temp file
                print(f"Generated {output_path} using mermaid-py")
                return True
            else:
                print(f"Failed to generate image with mermaid-py")
                return False
        except Exception as e:
            print(f"Error generating diagram with mermaid-py: {e}")
            return False
    elif method == 'mmdc':
        return generate_with_mmdc(mermaid_code, output_path, theme, background_color)
    elif method == 'online':
        return generate_with_online_service(mermaid_code, output_path)
    elif method == 'puppeteer':
        return generate_with_puppeteer(mermaid_code, output_path)
    else:
        print(f"Unknown method: {method}, falling back to puppeteer")
        return generate_with_puppeteer(mermaid_code, output_path)

def generate_with_mmdc(diagram_content, output_path, theme, background_color):
    """Generate a PNG image from a mermaid diagram using mmdc."""
    # First, try using mermaid-cli (mmdc) if installed
    with tempfile.NamedTemporaryFile(suffix='.mmd', delete=False) as temp_file:
        temp_file.write(diagram_content.encode('utf-8'))
        temp_file_path = temp_file.name
    
    try:
        # Try using mmdc (mermaid-cli) if installed
        subprocess.run(
            ['mmdc', '-i', temp_file_path, '-o', output_path, '-t', theme, '-c', background_color],
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Generated {output_path} using mmdc")
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("mmdc not available, trying online service...")
    
    # Fallback to using mermaid.ink online service
    try:
        diagram_base64 = base64.b64encode(diagram_content.encode('utf-8')).decode('utf-8')
        url = f"https://mermaid.ink/img/{diagram_base64}?theme={theme}"
        
        with urllib.request.urlopen(url) as response:
            image_data = response.read()
            
        # Save image to output path
        with open(output_path, 'wb') as f:
            f.write(image_data)
            
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Generated {output_path} using mermaid.ink")
            return True
    except Exception as e:
        print(f"Failed to generate image using mermaid.ink: {e}")
    
    # Final fallback: attempt to use puppeteer-based approach
    try:
        # Create a simple HTML page with mermaid
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
            <script>
                mermaid.initialize({{ startOnLoad: true }});
            </script>
        </head>
        <body>
            <div class="mermaid">
            {diagram_content}
            </div>
        </body>
        </html>
        """
        
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as html_file:
            html_file.write(html_content.encode('utf-8'))
            html_file_path = html_file.name
        
        # Use headless chrome with node if available
        screenshot_js = f"""
        const puppeteer = require('puppeteer');
        
        (async () => {{
            const browser = await puppeteer.launch();
            const page = await browser.newPage();
            await page.goto('file://{html_file_path}', {{waitUntil: 'networkidle0'}});
            await page.waitForSelector('.mermaid svg');
            const element = await page.$('.mermaid');
            await element.screenshot({{path: '{output_path}'}});
            await browser.close();
        }})();
        """
        
        with tempfile.NamedTemporaryFile(suffix='.js', delete=False) as js_file:
            js_file.write(screenshot_js.encode('utf-8'))
            js_file_path = js_file.name
        
        subprocess.run(
            ['node', js_file_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Generated {output_path} using puppeteer")
            return True
    except Exception as e:
        print(f"Failed to generate image using puppeteer: {e}")
    
    # If all methods failed, return False
    return False

def generate_with_online_service(diagram_content, output_path):
    """Generate a PNG image from a mermaid diagram using an online service."""
    try:
        diagram_base64 = base64.b64encode(diagram_content.encode('utf-8')).decode('utf-8')
        url = f"https://mermaid.ink/img/{diagram_base64}?theme=default"
        
        with urllib.request.urlopen(url) as response:
            image_data = response.read()
            
        # Save image to output path
        with open(output_path, 'wb') as f:
            f.write(image_data)
            
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Generated {output_path} using mermaid.ink")
            return True
    except Exception as e:
        print(f"Failed to generate image using mermaid.ink: {e}")
    
    # If all methods failed, return False
    return False

def generate_with_puppeteer(diagram_content, output_path):
    """Generate a PNG image from a mermaid diagram using puppeteer."""
    try:
        # Create a simple HTML page with mermaid
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
            <script>
                mermaid.initialize({{ startOnLoad: true }});
            </script>
        </head>
        <body>
            <div class="mermaid">
            {diagram_content}
            </div>
        </body>
        </html>
        """
        
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as html_file:
            html_file.write(html_content.encode('utf-8'))
            html_file_path = html_file.name
        
        # Use headless chrome with node if available
        screenshot_js = f"""
        const puppeteer = require('puppeteer');
        
        (async () => {{
            const browser = await puppeteer.launch();
            const page = await browser.newPage();
            await page.goto('file://{html_file_path}', {{waitUntil: 'networkidle0'}});
            await page.waitForSelector('.mermaid svg');
            const element = await page.$('.mermaid');
            await element.screenshot({{path: '{output_path}'}});
            await browser.close();
        }})();
        """
        
        with tempfile.NamedTemporaryFile(suffix='.js', delete=False) as js_file:
            js_file.write(screenshot_js.encode('utf-8'))
            js_file_path = js_file.name
        
        subprocess.run(
            ['node', js_file_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Generated {output_path} using puppeteer")
            return True
    except Exception as e:
        print(f"Failed to generate image using puppeteer: {e}")
    
    # If all methods failed, return False
    return False

def convert_markdown_with_mermaid(input_file, output_dir='.', method='puppeteer', theme='default', background_color='white'):
    """Process a markdown file to extract mermaid diagrams and convert them to images.
    
    Args:
        input_file: Path to the markdown file
        output_dir: Directory to save the generated images and output markdown
        method: Method to use for diagram generation ('mmdc', 'online', or 'puppeteer')
        theme: Theme to use for the diagrams
        background_color: Background color for the diagrams
        
    Returns:
        Path to the processed markdown file
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Read input markdown file
    with open(input_file, 'r') as f:
        markdown_content = f.read()
    
    # Extract diagrams and get modified content
    modified_content, diagrams = extract_mermaid_diagrams(markdown_content)
    
    # Generate images for each diagram
    success_count = 0
    for diagram_id, diagram_content in diagrams:
        output_path = os.path.join(output_dir, f"{diagram_id}.png")
        if generate_diagram_image(diagram_content, output_path, method, theme, background_color):
            success_count += 1
        else:
            print(f"Failed to generate image for {diagram_id}")
            # Revert to original mermaid code
            placeholder = f"![{diagram_id}]({diagram_id}.png)"
            diagram_block = f"```mermaid\n{diagram_content}\n```"
            modified_content = modified_content.replace(placeholder, diagram_block)
    
    # Create output filename based on input filename
    base_filename = os.path.basename(input_file)
    name, ext = os.path.splitext(base_filename)
    output_file = os.path.join(output_dir, f"modified_{name}{ext}")
    
    # Write modified markdown to output file
    with open(output_file, 'w') as f:
        f.write(modified_content)
    
    if success_count > 0:
        print(f"Successfully generated {success_count} out of {len(diagrams)} diagrams")
    else:
        print("Failed to generate any diagram images")
    
    return output_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert Mermaid diagrams in markdown to images')
    parser.add_argument('input_file', help='Input markdown file path')
    parser.add_argument('-o', '--output-dir', default='.', help='Output directory path')
    parser.add_argument('-m', '--method', default='puppeteer', choices=['mmdc', 'online', 'puppeteer', 'mermaid-py'],
                        help='Method to use for diagram generation')
    parser.add_argument('-t', '--theme', default='default', help='Theme to use for the diagrams')
    parser.add_argument('-b', '--background', default='white', help='Background color for the diagrams')
    
    args = parser.parse_args()
    
    input_file = args.input_file
    output_dir = args.output_dir
    
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found")
        sys.exit(1)
    
    try:
        modified_file = convert_markdown_with_mermaid(
            input_file, 
            output_dir, 
            method=args.method, 
            theme=args.theme, 
            background_color=args.background
        )
        print(f"Modified markdown file saved to: {modified_file}")
    except Exception as e:
        print(f"Error: {e}") 