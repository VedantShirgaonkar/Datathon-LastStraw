# Neo4j Aura Setup Guide

## Step 1: Create Neo4j Aura Account (5 minutes)

1. **Go to Neo4j Aura**: Open https://console.neo4j.io/
2. **Sign Up**:
   - Click "Start Free"
   - Use your email or GitHub account
   - Verify your email

## Step 2: Create Free Instance

1. **Create New Instance**:
   - Click "New Instance" button
   - Select **"AuraDB Free"** (no credit card needed)
   
2. **Configure Instance**:
   - **Name**: `datathon-engineering-intelligence`
   - **Region**: Choose closest region (e.g., `us-east-1`, `eu-west-1`)
   - **Version**: Neo4j 5.x (latest)
   - Click "Create"

3. **Download Credentials** (CRITICAL):
   - A popup appears with credentials - **DO NOT CLOSE IT**
   - Download the `.txt` file with credentials
   - Contains:
     - Connection URI (like `neo4j+s://xxxxx.databases.neo4j.io`)
     - Username (usually `neo4j`)
     - Password (auto-generated)
   - **You CANNOT retrieve the password later!**

## Step 3: Verify Connection

1. **Wait for Instance to Start** (2-3 minutes)
   - Status will change from "Creating" to "Running"
   - Green dot indicates it's ready

2. **Open Neo4j Browser**:
   - Click "Open" next to your instance
   - Or click "Query" button
   - This opens the web-based Neo4j Browser

3. **Test Connection**:
   - Login with your credentials
   - Run this Cypher query:
   ```cypher
   RETURN "Hello Neo4j!" as message
   ```
   - Should see output

## Step 4: Get Connection Details

From the Neo4j Aura Console:

1. Click on your instance name
2. Navigate to "Connect" tab
3. Copy these details:

   ```
   Connection URI: neo4j+s://xxxxx.databases.neo4j.io
   Username: neo4j
   Password: [your password from download]
   ```

## Step 5: Add to Project Environment

Create a `.env` file in your project root:

```env
# Neo4j Aura Connection
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password_here
NEO4J_DATABASE=neo4j
```

**Security Note**: 
- `.env` is already in `.gitignore`
- NEVER commit credentials to git
- Share credentials securely with teammates (use password manager)

## Step 6: Free Tier Limits

Neo4j Aura Free provides:
- ✓ 200,000 nodes
- ✓ 400,000 relationships
- ✓ Unlimited queries
- ✓ 1 GB storage
- ✓ Suitable for hackathon/prototype

For your use case (engineering intelligence):
- ~1,000 developers
- ~100 projects
- ~10,000 commits/PRs
- ~50,000 relationships

**You'll have plenty of space!**

## Step 7: Test with Python

Once you've added credentials to `.env`, run:

```bash
python -m database.neo4j.connection_test
```

Should output:
```
✓ Neo4j connection successful!
✓ Database version: 5.x.x
✓ Ready to create schema
```

## Troubleshooting

### Connection Refused
- Check instance is "Running" (green) in console
- Verify URI has `neo4j+s://` prefix (secure connection)
- Check firewall/VPN isn't blocking port 7687

### Authentication Failed
- Double-check password from downloaded credentials
- Username is case-sensitive (usually lowercase `neo4j`)
- Password may contain special characters - copy exactly

### Certificate Error
- Ensure using `neo4j+s://` (not `neo4j://`)
- Aura uses TLS encryption by default

## Next Steps

After successful connection:
1. Run schema setup: `python -m database.neo4j.setup_schema`
2. Test with sample data: `python -m database.neo4j.seed_sample_data`
3. Verify in Neo4j Browser:
   ```cypher
   MATCH (n) RETURN count(n) as node_count
   ```

## Useful Neo4j Browser Queries

**See all node types**:
```cypher
CALL db.labels()
```

**See all relationship types**:
```cypher
CALL db.relationshipTypes()
```

**View sample of everything**:
```cypher
MATCH (n)-[r]->(m)
RETURN n, r, m
LIMIT 25
```

**Delete everything (reset)**:
```cypher
MATCH (n)
DETACH DELETE n
```

---

**Ready to code!** The setup is complete once you see the connection test pass.
