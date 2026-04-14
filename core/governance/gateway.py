import re
from typing import List, Dict, Any, Tuple

class AntiHallucinationGateway:
    """
    Parses LLM outputs and strictly validates citation formats against the provided contexts.
    Fails any claims that hallucinate source files or pages.
    """
    
    # Regex to capture <citation src='X' page='Y'>text</citation>
    # Note: LLM might use single or double quotes, so we handle both.
    CITATION_PATTERN = re.compile(r'<citation\s+src=[\'"]([^\'"]+)[\'"]\s+page=[\'"]([^\'"]+)[\'"]>(.*?)</citation>', re.DOTALL | re.IGNORECASE)

    @classmethod
    def validate_and_parse(cls, llm_response: str, contexts: List[Dict[str, Any]]) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Parses the raw response.
        Returns:
            is_valid (bool): True if at least one valid citation and no invalid citations.
            clean_text (str): Response with invalid citations marked as hallucinations.
            citations (list): List of verified metadata dicts.
        """
        verified_citations = []
        valid_sources = {(str(c.get('metadata', {}).get('source', '')), str(c.get('metadata', {}).get('page', ''))) for c in contexts}
        
        has_invalid = False
        parsed_response = llm_response

        # Find all citations
        matches = cls.CITATION_PATTERN.finditer(llm_response)
        
        for match in matches:
            src = match.group(1).strip()
            page = match.group(2).strip()
            content = match.group(3).strip()
            
            # Check against provided contexts
            if (src, page) in valid_sources:
                # Retrieve full context metadata (taking the first matching context for bbox)
                meta = next((c['metadata'] for c in contexts if str(c['metadata'].get('source')) == src and str(c['metadata'].get('page')) == page), {})
                verified_citations.append({
                    "source_file": src,
                    "page_number": int(page) if page.isdigit() else 0,
                    "content": content,
                    "bbox": meta.get("bbox")
                })
            else:
                has_invalid = True
                # Replace hallucinated citation with a warning
                original_tag = match.group(0)
                parsed_response = parsed_response.replace(original_tag, f"[{content} ⚠️ 系统警告: 该引用来源 {src} 第 {page} 页不存在于本次检索知识中，疑似幻觉]")

        is_valid = not has_invalid and len(verified_citations) > 0
        
        return is_valid, parsed_response, verified_citations
