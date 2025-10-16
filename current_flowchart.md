# Current Lacework Alert Reporting Flow

```mermaid
flowchart TD
    A[Start] --> B[Parse Arguments & Load Credentials]
    B --> C[Initialize Components]
    C --> D[Get Compliance Alerts for Date Range]
    D --> E[Get Alert Details for Alert IDs]
    E --> F[Apply AWS Account Filtering]
    F --> G[Get AWS Accounts List]
    G --> H[Loop Through Each AWS Account]
    H --> I[Get Compliance Report for Account]
    I --> J[Parse Compliance Data]
    J --> K[Extract All Policy IDs]
    K --> L[Get Policy Details for All Policies]
    L --> M[Extract All Resource ARNs]
    M --> N[Get Resource Tags from Inventory]
    N --> O[Apply Fallback Tag Strategies]
    O --> P[Enrich Alerts with Policy Details]
    P --> Q[Enrich Compliance with Policy Details]
    Q --> R[Apply Tags to All Items]
    R --> S[Generate Excel Output]
    S --> T[End]

    style A fill:#e1f5fe
    style T fill:#c8e6c9
    style H fill:#fff3e0
    style I fill:#fff3e0
    style J fill:#fff3e0
```

## Current Flow Issues for Large FortiCNP Environment:

1. **Sequential Account Processing**: Each AWS account processed one-by-one
2. **Duplicate API Calls**: Same policy/resource data fetched multiple times across accounts
3. **Memory Inefficient**: All data loaded into memory before processing
4. **No Parallelization**: No concurrent processing of accounts
5. **Tag Retrieval Bottleneck**: Tags fetched for all resources at once, causing memory/API limits
