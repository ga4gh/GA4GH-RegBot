import re
from typing import List
from parse.framework_clause import framework_clause

DOCUMENT_NAME = "Framework for Responsible Sharing"

def clean(text):
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text

def parse_framework(text):
    
    # remove weird characters
    text = text.replace("\u00ad", "")
    text = text.replace("\xa0", " ")
    
    # remove page numbers
    text = re.sub(r"\[\[PAGE_\d+\]\]", "", text)
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    
    text = text.strip()
    
    # remove the title that keeps showing up
    text = text.replace("Framework for Responsible Sharing of Genomic and Health-Related Data", "")
    
    clauses = []
    banner_clauses = []
    
    # ---- get the foundational principles bullets ----
    
    fp_match = re.search(
        r"Foundational Principles for Responsible Sharing of\s+Genomic and Health-Related Data\s+(•.*?)(?=\n\s*II\.)",
        text,
        flags=re.S
    )
    
    if fp_match:
        all_bullets = re.findall(r"•\s+(.*)", fp_match.group(1))
        
        for b in all_bullets:
            new_clause = framework_clause(
                document_name=DOCUMENT_NAME,
                section_number="III",
                section_title="Foundational Principles",
                subsection="Core Principles",
                clause_text=clean(b),
            )
            banner_clauses.append(new_clause)
        
        text = text.replace(fp_match.group(0), "")
    
    # remove appendix we dont need it
    appendix_match = re.search(r"\nAppendix 1", text)
    if appendix_match:
        text = text[:appendix_match.start()]
    
    # split into sections
    section_pattern = re.compile(r"(?:^|\n)([IVXLCDM]+)\.?\s+([^\n]+)")
    matches = list(section_pattern.finditer(text))
    
    sections = []
    
    i = 0
    while i < len(matches):
        match = matches[i]
        
        start = match.start()
        
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(text)
        
        section_info = {}
        section_info["roman"] = match.group(1)
        section_info["title"] = match.group(2).strip()
        section_info["start"] = start
        section_info["end"] = end
        
        sections.append(section_info)
        i += 1
    
    # now loop through each section
    for section in sections:
        roman = section["roman"]
        title = section["title"]
        content = text[section["start"]:section["end"]]
        
        if roman == "I":
            
            purpose_match = re.search(r"1\.\s+Purpose\.(.*?)(?=\n2\.)", content, re.S)
            if purpose_match:
                subpoints = re.finditer(
                    r"\n\s*[ivxlcdm]+\.\s+(.*?)(?=\n\s*[ivxlcdm]+\.|\Z)",
                    purpose_match.group(1),
                    re.S
                )
                for sp in subpoints:
                    new_clause = framework_clause(
                        document_name=DOCUMENT_NAME,
                        section_number="I",
                        section_title=title,
                        subsection="Purpose",
                        clause_text=clean(sp.group(1)),
                    )
                    clauses.append(new_clause)
            
            interpretation_match = re.search(r"2\.\s+Interpretation\.(.*)", content, re.S)
            if interpretation_match:
                new_clause = framework_clause(
                    document_name=DOCUMENT_NAME,
                    section_number="I",
                    section_title=title,
                    subsection="Interpretation",
                    clause_text=clean(interpretation_match.group(1)),
                )
                clauses.append(new_clause)
        
        elif roman == "II":
            
            match = re.search(r"II\.\s+Application(.*)", content, re.S)
            if match:
                new_clause = framework_clause(
                    document_name=DOCUMENT_NAME,
                    section_number="II",
                    section_title=title,
                    subsection=None,
                    clause_text=clean(match.group(1)),
                )
                clauses.append(new_clause)
        
        elif roman == "III":
            
            # add the banner bullets we saved earlier
            for bc in banner_clauses:
                clauses.append(bc)
            
            body = content.split(title, 1)[-1]
            all_paragraphs = body.split("\n\n")
            
            for para in all_paragraphs:
                para = para.strip()
                if len(para) > 40:
                    new_clause = framework_clause(
                        document_name=DOCUMENT_NAME,
                        section_number="III",
                        section_title=title,
                        subsection=None,
                        clause_text=clean(para),
                    )
                    clauses.append(new_clause)
        
        elif roman == "IV":
            
            core_pattern = list(re.finditer(r"\n€\s+([^\n]+)", content))
            
            for i in range(len(core_pattern)):
                core = core_pattern[i]
                core_title = core.group(1).strip()
                core_start = core.end()
                
                if i + 1 < len(core_pattern):
                    core_end = core_pattern[i + 1].start()
                else:
                    core_end = len(content)
                
                core_block = content[core_start:core_end]
                
                bullet_pattern = re.finditer(
                    r"\n\s*•\s+(.*?)(?=\n\s*•|\Z)",
                    core_block,
                    re.S
                )
                
                for bullet in bullet_pattern:
                    new_clause = framework_clause(
                        document_name=DOCUMENT_NAME,
                        section_number="IV",
                        section_title=title,
                        subsection=core_title,
                        clause_text=clean(bullet.group(1)),
                    )
                    clauses.append(new_clause)
        
        elif roman == "V":
            
            numbered_clauses = re.finditer(
                r"\n\s*(\d+)\.\s+(.*?)(?=\n\s*\d+\.|\Z)",
                content,
                re.S
            )
            
            for nc in numbered_clauses:
                new=_clause = framework_clause(
                    document_name=DOCUMENT_NAME,
                    section_number="V",
                    section_title=title,
                    subsection=None,
                    clause_text=clean(nc.group(2)),
                )
                clauses.append(new_clause)
        
        elif roman == "VI":
            
            match = re.search(r"VI\.\s+Acknowledgements(.*)", content, re.S)
            if match:
                new_clause = framework_clause(
                    document_name=DOCUMENT_NAME,
                    section_number="VI",
                    section_title=title,
                    subsection=None,
                    clause_text=clean(match.group(1)),
                )
                clauses.append(new_clause)
    
    return clauses