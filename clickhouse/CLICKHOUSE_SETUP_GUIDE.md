# ClickHouse Cloud Setup Guide

This guide walks you through setting up ClickHouse Cloud for time-series analytics and event storage.

---

## Why ClickHouse?

**ClickHouse** is a columnar database optimized for analytics queries on massive datasets:
- **100x faster** than PostgreSQL for analytical queries
- Perfect for storing **millions of events** (commits, PRs, Jira updates, metrics)
- **Real-time aggregations** for DORA metrics, dashboards
- **Cost-effective** with columnar compression

---

## Step 1: Create ClickHouse Cloud Account

1. **Go to** [clickhouse.cloud](https://clickhouse.cloud)
2. **Sign Up** with your email or GitHub account
3. **Verify email** and log in

---

## Step 2: Create Your First Service

1. **Click "Create Service"** from the dashboard
2. **Select Cloud Provider**: Choose **AWS**
3. **Select Region**: Choose **us-east-1** (or closest to your location)
4. **Select Tier**:
   - **Development (Free Trial)**: 30-day trial with $300 credits
   - **Basic**: $67/month (recommended for hackathon if trial ends)
5. **Service Name**: `engineering-intelligence`
6. **Click "Create Service"**

⏱️ Service will be ready in 2-3 minutes.

---

## Step 3: Get Connection Details

Once service is running:

1. **Click on your service** name
2. **Go to "Connect" tab**
3. **Copy connection details**:
   - **Host**: `xyz.aws.clickhouse.cloud` (your unique host)
   - **Port**: `8443` (HTTPS port)
   - **Username**: `default` (default admin user)
   - **Password**: Click "Reset Password" if needed

4. **Download credentials** file (optional, for backup)

---

## Step 4: Add Credentials to .env File

Open your `.env` file and add:

```bash
# ClickHouse Cloud
CLICKHOUSE_HOST=xyz.aws.clickhouse.cloud
CLICKHOUSE_PORT=8443
CLICKHOUSE_DATABASE=default
CLICKHOUSE_USERNAME=default
CLICKHOUSE_PASSWORD=your_password_here
```

Replace:
- `xyz.aws.clickhouse.cloud` with your actual host
- `your_password_here` with your actual password

---

## Step 5: Test Connection

Run the connection test:

```bash
# Activate your virtual environment first
.venv\Scripts\Activate.ps1

# Run test
python clickhouse/clickhouse_connection_test.py
```

**Expected Output:**
```
🔗 Testing ClickHouse Cloud Connection...
============================================================
✅ Connection successful!

📊 Database Information:
   Host:     xyz.aws.clickhouse.cloud
   Port:     8443
   Database: default
   Version:  24.1.2.5

✅ ClickHouse is ready to use!
```

---

## Step 6: Create Schema

Run the schema setup script to create tables and views:

```bash
python clickhouse/clickhouse_schema.py
```

This creates:
- **`events` table**: Raw events from GitHub, Jira, Notion, Prometheus
- **`dora_daily_metrics` materialized view**: Pre-computed DORA metrics

---

## What Gets Stored in ClickHouse?

### Events Table
All time-series events from all sources:

| Source | Event Types | Examples |
|--------|------------|----------|
| **GitHub** | commit, pr_opened, pr_merged, pr_reviewed, workflow_run | Commits, PR activity, CI/CD runs |
| **Jira** | issue_created, issue_updated, issue_completed, sprint_started | Issue lifecycle, sprint events |
| **Notion** | page_created, page_updated, database_item_created | Documentation updates |
| **Prometheus** | metric_sample | Build times, error rates, deployment success |

### DORA Metrics View
Pre-aggregated daily metrics per project:
- **Deployment frequency**: Count of successful deployments
- **Lead time**: Average hours from commit to production
- **Change failure rate**: Ratio of failed to successful deployments
- **MTTR**: Mean time to recovery from failures

---

## Querying Your Data

### Example Queries

#### Get commits in last 30 days
```sql
SELECT 
    actor_id,
    count() as total_commits
FROM events
WHERE event_type = 'commit'
  AND timestamp >= today() - 30
GROUP BY actor_id
ORDER BY total_commits DESC
LIMIT 10
```

#### Get DORA metrics for a project
```sql
SELECT 
    date,
    deployments,
    avg_lead_time_hours,
    prs_merged
FROM dora_daily_metrics
WHERE project_id = 'your-project-id'
  AND date >= today() - 30
ORDER BY date
```

#### Developer activity summary
```sql
SELECT 
    actor_id,
    countIf(event_type = 'commit') as commits,
    countIf(event_type = 'pr_merged') as prs,
    countIf(event_type = 'pr_reviewed') as reviews
FROM events
WHERE timestamp >= today() - 30
GROUP BY actor_id
```

---

## Cost Optimization Tips

### For Hackathon (24-48 hours):
1. **Use free trial credits** → $300 covers everything
2. **Don't create multiple services** → One service is enough
3. **Delete after hackathon** if you won't use it

### For Production:
1. **Use TTL (Time To Live)** to auto-delete old events:
   ```sql
   ALTER TABLE events MODIFY TTL timestamp + INTERVAL 90 DAY
   ```
2. **Partition by month** instead of day for high-volume data
3. **Use sampling** for exploratory queries:
   ```sql
   SELECT * FROM events SAMPLE 0.1 WHERE ...
   ```

---

## Troubleshooting

### Connection Issues

**Problem**: "Connection refused" or timeout errors

**Solutions**:
1. Check your **IP whitelist** in ClickHouse Cloud console:
   - Go to service → Settings → IP Access List
   - Add `0.0.0.0/0` for testing (allow all IPs)
   - Or add your specific IP address
2. Verify port **8443** (HTTPS) is used, not 9000 (native)
3. Ensure `secure=True` in Python client

### Authentication Errors

**Problem**: "Authentication failed"

**Solutions**:
1. **Reset password** in ClickHouse Cloud console
2. Ensure username is `default` (not your email)
3. Check `.env` file has correct credentials

### Query Performance Issues

**Problem**: Queries are slow

**Solutions**:
1. Add `LIMIT` to queries during testing
2. Use `toDate()` instead of `toDateTime()` for daily aggregations
3. Order queries by primary key columns (source, event_type, timestamp)

---

## ClickHouse vs PostgreSQL

| Feature | ClickHouse | PostgreSQL |
|---------|-----------|-----------|
| **Analytical Queries** | 100x faster | Baseline |
| **Insert Speed** | High (batch inserts) | Moderate |
| **Storage** | Columnar (10x compression) | Row-based |
| **Joins** | Limited (not OLTP) | Full support |
| **Best For** | Time-series, analytics, logs | Transactional data, CRUD |

**Use Both**: PostgreSQL for entities (users, projects), ClickHouse for events (commits, metrics)

---

## Next Steps

After ClickHouse is set up:

1. ✅ **Connect from Python** → Use `clickhouse_client.py`
2. ✅ **Insert sample events** → Test with fake data
3. ✅ **Query DORA metrics** → Verify materialized view works
4. ⏭️ **Set up event ingestion** → Connect webhooks (later)

---

## Useful Resources

- **ClickHouse Docs**: https://clickhouse.com/docs
- **SQL Reference**: https://clickhouse.com/docs/en/sql-reference
- **Python Client**: https://clickhouse.com/docs/en/integrations/python
- **Playground**: Try queries in Cloud Console → SQL Console

---

*Your ClickHouse instance is ready for time-series analytics!* 🚀
