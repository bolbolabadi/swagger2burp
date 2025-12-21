# BApp Submission: Swagger2Burp

- Name: Swagger2Burp
- Author: BolbolSec
- License: MIT
- Repository URL: https://github.com/bolbolabadi/Swagger2Burp
- Entry class: `com.alireza.swagger2burp.Swagger2BurpMontoyaExtension`
- Extension type: Java (Montoya API)
- Minimum Burp version: TBD after final tests (Montoya API required)

## Short description
Import Swagger/OpenAPI (Swagger 2.0 and OpenAPI 3) and generate example HTTP requests per operation, ready to send to Repeater.

## Detailed description
Swagger2Burp adds a Burp tab to import Swagger/OpenAPI specs from URL(s) or pasted JSON. It supports optional JWT and custom headers for fetching protected specs. The extension can auto‑fill path parameters, include query parameters with sample values, and generate example JSON bodies based on schemas/examples.

The base URL is taken from `servers`/`basePath` when available, or you can provide a Base URL override. After import, you can review all generated requests and send the selected ones to Repeater.

- Inputs: URL(s) to JSON/YAML, or pasted Raw JSON
- Auth for fetching specs: JWT and custom headers
- Path/query parameters: optional auto-fill
- Request bodies: generated from schema/example
- Preview + send selected to Repeater

## Requirements
- Burp Suite with Montoya API support
- Bundled dependencies: Jackson (JSON) and SnakeYAML (YAML)

## Installation
1) Download the release JAR
2) In Burp: Extensions -> Add -> Extension type: Java -> Select the JAR

## Usage
1) Open the Swagger2Burp tab
2) (Optional) Enter JWT and custom headers
3) If Swagger 2.0 spec lacks `host`/`basePath`, set Base URL override
4) Choose input mode (Auto-detect, URL(s), Raw JSON), provide spec(s), and click Import
5) Select desired requests and click "Send selected to Repeater"

## Known limitations
- When no base URL can be resolved from spec and no Base URL override is provided, operations are skipped

## Changelog
See CHANGELOG.md

## Screenshots
- UI overview: <img width="1793" height="1036" alt="swagger2burp-tab-ui" src="https://github.com/user-attachments/assets/289a4dad-a84d-484c-952a-c8360df5f765" />

- Import and send to Repeater: <img width="1916" height="1007" alt="swagger2burp-tab-repeater" src="https://github.com/user-attachments/assets/8cf31369-2182-4920-a797-5b0d01311759" />

