#!./.venv/bin/python

import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
import os

@dataclass
class ExtendedCitation:
    full_cite: str
    corrected_cite: Optional[str] = None
    short_cite: Optional[str] = None
    case_title: Optional[str] = None
    volume: Optional[str] = None
    reporter: Optional[str] = None
    page: Optional[str] = None
    court: Optional[str] = None
    year: Optional[str] = None
    publication_status: Optional[str] = None
    petition_history: Optional[str] = None
    plaintiff: Optional[str] = None
    defendant: Optional[str] = None
    also_cited_as: List[str] = None
    appearances: Dict[str, List[int]] = None
    google_scholar_link: Optional[str] = None
    court_link: Optional[str] = None
    
    def __post_init__(self):
        if self.also_cited_as is None:
            self.also_cited_as = []
        if self.appearances is None:
            self.appearances = {}

class CitationDB:
    def __init__(self, db_path="citations.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path)
        self.create_tables()

    def create_tables(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS citations (
            id INTEGER PRIMARY KEY,
            full_cite TEXT NOT NULL,
            corrected_cite TEXT,
            short_cite TEXT,
            case_title TEXT,
            volume TEXT,
            reporter TEXT,
            page TEXT,
            court TEXT,
            year TEXT,
            publication_status TEXT,
            petition_history TEXT,
            plaintiff TEXT,
            defendant TEXT,
            google_scholar_link TEXT,
            court_link TEXT
        )""")
        
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS alternative_citations (
            citation_id INTEGER,
            alt_cite TEXT,
            FOREIGN KEY(citation_id) REFERENCES citations(id)
        )""")
        
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS appearances (
            citation_id INTEGER,
            document TEXT,
            page INTEGER,
            FOREIGN KEY(citation_id) REFERENCES citations(id)
        )""")
        
        self.conn.commit()

    def add_citation(self, citation: ExtendedCitation):
        cursor = self.conn.cursor()
        cursor.execute("""
        INSERT INTO citations (
            full_cite, corrected_cite, short_cite, case_title,
            volume, reporter, page, court, year,
            publication_status, petition_history,
            plaintiff, defendant,
            google_scholar_link, court_link
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            citation.full_cite, citation.corrected_cite,
            citation.short_cite, citation.case_title,
            citation.volume, citation.reporter, citation.page,
            citation.court, citation.year,
            citation.publication_status, citation.petition_history,
            citation.plaintiff, citation.defendant,
            citation.google_scholar_link, citation.court_link
        ))
        
        citation_id = cursor.lastrowid
        
        for alt_cite in citation.also_cited_as:
            cursor.execute("""
            INSERT INTO alternative_citations (citation_id, alt_cite)
            VALUES (?, ?)
            """, (citation_id, alt_cite))
            
        for doc, pages in citation.appearances.items():
            for page in pages:
                cursor.execute("""
                INSERT INTO appearances (citation_id, document, page)
                VALUES (?, ?, ?)
                """, (citation_id, doc, page))
                
        self.conn.commit()

    def get_citation(self, full_cite: str) -> Optional[ExtendedCitation]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM citations WHERE full_cite = ?", (full_cite,))
        row = cursor.fetchone()
        if not row:
            return None
            
        citation = ExtendedCitation(
            full_cite=row[1],
            corrected_cite=row[2],
            short_cite=row[3],
            case_title=row[4],
            volume=row[5],
            reporter=row[6],
            page=row[7],
            court=row[8],
            year=row[9],
            publication_status=row[10],
            petition_history=row[11],
            plaintiff=row[12],
            defendant=row[13],
            google_scholar_link=row[14],
            court_link=row[15]
        )
        
        cursor.execute("SELECT alt_cite FROM alternative_citations WHERE citation_id = ?", (row[0],))
        citation.also_cited_as = [r[0] for r in cursor.fetchall()]
        
        cursor.execute("SELECT document, page FROM appearances WHERE citation_id = ?", (row[0],))
        for doc, page in cursor.fetchall():
            if doc not in citation.appearances:
                citation.appearances[doc] = []
            citation.appearances[doc].append(page)
            
        return citation

    def update_citation(self, volume: str, reporter: str, page: str, **updates):
        with sqlite3.connect(self.db_path) as conn:
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            query = f"""
                UPDATE citations 
                SET {set_clause}
                WHERE volume = ? AND reporter = ? AND page = ?
            """
            values = list(updates.values()) + [volume, reporter, page]
            conn.execute(query, values)

    def get_missing_courts(self) -> list[ExtendedCitation]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM citations WHERE court IS NULL")
            return [ExtendedCitation(
                full_cite=row[1],
                corrected_cite=row[2],
                short_cite=row[3],
                case_title=row[4],
                volume=row[5],
                reporter=row[6],
                page=row[7],
                court=row[8],
                year=row[9],
                publication_status=row[10],
                petition_history=row[11],
                plaintiff=row[12],
                defendant=row[13],
                google_scholar_link=row[14],
                court_link=row[15]
            ) for row in cursor.fetchall()]

    def get_missing_plaintiffs(self) -> list[ExtendedCitation]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM citations WHERE plaintiff IS NULL")
            return [ExtendedCitation(
                full_cite=row[1],
                corrected_cite=row[2],
                short_cite=row[3],
                case_title=row[4],
                volume=row[5],
                reporter=row[6],
                page=row[7],
                court=row[8],
                year=row[9],
                publication_status=row[10],
                petition_history=row[11],
                plaintiff=row[12],
                defendant=row[13],
                google_scholar_link=row[14],
                court_link=row[15]
            ) for row in cursor.fetchall()]

    def get_incomplete_citations(self) -> list[ExtendedCitation]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM citations 
                WHERE year IS NULL 
                OR court IS NULL 
                OR plaintiff IS NULL 
                OR defendant IS NULL
            """)
            return [ExtendedCitation(
                full_cite=row[1],
                corrected_cite=row[2],
                short_cite=row[3],
                case_title=row[4],
                volume=row[5],
                reporter=row[6],
                page=row[7],
                court=row[8],
                year=row[9],
                publication_status=row[10],
                petition_history=row[11],
                plaintiff=row[12],
                defendant=row[13],
                google_scholar_link=row[14],
                court_link=row[15]
            ) for row in cursor.fetchall()] 