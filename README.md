# SEO Tools - LinkedIn Outreach Pipeline

Enrich LinkedIn leads via Bright Data and generate personalized cold emails with AI.

**Original post:** [Scaling highly personalized outbound with AI](https://sarthakmishra.com/blog/scaling-highly-personalized-outbound)

## Quick Start

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Configure environment:**
   ```bash
   cp env.example .env
   ```
   Edit `.env` and add:
   - `BRIGHTDATA_API_KEY`
   - `OPENAI_API_KEY`
   - `LLM_MODEL` (optional, defaults to `gpt-5.2`)

3. **Customize your product pitch:**
   - Edit `outreach_pipeline.py` line 333
   - Replace `"Product: [YOUR_PRODUCT_DESCRIPTION_HERE]\n\n"` with your actual product/service description

4. **Prepare leads CSV:**
   - Create `input_leads.csv` with columns: `email`, `first_name`, `last_name`, `profile_url`
   - Optionally add `company_url` for company enrichment

5. **Run:**
   ```bash
   uv run python outreach_pipeline.py
   ```

## Output

Results are saved to `output/` with timestamped filenames:
- `enriched_profiles_YYYYMMDD_HHMMSS.json` — raw Bright Data profile data
- `leads_YYYYMMDD_HHMMSS.csv` — enriched leads with personalized messages ready for import to outreach tools

## Stack

- Python 3.12+ with `uv`
- Bright Data Scrapers Library (LinkedIn profiles + companies)
- OpenAI Chat Completions API
