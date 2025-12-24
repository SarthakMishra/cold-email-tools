#!/usr/bin/env python3
"""
LinkedIn automation pipeline for profile visits and connection requests.

Campaign flow:
1. Visit LinkedIn profile (to establish engagement)
2. Send connection request with personalized note

Reads leads from input/leads.csv with columns: linkedin_url, note
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import requests

from .config import (
    ACCOUNT_HANDLE,
    ACCOUNT_USERNAME,
    ACCOUNT_PASSWORD,
    ACCOUNT_PROXY,
    ACCOUNT_DAILY_CONNECTIONS,
    ACCOUNT_DAILY_MESSAGES,
    API_BASE_URL,
    API_KEY,
    INPUT_LEADS_CSV,
    OUTPUT_DIR,
    PROFILE_VISIT_DURATION_S,
    PROFILE_VISIT_SCROLL_DEPTH,
    RUN_POLL_INTERVAL_S,
    RUN_POLL_TIMEOUT_S,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class OpenOutreachClient:
    """Client for OpenOutreach API server."""

    def __init__(self, api_url: str, api_key: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
        }
        # Only include API key header if provided
        if api_key:
            self.headers["X-API-Key"] = api_key

    def create_run(
        self,
        handle: str,
        touchpoint_type: str,
        touchpoint_data: Dict,
        tags: Optional[Dict] = None,
        dry_run: bool = False,
    ) -> Dict:
        """
        Create a new run via API.

        Args:
            handle: Account handle to execute touchpoint
            touchpoint_type: Type of touchpoint (e.g., "profile_visit", "connect")
            touchpoint_data: Touchpoint-specific data (url, note, etc.)
            tags: Optional tags for filtering
            dry_run: If true, validate but don't execute

        Returns:
            Run response dict with run_id, status, etc.
        """
        endpoint = f"{self.api_url}/api/v1/runs"
        payload = {
            "handle": handle,
            "touchpoint": {
                "type": touchpoint_type,
                **touchpoint_data,
            },
            "dry_run": dry_run,
            "tags": tags or {},
        }

        try:
            resp = requests.post(
                endpoint, headers=self.headers, json=payload, timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as err:
            logger.error("API error creating run: %s", err)
            raise

    def get_run(self, run_id: str) -> Dict:
        """Get run status and results."""
        endpoint = f"{self.api_url}/api/v1/runs/{run_id}"

        try:
            resp = requests.get(endpoint, headers=self.headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as err:
            logger.error("API error getting run %s: %s", run_id, err)
            raise

    def poll_run_until_complete(
        self,
        run_id: str,
        poll_interval: float = RUN_POLL_INTERVAL_S,
        timeout: float = RUN_POLL_TIMEOUT_S,
    ) -> Dict:
        """
        Poll run status until it reaches a terminal state (completed/failed).

        Args:
            run_id: Run ID to poll
            poll_interval: Seconds between polls
            timeout: Maximum seconds to wait

        Returns:
            Final run status dict

        Raises:
            TimeoutError: If run doesn't complete within timeout
        """
        start_time = time.time()
        last_status = None

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")

            run_data = self.get_run(run_id)
            status = run_data.get("status")
            run_id_from_api = run_data.get("run_id")

            # Log status changes
            if status != last_status:
                logger.info(
                    "Run %s: %s → %s", run_id_from_api, last_status or "initial", status
                )
                last_status = status

            # Terminal states
            if status in ["completed", "failed"]:
                return run_data

            # Wait before next poll
            time.sleep(poll_interval)

    def get_account(self, handle: str) -> Optional[Dict]:
        """Get account by handle. Returns None if not found."""
        endpoint = f"{self.api_url}/api/v1/accounts/{handle}"

        try:
            resp = requests.get(endpoint, headers=self.headers, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as err:
            logger.error("API error getting account %s: %s", handle, err)
            raise

    def account_exists(self, handle: str) -> bool:
        """Check if account exists."""
        return self.get_account(handle) is not None

    def create_account(
        self,
        handle: str,
        username: str,
        password: str,
        active: bool = True,
        proxy: Optional[str] = None,
        daily_connections: int = 50,
        daily_messages: int = 20,
        booking_link: Optional[str] = None,
    ) -> Dict:
        """
        Create or update an account.

        Args:
            handle: Unique account handle/identifier
            username: LinkedIn username/email
            password: LinkedIn password
            active: Whether account is active
            proxy: Optional proxy configuration
            daily_connections: Daily connection limit
            daily_messages: Daily message limit
            booking_link: Optional booking link

        Returns:
            Account response dict
        """
        endpoint = f"{self.api_url}/api/v1/accounts"
        payload = {
            "handle": handle,
            "username": username,
            "password": password,
            "active": active,
            "proxy": proxy,
            "daily_connections": daily_connections,
            "daily_messages": daily_messages,
            "booking_link": booking_link,
        }

        try:
            resp = requests.post(
                endpoint, headers=self.headers, json=payload, timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as err:
            logger.error("API error creating account: %s", err)
            raise


class LinkedInAutomationPipeline:
    """End-to-end LinkedIn automation pipeline."""

    def __init__(self) -> None:
        if not ACCOUNT_HANDLE:
            raise ValueError("ACCOUNT_HANDLE environment variable is required")
        if not ACCOUNT_USERNAME:
            raise ValueError("ACCOUNT_USERNAME environment variable is required")
        if not ACCOUNT_PASSWORD:
            raise ValueError("ACCOUNT_PASSWORD environment variable is required")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.client = OpenOutreachClient(API_BASE_URL, API_KEY)
        self.account_handle = ACCOUNT_HANDLE
        self.account_username = ACCOUNT_USERNAME
        self.account_password = ACCOUNT_PASSWORD
        self.account_proxy = ACCOUNT_PROXY
        self.account_daily_connections = ACCOUNT_DAILY_CONNECTIONS
        self.account_daily_messages = ACCOUNT_DAILY_MESSAGES

    def _ensure_account_exists(self) -> None:
        """Check if account exists, create if it doesn't."""
        logger.info("Checking if account '%s' exists...", self.account_handle)

        if self.client.account_exists(self.account_handle):
            logger.info(
                "Account '%s' already exists, skipping creation", self.account_handle
            )
            return

        logger.info(
            "Account '%s' not found, creating new account...", self.account_handle
        )
        account = self.client.create_account(
            handle=self.account_handle,
            username=self.account_username,
            password=self.account_password,
            active=True,
            proxy=self.account_proxy,
            daily_connections=self.account_daily_connections,
            daily_messages=self.account_daily_messages,
        )
        logger.info(
            "Account '%s' created successfully (active=%s, daily_connections=%s, daily_messages=%s)",
            account["handle"],
            account["active"],
            account["daily_connections"],
            account["daily_messages"],
        )

    def run(self) -> None:
        """Execute the pipeline."""
        logger.info("=== Starting LinkedIn Automation Pipeline ===")
        logger.info("Account handle: %s", self.account_handle)
        logger.info("API URL: %s", API_BASE_URL)

        # Ensure account exists before processing leads
        self._ensure_account_exists()

        leads_df = self._load_leads()
        results_df = self._process_leads(leads_df)
        self._export_csv(results_df)
        logger.info("=== Pipeline complete. Processed %s leads ===", len(results_df))

    def _load_leads(self) -> pd.DataFrame:
        """Load the input leads CSV."""
        if not Path(INPUT_LEADS_CSV).exists():
            raise FileNotFoundError(
                f"Lead file not found at {INPUT_LEADS_CSV}. "
                "Create input/leads.csv with columns: linkedin_url, note"
            )

        df = pd.read_csv(INPUT_LEADS_CSV)
        required_cols = {"linkedin_url", "note"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(
                f"Missing required columns in leads CSV: {sorted(missing)}. "
                "Required: linkedin_url, note"
            )

        logger.info("Loaded leads CSV with %s rows.", len(df))
        return df

    def _process_leads(self, leads_df: pd.DataFrame) -> pd.DataFrame:
        """
        Process each lead: visit profile, then send connection request.

        Returns DataFrame with results for each lead.
        """
        results = []

        for idx, lead in leads_df.iterrows():
            linkedin_url = str(lead.get("linkedin_url", "")).strip()
            note = str(lead.get("note", "")).strip()

            if not linkedin_url:
                logger.warning("Skipping lead %s: missing linkedin_url", idx)
                results.append(
                    {
                        "linkedin_url": linkedin_url,
                        "note": note,
                        "profile_visit_status": "skipped",
                        "profile_visit_error": "Missing linkedin_url",
                        "connect_status": "skipped",
                        "connect_error": "Missing linkedin_url",
                        "success": False,
                    }
                )
                continue

            if not note:
                logger.warning("Skipping lead %s: missing note", idx)
                results.append(
                    {
                        "linkedin_url": linkedin_url,
                        "note": note,
                        "profile_visit_status": "skipped",
                        "profile_visit_error": "Missing note",
                        "connect_status": "skipped",
                        "connect_error": "Missing note",
                        "success": False,
                    }
                )
                continue

            logger.info(
                "Processing lead %s/%s: %s", idx + 1, len(leads_df), linkedin_url
            )

            # Step 1: Visit profile
            profile_visit_result = self._visit_profile(linkedin_url, idx)
            profile_visit_status = profile_visit_result.get("status")
            profile_visit_error = profile_visit_result.get("error")

            # Step 2: Send connection request (only if profile visit succeeded)
            if profile_visit_status == "completed":
                connect_result = self._send_connection_request(linkedin_url, note, idx)
                connect_status = connect_result.get("status")
                connect_error = connect_result.get("error")
            else:
                logger.warning(
                    "Skipping connection request for %s due to profile visit failure",
                    linkedin_url,
                )
                connect_status = "skipped"
                connect_error = "Profile visit failed"

            # Build result record
            result = {
                "linkedin_url": linkedin_url,
                "note": note,
                "profile_visit_status": profile_visit_status,
                "profile_visit_error": profile_visit_error or "",
                "profile_visit_run_id": profile_visit_result.get("run_id", ""),
                "connect_status": connect_status,
                "connect_error": connect_error or "",
                "connect_run_id": connect_result.get("run_id", "")
                if profile_visit_status == "completed"
                else "",
                "success": (
                    profile_visit_status == "completed"
                    and connect_status == "completed"
                ),
            }

            # Add any additional columns from the original lead
            for col in leads_df.columns:
                if col not in result:
                    result[col] = lead.get(col, "")

            results.append(result)

            # Rate limiting: small delay between leads
            if idx < len(leads_df) - 1:
                time.sleep(1.0)

        return pd.DataFrame(results)

    def _visit_profile(self, linkedin_url: str, lead_idx: int) -> Dict:
        """Visit a LinkedIn profile."""
        logger.info(
            "Lead %s: Creating profile visit run for %s", lead_idx, linkedin_url
        )

        try:
            run_response = self.client.create_run(
                handle=self.account_handle,
                touchpoint_type="profile_visit",
                touchpoint_data={
                    "url": linkedin_url,
                    "duration_s": PROFILE_VISIT_DURATION_S,
                    "scroll_depth": PROFILE_VISIT_SCROLL_DEPTH,
                },
                tags={"campaign": "linkedin_automation", "lead_idx": str(lead_idx)},
            )

            run_id = run_response.get("run_id")
            logger.info("Lead %s: Profile visit run created: %s", lead_idx, run_id)

            # Poll until complete
            final_run = self.client.poll_run_until_complete(run_id)

            status = final_run.get("status")
            if status == "completed":
                logger.info("Lead %s: Profile visit completed successfully", lead_idx)
            else:
                error = final_run.get("error", "Unknown error")
                logger.error("Lead %s: Profile visit failed: %s", lead_idx, error)

            return {
                "run_id": run_id,
                "status": status,
                "error": final_run.get("error"),
                "result": final_run.get("result"),
            }

        except Exception as e:
            logger.error("Lead %s: Profile visit error: %s", lead_idx, e, exc_info=True)
            return {
                "run_id": "",
                "status": "failed",
                "error": str(e),
                "result": None,
            }

    def _send_connection_request(
        self, linkedin_url: str, note: str, lead_idx: int
    ) -> Dict:
        """Send a connection request with personalized note."""
        logger.info(
            "Lead %s: Creating connection request run for %s", lead_idx, linkedin_url
        )

        try:
            run_response = self.client.create_run(
                handle=self.account_handle,
                touchpoint_type="connect",
                touchpoint_data={
                    "url": linkedin_url,
                    "note": note,
                },
                tags={"campaign": "linkedin_automation", "lead_idx": str(lead_idx)},
            )

            run_id = run_response.get("run_id")
            logger.info("Lead %s: Connection request run created: %s", lead_idx, run_id)

            # Poll until complete
            final_run = self.client.poll_run_until_complete(run_id)

            status = final_run.get("status")
            if status == "completed":
                logger.info(
                    "Lead %s: Connection request completed successfully", lead_idx
                )
            else:
                error = final_run.get("error", "Unknown error")
                logger.error("Lead %s: Connection request failed: %s", lead_idx, error)

            return {
                "run_id": run_id,
                "status": status,
                "error": final_run.get("error"),
                "result": final_run.get("result"),
            }

        except Exception as e:
            logger.error(
                "Lead %s: Connection request error: %s", lead_idx, e, exc_info=True
            )
            return {
                "run_id": "",
                "status": "failed",
                "error": str(e),
                "result": None,
            }

    def _export_csv(self, df: pd.DataFrame) -> Path:
        """Export results to UTF-8 CSV with timestamped filename."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = OUTPUT_DIR / f"campaign_results_{timestamp}.csv"

        # Prioritize key columns, then include any others
        priority_columns = [
            "linkedin_url",
            "note",
            "profile_visit_status",
            "profile_visit_error",
            "profile_visit_run_id",
            "connect_status",
            "connect_error",
            "connect_run_id",
            "success",
        ]

        # Get columns in priority order, then any remaining columns
        columns = [c for c in priority_columns if c in df.columns]
        remaining = [c for c in df.columns if c not in columns]
        columns.extend(remaining)

        df.to_csv(output_file, index=False, columns=columns, encoding="utf-8")
        logger.info("Exported %s results to %s", len(df), output_file)
        return output_file


def main() -> None:
    """Main entry point."""
    pipeline = LinkedInAutomationPipeline()
    pipeline.run()


if __name__ == "__main__":
    main()
