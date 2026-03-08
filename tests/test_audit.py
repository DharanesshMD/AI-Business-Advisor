"""
Unit tests for the Audit Analyst Agent and Audit Data Engine.

Tests cover:
  - Risk assessment and materiality calculations
  - Audit program generation
  - Internal controls evaluation (COSO)
  - Audit finding generation
  - Benford's Law analysis
  - Duplicate detection
  - Gap analysis
  - Aging analysis
  - Stratified sampling
  - Journal entry testing
  - Three-way matching
  - Pydantic model validation
"""

import pytest
import json
import asyncio
from backend.agents.audit import AuditAnalystAgent, _compute_sample_size, _risk_to_numeric, _assess_severity
from backend.agents.audit_data import AuditDataEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def audit_agent():
    return AuditAnalystAgent()


@pytest.fixture
def data_engine():
    return AuditDataEngine()


@pytest.fixture
def sample_csv():
    """Simple CSV for testing."""
    return """invoice_number,vendor,amount,date,description
1001,Vendor A,5000.00,2025-01-15,Office supplies
1002,Vendor B,12500.50,2025-01-20,IT equipment
1003,Vendor A,5000.00,2025-01-25,Office supplies
1004,Vendor C,75000.00,2025-02-01,Server hardware
1005,Vendor B,3200.00,2025-02-10,Software license
1007,Vendor D,10000.00,2025-02-15,Consulting services
1008,Vendor A,5000.00,2025-02-20,Office supplies
1009,Vendor E,45000.00,2025-03-01,Marketing campaign
1010,Vendor C,8500.00,2025-03-05,Maintenance"""


@pytest.fixture
def benford_csv():
    """CSV with numbers that roughly follow Benford's Law."""
    import random
    random.seed(42)
    # Generate Benford-like data
    lines = ["id,amount"]
    for i in range(200):
        # Log-uniform distribution naturally follows Benford's
        val = 10 ** (random.uniform(1, 5))
        lines.append(f"{i+1},{round(val, 2)}")
    return "\n".join(lines)


@pytest.fixture
def journal_entry_csv():
    """CSV for journal entry testing."""
    return """entry_id,amount,date,user,description
JE001,10000.00,2025-01-15,admin,Monthly accrual
JE002,5000.00,2025-01-18,jsmith,Expense adjustment
JE003,50000.00,2025-01-19,admin,Revenue correction
JE004,9800.00,2025-01-20,admin,Miscellaneous adjustment
JE005,25000.00,2025-01-25,rjones,Intercompany transfer
JE006,3000.00,2025-02-01,admin,Office supplies
JE007,100000.00,2025-02-05,cfo_override,Year-end adjustment
JE008,4900.00,2025-02-08,admin,Various corrections
JE009,7500.00,2025-02-15,jsmith,Prepaid expense
JE010,15000.00,2025-02-22,admin,Depreciation entry
JE011,8000.00,2025-03-01,admin,Monthly accrual
JE012,20000.00,2025-03-08,admin,Adjustment"""


@pytest.fixture
def three_way_csv():
    """CSV for three-way match testing."""
    return """po_number,invoice_number,receipt_number,amount,quantity
PO001,INV001,REC001,5000.00,10
PO001,INV002,REC001,5500.00,10
PO002,INV003,REC002,12000.00,5
PO002,INV003,REC002,12000.00,5
PO003,INV004,,8000.00,3
PO004,INV005,REC004,3000.00,20"""


# ---------------------------------------------------------------------------
# Risk Assessment Tests
# ---------------------------------------------------------------------------

class TestRiskAssessment:
    """Tests for audit risk assessment."""

    @pytest.mark.asyncio
    async def test_basic_risk_assessment(self, audit_agent):
        """Test basic risk assessment with all inputs."""
        result = await audit_agent.assess_audit_risk(
            total_revenue=50_000_000,
            total_assets=200_000_000,
            pre_tax_income=5_000_000,
            gross_profit=20_000_000,
            inherent_risk="high",
            control_risk="medium",
        )

        assert "risk_assessment" in result
        assert "materiality" in result
        assert result["risk_assessment"]["inherent_risk"]["level"] == "high"
        assert result["risk_assessment"]["control_risk"]["level"] == "medium"
        assert result["risk_assessment"]["detection_risk"]["value"] > 0

    @pytest.mark.asyncio
    async def test_materiality_calculation(self, audit_agent):
        """Test materiality uses lowest benchmark."""
        result = await audit_agent.assess_audit_risk(
            total_revenue=100_000_000,  # 0.5% = 500,000
            total_assets=200_000_000,   # 1% = 2,000,000
            pre_tax_income=10_000_000,  # 5% = 500,000
            gross_profit=30_000_000,    # 2% = 600,000
            inherent_risk="medium",
            control_risk="medium",
        )

        mat = result["materiality"]
        assert mat["overall_materiality"] is not None
        # Should be the lowest: 500,000 (from revenue or pre-tax income)
        assert mat["overall_materiality"] == 500_000.0
        # Performance materiality = 60% of overall
        assert mat["performance_materiality"] == 300_000.0

    @pytest.mark.asyncio
    async def test_high_risk_both(self, audit_agent):
        """Test that high IR + high CR triggers critical recommendations."""
        result = await audit_agent.assess_audit_risk(
            inherent_risk="high",
            control_risk="high",
        )

        recs = result["recommendations"]
        assert any("CRITICAL" in r for r in recs)

    @pytest.mark.asyncio
    async def test_low_risk_approach(self, audit_agent):
        """Test that low risk levels result in combined approach (DR=0.556)."""
        result = await audit_agent.assess_audit_risk(
            inherent_risk="low",
            control_risk="low",
        )

        # DR = 0.05 / (0.3 * 0.3) = 0.556 -> Combined Approach
        assert result["risk_assessment"]["audit_approach"] == "Combined Approach"

    @pytest.mark.asyncio
    async def test_sox_considerations(self, audit_agent):
        """Test SOX notes are included for public companies."""
        result = await audit_agent.assess_audit_risk(
            inherent_risk="medium",
            control_risk="medium",
            is_public_company=True,
        )

        assert result["sox_considerations"] is not None
        assert "SOX 404" in result["sox_considerations"]


# ---------------------------------------------------------------------------
# Audit Program Tests
# ---------------------------------------------------------------------------

class TestAuditProgram:
    """Tests for audit program generation."""

    @pytest.mark.asyncio
    async def test_revenue_program(self, audit_agent):
        """Test revenue recognition audit program."""
        result = await audit_agent.generate_audit_program("revenue recognition")

        assert result["audit_area"] == "Revenue Recognition"
        assert len(result["objectives"]) > 0
        assert len(result["procedures"]) > 0
        assert "key_assertions" in result

    @pytest.mark.asyncio
    async def test_program_structure(self, audit_agent):
        """Test that program has required structure."""
        result = await audit_agent.generate_audit_program("accounts payable")

        assert "audit_area" in result
        assert "objectives" in result
        assert "procedures" in result
        assert "sample_size_guidance" in result
        for proc in result["procedures"]:
            assert "type" in proc
            assert "description" in proc

    @pytest.mark.asyncio
    async def test_sox_procedures(self, audit_agent):
        """Test SOX procedures are added when is_sox=True."""
        result = await audit_agent.generate_audit_program("revenue", is_sox=True)

        assert result["sox_procedures"] is not None
        assert len(result["sox_procedures"]) > 0


# ---------------------------------------------------------------------------
# Internal Controls Tests
# ---------------------------------------------------------------------------

class TestInternalControls:
    """Tests for COSO controls evaluation."""

    @pytest.mark.asyncio
    async def test_effective_controls(self, audit_agent):
        """Test that low-risk controls are rated effective."""
        result = await audit_agent.evaluate_internal_controls(
            control_environment="low",
            risk_assessment="low",
            control_activities="low",
            information_communication="low",
            monitoring="low",
        )

        assert result["overall_assessment"]["rating"] == "Effective"

    @pytest.mark.asyncio
    async def test_ineffective_controls(self, audit_agent):
        """Test that high-risk controls are rated ineffective."""
        result = await audit_agent.evaluate_internal_controls(
            control_environment="high",
            risk_assessment="high",
            control_activities="high",
            information_communication="high",
            monitoring="high",
        )

        assert result["overall_assessment"]["rating"] == "Ineffective"
        assert len(result["recommendations"]) > 0


# ---------------------------------------------------------------------------
# Audit Finding Tests
# ---------------------------------------------------------------------------

class TestAuditFinding:
    """Tests for structured audit finding generation."""

    @pytest.mark.asyncio
    async def test_finding_structure(self, audit_agent):
        """Test finding has all required fields."""
        result = await audit_agent.generate_audit_finding(
            condition="10% of journal entries lack supporting documentation",
            criteria="Company policy requires supporting documentation for all entries",
            cause="Inadequate training on documentation requirements",
            effect="Potential for undetected errors or fraud",
        )

        assert "finding_id" in result
        assert "condition" in result
        assert "criteria" in result
        assert "cause" in result
        assert "effect" in result
        assert "recommendation" in result
        assert "severity" in result

    @pytest.mark.asyncio
    async def test_severity_critical(self, audit_agent):
        """Test that fraud-related findings get Critical severity."""
        result = await audit_agent.generate_audit_finding(
            condition="Evidence of potential fraud in vendor payments",
            criteria="Anti-fraud policy",
            effect="Material misstatement risk",
        )

        assert result["severity"] == "Critical"


# ---------------------------------------------------------------------------
# Data Analytics Tests
# ---------------------------------------------------------------------------

class TestBenfordAnalysis:
    """Tests for Benford's Law analysis."""

    @pytest.mark.asyncio
    async def test_benford_conforming(self, data_engine, benford_csv):
        """Test Benford analysis on naturally distributed data."""
        result = await data_engine.benford_analysis(benford_csv, "amount")

        assert "chi_square_statistic" in result
        assert "digit_comparison" in result
        assert len(result["digit_comparison"]) == 9
        # Naturally generated data should roughly conform
        assert result["conformity"] in ("CONFORMING", "MARGINAL")

    @pytest.mark.asyncio
    async def test_benford_missing_column(self, data_engine, sample_csv):
        """Test Benford analysis with missing column returns error."""
        result = await data_engine.benford_analysis(sample_csv, "nonexistent")
        assert "error" in result


class TestDuplicateDetection:
    """Tests for duplicate detection."""

    @pytest.mark.asyncio
    async def test_find_duplicates(self, data_engine, sample_csv):
        """Test duplicate detection finds vendor+amount duplicates."""
        result = await data_engine.detect_duplicates(
            sample_csv, columns=["vendor", "amount"]
        )

        assert result["total_records"] == 9
        # Vendor A, 5000.00 appears 3 times
        assert result["duplicate_records"] > 0
        assert result["duplicate_groups"] > 0


class TestGapAnalysis:
    """Tests for gap analysis."""

    @pytest.mark.asyncio
    async def test_find_gaps(self, data_engine, sample_csv):
        """Test gap analysis finds missing invoice 1006."""
        result = await data_engine.gap_analysis(sample_csv, "invoice_number")

        assert result["gaps_found"] > 0
        assert result["total_missing_numbers"] > 0
        # Invoice 1006 is missing
        assert any(1006 in g["missing_values"] for g in result["gaps"])


class TestAgingAnalysis:
    """Tests for aging analysis."""

    @pytest.mark.asyncio
    async def test_aging_buckets(self, data_engine, sample_csv):
        """Test aging analysis produces correct buckets."""
        result = await data_engine.aging_analysis(
            sample_csv,
            date_column="date",
            amount_column="amount",
            reference_date="2025-03-10",
        )

        assert "aging_summary" in result
        assert len(result["aging_summary"]) == 5
        assert result["total_amount"] > 0


class TestStratifiedSampling:
    """Tests for stratified sampling."""

    @pytest.mark.asyncio
    async def test_sample_size(self, data_engine, sample_csv):
        """Test sampling returns reasonable sample."""
        result = await data_engine.stratified_sample(
            sample_csv, amount_column="amount", target_sample_size=5
        )

        assert result["population_size"] == 9
        assert result["sample_size"] > 0
        assert "strata" in result


class TestJournalEntryTesting:
    """Tests for journal entry testing."""

    @pytest.mark.asyncio
    async def test_round_amounts(self, data_engine, journal_entry_csv):
        """Test detection of round-dollar amounts."""
        result = await data_engine.journal_entry_testing(
            journal_entry_csv,
            amount_column="amount",
            date_column="date",
            user_column="user",
            description_column="description",
        )

        assert result["total_entries_tested"] > 0
        # Should flag round amounts (10000, 50000, 100000)
        round_flag = next((f for f in result["flags"] if f["test"] == "Round Dollar Amounts"), None)
        assert round_flag is not None
        assert round_flag["count"] > 0

    @pytest.mark.asyncio
    async def test_vague_descriptions(self, data_engine, journal_entry_csv):
        """Test detection of vague descriptions."""
        result = await data_engine.journal_entry_testing(
            journal_entry_csv,
            amount_column="amount",
            date_column="date",
            description_column="description",
        )

        # Should flag "Miscellaneous adjustment", "Various corrections"
        vague_flag = next((f for f in result["flags"] if f["test"] == "Vague Descriptions"), None)
        assert vague_flag is not None


class TestThreeWayMatch:
    """Tests for three-way matching."""

    @pytest.mark.asyncio
    async def test_match_mismatches(self, data_engine, three_way_csv):
        """Test three-way match finds mismatches."""
        result = await data_engine.three_way_match(three_way_csv)

        assert result["total_records"] > 0
        # PO001 has amount mismatch (5000 vs 5500)
        # PO003 has missing receipt
        assert result["mismatched_pos"] > 0


# ---------------------------------------------------------------------------
# Helper Function Tests
# ---------------------------------------------------------------------------

class TestHelpers:
    """Tests for helper functions."""

    def test_sample_size_computation(self):
        """Test sample size formula."""
        n = _compute_sample_size(500, 0.95, 0.05, 0.01)
        assert n >= 25  # Minimum sample
        assert n <= 500  # Cannot exceed population

    def test_risk_to_numeric(self):
        """Test risk level conversion."""
        assert _risk_to_numeric("high") == 1.0
        assert _risk_to_numeric("medium") == 0.6
        assert _risk_to_numeric("low") == 0.3
        assert _risk_to_numeric("unknown") == 0.6  # Default

    def test_severity_assessment_critical(self):
        """Test critical severity keywords."""
        result = _assess_severity("Evidence of fraud detected", "Material misstatement")
        assert result["level"] == "Critical"

    def test_severity_assessment_low(self):
        """Test low severity for generic text."""
        result = _assess_severity("Minor formatting issue", None)
        assert result["level"] == "Low"


# ---------------------------------------------------------------------------
# Pydantic Model Tests
# ---------------------------------------------------------------------------

class TestPydanticModels:
    """Tests for audit-related Pydantic models."""

    def test_audit_risk_request_valid(self):
        from backend.models import AuditRiskRequest
        req = AuditRiskRequest(
            total_revenue=50_000_000,
            inherent_risk="high",
            control_risk="medium",
        )
        assert req.inherent_risk == "high"
        assert req.control_risk == "medium"

    def test_audit_risk_request_invalid_level(self):
        from backend.models import AuditRiskRequest
        with pytest.raises(Exception):
            AuditRiskRequest(inherent_risk="extreme", control_risk="medium")

    def test_audit_data_request_valid(self):
        from backend.models import AuditDataRequest
        req = AuditDataRequest(
            csv_data="id,amount\n1,100\n2,200",
            analysis_type="benford",
        )
        assert req.analysis_type == "benford"

    def test_audit_data_request_invalid_type(self):
        from backend.models import AuditDataRequest
        with pytest.raises(Exception):
            AuditDataRequest(csv_data="id,amount\n1,100", analysis_type="invalid_type")

    def test_audit_program_request_valid(self):
        from backend.models import AuditProgramRequest
        req = AuditProgramRequest(audit_area="revenue recognition")
        assert req.risk_level == "medium"
        assert req.is_sox is False
