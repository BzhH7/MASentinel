REQUIREMENT_EXTRACTION_PROMPT = """Extract runnable software requirements from the document.

Focus on multi-agent collaboration, tool calls, output format, exception handling,
termination, and multi-turn context. Do not classify model answer quality or factual
knowledge mistakes as software failures.

Return JSON only:
{
  "requirements": [
    {
      "id": "R1",
      "description": "...",
      "expected_agents": [],
      "expected_tools": [],
      "expected_behavior": [],
      "negative_cases": []
    }
  ]
}
"""
