# Fallback Strategy Implementation

## Overview

Implemented a comprehensive fallback strategy for untagged resources in AWS accounts, specifically addressing CloudTrail trails and other resources that lack explicit ownership tags.

## Key Components

### 1. Account Tag Analyzer (`account_tag_analyzer.py`)
- **Purpose**: Analyzes tag distribution across an AWS account to determine fallback ownership information
- **Caching**: 24-hour TTL cache for account-level analysis (done once per account)
- **Analysis**: Determines most common technical owners, business owners, environments, and billing projects

### 2. Enhanced Tag Retriever V3 (`tag_retriever_v3.py`)
- **Purpose**: Retrieves tags with intelligent fallback strategy
- **Fallback Logic**: When resources have no tags, applies account-level defaults
- **Metadata**: Tracks whether tags came from inventory or fallback

### 3. Updated Compliance Processor V2
- **Integration**: Uses TagRetrieverV3 for enhanced tag retrieval
- **Enhanced Output**: Includes ownership information and fallback metadata

## Fallback Strategy

### Primary Fallbacks
1. **Technical Owner**: `erica-aws-tech-owner-research@groups.unsw.edu.au` (1,634 resources)
2. **Business Owner**: `luc@unsw.edu.au` (1,706 resources)
3. **Billing Project**: `PS69604` (1,698 resources)
4. **Environment**: `prod` (based on account analysis)

### Fallback Triggers
- **Resource not found in inventory**: Uses account-level defaults
- **Resource has no tags**: Uses account-level defaults
- **Resource exists but lacks ownership tags**: Uses account-level defaults

### Fallback Tags Applied
```json
{
  "unsw:technical-owner": "erica-aws-tech-owner-research@groups.unsw.edu.au",
  "unsw:business-owner": "luc@unsw.edu.au",
  "unsw:billing-project-id": "PS69604",
  "unsw:environment": "prod",
  "unsw:fallback-applied": "true",
  "unsw:fallback-reason": "no_tags_in_inventory",
  "unsw:fallback-source": "account-analysis"
}
```

## Implementation Details

### Account Analysis (Once per Account)
- **Total Resources**: 11,877
- **Tagged Resources**: 6,426 (54.1% coverage)
- **Environment Coverage**: 23.6%
- **Cache Location**: `cache/account-fallbacks/fallback_{account_id}.json`

### CloudTrail Example
**Before Fallback:**
```
ARN: arn:aws:cloudtrail:ap-southeast-2:116856931749:trail/AccountBaseline-CloudTrail-1S2U8XH7W7Z5P-UNSWCloudTrail-1VWM71NTL27P4
Tags: N/A (no tags)
```

**After Fallback:**
```
ARN: arn:aws:cloudtrail:ap-southeast-2:116856931749:trail/AccountBaseline-CloudTrail-1S2U8XH7W7Z5P-UNSWCloudTrail-1VWM71NTL27P4
Tags: 
  unsw:technical-owner: erica-aws-tech-owner-research@groups.unsw.edu.au
  unsw:business-owner: luc@unsw.edu.au
  unsw:billing-project-id: PS69604
  unsw:environment: prod
  unsw:fallback-applied: true
  unsw:fallback-reason: no_tags_in_inventory
  unsw:fallback-source: account-analysis
```

## Benefits

### 1. Complete Ownership Coverage
- **Before**: 76.4% of resources had no environment tags, many had no ownership tags
- **After**: 100% of resources have ownership information via fallback or direct tags

### 2. Consistent Compliance Reporting
- **Before**: CloudTrail resources showed "N/A" for tags
- **After**: All resources have actionable ownership information

### 3. Efficient Caching
- **Account Analysis**: Done once per account, cached for 24 hours
- **Fallback Application**: Applied in real-time during tag retrieval
- **Performance**: No additional API calls for fallback logic

### 4. Transparent Fallback
- **Metadata**: Clear indication when fallback is applied
- **Traceability**: Fallback reason and source tracked
- **Auditability**: Full visibility into ownership attribution

## Usage

### For CloudTrail Resources
CloudTrail trails like `AccountBaseline-CloudTrail-1S2U8XH7W7Z5P-UNSWCloudTrail-1VWM71NTL27P4` now receive:
- Technical Owner: `erica-aws-tech-owner-research@groups.unsw.edu.au`
- Business Owner: `luc@unsw.edu.au`
- Environment: `prod`
- Billing Project: `PS69604`

### For Other Untagged Resources
Any resource without tags receives the same account-level fallback ownership information, ensuring complete compliance coverage.

## Files Modified

1. **`script/modules/account_tag_analyzer.py`** - New account analysis module
2. **`script/modules/tag_retriever_v3.py`** - Enhanced tag retriever with fallback
3. **`script/modules/compliance_processor_v2.py`** - Updated to use V3 tag retriever
4. **`script/modules/main_v2.py`** - Enhanced Excel output with fallback metadata
5. **`script/modules/cache_manager.py`** - Added fallback cache path support

## Result

**CloudTrail resources with no tags now have complete ownership information instead of showing "N/A", providing actionable compliance data for all resources in the account.**
