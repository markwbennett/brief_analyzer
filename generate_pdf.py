#!./.venv/bin/python

import pypandoc
import weasyprint
import sys
import subprocess
import os
import re
import tempfile
import base64
import shutil

def extract_mermaid_diagrams(md_content):
    """Extract mermaid diagrams from markdown content and replace with image references"""
    # Pattern to find mermaid diagrams
    pattern = r'```mermaid\n+(.*?)\n+```'
    diagrams = re.findall(pattern, md_content, re.DOTALL)
    
    if not diagrams:
        return md_content, []
    
    diagram_files = []
    modified_content = md_content
    
    for i, diagram in enumerate(diagrams):
        # Create a unique filename for this diagram
        diagram_file = f"diagram_{i}.png"
        diagram_files.append(diagram_file)
        
        # Replace mermaid code block with image reference
        diagram_pattern = re.escape(f"```mermaid\n{diagram}\n```")
        replacement = f"\n\n![Diagram {i+1}]({diagram_file})\n\n"
        modified_content = re.sub(diagram_pattern, replacement, modified_content)
        
        # Save diagram to a temporary file
        temp_mermaid_file = f"temp_diagram_{i}.mmd"
        with open(temp_mermaid_file, 'w') as f:
            f.write(diagram)
        
        try:
            # Try to generate diagram image using mmdc (Mermaid CLI) if available
            cmd = ["npx", "@mermaid-js/mermaid-cli/index.bundle.js", "-i", temp_mermaid_file, "-o", diagram_file]
            process = subprocess.run(cmd, capture_output=True)
            if process.returncode != 0:
                # Fallback to basic rendering approach
                generate_diagram_image(diagram, diagram_file)
        except Exception as e:
            print(f"Error generating diagram with Mermaid CLI: {e}")
            # Fallback to basic rendering
            generate_diagram_image(diagram, diagram_file)
        
        # Clean up temp file
        try:
            os.remove(temp_mermaid_file)
        except:
            pass
    
    return modified_content, diagram_files

def generate_diagram_image(diagram_content, output_file):
    """Generate a diagram image using a simple text-based approach"""
    import matplotlib.pyplot as plt
    from PIL import Image, ImageDraw, ImageFont
    
    # Create an image with text
    lines = diagram_content.split('\n')
    
    if not lines:
        # Handle empty diagram content
        lines = ["Empty diagram"]
        
    font_size = 14
    line_height = font_size + 4
    
    # Estimate image size
    max_line_length = max([len(line) for line in lines])
    width = max(max_line_length * (font_size//2), 800)
    height = len(lines) * line_height + 50
    
    # Create a blank image
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("Arial", font_size)
    except:
        # Fallback to default font
        font = ImageFont.load_default()
    
    y_position = 20
    for line in lines:
        d.text((20, y_position), line, fill=(0, 0, 0), font=font)
        y_position += line_height
    
    img.save(output_file)

def generate_pdf():
    """Generate a PDF from the codebase summary markdown file"""
    md_file = 'codebase_summary_pdf.md'
    output_pdf = 'brief_analyzer_codebase_summary.pdf'
    
    # Read the markdown content
    with open(md_file, 'r') as f:
        md_content = f.read()
    
    # Extract mermaid diagrams and replace with image references
    modified_content, diagram_files = extract_mermaid_diagrams(md_content)
    
    # Write modified content to temporary file
    temp_md_file = 'temp_summary.md'
    with open(temp_md_file, 'w') as f:
        f.write(modified_content)
    
    # Convert Markdown to PDF
    try:
        output = pypandoc.convert_file(
            temp_md_file, 
            'pdf', 
            outputfile=output_pdf,
            extra_args=[
                '--pdf-engine=weasyprint',
                '--toc', 
                '--toc-depth=3',
                '--standalone',
                '--highlight-style=tango',
                '--variable', 'papersize=letter',
                '--variable', 'geometry:margin=1in',
                '--variable', 'fontsize=11pt'
            ]
        )
        print(f'PDF generated: {output_pdf}')
        
        # Clean up temporary files
        try:
            os.remove(temp_md_file)
            for diagram_file in diagram_files:
                if os.path.exists(diagram_file):
                    os.remove(diagram_file)
        except Exception as e:
            print(f"Error cleaning up temporary files: {e}")
        
        return 0
    except Exception as e:
        print(f"Error generating PDF with pandoc: {e}")
        
        # Fallback method using weasyprint directly
        try:
            print("Trying fallback method with markdown and weasyprint...")
            from markdown import markdown
            
            html = markdown(modified_content, extensions=['tables', 'fenced_code'])
            
            # Add some basic styling
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Brief Analyzer Codebase Summary</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.5; max-width: 800px; margin: 0 auto; padding: 20px; }}
                    h1 {{ color: #333; border-bottom: 1px solid #ddd; padding-bottom: 10px; }}
                    h2 {{ color: #444; margin-top: 30px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
                    h3 {{ color: #555; margin-top: 25px; }}
                    h4 {{ color: #666; margin-top: 20px; }}
                    code {{ background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-family: monospace; }}
                    pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; }}
                    th {{ background-color: #f2f2f2; text-align: left; }}
                    tr:nth-child(even) {{ background-color: #f9f9f9; }}
                    p {{ margin: 10px 0; }}
                    ul, ol {{ padding-left: 20px; }}
                    hr {{ border: none; border-top: 1px solid #ddd; margin: 20px 0; }}
                    img {{ max-width: 100%; }}
                </style>
            </head>
            <body>
                {html}
            </body>
            </html>
            """
            
            # Convert HTML to PDF
            weasyprint.HTML(string=html).write_pdf(output_pdf)
            print(f'PDF generated with fallback method: {output_pdf}')
            
            # Clean up temporary files
            try:
                os.remove(temp_md_file)
                for diagram_file in diagram_files:
                    if os.path.exists(diagram_file):
                        os.remove(diagram_file)
            except Exception as e:
                print(f"Error cleaning up temporary files: {e}")
                
            return 0
        except Exception as e2:
            print(f"Fallback method also failed: {e2}")
            return 1

if __name__ == "__main__":
    sys.exit(generate_pdf()) 