#!/usr/bin/env python3
"""
Local pipeline to generate email pattern variations and validate them using SMTP.

Finds verified work emails that never made it into public databases by:
1. Generating email pattern variations from first name, last name, and domain
2. Validating emails using SMTP (via Reacher API)
3. Exporting validated emails for outreach

Original post: https://sarthakmishra.com/blog/how-to-find-and-validate-work-emails
"""

import logging
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from .config import (
    INCLUDE_RISKY,
    MAX_PATTERNS_PER_LEAD,
    OUTPUT_DIR,
    REACHER_API_KEY,
    REACHER_API_URL,
    VALIDATION_DELAY_SECONDS,
    INPUT_LEADS_CSV,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _timestamped_filename(prefix: str, suffix: str) -> str:
    """Return a timestamped filename to avoid overwriting outputs."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}.{suffix}"


def generate_name_variants(first: str, last: str) -> List[Tuple[str, str]]:
    """
    Generate name variants to handle hyphenated and accented names.

    Examples:
    - "Jean-Pierre" -> ("Jean-Pierre", "Jean", "JeanPierre")
    - "María José" -> ("María José", "Maria Jose")
    """
    variants = [
        (first, last),
        (first.replace("-", ""), last),  # Remove hyphen
        (first.split("-")[0], last),  # Use first part only
    ]

    # Handle accented characters: María -> Maria, José -> Jose
    if any(ord(c) > 127 for c in first + last):
        first_ascii = "".join(
            c
            for c in unicodedata.normalize("NFD", first)
            if unicodedata.category(c) != "Mn"
        )
        last_ascii = "".join(
            c
            for c in unicodedata.normalize("NFD", last)
            if unicodedata.category(c) != "Mn"
        )
        variants.append((first_ascii, last_ascii))

    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for variant in variants:
        if variant not in seen:
            seen.add(variant)
            unique_variants.append(variant)

    return unique_variants


def generate_email_patterns(first_name: str, last_name: str, domain: str) -> List[str]:
    """
    Generate email pattern variations based on common corporate email formats.

    Patterns ordered by prevalence (most common first):
    - firstname@domain (Very High)
    - firstname.lastname@domain (Very High)
    - firstlast@domain (High)
    - f.lastname@domain (Medium)
    - first_last@domain (Medium)
    - first-last@domain (Low)
    - firstname.lastinitial@domain (Low)
    - lastname.firstname@domain (Low)
    """
    first = first_name.lower().strip()
    last = last_name.lower().strip()

    if not first or not last or not domain:
        return []

    patterns = [
        f"{first}@{domain}",
        f"{first}.{last}@{domain}",
        f"{first}{last}@{domain}",
        f"{first[0]}.{last}@{domain}",
        f"{first[0]}{last}@{domain}",
        f"{first}_{last}@{domain}",
        f"{first}-{last}@{domain}",
        f"{first}.{last[0]}@{domain}",
        f"{last}.{first}@{domain}",
    ]

    # Remove duplicates while preserving order
    seen = set()
    unique_patterns = []
    for pattern in patterns:
        if pattern not in seen:
            seen.add(pattern)
            unique_patterns.append(pattern)

    return unique_patterns[:MAX_PATTERNS_PER_LEAD]


class ReacherClient:
    """Client for Reacher email validation API (self-hosted or managed)."""

    def __init__(self, api_url: str, api_key: Optional[str] = None) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def validate_email(self, email: str) -> Dict:
        """
        Validate a single email address using SMTP.

        Returns dict with nested structure:
        - is_reachable: "safe" | "risky" | "invalid"
        - smtp.is_deliverable: bool (SMTP validation success)
        - smtp.can_connect_smtp: bool
        - misc.is_disposable: bool
        - misc.is_role_account: bool
        - mx.records: List[str] (MX records)
        - syntax: Dict (syntax validation)
        """
        endpoint = f"{self.api_url}/v0/check_email"
        payload = {"to_email": email}

        try:
            resp = requests.post(
                endpoint, headers=self.headers, json=payload, timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as err:
            logger.error("Reacher API error for %s: %s", email, err)
            return {
                "is_reachable": "invalid",
                "is_reachable_smtp": False,
                "can_connect_smtp": False,
                "error": str(err),
            }

    def validate_batch(self, emails: List[str], delay: float = 1.5) -> List[Dict]:
        """
        Validate multiple emails with rate limiting.

        Args:
            emails: List of email addresses to validate
            delay: Seconds to wait between requests

        Returns:
            List of validation results (one per email)
        """
        results = []
        total = len(emails)

        for idx, email in enumerate(emails, 1):
            logger.info("Validating %s/%s: %s", idx, total, email)
            result = self.validate_email(email)
            result["email"] = email
            results.append(result)

            # Rate limiting: wait between requests (except for the last one)
            if idx < total:
                time.sleep(delay)

        return results


class EmailValidationPipeline:
    """End-to-end email pattern generation and validation pipeline."""

    def __init__(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.reacher_client = ReacherClient(REACHER_API_URL, REACHER_API_KEY)

    def run(self) -> None:
        """Execute the pipeline."""
        logger.info("=== Starting Email Validation Pipeline ===")
        leads_df = self._load_leads()
        validated_df = self._validate_leads(leads_df)
        self._export_csv(validated_df)
        logger.info("=== Pipeline complete. validated_leads=%s ===", len(validated_df))

    def _load_leads(self) -> pd.DataFrame:
        """Load the input leads CSV."""
        if not Path(INPUT_LEADS_CSV).exists():
            raise FileNotFoundError(
                f"Lead file not found at {INPUT_LEADS_CSV}. Set INPUT_LEADS_CSV or create the file."
            )
        df = pd.read_csv(INPUT_LEADS_CSV)
        required_cols = {"first_name", "last_name", "company_domain"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(
                f"Missing required columns in leads CSV: {sorted(missing)}. "
                "Required: first_name, last_name, company_domain"
            )
        logger.info("Loaded leads CSV with %s rows.", len(df))
        return df

    def _validate_leads(self, leads_df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate email patterns and validate them for each lead.

        Returns DataFrame with validated emails and their status.
        """
        validated_records = []

        for idx, lead in leads_df.iterrows():
            first_name = str(lead.get("first_name", "")).strip()
            last_name = str(lead.get("last_name", "")).strip()
            domain = str(lead.get("company_domain", "")).strip()

            if not first_name or not last_name or not domain:
                logger.warning(
                    "Skipping lead %s: missing first_name, last_name, or company_domain",
                    idx,
                )
                continue

            # Generate name variants (handles hyphenated/accented names)
            name_variants = generate_name_variants(first_name, last_name)

            # Generate email patterns for each name variant
            all_patterns = []
            for first_var, last_var in name_variants:
                patterns = generate_email_patterns(first_var, last_var, domain)
                all_patterns.extend(patterns)

            # Remove duplicates while preserving order
            seen = set()
            unique_patterns = []
            for pattern in all_patterns:
                if pattern not in seen:
                    seen.add(pattern)
                    unique_patterns.append(pattern)

            logger.info(
                "Lead %s: Generated %s email patterns for %s %s @ %s",
                idx,
                len(unique_patterns),
                first_name,
                last_name,
                domain,
            )

            # Validate patterns one at a time, stopping early when a validated email is found
            best_email = None
            best_status = None
            best_result = None
            patterns_tested = 0
            patterns_validated = 0

            for pattern_idx, pattern in enumerate(unique_patterns, 1):
                patterns_tested = pattern_idx
                logger.info(
                    "Validating %s/%s: %s", pattern_idx, len(unique_patterns), pattern
                )

                result = self.reacher_client.validate_email(pattern)
                result["email"] = pattern

                status = result.get("is_reachable", "invalid")
                # Parse nested structure: smtp.is_deliverable indicates SMTP validation success
                smtp_data = result.get("smtp", {})
                is_reachable_smtp = smtp_data.get("is_deliverable", False)

                # Track validated patterns
                if is_reachable_smtp:
                    patterns_validated += 1

                # Skip invalid emails
                if status == "invalid" or not is_reachable_smtp:
                    # Rate limiting: wait between requests (except for the last one)
                    if pattern_idx < len(unique_patterns):
                        time.sleep(VALIDATION_DELAY_SECONDS)
                    continue

                # Found a valid email
                if status == "safe":
                    # "safe" is the best status - stop immediately
                    best_email = pattern
                    best_status = status
                    best_result = result
                    logger.info(
                        "Lead %s: Found safe email %s, stopping validation",
                        idx,
                        pattern,
                    )
                    break
                elif status == "risky" and best_status != "safe":
                    # Store risky email but continue searching for a safe one
                    if INCLUDE_RISKY:
                        best_email = pattern
                        best_status = status
                        best_result = result
                        # Continue searching for a safe email, but we have a risky fallback

                # Rate limiting: wait between requests (except for the last one or if stopping)
                if pattern_idx < len(unique_patterns):
                    time.sleep(VALIDATION_DELAY_SECONDS)

            # Build record with all validation details
            record = {
                "first_name": first_name,
                "last_name": last_name,
                "company_domain": domain,
                "validated_email": best_email or "",
                "validation_status": best_status or "none_found",
                "is_reachable": best_result.get("is_reachable", "")
                if best_result
                else "",
                "is_reachable_smtp": (
                    best_result.get("smtp", {}).get("is_deliverable", False)
                    if best_result
                    else False
                ),
                "is_disposable": (
                    best_result.get("misc", {}).get("is_disposable", False)
                    if best_result
                    else False
                ),
                "is_role_account": (
                    best_result.get("misc", {}).get("is_role_account", False)
                    if best_result
                    else False
                ),
                "mx_records": (
                    ", ".join(best_result.get("mx", {}).get("records", []))
                    if best_result and best_result.get("mx", {}).get("records")
                    else ""
                ),
                "patterns_tested": patterns_tested,
                "patterns_validated": patterns_validated,
            }

            # Add any additional columns from the original lead
            for col in leads_df.columns:
                if col not in record:
                    record[col] = lead.get(col, "")

            validated_records.append(record)

            logger.info(
                "Lead %s: Found %s validated email (status=%s)",
                idx,
                best_email or "none",
                best_status or "none",
            )

        return pd.DataFrame(validated_records)

    def _export_csv(self, df: pd.DataFrame) -> Path:
        """Export validated emails to UTF-8 CSV with timestamped filename."""
        output_file = OUTPUT_DIR / _timestamped_filename("validated_emails", "csv")

        # Prioritize key columns, then include any others
        priority_columns = [
            "first_name",
            "last_name",
            "company_domain",
            "validated_email",
            "validation_status",
            "is_reachable",
            "is_reachable_smtp",
            "is_disposable",
            "is_role_account",
            "patterns_tested",
            "patterns_validated",
        ]

        # Get columns in priority order, then any remaining columns
        columns = [c for c in priority_columns if c in df.columns]
        remaining = [c for c in df.columns if c not in columns]
        columns.extend(remaining)

        df.to_csv(output_file, index=False, columns=columns, encoding="utf-8")
        logger.info("Exported %s validated leads to %s", len(df), output_file)
        return output_file


def main() -> None:
    pipeline = EmailValidationPipeline()
    pipeline.run()


if __name__ == "__main__":
    main()
