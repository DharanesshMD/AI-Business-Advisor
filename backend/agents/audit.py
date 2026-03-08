"""
Audit Analyst Agent for ARIA — Senior Audit Analyst Skill.

Provides audit-specific analysis:
  - Audit risk assessment (AR = IR × CR × DR)
  - Performance materiality calculation
  - Audit program generation for any audit area
  - Internal controls evaluation (COSO framework)
  - Structured audit finding reports (Condition/Criteria/Cause/Effect)

Acts as a Senior Audit Analyst with expertise in ISA, GAAS, IIA standards,
financial statement audits, and internal audit procedures.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("advisor.audit")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Risk levels → numeric multipliers for the audit risk model
_RISK_LEVELS = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.3,
}

# Materiality benchmarks (percentage of each base)
_MATERIALITY_BENCHMARKS = {
    "pre_tax_income": 0.05,   # 5% of pre-tax income
    "total_revenue": 0.005,   # 0.5% of total revenue
    "total_assets": 0.01,     # 1% of total assets
    "gross_profit": 0.02,     # 2% of gross profit
}

# COSO Framework dimensions
_COSO_COMPONENTS = [
    "Control Environment",
    "Risk Assessment",
    "Control Activities",
    "Information & Communication",
    "Monitoring Activities",
]

# Financial statement assertions
_ASSERTIONS = [
    "Existence/Occurrence",
    "Completeness",
    "Valuation/Allocation",
    "Rights & Obligations",
    "Presentation & Disclosure",
]

# ---------------------------------------------------------------------------
# Audit program templates
# ---------------------------------------------------------------------------

_AUDIT_PROGRAMS = {
    "revenue_recognition": {
        "area": "Revenue Recognition",
        "objectives": [
            "Verify that revenue is recorded in the correct period (cut-off)",
            "Confirm revenue is properly recognized per applicable standards (ASC 606 / IFRS 15)",
            "Ensure completeness of revenue transactions",
            "Validate accuracy of revenue amounts and classifications",
        ],
        "key_assertions": ["Occurrence", "Completeness", "Accuracy", "Cut-off", "Classification"],
        "procedures": [
            {"type": "Analytical", "description": "Compare revenue by month/quarter to prior year and budget — investigate variances > 10%", "risk_level": "all"},
            {"type": "Inspection", "description": "Select a sample of sales contracts and verify the 5-step model: (1) identify contract, (2) identify obligations, (3) determine price, (4) allocate price, (5) recognize when satisfied", "risk_level": "all"},
            {"type": "Confirmation", "description": "Send confirmations to top 20 customers for balances and transactions near year-end", "risk_level": "high"},
            {"type": "Recalculation", "description": "Recalculate revenue for multi-element arrangements and verify allocation methodology", "risk_level": "all"},
            {"type": "Inspection", "description": "Examine credit notes and sales returns issued after year-end for potential cut-off issues", "risk_level": "high"},
            {"type": "Inquiry", "description": "Interview sales managers about side agreements, bill-and-hold arrangements, or channel stuffing", "risk_level": "high"},
            {"type": "Inspection", "description": "Test journal entries affecting revenue accounts — focus on manual entries, round amounts, and entries by unusual users", "risk_level": "all"},
            {"type": "Observation", "description": "Observe the revenue cycle process from order to cash collection", "risk_level": "medium"},
        ],
    },
    "accounts_receivable": {
        "area": "Accounts Receivable",
        "objectives": [
            "Verify existence of recorded receivables",
            "Confirm valuation and adequacy of allowance for doubtful accounts",
            "Ensure completeness of AR balance",
            "Verify proper aging and classification",
        ],
        "key_assertions": ["Existence", "Valuation", "Completeness", "Rights & Obligations"],
        "procedures": [
            {"type": "Confirmation", "description": "Send positive confirmations to a statistical sample of customer balances, with emphasis on large and aged balances", "risk_level": "all"},
            {"type": "Analytical", "description": "Perform aging analysis and compare aging buckets to prior periods — investigate shifts", "risk_level": "all"},
            {"type": "Recalculation", "description": "Independently recalculate the allowance for doubtful accounts using historical write-off rates and current economic conditions", "risk_level": "all"},
            {"type": "Inspection", "description": "Examine subsequent cash receipts for the top 25 receivable balances to verify existence", "risk_level": "high"},
            {"type": "Inspection", "description": "Review credit notes issued after period-end for potential overstatement", "risk_level": "all"},
            {"type": "Inquiry", "description": "Discuss collection issues and customer disputes with the credit manager", "risk_level": "medium"},
        ],
    },
    "accounts_payable": {
        "area": "Accounts Payable",
        "objectives": [
            "Verify completeness of recorded liabilities (search for unrecorded liabilities)",
            "Confirm accuracy of AP balances",
            "Ensure proper cut-off at period-end",
            "Validate three-way matching controls are operating effectively",
        ],
        "key_assertions": ["Completeness", "Existence", "Accuracy", "Cut-off"],
        "procedures": [
            {"type": "Analytical", "description": "Compare AP balances and days payable outstanding (DPO) to prior periods — investigate significant changes", "risk_level": "all"},
            {"type": "Inspection", "description": "Search for unrecorded liabilities: examine invoices received and payments made after year-end, review receiving reports around cut-off", "risk_level": "all"},
            {"type": "Confirmation", "description": "Confirm balances with major vendors, especially those with zero or low recorded balances", "risk_level": "high"},
            {"type": "Inspection", "description": "Perform three-way match testing: agree PO → receiving report → vendor invoice for a sample of transactions", "risk_level": "all"},
            {"type": "Recalculation", "description": "Vouch a sample of AP entries to supporting invoices and verify mathematical accuracy", "risk_level": "all"},
            {"type": "Inspection", "description": "Review vendor statement reconciliations for the top 20 vendors", "risk_level": "medium"},
        ],
    },
    "inventory": {
        "area": "Inventory",
        "objectives": [
            "Verify existence of recorded inventory quantities",
            "Confirm proper valuation (lower of cost or net realizable value)",
            "Assess completeness of inventory count",
            "Evaluate obsolescence reserves",
        ],
        "key_assertions": ["Existence", "Valuation", "Completeness", "Rights & Obligations"],
        "procedures": [
            {"type": "Observation", "description": "Observe the physical inventory count — perform independent test counts on a sample basis", "risk_level": "all"},
            {"type": "Recalculation", "description": "Test inventory costing: verify standard costs, FIFO/LIFO/weighted-average calculations for a sample", "risk_level": "all"},
            {"type": "Analytical", "description": "Analyze inventory turnover by product category and age — flag slow-moving items for obsolescence risk", "risk_level": "all"},
            {"type": "Inspection", "description": "Review NRV calculations: compare carrying cost to recent selling prices less costs to sell", "risk_level": "all"},
            {"type": "Inspection", "description": "Examine intercompany and consignment inventory agreements for proper ownership classification", "risk_level": "high"},
            {"type": "Inspection", "description": "Review roll-forward from physical count date to period-end for accuracy", "risk_level": "high"},
        ],
    },
    "fixed_assets": {
        "area": "Property, Plant & Equipment",
        "objectives": [
            "Verify existence and condition of major fixed assets",
            "Confirm proper capitalization vs. expensing decisions",
            "Validate depreciation calculations and useful life estimates",
            "Assess impairment indicators",
        ],
        "key_assertions": ["Existence", "Valuation", "Completeness", "Presentation"],
        "procedures": [
            {"type": "Inspection", "description": "Physically inspect a sample of high-value additions during the period", "risk_level": "all"},
            {"type": "Recalculation", "description": "Recalculate depreciation expense for major asset classes — verify useful lives and methods are appropriate", "risk_level": "all"},
            {"type": "Inspection", "description": "Review the capitalization policy and test a sample of additions to verify proper application (capital vs. expense)", "risk_level": "all"},
            {"type": "Analytical", "description": "Compare repairs & maintenance expense to prior year — investigate significant decreases that might indicate improper capitalization", "risk_level": "all"},
            {"type": "Inspection", "description": "Examine asset disposals and retirements — verify gains/losses are properly calculated", "risk_level": "medium"},
            {"type": "Inquiry", "description": "Discuss with management whether any impairment indicators exist (market changes, physical damage, restructuring)", "risk_level": "all"},
        ],
    },
    "payroll": {
        "area": "Payroll & Employee Benefits",
        "objectives": [
            "Verify existence of employees on payroll (ghost employee detection)",
            "Confirm accuracy of payroll calculations",
            "Ensure proper withholding and remittance of taxes",
            "Validate proper classification of employees vs. contractors",
        ],
        "key_assertions": ["Occurrence", "Accuracy", "Completeness", "Classification"],
        "procedures": [
            {"type": "Analytical", "description": "Compare payroll expense by department to budget and prior year — investigate significant variances", "risk_level": "all"},
            {"type": "Inspection", "description": "Select a sample of employees and trace from HR records → payroll register → bank disbursement", "risk_level": "all"},
            {"type": "Recalculation", "description": "Recalculate gross-to-net pay for a sample: verify statutory deductions, tax rates, overtime calculations", "risk_level": "all"},
            {"type": "Inspection", "description": "Review payroll exception reports: new hires, terminations, salary changes, and duplicate bank accounts", "risk_level": "high"},
            {"type": "Observation", "description": "Observe a payroll distribution to verify employees match records (surprise payroll observation)", "risk_level": "high"},
            {"type": "Inspection", "description": "Verify contractor vs. employee classification using IRS 20-factor test or local equivalent", "risk_level": "medium"},
        ],
    },
    "cash": {
        "area": "Cash & Bank Balances",
        "objectives": [
            "Verify existence of cash balances",
            "Confirm completeness — all accounts are recorded",
            "Identify restricted cash and proper disclosure",
            "Test bank reconciliation accuracy",
        ],
        "key_assertions": ["Existence", "Completeness", "Valuation", "Presentation"],
        "procedures": [
            {"type": "Confirmation", "description": "Send bank confirmations for all accounts (active and closed during the period)", "risk_level": "all"},
            {"type": "Recalculation", "description": "Independently reconcile bank statements to GL for all material accounts at period-end", "risk_level": "all"},
            {"type": "Inspection", "description": "Review outstanding checks > 90 days and investigate stale-dated items", "risk_level": "all"},
            {"type": "Inspection", "description": "Examine deposits in transit — verify cleared on bank statement within reasonable timeframe", "risk_level": "all"},
            {"type": "Inspection", "description": "Review intercompany/related-party transfers near period-end for kiting indicators", "risk_level": "high"},
            {"type": "Inquiry", "description": "Inquire about compensating balance arrangements, restricted cash, and lines of credit", "risk_level": "all"},
        ],
    },
}

# Default program for areas not in the template
_DEFAULT_PROGRAM = {
    "area": "General",
    "objectives": [
        "Verify existence/occurrence of recorded transactions",
        "Confirm completeness of recorded balances",
        "Validate accuracy and proper valuation",
        "Ensure proper period cut-off",
        "Verify rights and obligations",
    ],
    "key_assertions": _ASSERTIONS,
    "procedures": [
        {"type": "Analytical", "description": "Perform trend analysis and compare to prior periods and industry benchmarks", "risk_level": "all"},
        {"type": "Inspection", "description": "Select a representative sample and trace to supporting documentation", "risk_level": "all"},
        {"type": "Recalculation", "description": "Independently recalculate key balances and computations", "risk_level": "all"},
        {"type": "Inquiry", "description": "Interview process owners about significant changes, unusual transactions, and control weaknesses", "risk_level": "all"},
        {"type": "Observation", "description": "Observe key processes and controls in operation", "risk_level": "medium"},
    ],
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _compute_sample_size(
    population_size: int,
    confidence_level: float = 0.95,
    tolerable_error_rate: float = 0.05,
    expected_error_rate: float = 0.01,
) -> int:
    """
    Compute audit sample size using attribute sampling formula.
    
    Uses the simplified formula: n = (Z² × p × (1-p)) / E²
    adjusted for finite population.
    """
    import math
    
    # Z-scores for common confidence levels
    z_scores = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_scores.get(confidence_level, 1.96)
    
    p = expected_error_rate
    e = tolerable_error_rate
    
    # Infinite population sample size
    n_infinite = (z ** 2 * p * (1 - p)) / (e ** 2)
    
    # Finite population correction
    if population_size > 0:
        n = n_infinite / (1 + (n_infinite - 1) / population_size)
    else:
        n = n_infinite
    
    return max(int(math.ceil(n)), 25)  # Minimum sample of 25


def _risk_to_numeric(level: str) -> float:
    """Convert risk level string to numeric value."""
    return _RISK_LEVELS.get(level.lower().strip(), 0.6)


# ---------------------------------------------------------------------------
# Main Agent
# ---------------------------------------------------------------------------

class AuditAnalystAgent:
    """
    Senior Audit Analyst Agent.
    
    Provides comprehensive audit analysis capabilities following
    ISA, GAAS, and IIA standards.
    """

    async def assess_audit_risk(
        self,
        total_revenue: Optional[float] = None,
        total_assets: Optional[float] = None,
        pre_tax_income: Optional[float] = None,
        gross_profit: Optional[float] = None,
        inherent_risk: str = "medium",
        control_risk: str = "medium",
        industry: Optional[str] = None,
        is_public_company: bool = False,
    ) -> Dict[str, Any]:
        """
        Compute audit risk assessment and performance materiality.

        Uses the audit risk model: AR = IR × CR × DR
        Calculates materiality using multiple benchmarks and selects
        the most conservative (lowest) value.
        """
        # --- Risk Assessment ---
        ir = _risk_to_numeric(inherent_risk)
        cr = _risk_to_numeric(control_risk)
        
        # Target audit risk (generally 5% for reasonable assurance)
        target_ar = 0.05
        
        # Detection risk = AR / (IR × CR)
        ir_cr = ir * cr
        if ir_cr > 0:
            dr = target_ar / ir_cr
            dr = min(dr, 1.0)  # Cap at 1.0
        else:
            dr = 1.0
        
        # Actual audit risk
        actual_ar = ir * cr * dr
        
        # Determine audit approach based on detection risk
        if dr <= 0.3:
            audit_approach = "Primarily Substantive"
            approach_detail = (
                "Detection risk is very low — extensive substantive procedures required. "
                "Increase sample sizes, add surprise procedures, use more experienced staff."
            )
        elif dr <= 0.6:
            audit_approach = "Combined Approach"
            approach_detail = (
                "Moderate detection risk — use a combination of tests of controls and "
                "substantive procedures. Standard sample sizes appropriate."
            )
        else:
            audit_approach = "Reduced Substantive"
            approach_detail = (
                "High detection risk tolerance — may rely more on tests of controls. "
                "Reduced substantive sample sizes may be acceptable."
            )
        
        # --- Materiality Calculation ---
        materiality_calcs = {}
        materiality_values = []
        
        bases = {
            "pre_tax_income": pre_tax_income,
            "total_revenue": total_revenue,
            "total_assets": total_assets,
            "gross_profit": gross_profit,
        }
        
        for base_name, base_value in bases.items():
            if base_value and base_value > 0:
                pct = _MATERIALITY_BENCHMARKS[base_name]
                mat_value = base_value * pct
                materiality_calcs[base_name] = {
                    "base_value": round(base_value, 2),
                    "benchmark_percentage": f"{pct:.1%}",
                    "materiality": round(mat_value, 2),
                }
                materiality_values.append(mat_value)
        
        # Overall materiality = lowest computed value (most conservative)
        overall_materiality = round(min(materiality_values), 2) if materiality_values else None
        
        # Performance materiality = 50-75% of overall (use 60% as default)
        performance_materiality = round(overall_materiality * 0.60, 2) if overall_materiality else None
        
        # SAD threshold (clearly trivial) = 5% of overall materiality
        sad_threshold = round(overall_materiality * 0.05, 2) if overall_materiality else None
        
        # SOX considerations
        sox_notes = None
        if is_public_company:
            sox_notes = (
                "As a public company, SOX 404 requirements apply. Management must assess "
                "and report on the effectiveness of internal controls over financial reporting (ICFR). "
                "The auditor must issue a separate opinion on ICFR effectiveness."
            )
        
        return {
            "risk_assessment": {
                "inherent_risk": {"level": inherent_risk, "value": ir},
                "control_risk": {"level": control_risk, "value": cr},
                "detection_risk": {"value": round(dr, 4)},
                "target_audit_risk": target_ar,
                "actual_audit_risk": round(actual_ar, 4),
                "audit_approach": audit_approach,
                "approach_detail": approach_detail,
            },
            "materiality": {
                "calculations": materiality_calcs,
                "overall_materiality": overall_materiality,
                "performance_materiality": performance_materiality,
                "clearly_trivial_threshold": sad_threshold,
                "note": (
                    "Overall materiality is the lowest of the computed values (most conservative). "
                    "Performance materiality is set at 60% of overall to reduce aggregation risk."
                ),
            },
            "sox_considerations": sox_notes,
            "industry": industry,
            "recommendations": _generate_risk_recommendations(inherent_risk, control_risk, dr),
        }

    async def generate_audit_program(
        self,
        audit_area: str,
        industry: Optional[str] = None,
        is_sox: bool = False,
        risk_level: str = "medium",
    ) -> Dict[str, Any]:
        """
        Generate a structured audit program for the specified area.
        """
        # Normalize the audit area to match templates
        area_key = audit_area.lower().strip().replace(" ", "_").replace("&", "and")
        
        # Try to find matching template
        program = None
        for key, template in _AUDIT_PROGRAMS.items():
            if key in area_key or area_key in key:
                program = template.copy()
                break
        
        if not program:
            # Check for partial matches
            for key, template in _AUDIT_PROGRAMS.items():
                if any(word in area_key for word in key.split("_")):
                    program = template.copy()
                    break
        
        if not program:
            program = _DEFAULT_PROGRAM.copy()
            program["area"] = audit_area.title()
        
        # Filter procedures by risk level
        if risk_level.lower() == "low":
            procedures = [p for p in program["procedures"] if p["risk_level"] in ("all", "low")]
        elif risk_level.lower() == "high":
            procedures = program["procedures"]  # Include all procedures
        else:
            procedures = [p for p in program["procedures"] if p["risk_level"] in ("all", "medium")]
        
        # Recommend sample sizes
        sample_guidance = {
            "high_risk": _compute_sample_size(500, 0.95, 0.05, 0.02),
            "medium_risk": _compute_sample_size(500, 0.90, 0.05, 0.01),
            "low_risk": _compute_sample_size(500, 0.90, 0.07, 0.01),
        }
        
        # SOX additions
        sox_procedures = []
        if is_sox:
            sox_procedures = [
                {"type": "Control Testing", "description": "Test operating effectiveness of key controls — minimum 25 items for daily controls, 5 for monthly, 2 for quarterly, 1 for annual"},
                {"type": "Walkthrough", "description": "Perform end-to-end walkthrough of the process — document control points, IT dependencies, and segregation of duties"},
                {"type": "IT General Controls", "description": "Verify ITGCs supporting automated controls: access management, change management, computer operations, program development"},
            ]
        
        return {
            "audit_area": program["area"],
            "objectives": program["objectives"],
            "key_assertions": program["key_assertions"],
            "procedures": procedures,
            "sox_procedures": sox_procedures if is_sox else None,
            "sample_size_guidance": sample_guidance,
            "risk_level": risk_level,
            "industry_context": industry,
            "generated_at": datetime.now().isoformat(),
        }

    async def evaluate_internal_controls(
        self,
        control_environment: str = "medium",
        risk_assessment: str = "medium",
        control_activities: str = "medium",
        information_communication: str = "medium",
        monitoring: str = "medium",
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate internal controls using the COSO framework.
        """
        components = {
            "Control Environment": control_environment,
            "Risk Assessment": risk_assessment,
            "Control Activities": control_activities,
            "Information & Communication": information_communication,
            "Monitoring Activities": monitoring,
        }
        
        # Score each component
        scored = {}
        total_score = 0
        for component, level in components.items():
            numeric = _risk_to_numeric(level)
            # For controls, lower risk = higher effectiveness
            effectiveness = 1.0 - numeric
            scored[component] = {
                "assessed_level": level,
                "effectiveness_score": round(effectiveness, 2),
                "rating": (
                    "Effective" if effectiveness >= 0.7
                    else "Partially Effective" if effectiveness >= 0.4
                    else "Ineffective"
                ),
            }
            total_score += effectiveness
        
        avg_score = total_score / len(components)
        
        # Overall assessment
        if avg_score >= 0.7:
            overall = "Effective"
            overall_detail = (
                "The system of internal controls is operating effectively. "
                "The auditor may rely on controls to reduce substantive testing."
            )
        elif avg_score >= 0.4:
            overall = "Partially Effective"
            overall_detail = (
                "Material weaknesses or significant deficiencies exist. "
                "A combined audit approach is recommended with increased substantive procedures "
                "in areas where controls are weak."
            )
        else:
            overall = "Ineffective"
            overall_detail = (
                "The control environment has pervasive weaknesses. "
                "A fully substantive audit approach is required. "
                "Consider communicating material weaknesses to those charged with governance."
            )
        
        # Generate recommendations per weak component
        recommendations = []
        for component, data in scored.items():
            if data["rating"] != "Effective":
                recommendations.append({
                    "component": component,
                    "issue": f"{component} assessed as {data['rating']}",
                    "recommendation": _get_control_recommendation(component, data["assessed_level"]),
                })
        
        return {
            "framework": "COSO 2013 (Internal Control — Integrated Framework)",
            "component_assessments": scored,
            "overall_assessment": {
                "rating": overall,
                "average_effectiveness": round(avg_score, 2),
                "detail": overall_detail,
            },
            "recommendations": recommendations,
            "description": description,
            "assessed_at": datetime.now().isoformat(),
        }

    async def generate_audit_finding(
        self,
        condition: str,
        criteria: str,
        cause: Optional[str] = None,
        effect: Optional[str] = None,
        audit_area: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a structured audit finding in the standard
        Condition/Criteria/Cause/Effect format.
        """
        # Auto-assess severity based on keywords
        severity = _assess_severity(condition, effect)
        
        # Generate recommendation based on the finding
        recommendation = _generate_finding_recommendation(condition, criteria)
        
        return {
            "finding_id": f"FIND-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "audit_area": audit_area or "General",
            "severity": severity["level"],
            "severity_score": severity["score"],
            "condition": condition,
            "criteria": criteria,
            "cause": cause or "Root cause analysis in progress — additional inquiry recommended.",
            "effect": effect or "Potential impact requires further quantification.",
            "recommendation": recommendation,
            "management_response": "[To be completed by management]",
            "remediation_deadline": "[To be determined]",
            "status": "Open",
            "generated_at": datetime.now().isoformat(),
        }


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _generate_risk_recommendations(
    inherent_risk: str, control_risk: str, detection_risk: float
) -> List[str]:
    """Generate practical recommendations based on risk levels."""
    recs = []
    
    if inherent_risk.lower() == "high":
        recs.append(
            "High inherent risk: Assign senior audit staff to high-risk areas. "
            "Consider involving specialists (valuation, IT, tax) where applicable."
        )
    
    if control_risk.lower() == "high":
        recs.append(
            "High control risk: Internal controls cannot be relied upon. "
            "Perform a fully substantive audit approach with expanded sample sizes."
        )
        recs.append(
            "Consider communicating control weaknesses as a significant deficiency "
            "or material weakness to those charged with governance."
        )
    
    if detection_risk <= 0.3:
        recs.append(
            "Low detection risk required: Use experienced staff, "
            "increase sample sizes by 50%, add surprise procedures, "
            "and consider dual-purpose tests."
        )
    
    if inherent_risk.lower() == "high" and control_risk.lower() == "high":
        recs.append(
            "CRITICAL: Both inherent and control risk are high. "
            "Consider whether the engagement risk is acceptable. "
            "Document the risk assessment thoroughly and discuss with the engagement partner."
        )
    
    if not recs:
        recs.append(
            "Standard audit approach is appropriate. "
            "Focus on efficient procedures while maintaining professional skepticism."
        )
    
    return recs


def _get_control_recommendation(component: str, level: str) -> str:
    """Get specific recommendation for a weak COSO component."""
    recommendations = {
        "Control Environment": (
            "Strengthen tone at the top — ensure management demonstrates commitment to integrity. "
            "Review and update the code of conduct. Assess board independence and oversight."
        ),
        "Risk Assessment": (
            "Implement a formal risk assessment process. Identify and analyze risks to achieving objectives. "
            "Consider both internal and external factors, including fraud risk."
        ),
        "Control Activities": (
            "Review and strengthen authorization procedures, segregation of duties, and physical controls. "
            "Ensure automated controls have proper IT general controls supporting them."
        ),
        "Information & Communication": (
            "Improve internal reporting and communication channels. Ensure relevant information flows "
            "to appropriate personnel for decision-making. Review IT system controls."
        ),
        "Monitoring Activities": (
            "Establish ongoing monitoring and periodic evaluations of internal controls. "
            "Implement an internal audit function if one does not exist. "
            "Ensure deficiencies are communicated and remediated timely."
        ),
    }
    return recommendations.get(component, "Implement corrective actions to address the identified weakness.")


def _assess_severity(condition: str, effect: Optional[str]) -> Dict[str, Any]:
    """Assess severity of an audit finding based on keywords."""
    text = f"{condition} {effect or ''}".lower()
    
    critical_keywords = ["fraud", "material misstatement", "regulatory violation", "illegal", "theft",
                         "embezzlement", "data breach", "securities violation", "restatement"]
    high_keywords = ["material weakness", "significant deficiency", "non-compliance", "overstatement",
                     "understatement", "segregation of duties", "override", "unauthorized"]
    medium_keywords = ["inconsistency", "untimely", "incomplete", "error", "variance", "deviation",
                       "reconciliation", "documentation"]
    
    if any(kw in text for kw in critical_keywords):
        return {"level": "Critical", "score": 4}
    elif any(kw in text for kw in high_keywords):
        return {"level": "High", "score": 3}
    elif any(kw in text for kw in medium_keywords):
        return {"level": "Medium", "score": 2}
    else:
        return {"level": "Low", "score": 1}


def _generate_finding_recommendation(condition: str, criteria: str) -> str:
    """Generate a recommendation based on the finding."""
    text = f"{condition} {criteria}".lower()
    
    if "segregation" in text or "duties" in text:
        return (
            "Implement proper segregation of duties by separating authorization, custody, "
            "and recording functions. Where segregation is not feasible due to size constraints, "
            "implement compensating controls such as independent review and management oversight."
        )
    elif "reconciliation" in text:
        return (
            "Establish a timely reconciliation process with independent review. "
            "Reconciliations should be performed at least monthly, reviewed by a supervisor, "
            "and discrepancies investigated and resolved promptly."
        )
    elif "documentation" in text:
        return (
            "Implement proper documentation procedures including standardized templates, "
            "clear retention policies, and regular compliance monitoring. "
            "Ensure all transactions are supported by appropriate evidence."
        )
    elif "approval" in text or "authorization" in text:
        return (
            "Review and enforce authorization policies. Ensure proper approval hierarchies "
            "with defined dollar thresholds. Implement system-enforced approval workflows "
            "where possible to prevent unauthorized transactions."
        )
    else:
        return (
            "Management should develop and implement a corrective action plan addressing "
            "the root cause of this finding. The plan should include specific actions, "
            "responsible parties, and target completion dates. Internal audit should "
            "perform follow-up testing to verify remediation effectiveness."
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_audit_agent: Optional[AuditAnalystAgent] = None


def get_audit_agent() -> AuditAnalystAgent:
    global _audit_agent
    if _audit_agent is None:
        _audit_agent = AuditAnalystAgent()
    return _audit_agent
