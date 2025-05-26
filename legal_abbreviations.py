#!./.venv/bin/python
"""
Legal abbreviations for preprocessing text before citation extraction.
This module provides a comprehensive list of common legal abbreviations
and functions to expand them in text.
"""
import re

# Common legal abbreviations used in case names and citations
# Format: {abbreviation: expanded form}
LEGAL_ABBREVIATIONS = {
    # Organizations and entities
    "Acad.": "Academy",
    "Adm.": "Administration",
    "Admin.": "Administrative",
    "Advert.": "Advertising",
    "Agric.": "Agriculture",
    "Alt.": "Alternative",
    "Am.": "American",
    "Annot.": "Annotated",
    "Ass'n": "Association",
    "Assoc.": "Associates",
    "Assocs.": "Associates",
    "Auth.": "Authority",
    "Auto.": "Automobile",
    "Bd.": "Board",
    "Bldg.": "Building",
    "Bros.": "Brothers",
    "Broad.": "Broadcasting",
    "Bur.": "Bureau",
    "Bus.": "Business",
    "Cent.": "Central",
    "Ch.": "Chapter",
    "Chem.": "Chemical",
    "Co.": "Company",
    "Coll.": "College",
    "Comm.": "Commission",
    "Comm'n": "Commission",
    "Commc'n": "Communication",
    "Commc'ns": "Communications", 
    "Commr.": "Commissioner",
    "Cmty.": "Community",
    "Condo.": "Condominium",
    "Cong.": "Congress",
    "Consol.": "Consolidated",
    "Constr.": "Construction",
    "Cont'l": "Continental",
    "Coop.": "Cooperative",
    "Corp.": "Corporation",
    "Corr.": "Correction",
    "Cnty.": "County",
    "Ctr.": "Center",
    "Def.": "Defense",
    "Dep't": "Department",
    "Dev.": "Development",
    "Dir.": "Director",
    "Dist.": "District",
    "Distrib.": "Distributing",
    "Div.": "Division",
    "E.": "East",
    "Econ.": "Economic",
    "Educ.": "Education",
    "Elec.": "Electric",
    "Emp.": "Employment",
    "Eng'g": "Engineering",
    "Enters.": "Enterprises",
    "Env't": "Environment",
    "Envtl.": "Environmental",
    "Equal.": "Equality",
    "Equip.": "Equipment",
    "Est.": "Estate",
    "Exam'r": "Examiner",
    "Exch.": "Exchange",
    "Exec.": "Executive",
    "Fed.": "Federal",
    "Fed'n": "Federation",
    "Fin.": "Financial",
    "Fla.": "Florida",
    "Found.": "Foundation",
    "Gen.": "General",
    "Gov't": "Government",
    "Grp.": "Group",
    "Guar.": "Guaranty",
    "Hosp.": "Hospital",
    "Hous.": "Housing",
    "Indep.": "Independent",
    "Indus.": "Industrial",
    "Info.": "Information",
    "Ins.": "Insurance",
    "Inst.": "Institute",
    "Int'l": "International",
    "Inv.": "Investment",
    "Lab.": "Laboratory",
    "Liab.": "Liability",
    "Litig.": "Litigation",
    "Ltd.": "Limited",
    "Mach.": "Machine",
    "Maint.": "Maintenance",
    "Mgmt.": "Management",
    "Mfg.": "Manufacturing",
    "Mfr.": "Manufacturer",
    "Mktg.": "Marketing",
    "Med.": "Medical",
    "Mem'l": "Memorial",
    "Metro.": "Metropolitan",
    "Mortg.": "Mortgage",
    "Mun.": "Municipal",
    "Mut.": "Mutual",
    "Nat'l": "National",
    "N.": "North",
    "Ne.": "Northeast",
    "Nw.": "Northwest",
    "No.": "Number",
    "Org.": "Organization",
    "Pac.": "Pacific",
    "Pers.": "Personnel",
    "Pharm.": "Pharmaceutical",
    "Pres.": "President",
    "Prof'l": "Professional",
    "Prop.": "Property",
    "Prot.": "Protection",
    "Pub.": "Public",
    "Publ'g": "Publishing",
    "R.R.": "Railroad",
    "Ry.": "Railway",
    "Rec.": "Record",
    "Ref.": "Reference",
    "Reg'l": "Regional",
    "Rehab.": "Rehabilitation",
    "Res.": "Research",
    "Restoration": "Restoration",
    "S.": "South",
    "Sav.": "Savings",
    "Sch.": "School",
    "Sci.": "Science",
    "Se.": "Southeast",
    "Sec.": "Security",
    "Servs.": "Services",
    "Soc.": "Society",
    "Soc'y": "Society",
    "Sw.": "Southwest",
    "St.": "Street",
    "Sys.": "System",
    "Tech.": "Technology",
    "Tel.": "Telephone",
    "Telecomm.": "Telecommunications",
    "Temp.": "Temporary",
    "Transp.": "Transportation",
    "Twp.": "Township",
    "U.": "University",
    "Unif.": "Uniform",
    "Univ.": "University",
    "Util.": "Utility",
    "W.": "West",
    
    # Common combinable abbreviations
    "Sch. Dist.": "School District",
    "Indep. Sch. Dist.": "Independent School District",
}

def expand_abbreviations(text):
    """
    Expand common legal abbreviations in text, while preserving reporter names.
    
    Args:
        text: String containing legal text with abbreviations
        
    Returns:
        String with abbreviations expanded
    """
    # First save any reporter abbreviations which we DON'T want to expand
    # These are carefully standardized names that should not be changed
    reporter_patterns = {
        r'(\d+)\s+S\.W\.2d\s+(\d+)': lambda m: f"{m.group(1)} S.W.2d {m.group(2)}",
        r'(\d+)\s+F\.3d\s+(\d+)': lambda m: f"{m.group(1)} F.3d {m.group(2)}",
        r'(\d+)\s+F\.2d\s+(\d+)': lambda m: f"{m.group(1)} F.2d {m.group(2)}",
        r'(\d+)\s+F\.\s+Supp\.\s+(\d+)': lambda m: f"{m.group(1)} F. Supp. {m.group(2)}",
        r'(\d+)\s+U\.S\.\s+(\d+)': lambda m: f"{m.group(1)} U.S. {m.group(2)}",
    }
    
    # Replace reporter patterns with placeholders
    placeholders = {}
    for i, (pattern, replacement_func) in enumerate(reporter_patterns.items()):
        def make_replacement(match, i=i, func=replacement_func):
            original = match.group(0)
            placeholders[f"REPORTER_PLACEHOLDER_{i}_{len(placeholders)}"] = original
            return f"REPORTER_PLACEHOLDER_{i}_{len(placeholders)-1}"
            
        text = re.sub(pattern, make_replacement, text)
    
    # Apply abbreviation expansions (excluding protected reporters)
    # Special case for Independent School District, which eyecite has trouble with
    text = re.sub(r'([A-Za-z]+) Indep\. Sch\. Dist\.', r'\1 Independent School District', text)
    
    # Expand multi-word abbreviations first (sorted by length in reverse order)
    for abbr, expanded in sorted(LEGAL_ABBREVIATIONS.items(), key=lambda x: len(x[0]), reverse=True):
        text = text.replace(abbr, expanded)
    
    # Restore reporters from placeholders
    for placeholder, original in placeholders.items():
        text = text.replace(placeholder, original)
    
    return text