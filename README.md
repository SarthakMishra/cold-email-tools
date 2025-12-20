# SEO Tools - Cold Outreach Pipelines

Two complementary pipelines for modern cold outreach:
1. **Email Enrichment Pipeline** - Find verified work emails that never made it into public databases
2. **Personalization Pipeline** - Enrich LinkedIn leads and generate personalized cold emails with AI

## Email Enrichment Pipeline

Generate email pattern variations and validate them using SMTP to find verified work emails.

**Original post:** [How to find verified work emails for cold outreach](https://sarthakmishra.com/blog/how-to-find-and-validate-work-emails)

### Quick Start

1. **Set up Reacher (email validation):**
   - **Option A (Self-hosted):** Deploy Reacher on a VPS with port 25 open:
     ```bash
     docker run -d -p 8081:8080 reacherhq/backend:latest
     ```
   - **Option B (Managed):** Use Reacher's hosted API at `https://api.reacher.email`

2. **Configure environment:**
   ```bash
   cp env.example .env
   ```
   Edit `.env` and add:
   - `REACHER_API_KEY` (only needed for managed Reacher)

3. **Configure pipeline settings:**
   - Edit `email_enrichment/config.py` to customize:
     - `REACHER_API_URL` (default: `http://localhost:8080`)
     - `VALIDATION_DELAY_SECONDS` (default: `1.5`)
     - `MAX_PATTERNS_PER_LEAD` (default: `20`)
     - `INCLUDE_RISKY` (default: `false`)

4. **Prepare leads CSV:**
   - Copy the sample file: `cp email_enrichment/input/leads.sample.csv email_enrichment/input/leads.csv`
   - Edit `email_enrichment/input/leads.csv` with your leads
   - Required columns: `first_name`, `last_name`, `company_domain`
   - Example:
     ```csv
     first_name,last_name,company_domain
     John,Doe,acme.com
     Jane,Smith,techcorp.io
     ```

5. **Run:**
   ```bash
   uv run python -m email_enrichment.pipeline
   ```

### Output

Results are saved to `email_enrichment/output/validated_emails_YYYYMMDD_HHMMSS.csv` with:
- `validated_email` - Best validated email found (prefers "safe" over "risky")
- `validation_status` - "safe", "risky", or "none_found"
- `is_reachable_smtp` - Whether mailbox exists
- `is_disposable` - Whether it's a disposable email
- `is_role_account` - Whether it's a role account (e.g., info@, support@)
- `patterns_tested` - Number of email patterns generated
- `patterns_validated` - Number of patterns that validated successfully

## Personalization Pipeline

Enrich LinkedIn leads via Bright Data and generate personalized cold emails with an LLM.

**Original post:** [Scaling highly personalized outbound with AI](https://sarthakmishra.com/blog/scaling-highly-personalized-outbound)

### Quick Start

1. **Configure environment:**
   ```bash
   cp env.example .env
   ```
   Edit `.env` and add:
   - `BRIGHTDATA_API_KEY`
   - `OPENAI_API_KEY`

2. **Configure pipeline settings:**
   - Edit `personalization/config.py` to customize:
     - `LLM_MODEL` (default: `gpt-5.2`)
     - `POLL_INTERVAL_SECONDS` (default: `5`)
     - `POLL_TIMEOUT_SECONDS` (default: `300`)

3. **Customize your product pitch:**
   - Edit `personalization/pipeline.py` line 335
   - Replace `"Product: [YOUR_PRODUCT_DESCRIPTION_HERE]\n\n"` with your actual product/service description

4. **Prepare leads CSV:**
   - Copy the sample file: `cp personalization/input/leads.sample.csv personalization/input/leads.csv`
   - Edit `personalization/input/leads.csv` with your leads
   - Required columns: `email`, `first_name`, `last_name`, `profile_url`
   - Optionally add `company_url` for company enrichment

5. **Run:**
   ```bash
   uv run python -m personalization.pipeline
   ```

### Output

Results are saved to `personalization/output/` with timestamped filenames:
- `enriched_profiles_YYYYMMDD_HHMMSS.json` — raw Bright Data profile data
- `leads_YYYYMMDD_HHMMSS.csv` — enriched leads with personalized messages ready for import to outreach tools
