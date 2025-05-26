#!./.venv/bin/python

import sqlite3
import sys
import os
from tabulate import tabulate
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class CitationSummary:
    full_cite: str
    case_title: str
    reporter: str
    court: Optional[str] = None
    year: Optional[str] = None
    appearances: int = 0
    page_references: List[int] = None
    
    def __post_init__(self):
        if self.page_references is None:
            self.page_references = []

def get_citation_data(db_path="citations.db"):
    """Extract citation data from the database"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all citations
    cursor.execute("""
        SELECT c.id, c.full_cite, c.case_title, c.volume, c.reporter, c.page, c.year, c.court,
               c.plaintiff, c.defendant
        FROM citations c
        ORDER BY c.reporter, c.volume, c.page
    """)
    
    citations = []
    citation_dict = {}
    
    for row in cursor.fetchall():
        citation_id = row['id']
        full_cite = row['full_cite']
        
        # Handle missing case title by constructing from plaintiff/defendant
        case_title = row['case_title']
        if not case_title and row['plaintiff'] and row['defendant']:
            case_title = f"{row['plaintiff']} v. {row['defendant']}"
        
        reporter = row['reporter'] or "Unknown"
        
        citation = CitationSummary(
            full_cite=full_cite,
            case_title=case_title or "Unknown Case",
            reporter=reporter,
            court=row['court'],
            year=row['year']
        )
        
        citation_dict[citation_id] = citation
        citations.append(citation)
    
    # Count appearances for each citation
    cursor.execute("""
        SELECT citation_id, COUNT(*) as count
        FROM appearances
        GROUP BY citation_id
    """)
    
    for row in cursor.fetchall():
        citation_id = row['citation_id']
        if citation_id in citation_dict:
            citation_dict[citation_id].appearances = row['count']
    
    # Get page references for each citation
    cursor.execute("""
        SELECT citation_id, page_number
        FROM page_references
        ORDER BY citation_id, page_number
    """)
    
    for row in cursor.fetchall():
        citation_id = row['citation_id']
        if citation_id in citation_dict:
            citation_dict[citation_id].page_references.append(row['page_number'])
    
    conn.close()
    return citations

def group_by_reporter(citations):
    """Group citations by reporter"""
    reporters = {}
    for citation in citations:
        reporter = citation.reporter
        if reporter not in reporters:
            reporters[reporter] = []
        reporters[reporter].append(citation)
    return reporters

def generate_report(citations, output_format="text"):
    """Generate a report of citations in the specified format"""
    if not citations:
        return "No citations found in the database."
    
    if output_format == "text":
        reporters = group_by_reporter(citations)
        output = []
        
        for reporter, reporter_citations in sorted(reporters.items()):
            output.append(f"\n{reporter} ({len(reporter_citations)} citations)")
            output.append("-" * (len(reporter) + 15))
            
            table_data = []
            for citation in reporter_citations:
                pages = ", ".join(str(p) for p in citation.page_references) if citation.page_references else "N/A"
                court_year = f"{citation.court or 'Unknown'} ({citation.year or 'Unknown'})"
                table_data.append([
                    citation.case_title,
                    citation.full_cite,
                    court_year,
                    citation.appearances,
                    pages
                ])
            
            output.append(tabulate(
                table_data,
                headers=["Case Title", "Citation", "Court (Year)", "Appearances", "Pages"],
                tablefmt="grid"
            ))
        
        return "\n".join(output)
    
    elif output_format == "csv":
        lines = ["Case Title,Citation,Reporter,Court,Year,Appearances,Pages"]
        for citation in citations:
            pages = "|".join(str(p) for p in citation.page_references) if citation.page_references else ""
            line = [
                f'"{citation.case_title}"',
                f'"{citation.full_cite}"',
                f'"{citation.reporter}"',
                f'"{citation.court or ""}"',
                f'"{citation.year or ""}"',
                str(citation.appearances),
                f'"{pages}"'
            ]
            lines.append(",".join(line))
        return "\n".join(lines)
    
    else:
        return f"Unsupported output format: {output_format}"

def main():
    db_path = "citations.db"
    output_format = "text"
    output_file = None
    
    # Parse command line arguments
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--db":
            if i + 1 < len(sys.argv):
                db_path = sys.argv[i + 1]
                i += 2
            else:
                print("Error: Missing value for --db")
                return 1
        elif sys.argv[i] == "--format":
            if i + 1 < len(sys.argv):
                output_format = sys.argv[i + 1].lower()
                if output_format not in ["text", "csv"]:
                    print(f"Error: Unsupported output format: {output_format}")
                    return 1
                i += 2
            else:
                print("Error: Missing value for --format")
                return 1
        elif sys.argv[i] == "--output":
            if i + 1 < len(sys.argv):
                output_file = sys.argv[i + 1]
                i += 2
            else:
                print("Error: Missing value for --output")
                return 1
        else:
            i += 1
    
    # Get citation data and generate report
    try:
        citations = get_citation_data(db_path)
        report = generate_report(citations, output_format)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
            print(f"Report written to {output_file}")
        else:
            print(report)
        
        return 0
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 