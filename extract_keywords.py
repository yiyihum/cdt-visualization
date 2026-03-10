"""Extract keywords from CDT statements and gates, output editable JSON for visualization.

Workflow:
  1. Run this script to generate initial keyword suggestions
  2. Manually edit docs/data/cdt_with_keywords.json to refine keywords
  3. Push to GitHub Pages — visualization loads data via fetch()

Usage:
    python openai_case/adapter_phase/visualization/extract_keywords.py
"""

import json
import re
from pathlib import Path

FUNCTION_WORDS = set(
    "a an the this that these those of in on at by for with from to as is are "
    "was were has have had do does did be been being but and or if so no not "
    "may can could would should might must shall will it its they their them "
    "we our us he his him she her you your who whom whose which when where "
    "how what why each every some any all many much few several other another "
    "both either neither nor yet also often frequently actively consistently "
    "only just even still already very quite rather too enough such same own "
    "new next than then there here thus hence into upon within without across "
    "along among through between against during before after until since while "
    "although though whereas unless because whether despite about regarding "
    "concerning tends appears seems likely able".split()
)

# Gate text → short label (hand-crafted)
GATE_LABELS = {
    "Does the scene involve OpenAI piloting, testing, or limiting access to new features or products before a broader rollout?":
        "Product Piloting",
    "Does the scene describe OpenAI collaborating with external partners, organizations, or platforms, or seeking to expand its ecosystem?":
        "Partnership & Ecosystem",
    "Does the scene indicate that OpenAI is encountering or anticipating technical, safety, or ethical challenges, or facing public or regulatory scrutiny?":
        "Safety & Ethics",
    "Does the scene describe OpenAI facing legal, regulatory, or governance challenges, or significant stakeholder pressure?":
        "Legal & Governance",
    "Does the scene involve OpenAI facing criticism, negative feedback, or evidence of unmet user needs regarding its products or user experience?":
        "User Feedback",
    "Does the scene involve OpenAI pursuing significant growth, expansion, or investment opportunities?":
        "Growth & Investment",
    "Does the scene indicate that OpenAI is engaging with new regulatory environments or compliance requirements in different regions?":
        "Regional Compliance",
    "Does the scene suggest that OpenAI's next action may involve restoring, re-enabling, or maintaining previously removed or deprecated features or models due to renewed user demand or backlash?":
        "Feature Restoration",
    "Does the scene involve OpenAI collaborating with external partners or integrating third-party services, suggesting a possible expansion or deepening of such integrations?":
        "Third-party Integration",
    "Does the scene mention OpenAI releasing a simplified or limited version of a tool or feature, implying that OpenAI may monitor usage and adjust availability or functionality in response?":
        "Lightweight Launch",
    "Does the scene involve OpenAI facing legal, regulatory, or stakeholder pressures that could impact its governance, organizational structure, or autonomy?":
        "Governance Pressure",
    "Does the scene suggest that OpenAI is encountering financial pressures, increased operational costs, or the need for substantial capital to support ongoing or planned initiatives?":
        "Financial Pressure",
    "Does the scene involve OpenAI experiencing strained, shifting, or insufficient partnerships, dependencies, or market dynamics that could prompt a change in alliances or business relationships?":
        "Partnership Shifts",
    "Does the scene describe OpenAI piloting, testing, or gradually rolling out new features, products, or interaction models to select regions or user groups?":
        "Gradual Rollout",
    "Does the scene suggest that OpenAI is seeking to enhance user engagement, collaboration, or expand the types of activities users can perform within its platform?":
        "User Engagement",
    "Does the scene involve the availability of specialized talent, teams, or startups with relevant expertise or technology that could accelerate OpenAI's goals?":
        "Talent & Acquisitions",
    "Does the scene indicate that OpenAI is responding to region-specific regulatory, cultural, or market requirements?":
        "Regional Adaptation",
    "Does the scene suggest that OpenAI is seeking to accelerate adoption, differentiation, or market presence through collaborations with influential partners, organizations, or experts?":
        "Strategic Collaboration",
    "Does the scene involve OpenAI encountering significant stakeholder, legal, or regulatory pressures that could prompt reconsideration or adjustment of its governance or organizational structure?":
        "Governance Restructuring",
    "Does the scene involve OpenAI encountering gaps in expertise, leadership, or technical capability—such as departures or competitive talent movement—that could prompt recruitment or rehiring of key personnel?":
        "Talent Recruitment",
    "Does the scene suggest that OpenAI's next action could be influenced by the need to meet compliance, security, or operational requirements of specific industries, sectors, or customer segments?":
        "Industry Compliance",
    "Does the scene involve significant organizational or leadership changes, or internal restructuring, that could influence OpenAI's next action?":
        "Org Restructuring",
    "Does the scene suggest that OpenAI's next action could be motivated by the need to accelerate adoption among large-scale, institutional, or government customers?":
        "Enterprise Adoption",
    "Does the scene involve OpenAI responding to increased competition, market shifts, or the emergence of rival products?":
        "Competition Response",
    "Does the scene indicate OpenAI facing public, media, or stakeholder criticism regarding its policies, transparency, or the societal impact of its products?":
        "Public Criticism",
    "Does the scene involve OpenAI encountering incidents, risks, or scrutiny related to user safety, harm, or the well-being of vulnerable groups?":
        "User Safety Incidents",
    "Does the scene describe OpenAI facing heightened scrutiny or requirements regarding privacy, data security, or responsible AI use?":
        "Privacy & Data Security",
    "Does the scene involve OpenAI being subject to legal disputes, acquisition offers, or challenges to its organizational autonomy or governance?":
        "Legal Disputes",
    "Does the scene indicate OpenAI experiencing resource constraints, time pressure, or external urgency affecting its safety, evaluation, or reporting processes?":
        "Resource Constraints",
    "Does the scene involve OpenAI responding to calls for increased transparency, openness, or alignment with industry norms regarding open-source or accessible AI?":
        "Transparency & Openness",
    "Does the scene show OpenAI engaging with influential stakeholders, such as regulators, policymakers, major partners, or investors, in ways that could affect its strategy or operations?":
        "Stakeholder Engagement",
    "Does the scene involve OpenAI encountering new or intensified risks related to misuse, security breaches, or information leaks?":
        "Security & Misuse",
    "Does the scene describe OpenAI seeking to expand its reach or accessibility through new platforms, partnerships, or distribution channels?":
        "Distribution Expansion",
    "Does the scene involve OpenAI's next action being triggered by incidents or concerns related to user safety, especially for vulnerable groups such as minors?":
        "Vulnerable User Safety",
    "Does the scene involve OpenAI's next action being shaped by increased competition or external pressure from other technology providers?":
        "Competitive Pressure",
    "Does the scene involve OpenAI's next action being motivated by opportunities to expand its user base, enter new markets, or respond to stakeholder expectations?":
        "Market Expansion",
}


def extract_keywords(text: str) -> list[str]:
    """Extract content words from text by filtering out function words."""
    words = re.findall(r"[A-Za-z][\w']*(?:-[\w]+)*", text)
    keywords = []
    for w in words:
        if w.lower() not in FUNCTION_WORDS and len(w) >= 2:
            keywords.append(w)
    return keywords


def gate_to_label(gate: str) -> str:
    if gate in GATE_LABELS:
        return GATE_LABELS[gate]
    return gate[:45] + "…" if len(gate) > 45 else gate


def enrich_cdt_node(node: dict, node_id: str = "Root") -> dict:
    """Convert raw CDT node → d3 tree node with keyword annotations."""
    stmts = node.get("statements", [])
    gates = node.get("gates", [])
    children_raw = node.get("children", [])

    result = {
        "name": "Root" if node_id == "Root" else node_id,
        "node_id": node_id,
        "gate": "",
        "gate_keywords": [],
        "statements": [
            {"text": s, "keywords": extract_keywords(s)} for s in stmts
        ],
        "children": [],
    }

    for i, (gate, child) in enumerate(zip(gates, children_raw)):
        child_id = f"{i+1}" if node_id == "Root" else f"{node_id}-{i+1}"
        child_node = enrich_cdt_node(child, child_id)
        child_node["name"] = gate_to_label(gate)
        child_node["gate"] = gate
        child_node["gate_keywords"] = extract_keywords(gate)
        result["children"].append(child_node)

    return result


def enrich_adapter(adapter_data: list) -> list:
    """Add keywords to adapter action statements."""
    enriched = []
    for phase in adapter_data:
        phase_out = dict(phase)
        actions = []
        for a in phase.get("actions", []):
            a_out = dict(a)
            if "old_statement" in a:
                a_out["old_keywords"] = extract_keywords(a["old_statement"])
            if "new_statement" in a:
                a_out["new_keywords"] = extract_keywords(a["new_statement"])
            actions.append(a_out)
        phase_out["actions"] = actions
        enriched.append(phase_out)
    return enriched


def main():
    root = Path(__file__).resolve().parents[3]  # group-behaviors/
    cdt_path = root / "openai_case/adapter_phase/adapted_cdts/base_cdt.json"
    adapter_path = root / "openai_case/adapter_phase/visualization/adapter_display.json"
    out_dir = root / "docs" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Enrich CDT
    cdt = json.loads(cdt_path.read_text())
    tree = enrich_cdt_node(cdt)
    tree_out = out_dir / "cdt_with_keywords.json"
    tree_out.write_text(json.dumps(tree, ensure_ascii=False, indent=2))
    print(f"CDT tree → {tree_out}")

    # Enrich adapter phases
    adapter = json.loads(adapter_path.read_text())
    adapter_enriched = enrich_adapter(adapter)
    adapter_out = out_dir / "adapter_phases.json"
    adapter_out.write_text(json.dumps(adapter_enriched, ensure_ascii=False, indent=2))
    print(f"Adapter phases → {adapter_out}")

    print(f"\nEdit keywords in {out_dir}/, then push to GitHub Pages.")


if __name__ == "__main__":
    main()
