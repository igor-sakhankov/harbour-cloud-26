# CSV Payment Import

Batch import coffee payments from a CSV file with automatic validation, retry logic, and idempotency guarantees.

## Quick Start

### 1. Prepare CSV file

```csv
storeId,coffeeType,price,currency,loyaltyCardId,idempotencyKey
store-london-01,LATTE,3.50,EUR,card-999,order-001
store-london-01,CAPPUCCINO,4.00,EUR,card-888,order-002
store-paris-02,ESPRESSO,2.50,EUR,card-777,order-003
```

### 2. Upload via Postman

- **Method**: POST
- **URL**: `http://localhost:8080/api/v1/payments/import`
- **Body**: form-data → `file` field (select CSV)
- **Send**

### 3. Check response

```json
{
  "totalRecords": 3,
  "successCount": 3,
  "failures": []
}
```

---

## CSV Format

### Required header row:
```
storeId,coffeeType,price,currency,loyaltyCardId,idempotencyKey
```

### Fields

| Field | Type | Constraints | Example |
|-------|------|-------------|---------|
| **storeId** | String | Non-empty | `store-london-01` |
| **coffeeType** | Enum | Must be valid coffee type | `LATTE` |
| **price** | Decimal | > 0, max 2 decimals | `3.50` |
| **currency** | String | 3-letter ISO code | `EUR` |
| **loyaltyCardId** | String | Any non-empty string | `card-999` |
| **idempotencyKey** | String | Uniquely identifies payment | `order-001` |

### Valid coffee types
```
ESPRESSO, DOUBLE_ESPRESSO, AMERICANO, LATTE, CAPPUCCINO,
FLAT_WHITE, MOCHA, CORTADO, MACCHIATO, COLD_BREW
```

---

## API Endpoint

### POST `/api/v1/payments/import`

**Content-Type**: `multipart/form-data`

**Parameter**: `file` (CSV file)

### Response (HTTP 200 OK)

**Success - all rows valid:**
```json
{
  "totalRecords": 3,
  "successCount": 3,
  "failures": []
}
```

**Partial success - some rows invalid:**
```json
{
  "totalRecords": 4,
  "successCount": 2,
  "failures": [
    {
      "rowNumber": 3,
      "record": null,
      "reason": "Invalid coffeeType: INVALID. Valid types: [ESPRESSO, DOUBLE_ESPRESSO, ...]"
    },
    {
      "rowNumber": 4,
      "record": null,
      "reason": "price must be greater than zero"
    }
  ]
}
```

### Response (HTTP 400 Bad Request)

**Empty file:**
```json
{
  "totalRecords": 0,
  "successCount": 0,
  "failures": [
    {
      "rowNumber": 0,
      "record": null,
      "reason": "File is empty"
    }
  ]
}
```

**Wrong file type:**
```json
{
  "totalRecords": 0,
  "successCount": 0,
  "failures": [
    {
      "rowNumber": 0,
      "record": null,
      "reason": "File must be a CSV file"
    }
  ]
}
```

---

## Validation Rules

Each row is validated independently:

| Rule | Error Message | Example |
|------|---------------|---------|
| storeId is empty | `Empty storeId` | `,LATTE,3.50,EUR,card-999,key-001` |
| coffeeType not in enum | `Invalid coffeeType: X. Valid types: [...]` | `store-01,UNKNOWN,3.50,EUR,card-999,key-001` |
| price ≤ 0 | `price must be greater than zero` | `store-01,LATTE,-1.00,EUR,card-999,key-001` |
| price not a number | `Invalid price format` | `store-01,LATTE,abc,EUR,card-999,key-001` |
| price has >2 decimals | `Invalid price format` | `store-01,LATTE,3.505,EUR,card-999,key-001` |
| currency not 3 letters | `currency must be a 3-letter ISO-4217 code` | `store-01,LATTE,3.50,E,card-999,key-001` |
| wrong field count | `Expected 6 fields but got N` | `store-01,LATTE,3.50` (missing 3 fields) |
| invalid header | `Invalid CSV header. Expected: storeId,coffeeType,...` | `wrong,header,row,here,foo,bar` |

---

## Integration with Existing Payment API

Each validated CSV row is sent to the existing `POST /api/v1/payments` endpoint with:

- **Store-Id header**: Set to the CSV row's `storeId`
- **Idempotency-Key header**: Set to the CSV row's `idempotencyKey`
- **Request body**: Standard `PaymentRequest` JSON

### Idempotency Guarantee

If you upload the same CSV twice (same storeId + idempotencyKey combinations):

1. **First upload** → Payments created (HTTP 201 internally) → Counted in success
2. **Second upload** → Payments replayed (HTTP 200 internally) → Still counted as success, **NO duplicates created**

This makes CSV import **safe to retry** without creating duplicate payments.

### Retry Logic

If sending a payment to the API fails:
- **Attempt 1**: Retry after 500ms
- **Attempt 2**: Retry after 1000ms (1s)
- **Attempt 3**: Retry after 2000ms (2s)
- **Final**: Record failure with detailed error reason

---

## Command-Line Testing (curl)

```bash
# Create test CSV
cat > /tmp/test.csv << 'EOF'
storeId,coffeeType,price,currency,loyaltyCardId,idempotencyKey
store-london-01,LATTE,3.50,EUR,card-999,order-001
store-london-01,CAPPUCCINO,4.00,EUR,card-888,order-002
EOF

# Upload
curl -X POST http://localhost:8080/api/v1/payments/import \
  -F "file=@/tmp/test.csv" | jq

# Verify imports
curl "http://localhost:8080/api/v1/payments?storeId=store-london-01" | jq
```

---

## Implementation Details

### Components

| File | Purpose |
|------|---------|
| `CsvPaymentRecord.java` | DTO for a parsed CSV row |
| `CsvImportResult.java` | Result DTO with success count and failures |
| `CsvPaymentImportService.java` | CSV parser, validator, and HTTP sender |
| `CsvImportController.java` | REST endpoint handler |
| `RestTemplateConfig.java` | Spring HTTP client configuration |

### How it Works

1. **Upload** - User sends CSV file via `POST /api/v1/payments/import`
2. **Validate file** - Check file exists, is `.csv`, not empty
3. **Parse header** - Verify CSV header matches expected format
4. **Parse rows** - Split each line by comma, validate field count
5. **Validate fields** - Check each field for type/format/value constraints
6. **Send payments** - For each valid row, send to existing `/api/v1/payments` API
7. **Retry on failure** - Exponential backoff for failed sends
8. **Collect results** - Aggregate success count and per-row failure reasons
9. **Return summary** - JSON response with total, success count, and failure details

---

## Error Recovery

### "Connection refused" / No app running
```bash
./gradlew bootRun
```

### "All rows failed with network errors"
- Check if app is running on port 8080
- Verify firewall allows local connections
- App retries automatically 3 times with exponential backoff

### "Unexpected error: CSV parsing error"
- Verify CSV header matches exactly: `storeId,coffeeType,price,currency,loyaltyCardId,idempotencyKey`
- No leading/trailing spaces in header
- Each data row must have exactly 6 comma-separated fields

---

## Notes

- **No database required** - Payments are stored in-memory via the existing `PaymentRepository`
- **No breaking changes** - Existing `/api/v1/payments` endpoints unchanged
- **Safe to retry** - Idempotency guarantee prevents duplicate payments
- **Row-level errors** - Invalid rows don't stop processing; valid rows are still sent
- **Atomic sends** - Each row either succeeds or fails; no partial updates
