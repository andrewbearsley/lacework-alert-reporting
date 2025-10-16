# Tag Retrieval Optimization Plan

## Current Approach
For each AWS account:
  - For each resource type:
    - Query Lacework inventory (filtered by account + type)
    - Extract tags

**Problem**: If we have 150 accounts × 15 resource types = 2,250 API calls

## Optimized Approach

### Phase 1: Query by resource type (across ALL accounts)
For each resource type:
  - Query Lacework inventory for that type (no account filter)
  - Check response: `paging.totalRows` vs `len(data)`
  - If `len(data) < totalRows`: TRUNCATED - need per-account queries
  - If `len(data) == totalRows`: SUCCESS - we got everything

### Phase 2: Query by account for types that were truncated
For each resource type that was truncated:
  - For each account that needs this type:
    - Query Lacework inventory (filtered by account + type)

## Example Scenario

**Phase 1 Results**:
- `ec2:instance`: 850/850 resources ✅ (complete)
- `ec2:vpc`: 320/320 resources ✅ (complete)
- `lambda:function`: 2,400/2,400 resources ✅ (complete)
- `s3:bucket`: 5,000/8,542 resources ⚠️ (TRUNCATED, need per-account)
- `iam:role`: 5,000/12,389 resources ⚠️ (TRUNCATED, need per-account)

**Phase 2**: Only query s3:bucket and iam:role per-account

**Result**: Instead of 2,250 API calls, we make ~17 calls (15 types + 2 types × ~75 accounts) = ~167 calls

## Implementation Status

✅ **DONE**: Response now captures and reports `totalRows` from `paging` object
- Shows: `Found 5000 resources of type s3:bucket (totalRows: 8542, TRUNCATED)`

🔄 **TODO**: Implement two-phase query strategy
1. First pass: query all types without account filter
2. Track which types are truncated
3. Second pass: only query truncated types per-account

## API Response Structure
```json
{
  "data": [ /* resources */ ],
  "paging": {
    "rows": 5000,
    "totalRows": 8542,
    "urls": {
      "nextPage": "..."
    }
  }
}
```

