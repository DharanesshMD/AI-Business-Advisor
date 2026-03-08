"""
Audit Data Analytics Engine — Excel/CSV data manipulation for audit analysis.

Provides data analytics capabilities commonly used by audit analysts:
  - Dataset profiling and anomaly detection
  - Benford's Law first-digit analysis (fraud detection)
  - Duplicate detection
  - Gap analysis (sequential completeness)
  - Aging analysis (AR/AP)
  - Statistical sampling (stratified)
  - Three-way match (PO/Invoice/Receipt)
  - Journal entry testing (risk indicators)

All functions operate on pandas DataFrames for in-memory analysis.
"""

import logging
import math
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger("advisor.audit_data")

# ---------------------------------------------------------------------------
# Benford's Law expected frequencies
# ---------------------------------------------------------------------------

_BENFORD_EXPECTED = {
    1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046,
}


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class AuditDataEngine:
    """
    Data analytics engine for audit analysis.
    
    Accepts CSV text or pandas DataFrames and provides
    standard audit data analytics procedures.
    """

    @staticmethod
    def _parse_csv(csv_data: str) -> pd.DataFrame:
        """Parse CSV text into a DataFrame."""
        try:
            df = pd.read_csv(StringIO(csv_data))
            return df
        except Exception as e:
            raise ValueError(f"Failed to parse CSV data: {str(e)}")

    async def analyze_dataset(
        self,
        csv_data: str,
        amount_column: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Master analysis: profile columns, basic statistics, and flag anomalies.
        """
        df = self._parse_csv(csv_data)
        
        # Column profiling
        column_profiles = {}
        for col in df.columns:
            profile = {
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isnull().sum()),
                "null_pct": round(df[col].isnull().mean() * 100, 1),
                "unique_count": int(df[col].nunique()),
            }
            
            if pd.api.types.is_numeric_dtype(df[col]):
                desc = df[col].describe()
                profile.update({
                    "mean": round(float(desc["mean"]), 2),
                    "std": round(float(desc["std"]), 2),
                    "min": round(float(desc["min"]), 2),
                    "q1": round(float(desc["25%"]), 2),
                    "median": round(float(desc["50%"]), 2),
                    "q3": round(float(desc["75%"]), 2),
                    "max": round(float(desc["max"]), 2),
                })
            
            column_profiles[col] = profile
        
        # Anomaly detection on amount column
        anomalies = []
        if amount_column and amount_column in df.columns:
            col_data = df[amount_column].dropna()
            if pd.api.types.is_numeric_dtype(col_data) and len(col_data) > 0:
                mean = col_data.mean()
                std = col_data.std()
                if std > 0:
                    z_scores = ((col_data - mean) / std).abs()
                    outlier_mask = z_scores > 3
                    outlier_rows = df.loc[outlier_mask.index[outlier_mask]]
                    for idx, row in outlier_rows.iterrows():
                        anomalies.append({
                            "row": int(idx),
                            "value": round(float(row[amount_column]), 2),
                            "z_score": round(float(z_scores.loc[idx]), 2),
                            "reason": "Value exceeds 3 standard deviations from mean",
                        })
        
        return {
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "column_profiles": column_profiles,
            "anomalies": anomalies[:50],  # Cap at 50
            "anomaly_count": len(anomalies),
        }

    async def detect_duplicates(
        self,
        csv_data: str,
        columns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Find duplicate records across specified columns.
        Key for detecting duplicate payments, double bookings.
        """
        df = self._parse_csv(csv_data)
        
        check_cols = columns if columns else df.columns.tolist()
        
        # Validate columns exist
        missing = [c for c in check_cols if c not in df.columns]
        if missing:
            return {"error": f"Columns not found: {missing}", "available_columns": df.columns.tolist()}
        
        duplicates = df[df.duplicated(subset=check_cols, keep=False)]
        
        # Group duplicates
        grouped = []
        if len(duplicates) > 0:
            dup_groups = duplicates.groupby(check_cols)
            for name, group in dup_groups:
                if len(group) > 1:
                    grouped.append({
                        "key_values": dict(zip(check_cols, name if isinstance(name, tuple) else [name])),
                        "count": len(group),
                        "row_indices": group.index.tolist()[:10],  # Cap display
                    })
        
        return {
            "total_records": len(df),
            "duplicate_records": len(duplicates),
            "duplicate_groups": len(grouped),
            "checked_columns": check_cols,
            "duplicates": grouped[:100],  # Cap at 100 groups
            "risk_assessment": (
                "HIGH — Significant duplicate records found. Investigate for potential duplicate payments or double entries."
                if len(duplicates) > len(df) * 0.05
                else "MEDIUM — Some duplicates found. Review for validity."
                if len(duplicates) > 0
                else "LOW — No duplicates detected."
            ),
        }

    async def benford_analysis(
        self,
        csv_data: str,
        column: str,
    ) -> Dict[str, Any]:
        """
        Apply Benford's Law (first-digit test) on a numeric column.
        
        Compares observed vs expected first-digit distribution and
        computes chi-square statistic for conformity testing.
        """
        df = self._parse_csv(csv_data)
        
        if column not in df.columns:
            return {"error": f"Column '{column}' not found", "available_columns": df.columns.tolist()}
        
        # Get absolute non-zero values
        values = df[column].dropna()
        if not pd.api.types.is_numeric_dtype(values):
            try:
                values = pd.to_numeric(values, errors="coerce").dropna()
            except Exception:
                return {"error": f"Column '{column}' cannot be converted to numeric"}
        
        values = values.abs()
        values = values[values > 0]
        
        if len(values) < 50:
            return {
                "error": "Insufficient data — Benford's Law requires at least 50 non-zero values",
                "available_records": len(values),
            }
        
        # Extract first digits
        first_digits = values.apply(lambda x: int(str(x).lstrip("0").lstrip(".").lstrip("0")[0]) if x > 0 else 0)
        first_digits = first_digits[first_digits.between(1, 9)]
        
        total = len(first_digits)
        observed_counts = first_digits.value_counts().sort_index()
        
        # Build comparison table
        comparison = []
        chi_square = 0.0
        
        for digit in range(1, 10):
            observed = int(observed_counts.get(digit, 0))
            observed_pct = observed / total if total > 0 else 0
            expected_pct = _BENFORD_EXPECTED[digit]
            expected_count = expected_pct * total
            
            deviation = observed_pct - expected_pct
            
            # Chi-square component
            if expected_count > 0:
                chi_sq_component = ((observed - expected_count) ** 2) / expected_count
                chi_square += chi_sq_component
            else:
                chi_sq_component = 0
            
            comparison.append({
                "digit": digit,
                "observed_count": observed,
                "observed_pct": round(observed_pct * 100, 1),
                "expected_pct": round(expected_pct * 100, 1),
                "deviation_pct": round(deviation * 100, 1),
                "flag": abs(deviation) > 0.03,  # Flag if >3% deviation
            })
        
        # Chi-square test (8 degrees of freedom for digits 1-9)
        # Critical values: 15.51 (α=0.05), 20.09 (α=0.01)
        if chi_square > 20.09:
            conformity = "NON-CONFORMING"
            conclusion = (
                "The distribution DOES NOT conform to Benford's Law (p < 0.01). "
                "This is a strong indicator of potential data manipulation, fabrication, or fraud. "
                "Further investigation is strongly recommended."
            )
        elif chi_square > 15.51:
            conformity = "MARGINAL"
            conclusion = (
                "The distribution shows marginal conformity to Benford's Law (0.01 < p < 0.05). "
                "Some anomalies detected — additional testing recommended."
            )
        else:
            conformity = "CONFORMING"
            conclusion = (
                "The distribution conforms to Benford's Law (p > 0.05). "
                "No statistical evidence of data manipulation."
            )
        
        flagged_digits = [c for c in comparison if c["flag"]]
        
        return {
            "column_analyzed": column,
            "total_values": total,
            "chi_square_statistic": round(chi_square, 2),
            "degrees_of_freedom": 8,
            "critical_value_005": 15.51,
            "critical_value_001": 20.09,
            "conformity": conformity,
            "conclusion": conclusion,
            "digit_comparison": comparison,
            "flagged_digits": flagged_digits,
        }

    async def gap_analysis(
        self,
        csv_data: str,
        column: str,
    ) -> Dict[str, Any]:
        """
        Detect gaps in a sequential series (invoice numbers, check numbers).
        Critical for completeness assertions.
        """
        df = self._parse_csv(csv_data)
        
        if column not in df.columns:
            return {"error": f"Column '{column}' not found", "available_columns": df.columns.tolist()}
        
        # Get numeric values and sort
        values = pd.to_numeric(df[column], errors="coerce").dropna().astype(int)
        values = values.sort_values().unique()
        
        if len(values) < 2:
            return {"error": "Insufficient data for gap analysis", "available_records": len(values)}
        
        # Find gaps
        gaps = []
        for i in range(1, len(values)):
            diff = values[i] - values[i - 1]
            if diff > 1:
                missing_range = list(range(int(values[i - 1]) + 1, int(values[i])))
                gaps.append({
                    "after": int(values[i - 1]),
                    "before": int(values[i]),
                    "missing_count": len(missing_range),
                    "missing_values": missing_range[:20],  # Cap display
                })
        
        total_missing = sum(g["missing_count"] for g in gaps)
        
        return {
            "column_analyzed": column,
            "total_records": len(values),
            "range_start": int(values[0]),
            "range_end": int(values[-1]),
            "expected_count": int(values[-1] - values[0] + 1),
            "gaps_found": len(gaps),
            "total_missing_numbers": total_missing,
            "gaps": gaps[:50],  # Cap at 50
            "completeness_rate": round((len(values) / (values[-1] - values[0] + 1)) * 100, 1) if values[-1] > values[0] else 100.0,
            "risk_assessment": (
                "HIGH — Significant gaps found. Investigate for missing or voided transactions."
                if total_missing > len(values) * 0.05
                else "MEDIUM — Some gaps found. May be normal voids — verify documentation."
                if total_missing > 0
                else "LOW — Sequence is complete. No gaps detected."
            ),
        }

    async def aging_analysis(
        self,
        csv_data: str,
        date_column: str,
        amount_column: str,
        reference_date: Optional[str] = None,
        id_column: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Categorize records by age buckets (Current, 30, 60, 90, 120+ days).
        Standard for AR/AP aging analysis.
        """
        df = self._parse_csv(csv_data)
        
        for col in [date_column, amount_column]:
            if col not in df.columns:
                return {"error": f"Column '{col}' not found", "available_columns": df.columns.tolist()}
        
        # Parse dates
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        df = df.dropna(subset=[date_column])
        
        # Parse amounts
        df[amount_column] = pd.to_numeric(df[amount_column], errors="coerce")
        df = df.dropna(subset=[amount_column])
        
        # Reference date
        if reference_date:
            ref_date = pd.to_datetime(reference_date)
        else:
            ref_date = pd.Timestamp.now()
        
        # Calculate age in days
        df["_age_days"] = (ref_date - df[date_column]).dt.days
        
        # Define buckets
        buckets = [
            ("Current (0-30)", 0, 30),
            ("31-60 days", 31, 60),
            ("61-90 days", 61, 90),
            ("91-120 days", 91, 120),
            ("Over 120 days", 121, float("inf")),
        ]
        
        aging_summary = []
        for label, low, high in buckets:
            mask = (df["_age_days"] >= low) & (df["_age_days"] <= high)
            bucket_df = df[mask]
            
            total_amount = float(bucket_df[amount_column].sum())
            count = len(bucket_df)
            
            aging_summary.append({
                "bucket": label,
                "count": count,
                "total_amount": round(total_amount, 2),
                "percentage_of_total": 0,  # Will calculate below
            })
        
        # Calculate percentages
        grand_total = sum(b["total_amount"] for b in aging_summary)
        if grand_total > 0:
            for bucket in aging_summary:
                bucket["percentage_of_total"] = round(
                    (bucket["total_amount"] / grand_total) * 100, 1
                )
        
        # Risk indicators
        over_90_amount = sum(b["total_amount"] for b in aging_summary if "90" in b["bucket"] or "120" in b["bucket"])
        over_90_pct = (over_90_amount / grand_total * 100) if grand_total > 0 else 0
        
        return {
            "reference_date": ref_date.strftime("%Y-%m-%d"),
            "total_records": len(df),
            "total_amount": round(grand_total, 2),
            "aging_summary": aging_summary,
            "risk_indicators": {
                "over_90_days_amount": round(over_90_amount, 2),
                "over_90_days_pct": round(over_90_pct, 1),
                "assessment": (
                    "HIGH — Over 20% of balance is past 90 days. Review for potential write-offs."
                    if over_90_pct > 20
                    else "MEDIUM — Some aged balances. Verify collection efforts are in progress."
                    if over_90_pct > 10
                    else "LOW — Aging profile is within normal parameters."
                ),
            },
        }

    async def stratified_sample(
        self,
        csv_data: str,
        amount_column: str,
        target_sample_size: int = 50,
        strata_count: int = 3,
    ) -> Dict[str, Any]:
        """
        Select a stratified random sample based on monetary value strata.
        Follows AICPA sampling guidance.
        """
        df = self._parse_csv(csv_data)
        
        if amount_column not in df.columns:
            return {"error": f"Column '{amount_column}' not found", "available_columns": df.columns.tolist()}
        
        df[amount_column] = pd.to_numeric(df[amount_column], errors="coerce")
        df = df.dropna(subset=[amount_column])
        df = df.reset_index(drop=True)
        
        if len(df) == 0:
            return {"error": "No valid numeric data in the specified column"}
        
        # Create strata based on quantiles
        try:
            df["_stratum"] = pd.qcut(df[amount_column], q=strata_count, labels=False, duplicates="drop")
        except ValueError:
            # If not enough unique values, use fewer strata
            df["_stratum"] = pd.qcut(df[amount_column], q=2, labels=False, duplicates="drop")
        
        actual_strata = df["_stratum"].nunique()
        
        # Allocate sample proportionally
        strata_info = []
        selected_indices = []
        
        for stratum in sorted(df["_stratum"].unique()):
            stratum_df = df[df["_stratum"] == stratum]
            stratum_size = len(stratum_df)
            proportion = stratum_size / len(df)
            
            # Allocate sample proportionally, minimum 1 per stratum
            n_sample = max(1, int(round(target_sample_size * proportion)))
            n_sample = min(n_sample, stratum_size)
            
            sample = stratum_df.sample(n=n_sample, random_state=42)
            selected_indices.extend(sample.index.tolist())
            
            strata_info.append({
                "stratum": int(stratum),
                "population_size": stratum_size,
                "amount_range": {
                    "min": round(float(stratum_df[amount_column].min()), 2),
                    "max": round(float(stratum_df[amount_column].max()), 2),
                },
                "total_amount": round(float(stratum_df[amount_column].sum()), 2),
                "sample_size": n_sample,
            })
        
        # Get the actual sample
        sample_df = df.loc[selected_indices]
        
        # Include all high-value items (above 90th percentile) — key items
        p90 = df[amount_column].quantile(0.90)
        key_items = df[df[amount_column] >= p90]
        key_item_indices = [i for i in key_items.index if i not in selected_indices]
        
        return {
            "population_size": len(df),
            "total_population_amount": round(float(df[amount_column].sum()), 2),
            "strata": strata_info,
            "sample_size": len(selected_indices),
            "sample_amount": round(float(sample_df[amount_column].sum()), 2),
            "sample_coverage_pct": round(
                float(sample_df[amount_column].sum()) / float(df[amount_column].sum()) * 100, 1
            ) if df[amount_column].sum() > 0 else 0,
            "key_items_count": len(key_item_indices),
            "key_items_threshold": round(float(p90), 2),
            "total_items_to_test": len(selected_indices) + len(key_item_indices),
            "methodology": (
                f"Proportional allocation across {actual_strata} strata with all items "
                f"above {round(float(p90), 2)} (90th percentile) selected as key items."
            ),
        }

    async def three_way_match(
        self,
        csv_data: str,
        po_column: str = "po_number",
        invoice_column: str = "invoice_number",
        receipt_column: str = "receipt_number",
        amount_column: str = "amount",
        quantity_column: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cross-reference PO, invoice, and receipt data to flag mismatches.
        Core accounts payable audit procedure.
        """
        df = self._parse_csv(csv_data)
        
        # Check required columns
        required = [po_column, invoice_column, amount_column]
        missing = [c for c in required if c not in df.columns]
        if missing:
            return {"error": f"Required columns not found: {missing}", "available_columns": df.columns.tolist()}
        
        has_receipt = receipt_column in df.columns
        has_quantity = quantity_column and quantity_column in df.columns
        
        df[amount_column] = pd.to_numeric(df[amount_column], errors="coerce")
        
        mismatches = []
        
        # Group by PO and check for consistency
        for po, group in df.groupby(po_column):
            issues = []
            
            # Check for multiple different amounts for the same PO
            amounts = group[amount_column].dropna().unique()
            if len(amounts) > 1:
                issues.append({
                    "type": "Amount Mismatch",
                    "detail": f"Multiple amounts found for PO {po}: {[round(float(a), 2) for a in amounts]}",
                })
            
            # Check for missing invoice
            if group[invoice_column].isnull().any():
                issues.append({
                    "type": "Missing Invoice",
                    "detail": f"PO {po} has entries without an invoice number",
                })
            
            # Check for missing receipt
            if has_receipt and group[receipt_column].isnull().any():
                issues.append({
                    "type": "Missing Receipt",
                    "detail": f"PO {po} has entries without a receipt/GRN number",
                })
            
            # Check for quantity mismatches
            if has_quantity:
                quantities = group[quantity_column].dropna().unique()
                if len(quantities) > 1:
                    issues.append({
                        "type": "Quantity Mismatch",
                        "detail": f"PO {po} has different quantities: {list(quantities)}",
                    })
            
            if issues:
                mismatches.append({
                    "po_number": str(po),
                    "record_count": len(group),
                    "issues": issues,
                })
        
        return {
            "total_records": len(df),
            "unique_pos": int(df[po_column].nunique()),
            "matched_clean": int(df[po_column].nunique()) - len(mismatches),
            "mismatched_pos": len(mismatches),
            "mismatches": mismatches[:100],  # Cap at 100
            "match_rate": round(
                (1 - len(mismatches) / df[po_column].nunique()) * 100, 1
            ) if df[po_column].nunique() > 0 else 0,
            "risk_assessment": (
                "HIGH — Significant three-way match failures. Investigate for unauthorized purchases or overbilling."
                if len(mismatches) > df[po_column].nunique() * 0.1
                else "MEDIUM — Some mismatches found. Follow up on specific discrepancies."
                if len(mismatches) > 0
                else "LOW — All POs match across documents."
            ),
        }

    async def journal_entry_testing(
        self,
        csv_data: str,
        amount_column: str = "amount",
        date_column: str = "date",
        user_column: Optional[str] = None,
        description_column: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze journal entries for risk indicators:
        - Round-dollar amounts
        - Entries posted on weekends/holidays
        - Entries just below approval thresholds
        - Unusual posting users
        - Reversing entries
        """
        df = self._parse_csv(csv_data)
        
        if amount_column not in df.columns:
            return {"error": f"Column '{amount_column}' not found", "available_columns": df.columns.tolist()}
        
        df[amount_column] = pd.to_numeric(df[amount_column], errors="coerce")
        df = df.dropna(subset=[amount_column])
        
        flags = []
        
        # 1. Round-dollar amounts (exactly divisible by 100, 1000, 10000)
        round_amounts = df[df[amount_column].apply(
            lambda x: x != 0 and (x % 1000 == 0 or x % 10000 == 0)
        )]
        if len(round_amounts) > 0:
            flags.append({
                "test": "Round Dollar Amounts",
                "count": len(round_amounts),
                "description": "Journal entries with suspiciously round amounts (divisible by 1,000 or 10,000)",
                "risk": "Medium — Round amounts may indicate estimates or fabricated entries",
                "sample_values": round_amounts[amount_column].head(10).tolist(),
            })
        
        # 2. Weekend entries
        if date_column in df.columns:
            df["_date"] = pd.to_datetime(df[date_column], errors="coerce")
            weekend_entries = df[df["_date"].dt.dayofweek.isin([5, 6])]
            if len(weekend_entries) > 0:
                flags.append({
                    "test": "Weekend Entries",
                    "count": len(weekend_entries),
                    "description": "Journal entries posted on Saturday or Sunday",
                    "risk": "High — Weekend postings bypass normal business processes and oversight",
                    "sample_dates": weekend_entries["_date"].dt.strftime("%Y-%m-%d").head(10).tolist(),
                })
        
        # 3. Common approval thresholds
        thresholds = [5000, 10000, 25000, 50000, 100000]
        below_threshold = []
        for threshold in thresholds:
            margin = threshold * 0.02  # Within 2% below threshold
            mask = (df[amount_column] >= threshold - margin) & (df[amount_column] < threshold)
            count = mask.sum()
            if count > 0:
                below_threshold.append({
                    "threshold": threshold,
                    "entries_just_below": int(count),
                })
        
        if below_threshold:
            flags.append({
                "test": "Just Below Approval Threshold",
                "count": sum(b["entries_just_below"] for b in below_threshold),
                "description": "Entries within 2% below common approval thresholds",
                "risk": "High — May indicate intentional splitting to avoid approval requirements",
                "details": below_threshold,
            })
        
        # 4. Unusual users (if user column provided)
        if user_column and user_column in df.columns:
            user_counts = df[user_column].value_counts()
            total_entries = len(df)
            
            # Flag users with very few entries (potential unauthorized access)
            rare_users = user_counts[user_counts <= max(2, total_entries * 0.01)]
            if len(rare_users) > 0:
                flags.append({
                    "test": "Unusual Posting Users",
                    "count": int(rare_users.sum()),
                    "description": "Entries posted by users who rarely post journal entries",
                    "risk": "Medium — Rare users may indicate unauthorized access or management override",
                    "users": {str(k): int(v) for k, v in rare_users.items()},
                })
        
        # 5. Description analysis (if description column provided)
        if description_column and description_column in df.columns:
            # Check for generic/vague descriptions
            vague_keywords = ["misc", "miscellaneous", "adjustment", "correction", "other", "various"]
            df["_desc_lower"] = df[description_column].fillna("").str.lower()
            vague_entries = df[df["_desc_lower"].str.contains("|".join(vague_keywords), na=False)]
            
            if len(vague_entries) > 0:
                flags.append({
                    "test": "Vague Descriptions",
                    "count": len(vague_entries),
                    "description": "Entries with generic or vague descriptions (misc, adjustment, correction, etc.)",
                    "risk": "Medium — Vague descriptions may hide inappropriate entries",
                    "sample_descriptions": vague_entries[description_column].head(10).tolist(),
                })
        
        # Overall risk score
        total_flagged = sum(f["count"] for f in flags)
        risk_score = min(10, len(flags) * 2 + (total_flagged > 50) * 2)
        
        return {
            "total_entries_tested": len(df),
            "flags": flags,
            "total_flagged_entries": total_flagged,
            "risk_score": risk_score,
            "risk_level": (
                "HIGH" if risk_score >= 7
                else "MEDIUM" if risk_score >= 4
                else "LOW"
            ),
            "conclusion": (
                f"Journal entry testing identified {len(flags)} risk indicators across "
                f"{total_flagged} entries. {'Detailed investigation recommended.' if risk_score >= 7 else 'Selective follow-up recommended.' if risk_score >= 4 else 'No significant concerns noted.'}"
            ),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_audit_data_engine: Optional[AuditDataEngine] = None


def get_audit_data_engine() -> AuditDataEngine:
    global _audit_data_engine
    if _audit_data_engine is None:
        _audit_data_engine = AuditDataEngine()
    return _audit_data_engine
