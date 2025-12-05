"""
VerdictAgent - generates final merge/needs_fixes/reject verdict.
This agent runs AFTER all other agents and analyzes their findings.
"""
import json
import re
from dataclasses import dataclass
from enum import Enum

from ..models import AgentFinding, AgentPayload, AgentResult
from .base import BaseAgent


class Verdict(str, Enum):
    APPROVE = "approve"
    NEEDS_FIXES = "needs_fixes"
    REJECT = "reject"


@dataclass
class VerdictResult:
    verdict: Verdict
    confidence: float  # 0.0 - 1.0
    summary: str
    blocking_issues: list[str]
    suggestions: list[str]


class VerdictAgent(BaseAgent):
    """
    Analyzes all findings from other agents and produces a final verdict.
    
    Logic:
    - If any CRITICAL severity finding → REJECT
    - If >3 WARNING findings → NEEDS_FIXES
    - If only INFO findings → APPROVE
    """
    
    def __init__(self) -> None:
        super().__init__(key="verdict", title="Review Verdict")
        self.all_findings: list[AgentFinding] = []
        self.agent_summaries: dict[str, str] = {}
    
    def set_context(self, findings: list[AgentFinding], summaries: dict[str, str]) -> None:
        """Set findings and summaries from other agents before execution."""
        self.all_findings = findings
        self.agent_summaries = summaries

    def build_prompt(self, payload: AgentPayload) -> str:
        findings_text = self._format_findings()
        summaries_text = self._format_summaries()
        
        return f'''You are a RUTHLESS senior code reviewer who makes the final call on merge requests.
Your reputation depends on NOT letting bugs into production, but also NOT blocking good code.

ROLE: You are the last line of defense. Be paranoid but fair.

TASK: Analyze the findings from other review agents and determine the verdict.

OUTPUT FORMAT (STRICT JSON, no extra text):
{{
    "verdict": "approve" | "needs_fixes" | "reject",
    "confidence": 0.0-1.0,
    "summary": "One sentence explaining the decision",
    "blocking_issues": ["List of issues that MUST be fixed before merge"],
    "suggestions": ["Nice-to-have improvements, not blocking"]
}}

DECISION RULES:
1. REJECT if:
   - Security vulnerability (SQL injection, XSS, hardcoded secrets, etc.)
   - Will definitely cause runtime crash or data loss
   - Breaks existing tests or CI
   - Missing critical error handling that could crash production

2. NEEDS_FIXES if:
   - Missing tests for new functionality
   - Poor naming that hurts maintainability
   - Missing documentation for public APIs
   - Code duplication that should be refactored
   - > 3 warning-level issues

3. APPROVE if:
   - Code is functional and safe
   - Only minor style/preference issues
   - Tests are present or not needed
   - Changes are low-risk

BE RUTHLESS ON:
- Security issues (always REJECT)
- Missing error handling in critical paths
- Changes that break backward compatibility without migration

BE LENIENT ON:
- Style preferences (unless egregiously bad)
- Minor naming improvements
- Optional optimizations
- Documentation for internal code

---

MR TITLE: {payload.title}

MR DESCRIPTION:
{payload.description or "No description provided"}

FINDINGS FROM OTHER AGENTS:
{findings_text}

AGENT SUMMARIES:
{summaries_text}

CHANGED FILES: {len(payload.changed_files)} files
COMMIT MESSAGES:
{payload.commits_blob()}

Now provide your verdict as JSON:'''

    def _format_findings(self) -> str:
        if not self.all_findings:
            return "No issues found by other agents."
        
        lines = []
        for f in self.all_findings:
            severity = getattr(f, 'severity', 'warning')
            lines.append(f"- [{severity.upper()}] {f.path}:{f.line} - {f.body}")
        return "\n".join(lines)
    
    def _format_summaries(self) -> str:
        if not self.agent_summaries:
            return "No summaries available."
        
        lines = []
        for agent, summary in self.agent_summaries.items():
            lines.append(f"## {agent}\n{summary}")
        return "\n\n".join(lines)
    
    def parse_output(self, output: str) -> AgentResult:
        text = self.postprocess(output)
        try:
            data = json.loads(self._strip_code_fence(text))
        except Exception:
            # Fallback: try to extract verdict from text
            return self._fallback_parse(text)
        
        verdict = data.get("verdict", "needs_fixes").lower()
        confidence = min(1.0, max(0.0, float(data.get("confidence", 0.7))))
        summary = data.get("summary", "Review completed.")
        blocking = data.get("blocking_issues", [])
        suggestions = data.get("suggestions", [])
        
        # Build formatted output
        emoji = {"approve": "✅", "needs_fixes": "⚠️", "reject": "❌"}.get(verdict, "❓")
        verdict_label = {"approve": "APPROVED", "needs_fixes": "NEEDS FIXES", "reject": "REJECTED"}.get(verdict, verdict.upper())
        
        body_parts = [
            f"## {emoji} Verdict: **{verdict_label}**",
            f"*Confidence: {confidence:.0%}*",
            "",
            summary,
        ]
        
        if blocking:
            body_parts.append("\n### 🚫 Blocking Issues")
            for issue in blocking:
                body_parts.append(f"- {issue}")
        
        if suggestions:
            body_parts.append("\n### 💡 Suggestions (non-blocking)")
            for sug in suggestions:
                body_parts.append(f"- {sug}")
        
        content = "\n".join(body_parts)
        
        # Create finding for critical issues
        findings = []
        if verdict == "reject" and blocking:
            for issue in blocking[:3]:
                findings.append(AgentFinding(
                    path="",
                    line=0,
                    body=f"[BLOCKING] {issue}",
                    source=self.key
                ))
        
        return AgentResult(
            key=self.key,
            content=content,
            success=True,
            findings=findings
        )
    
    def _fallback_parse(self, text: str) -> AgentResult:
        """Fallback parsing when JSON fails."""
        lower = text.lower()
        if "reject" in lower:
            verdict = "REJECTED"
            emoji = "❌"
        elif "approve" in lower or "lgtm" in lower:
            verdict = "APPROVED"
            emoji = "✅"
        else:
            verdict = "NEEDS FIXES"
            emoji = "⚠️"
        
        return AgentResult(
            key=self.key,
            content=f"## {emoji} Verdict: **{verdict}**\n\n{text[:500]}",
            success=True
        )
    
    def _strip_code_fence(self, text: str) -> str:
        strip = text.strip()
        if strip.startswith("```"):
            strip = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", strip)
            strip = re.sub(r"\s*```$", "", strip)
        return strip
