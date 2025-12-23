# Cold Outreach Pipelines

Three complementary pipelines for modern cold outreach:
1. **Email Enrichment Pipeline** - Find verified work emails that never made it into public databases
2. **Personalization Pipeline** - Enrich LinkedIn leads and generate personalized cold emails with AI
3. **LinkedIn Automation Pipeline** - Automated LinkedIn campaign pipeline that visits profiles and sends connection requests with personalized notes

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

## LinkedIn Automation Pipeline

Automated LinkedIn campaign pipeline that visits profiles and sends connection requests with personalized notes.

### Quick Start

1. **Prerequisites:**
   - [OpenOutreach API server](https://github.com/SarthakMishra/OpenOutreach) running

2. **Configure environment:**
   ```bash
   cp env.example .env
   ```
   Edit `.env` and add:
   - `OPENOUTREACH_API_URL` (default: `http://localhost:8000`)
   - `OPENOUTREACH_API_KEY`
   - `ACCOUNT_HANDLE` - Unique identifier for this account
   - `ACCOUNT_USERNAME` - LinkedIn email/username
   - `ACCOUNT_PASSWORD` - LinkedIn password
   - `ACCOUNT_PROXY` (optional) - Proxy URL
   - `ACCOUNT_DAILY_CONNECTIONS` (optional, default: `50`)
   - `ACCOUNT_DAILY_MESSAGES` (optional, default: `20`)

3. **Configure pipeline settings:**
   - Edit `linkedin_automation/config.py` to customize:
     - `PROFILE_VISIT_DURATION_S` (default: `5.0`)
     - `PROFILE_VISIT_SCROLL_DEPTH` (default: `3`)
     - `RUN_POLL_INTERVAL_S` (default: `2.0`)
     - `RUN_POLL_TIMEOUT_S` (default: `300.0`)

4. **Prepare leads CSV:**
   - Copy the sample file: `cp linkedin_automation/input/leads.sample.csv linkedin_automation/input/leads.csv`
   - Edit `linkedin_automation/input/leads.csv` with your leads
   - Required columns: `linkedin_url`, `note`
   - Example:
     ```csv
     linkedin_url,note
     https://www.linkedin.com/in/example1/,Hi! I noticed your work in [industry] and would love to connect.
     https://www.linkedin.com/in/example2/,Hello! I'd like to connect and learn more about your experience.
     ```

5. **Run:**
   ```bash
   uv run python -m linkedin_automation.pipeline
   ```

### Output

Results are saved to `linkedin_automation/output/campaign_results_YYYYMMDD_HHMMSS.csv` with:
- `linkedin_url` - Profile URL processed
- `note` - Connection note used
- `profile_visit_status` - Status: "completed", "failed", or "skipped"
- `profile_visit_error` - Error message if visit failed
- `profile_visit_run_id` - Run ID for profile visit
- `connect_status` - Status: "completed", "failed", or "skipped"
- `connect_error` - Error message if connection failed
- `connect_run_id` - Run ID for connection request
- `success` - True if both steps completed successfully

### How It Works

1. **Account Setup** - Checks if account exists in OpenOutreach, creates it if missing
2. **Load Leads** - Reads `input/leads.csv` and validates required columns
3. **Process Each Lead**:
   - Creates a `profile_visit` run via API
   - Polls until completion (or timeout)
   - If successful, creates a `connect` run with the note
   - Polls until completion (or timeout)
4. **Export Results** - Writes timestamped CSV with all results
