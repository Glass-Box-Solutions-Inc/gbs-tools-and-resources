# Phileas

Java library to deidentify and redact PII, PHI, and sensitive information from text and PDF documents.

## Overview

Phileas analyzes text and documents to identify over 30 types of sensitive information including person names, SSNs, credit cards, medical conditions, IP addresses, and more. When sensitive information is found, Phileas can replace, encrypt, anonymize, or redact it based on configurable policies. Supports conditional redaction, sentiment classification, and consistent deidentification across documents.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Java |
| Build Tool | Maven |
| Version | 3.0.0 |
| License | Apache License 2.0 (as of v2.2.1) |
| Distribution | Maven Central |
| Related Service | Philter API (built on Phileas) |

## Commands

```bash
# Clone and download models
git lfs pull

# Build library
mvn clean install

# Add to Maven project
<dependency>
  <groupId>ai.philterd</groupId>
  <artifactId>phileas</artifactId>
  <version>3.0.0</version>
</dependency>
```

## Architecture

### Supported Information Types (30+)

**Persons:**
- Person names (NER, dictionary, census data)
- Physician names, first names, surnames

**Medical:**
- Medical conditions

**Common:**
- Ages, bank account numbers, Bitcoin addresses
- Credit cards, currency (USD), dates
- Driver's license numbers (US), email addresses
- IBAN codes, IP addresses (IPv4/IPv6), MAC addresses
- Passport numbers (US), phone numbers, phone extensions
- SSNs/TINs, tracking numbers (UPS/FedEx/USPS)
- URLs, VINs, zip codes

**US Locations:**
- Cities, counties, hospitals, states, state abbreviations

**Custom Filters:**
- Dictionary, identifier

### Core Components

**FilterService** - Main service for text/PDF filtering
- `PlainTextFilterService` - For text processing
- `PdfFilterService` - For PDF redaction

**Policy** - Defines filtering rules
- Types of sensitive information to find
- Redaction strategies per type
- Conditions for redaction
- Terms to ignore

**PhileasConfiguration** - Configuration properties

### Example Policy (JSON)

```json
{
  "name": "default",
  "ignored": [],
  "identifiers": {
    "age": {
      "ageFilterStrategies": [{
        "strategy": "REDACT",
        "redactionFormat": "{{{REDACTED-%t}}}"
      }]
    }
  }
}
```

## Environment Variables

No environment variables required for core library usage. Configuration is provided through `Properties` objects and policy files.

## Note

For company-wide development standards, see the main CLAUDE.md at /home/vncuser/Desktop/CLAUDE.md.

---

For company-wide development standards, see the main CLAUDE.md at `~/Desktop/CLAUDE.md`.

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
