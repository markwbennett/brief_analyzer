```mermaid
graph TD
    %% Input Sources
    PDF[PDF Brief]
    TXT[Text Document]
    DOCX[DOCX Document]
    CSV[CSV with Citations]
    
    %% Extraction Tools
    ET[extract_text.py]
    EA[extract_authorities.py]
    EE[eyecite_extractor.py]
    EM[extract_minimal.py]
    
    %% API and Lookup Tools
    CL[courtlistener_api.py]
    CLT[citation_lookup_test.py]
    CL_SIMPLE[citation_lookup.py]
    CI[citation_info.py]
    CE[citations_enricher.py]
    FO[fetch_opinion.py]
    GOT[get_opinion_text.py]
    
    %% Processing and Formatting
    FORMAT[format_opinion.py]
    GR[generate_report.py]
    
    %% Storage
    DB[(citations.db)]
    CDB[citations_db.py]
    
    %% Utilities
    LA[legal_abbreviations.py]
    
    %% Flow
    PDF --> ET
    PDF --> EA
    TXT --> EE
    DOCX --> EE
    
    ET --> |extracted text| EA
    EA --> |cleaned text| DB
    EA --> |finds citations| DB
    
    EE --> |citation data| DB
    EM --> |minimal citation data| DB
    
    CL_SIMPLE --> |uses| CL
    CLT --> |uses| CL
    CI --> |uses| CL
    GOT --> |uses| CL
    FO --> |uses| CL
    CE --> |uses| CL
    
    CSV --> CE
    CE --> |enriched data| CSV
    
    DB <--> CDB
    CDB --> GR
    GR --> |reports| TXT
    
    CL --> |opinion data| FORMAT
    FORMAT --> |formatted opinions| TXT
    
    EE --> |uses| LA
    
    %% Subgraphs for organization
    subgraph Extraction
        ET
        EA
        EE
        EM
    end
    
    subgraph "API Clients"
        CL
        CL_SIMPLE
        CLT
        CI
        GOT
        FO
    end
    
    subgraph "Enrichment"
        CE
    end
    
    subgraph "Formatting"
        FORMAT
        GR
    end
    
    subgraph "Storage"
        DB
        CDB
    end
    
    subgraph "Utilities"
        LA
    end
```

## Component Interaction Description

The diagram above illustrates the primary components of the Brief Analyzer codebase and how they interact:

1. **Extraction Layer**:
   - PDF briefs are processed by `extract_text.py` to extract raw text
   - `extract_authorities.py` identifies the Table of Authorities and extracts citations
   - `eyecite_extractor.py` provides more general-purpose citation extraction
   - `extract_minimal.py` offers simplified citation extraction

2. **API and Lookup Layer**:
   - `courtlistener_api.py` is the core API client used by other modules
   - `citation_lookup.py` provides a simple citation lookup interface
   - `citation_lookup_test.py` offers an interactive testing interface
   - `citation_info.py` is a command-line utility for citation information
   - `get_opinion_text.py` retrieves full opinion text
   - `fetch_opinion.py` is an interactive tool to fetch and save opinions

3. **Enrichment Layer**:
   - `citations_enricher.py` adds metadata to citation records in CSV files

4. **Formatting Layer**:
   - `format_opinion.py` converts opinion data to various formats (HTML, PDF, etc.)
   - `generate_report.py` creates reports from citation data

5. **Storage Layer**:
   - `citations.db` stores citation data in SQLite format
   - `citations_db.py` provides the database interface

6. **Utilities**:
   - `legal_abbreviations.py` helps with abbreviation expansion to improve citation extraction 