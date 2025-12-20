#!/usr/bin/env python3
"""
Local, on-demand pipeline to enrich LinkedIn leads via Bright Data and
generate personalized cold emails with an LLM.

Original post: https://sarthakmishra.com/blog/scaling-highly-personalized-outbound
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Union

import pandas as pd
import requests
from openai import APIError, OpenAI, RateLimitError

from .config import (
    BRIGHTDATA_API_KEY,
    BRIGHTDATA_SNAPSHOT_URL,
    BRIGHTDATA_TRIGGER_URL,
    COMPANY_DATASET_ID,
    INPUT_LEADS_CSV,
    LLM_MODEL,
    LOCAL_PROFILES_PATH,
    OPENAI_API_KEY,
    OUTPUT_DIR,
    POLL_INTERVAL_SECONDS,
    POLL_TIMEOUT_SECONDS,
    PROFILE_DATASET_ID,
    USE_LOCAL_PROFILES,
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


class BrightDataClient:
    """Thin wrapper around Bright Data Scrapers Library trigger + snapshot APIs."""

    def __init__(self, api_key: str, dataset_id: str) -> None:
        if not api_key:
            raise ValueError(
                "BRIGHTDATA_API_KEY is required to scrape LinkedIn profiles."
            )
        if not dataset_id:
            raise ValueError("Bright Data dataset_id is required for scraping.")

        self.api_key = api_key
        self.dataset_id = dataset_id
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def submit(self, urls: Sequence[str]) -> Union[List[Dict], str]:
        """
        Submit LinkedIn profile URLs via the Scrapers Library trigger API.
        Returns either results (if synchronous) or a snapshot_id (if async).
        """
        params = {
            "dataset_id": self.dataset_id,
            "include_errors": "true",
            "format": "json",
        }
        payload = [{"url": url} for url in urls]

        resp = requests.post(
            BRIGHTDATA_TRIGGER_URL,
            headers=self.headers,
            params=params,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        # The API can respond synchronously with data (list) or with snapshot metadata (dict)
        if isinstance(data, list):
            logger.info(
                "Bright Data returned synchronous results. profiles=%s", len(data)
            )
            return data

        snapshot_id = data.get("snapshot_id") or data.get("id")
        if not snapshot_id:
            raise RuntimeError(f"Bright Data response missing snapshot_id: {data}")
        logger.info("Bright Data submission accepted. snapshot_id=%s", snapshot_id)
        return snapshot_id

    def poll_results(self, snapshot_id: str) -> List[Dict]:
        """Poll snapshots until results are ready or timeout."""
        start = time.time()
        # Web Scraper API: poll the snapshot download endpoint
        # Returns 202 while building, 200 when ready
        snapshot_url = f"{BRIGHTDATA_SNAPSHOT_URL}/{snapshot_id}"
        params = {"format": "json"}

        while True:
            resp = requests.get(
                snapshot_url,
                headers=self.headers,
                params=params,
                timeout=60,
            )

            # HTTP 202: snapshot still building
            if resp.status_code == 202:
                data = resp.json()
                status = data.get("status", "building")
                elapsed = time.time() - start
                if elapsed > POLL_TIMEOUT_SECONDS:
                    raise TimeoutError(
                        f"Bright Data polling timed out after {POLL_TIMEOUT_SECONDS}s; last status={status}"
                    )
                logger.info(
                    "Waiting for Bright Data results... status=%s elapsed=%.1fs",
                    status,
                    elapsed,
                )
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            # HTTP 200: snapshot ready, data returned
            resp.raise_for_status()
            results = resp.json() or []
            logger.info("Bright Data results ready. profiles=%s", len(results))
            return results


class OutreachPipeline:
    """End-to-end enrichment + personalization pipeline."""

    def __init__(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

    def run(self) -> None:
        """Execute the pipeline."""
        logger.info("=== Starting Outreach Pipeline ===")
        leads_df = self._load_leads()
        profiles = self._fetch_profiles(leads_df)
        companies = self._fetch_companies(leads_df)
        merged_df = self._merge_leads_with_profiles(leads_df, profiles, companies)
        personalized_df = self._personalize_messages(merged_df)
        self._export_csv(personalized_df)
        logger.info("=== Pipeline complete. leads=%s ===", len(personalized_df))

    def _load_leads(self) -> pd.DataFrame:
        """Load the input leads CSV."""
        if not Path(INPUT_LEADS_CSV).exists():
            raise FileNotFoundError(
                f"Lead file not found at {INPUT_LEADS_CSV}. Set INPUT_LEADS_CSV or create the file."
            )
        df = pd.read_csv(INPUT_LEADS_CSV)
        required_cols = {"email", "first_name", "last_name", "profile_url"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(
                f"Missing required columns in leads CSV: {sorted(missing)}"
            )
        logger.info("Loaded leads CSV with %s rows.", len(df))
        return df

    def _fetch_profiles(self, leads_df: pd.DataFrame) -> List[Dict]:
        """Fetch or load LinkedIn profile data."""
        if USE_LOCAL_PROFILES:
            if not LOCAL_PROFILES_PATH:
                raise ValueError(
                    "USE_LOCAL_PROFILES is true but LOCAL_PROFILES_PATH is empty."
                )
            path = Path(LOCAL_PROFILES_PATH)
            if not path.exists():
                raise FileNotFoundError(f"LOCAL_PROFILES_PATH not found: {path}")
            with path.open() as f:
                data = json.load(f)
            logger.info("Loaded %s profiles from %s", len(data), path)
            return data

        client = BrightDataClient(BRIGHTDATA_API_KEY, PROFILE_DATASET_ID)
        profile_urls = (
            leads_df["profile_url"].dropna().astype(str).str.strip().unique().tolist()
        )
        if not profile_urls:
            raise ValueError("No profile_url values found in the leads file.")

        submission = client.submit(profile_urls)
        if isinstance(submission, list):
            results = submission
        else:
            results = client.poll_results(submission)
        output_path = OUTPUT_DIR / _timestamped_filename("enriched_profiles", "json")
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("Saved raw Bright Data profile results to %s", output_path)
        return results

    def _fetch_companies(self, leads_df: pd.DataFrame) -> List[Dict]:
        """Fetch LinkedIn company data when company URLs are provided."""
        company_urls = (
            leads_df["company_url"].dropna().astype(str).str.strip().unique().tolist()
            if "company_url" in leads_df.columns
            else []
        )
        if not company_urls:
            return []

        client = BrightDataClient(BRIGHTDATA_API_KEY, COMPANY_DATASET_ID)
        submission = client.submit(company_urls)
        if isinstance(submission, list):
            results = submission
        else:
            results = client.poll_results(submission)
        output_path = OUTPUT_DIR / _timestamped_filename("enriched_companies", "json")
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("Saved raw Bright Data company results to %s", output_path)
        return results

    def _merge_leads_with_profiles(
        self, leads_df: pd.DataFrame, profiles: List[Dict], companies: List[Dict]
    ) -> pd.DataFrame:
        """Merge Bright Data profile and company data into the lead list."""
        profiles_by_url: Dict[str, Dict] = {}
        for p in profiles:
            if isinstance(p, dict):
                url = p.get("url") or p.get("profile_url") or p.get("input_url")
                if url:
                    profiles_by_url[url] = p

        companies_by_url: Dict[str, Dict] = {}
        for c in companies:
            if isinstance(c, dict):
                url = c.get("url") or c.get("input_url")
                if url:
                    companies_by_url[url] = c

        merged: List[Dict] = []
        for _, lead in leads_df.iterrows():
            profile_url = str(lead.get("profile_url", "")).strip()
            company_url = (
                str(lead.get("company_url", "")).strip()
                if "company_url" in leads_df.columns
                else ""
            )

            profile = profiles_by_url.get(profile_url, {})
            company_rec = companies_by_url.get(company_url, {})

            headline = profile.get("headline", "") or lead.get("title", "")
            company = ""
            if isinstance(headline, str) and " at " in headline:
                company = headline.split(" at ")[-1].strip()
            company = company or lead.get("company", "") or company_rec.get("name", "")

            merged.append(
                {
                    "email": lead.get("email", ""),
                    "first_name": lead.get("first_name", ""),
                    "last_name": lead.get("last_name", ""),
                    "company": company,
                    "title": headline,
                    "about": profile.get("summary", "")
                    or profile.get("about", "")
                    or lead.get("about", ""),
                    "location": profile.get("location", "") or profile.get("city", ""),
                    "education": profile.get("educations_details", ""),
                    "profile_url": profile_url,
                    "company_url": company_url,
                    "company_about": company_rec.get("about", ""),
                    "company_industry": company_rec.get("industries", ""),
                    "company_size": company_rec.get("company_size", ""),
                    "company_website": company_rec.get("website", ""),
                }
            )

        logger.info(
            "Merged leads with %s profiles and %s companies.",
            len(profiles_by_url),
            len(companies_by_url),
        )
        return pd.DataFrame(merged)

    def _personalize_messages(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate personalized messages for each lead."""
        if not self.openai_client:
            raise ValueError("OPENAI_API_KEY is required for personalization.")

        messages: List[str] = []
        for _, row in df.iterrows():
            msg = self._generate_personalized_message(row.to_dict())
            messages.append(msg)

        df = df.copy()
        df["personalized_message"] = messages
        df["custom_field_1"] = df["personalized_message"]
        return df

    def _generate_personalized_message(self, prospect: Dict) -> str:
        """Call the LLM to create a short personalized cold email."""
        about = prospect.get("about", "") or ""
        prompt = (
            "You are a sales outreach specialist. Craft a concise, highly personalized cold email "
            "that feels written just for this person. Limit to 140-160 words, avoid fluff, and make one clear CTA.\n\n"
            "Use the data below thoughtfully—reference only what is relevant and authentic. If a field is empty, just skip it.\n"
            f"- Name: {prospect.get('first_name', '')} {prospect.get('last_name', '')}\n"
            f"- Title: {prospect.get('title', '')}\n"
            f"- Location: {prospect.get('location', '')}\n"
            f"- Education: {prospect.get('education', '')}\n"
            f"- About/Bio: {about[:600]}\n"
            f"- Company: {prospect.get('company', '')}\n"
            f"- Company about: {prospect.get('company_about', '')}\n"
            f"- Company industry: {prospect.get('company_industry', '')}\n"
            f"- Company size: {prospect.get('company_size', '')}\n"
            f"- Company website: {prospect.get('company_website', '')}\n\n"
            "Product: [YOUR_PRODUCT_DESCRIPTION_HERE]\n\n"
            "Structure:\n"
            "1) One-line opener that shows you've actually read their background (title, location, education, or company mission—pick the best hook).\n"
            "2) One-sentence bridge linking their context to your product's specific value (be concrete: metrics, outcomes, or workflow saved).\n"
            "3) One short bullet or micro-example that proves the benefit (no jargon; relevant to media/tech audiences if applicable).\n"
            "4) Close with a single, low-friction CTA (e.g., 10-minute intro this week) and offer to share a tailored example.\n"
            "Keep tone warm, professional, and direct."
        )

        try:
            response = self.openai_client.chat.completions.create(
                model=LLM_MODEL,
                max_completion_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return (response.choices[0].message.content or "").strip()
        except RateLimitError as err:
            logger.error("OpenAI rate limit hit: %s", err, exc_info=True)
            raise
        except APIError as api_err:
            logger.error("OpenAI API error: %s", api_err, exc_info=True)
            raise
        except Exception as exc:  # pragma: no cover - protective catch for runtime use
            logger.error(
                "Failed to generate message for %s: %s", prospect, exc, exc_info=True
            )
            raise

    def _export_csv(self, df: pd.DataFrame) -> Path:
        """Export to UTF-8 CSV with timestamped filename."""
        output_file = OUTPUT_DIR / _timestamped_filename("leads", "csv")
        columns = [
            "email",
            "first_name",
            "last_name",
            "company",
            "title",
            "custom_field_1",
            "profile_url",
            "company_url",
            "company_about",
        ]
        df.to_csv(output_file, index=False, columns=columns, encoding="utf-8")
        logger.info("Exported %s leads to %s", len(df), output_file)
        return output_file


def main() -> None:
    pipeline = OutreachPipeline()
    pipeline.run()


if __name__ == "__main__":
    main()

