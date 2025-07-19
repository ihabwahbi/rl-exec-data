# Error Handling Strategy

The pipeline is designed to be robust and fail explicitly. It will not silently ignore errors. Structured logging via **`Loguru`** will be used throughout to ensure all errors are captured with context for easy debugging.

* **Data Ingestion Errors:** If raw data for a specific period (e.g., a day or hour) is missing, corrupt, or fails schema validation, the pipeline will log a `WARNING` or `ERROR`, skip that specific period, and continue processing the next available data chunk. The entire pipeline will not halt.
* **Configuration Errors:** The pipeline will fail fast at startup if critical configurations (e.g., input data path, credentials in the `.env` file) are missing or invalid.
* **Reconstruction Errors:** Any unexpected error during data transformation (e.g., a data type mismatch) will cause the processing for that specific chunk to fail. The error, along with its full traceback and the identifier of the failing data chunk, will be logged. The pipeline will then attempt to proceed to the next chunk.
* **Fidelity Validation Errors:** If the **`FidelityReporter`** determines that the processed data does not meet the required statistical similarity to the "golden sample," it will generate a report with a clear "FAIL" status and log a `CRITICAL` error. This will not stop the pipeline but will serve as a clear signal that the output data is not suitable for model training without further investigation.

## Delta Feed and Microstructure-Specific Error Handling

* **Sequence Gap Detection:** When processing `book_delta_v2` data, the pipeline monitors `update_id` continuity. Upon detecting a gap:
  1. Log `WARNING` with gap details (expected vs actual update_id, gap size)
  2. Mark current order book state as potentially corrupted
  3. Fast-forward to next available full snapshot for state recovery
  4. Track gap statistics for the Fidelity Report
  
* **Clock Skew Compensation:** The pipeline detects and handles timing discrepancies:
  - If vendor `origin_time` differs from exchange time by >100ms, log `WARNING`
  - Apply configurable clock skew correction (default: use exchange time)
  - If 95th percentile skew exceeds threshold, fail validation with detailed report
  
* **Memory Pressure Handling:** When approaching the 28GB memory limit:
  1. Log `WARNING` when memory usage exceeds 24GB (85% threshold)
  2. Automatically switch to streaming mode for current batch
  3. Flush intermediate results to disk more frequently
  4. If OOM risk persists, gracefully save state and exit with `ERROR`
  
* **Write-Ahead Log (WAL) Recovery:**
  - On startup, check for incomplete WAL segments
  - If found, attempt automatic recovery from last checkpoint
  - If WAL is corrupted, log `ERROR` and provide manual recovery instructions
  - Never silently skip WAL recovery - data integrity is paramount
