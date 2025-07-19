"""Data integrity validator for downloaded files."""

import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass

import polars as pl
from loguru import logger


@dataclass
class ValidationResult:
    """Result of file validation."""
    file_path: Path
    passed: bool
    checks: Dict[str, bool]
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]


class IntegrityValidator:
    """Validates downloaded data files for completeness and quality."""
    
    def __init__(self):
        """Initialize validator with expected schemas."""
        self.expected_schemas = {
            'trades': {
                'required_columns': ['origin_time', 'price', 'quantity', 'side'],
                'optional_columns': ['trade_id', 'timestamp', 'symbol', 'exchange'],
                'numeric_columns': ['price', 'quantity'],
                'positive_columns': ['price', 'quantity']
            },
            'book': {
                'required_columns': ['origin_time'],
                'optional_columns': ['timestamp', 'symbol', 'exchange', 'bids', 'asks'],
                'numeric_columns': [],
                'positive_columns': []
            },
            'book_delta_v2': {
                'required_columns': ['origin_time', 'update_id'],
                'optional_columns': ['timestamp', 'symbol', 'exchange', 'bids', 'asks', 'side', 'price', 'new_quantity'],
                'numeric_columns': ['update_id', 'price', 'new_quantity'],
                'positive_columns': ['price']  # new_quantity can be 0 for deletions
            }
        }
        
    def validate_file(self, 
                     file_path: Path, 
                     data_type: str,
                     expected_checksum: Optional[str] = None) -> ValidationResult:
        """Run comprehensive validation on a data file.
        
        Args:
            file_path: Path to file to validate
            data_type: Type of data ('trades', 'book', 'book_delta_v2')
            expected_checksum: Optional checksum for verification
            
        Returns:
            ValidationResult with detailed findings
        """
        errors = []
        warnings = []
        checks = {}
        metadata = {}
        
        # Level 1: File existence and basic checks
        checks['file_exists'] = file_path.exists()
        if not checks['file_exists']:
            errors.append(f"File not found: {file_path}")
            return ValidationResult(file_path, False, checks, errors, warnings, metadata)
        
        # File size check
        file_size = file_path.stat().st_size
        metadata['file_size_bytes'] = file_size
        metadata['file_size_mb'] = file_size / (1024 * 1024)
        
        checks['non_empty'] = file_size > 0
        if not checks['non_empty']:
            errors.append(f"File is empty: {file_path}")
        
        # Checksum validation
        if expected_checksum:
            actual_checksum = self._calculate_checksum(file_path)
            checks['checksum_valid'] = actual_checksum == expected_checksum
            metadata['checksum'] = actual_checksum
            if not checks['checksum_valid']:
                errors.append(f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}")
        
        # Level 2: File format validation
        try:
            df = pl.read_parquet(file_path)
            checks['readable'] = True
            metadata['row_count'] = len(df)
            metadata['column_count'] = len(df.columns)
            metadata['columns'] = df.columns
            
        except Exception as e:
            checks['readable'] = False
            errors.append(f"Failed to read Parquet file: {str(e)}")
            return ValidationResult(file_path, False, checks, errors, warnings, metadata)
        
        # Level 3: Schema validation
        if data_type in self.expected_schemas:
            schema_result = self._validate_schema(df, data_type)
            checks.update(schema_result['checks'])
            errors.extend(schema_result['errors'])
            warnings.extend(schema_result['warnings'])
            metadata.update(schema_result['metadata'])
        else:
            warnings.append(f"Unknown data type: {data_type}")
        
        # Level 4: Data quality validation
        if checks.get('readable', False):
            quality_result = self._validate_data_quality(df, data_type)
            checks.update(quality_result['checks'])
            errors.extend(quality_result['errors'])
            warnings.extend(quality_result['warnings'])
            metadata.update(quality_result['metadata'])
        
        # Overall pass/fail
        passed = len(errors) == 0
        
        return ValidationResult(file_path, passed, checks, errors, warnings, metadata)
    
    def _calculate_checksum(self, file_path: Path, algorithm: str = 'sha256') -> str:
        """Calculate file checksum.
        
        Args:
            file_path: Path to file
            algorithm: Hash algorithm ('md5', 'sha256', etc.)
            
        Returns:
            Hexadecimal checksum string
        """
        hash_func = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    
    def _validate_schema(self, df: pl.DataFrame, data_type: str) -> Dict[str, Any]:
        """Validate DataFrame schema.
        
        Args:
            df: DataFrame to validate
            data_type: Expected data type
            
        Returns:
            Dictionary with validation results
        """
        checks = {}
        errors = []
        warnings = []
        metadata = {}
        
        schema = self.expected_schemas[data_type]
        required_cols = schema['required_columns']
        optional_cols = schema.get('optional_columns', [])
        
        # Check required columns
        missing_required = set(required_cols) - set(df.columns)
        checks['has_required_columns'] = len(missing_required) == 0
        if missing_required:
            errors.append(f"Missing required columns: {missing_required}")
        
        # Check for unexpected columns
        expected_cols = set(required_cols + optional_cols)
        unexpected_cols = set(df.columns) - expected_cols
        if unexpected_cols:
            warnings.append(f"Unexpected columns found: {unexpected_cols}")
        
        metadata['missing_required'] = list(missing_required)
        metadata['unexpected_columns'] = list(unexpected_cols)
        
        return {
            'checks': checks,
            'errors': errors,
            'warnings': warnings,
            'metadata': metadata
        }
    
    def _validate_data_quality(self, df: pl.DataFrame, data_type: str) -> Dict[str, Any]:
        """Validate data quality and consistency.
        
        Args:
            df: DataFrame to validate
            data_type: Data type being validated
            
        Returns:
            Dictionary with validation results
        """
        checks = {}
        errors = []
        warnings = []
        metadata = {}
        
        # Check for completely empty DataFrame
        if len(df) == 0:
            errors.append("DataFrame is empty")
            return {'checks': checks, 'errors': errors, 'warnings': warnings, 'metadata': metadata}
        
        # Origin time validation
        if 'origin_time' in df.columns:
            origin_time_checks = self._validate_origin_time(df)
            checks.update(origin_time_checks['checks'])
            errors.extend(origin_time_checks['errors'])
            warnings.extend(origin_time_checks['warnings'])
            metadata.update(origin_time_checks['metadata'])
        
        # Numeric column validation
        if data_type in self.expected_schemas:
            schema = self.expected_schemas[data_type]
            
            # Check numeric columns
            for col in schema.get('numeric_columns', []):
                if col in df.columns:
                    numeric_checks = self._validate_numeric_column(df, col)
                    checks.update({f'{col}_{k}': v for k, v in numeric_checks['checks'].items()})
                    errors.extend([f'{col}: {e}' for e in numeric_checks['errors']])
                    warnings.extend([f'{col}: {w}' for w in numeric_checks['warnings']])
            
            # Check positive columns
            for col in schema.get('positive_columns', []):
                if col in df.columns:
                    positive_checks = self._validate_positive_column(df, col)
                    checks.update({f'{col}_{k}': v for k, v in positive_checks['checks'].items()})
                    errors.extend([f'{col}: {e}' for e in positive_checks['errors']])
        
        # Data type specific validation
        if data_type == 'trades':
            trade_checks = self._validate_trades_data(df)
            checks.update(trade_checks['checks'])
            errors.extend(trade_checks['errors'])
            warnings.extend(trade_checks['warnings'])
        elif data_type == 'book_delta_v2':
            delta_checks = self._validate_delta_data(df)
            checks.update(delta_checks['checks'])
            errors.extend(delta_checks['errors'])
            warnings.extend(delta_checks['warnings'])
        
        return {
            'checks': checks,
            'errors': errors,
            'warnings': warnings,
            'metadata': metadata
        }
    
    def _validate_origin_time(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Validate origin_time column."""
        checks = {}
        errors = []
        warnings = []
        metadata = {}
        
        col = df['origin_time']
        
        # Check for null values
        null_count = col.null_count()
        checks['no_null_origin_time'] = null_count == 0
        if null_count > 0:
            errors.append(f"Found {null_count} null values in origin_time")
        
        # Check temporal ordering
        is_sorted = col.is_sorted()
        checks['origin_time_sorted'] = is_sorted
        if not is_sorted:
            warnings.append("Data not sorted by origin_time")
        
        # Check for reasonable time range (not too far in past/future)
        if not col.is_empty():
            min_time = col.min()
            max_time = col.max()
            
            # Convert to datetime if needed
            try:
                if isinstance(min_time, int):
                    # Assume nanoseconds timestamp
                    min_dt = datetime.fromtimestamp(min_time / 1e9)
                    max_dt = datetime.fromtimestamp(max_time / 1e9)
                else:
                    min_dt = min_time
                    max_dt = max_time
                
                # Check if times are reasonable (between 2020 and 2030)
                year_2020 = datetime(2020, 1, 1)
                year_2030 = datetime(2030, 1, 1)
                
                checks['reasonable_time_range'] = year_2020 <= min_dt <= year_2030 and year_2020 <= max_dt <= year_2030
                if not checks['reasonable_time_range']:
                    warnings.append(f"Unusual time range: {min_dt} to {max_dt}")
                
                metadata['time_range'] = {
                    'min': str(min_dt),
                    'max': str(max_dt),
                    'span_hours': (max_dt - min_dt).total_seconds() / 3600
                }
                
            except Exception as e:
                warnings.append(f"Could not parse origin_time values: {e}")
        
        return {
            'checks': checks,
            'errors': errors,
            'warnings': warnings,
            'metadata': metadata
        }
    
    def _validate_numeric_column(self, df: pl.DataFrame, col_name: str) -> Dict[str, Any]:
        """Validate numeric column."""
        checks = {}
        errors = []
        warnings = []
        
        if col_name not in df.columns:
            return {'checks': checks, 'errors': errors, 'warnings': warnings}
        
        col = df[col_name]
        
        # Check for null values
        null_count = col.null_count()
        checks['no_nulls'] = null_count == 0
        if null_count > 0:
            warnings.append(f"Found {null_count} null values")
        
        # Check if actually numeric
        try:
            # Try basic numeric operations
            col.min()
            col.max()
            checks['is_numeric'] = True
        except Exception:
            checks['is_numeric'] = False
            errors.append("Column is not numeric")
        
        return {
            'checks': checks,
            'errors': errors,
            'warnings': warnings
        }
    
    def _validate_positive_column(self, df: pl.DataFrame, col_name: str) -> Dict[str, Any]:
        """Validate that column contains only positive values."""
        checks = {}
        errors = []
        warnings = []
        
        if col_name not in df.columns:
            return {'checks': checks, 'errors': errors, 'warnings': warnings}
        
        col = df[col_name]
        
        try:
            # Check for non-positive values
            non_positive_count = (col <= 0).sum()
            checks['all_positive'] = non_positive_count == 0
            if non_positive_count > 0:
                errors.append(f"Found {non_positive_count} non-positive values")
        except Exception as e:
            warnings.append(f"Could not validate positive values: {e}")
        
        return {
            'checks': checks,
            'errors': errors,
            'warnings': warnings
        }
    
    def _validate_trades_data(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Validate trades-specific data quality."""
        checks = {}
        errors = []
        warnings = []
        
        # Check side column if present
        if 'side' in df.columns:
            side_values = set(df['side'].unique().to_list())
            valid_sides = {'BUY', 'SELL', 'buy', 'sell', 'B', 'S'}
            
            checks['valid_sides'] = side_values.issubset(valid_sides)
            if not checks['valid_sides']:
                invalid_sides = side_values - valid_sides
                warnings.append(f"Unexpected side values: {invalid_sides}")
        
        return {
            'checks': checks,
            'errors': errors,
            'warnings': warnings
        }
    
    def _validate_delta_data(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Validate book delta specific data quality."""
        checks = {}
        errors = []
        warnings = []
        
        # Check update_id sequence if present
        if 'update_id' in df.columns:
            update_ids = df['update_id']
            
            # Check for gaps in sequence
            if len(update_ids) > 1:
                diffs = update_ids.diff().drop_nulls()
                
                # Most differences should be 1, but gaps are possible
                gap_count = (diffs > 1).sum()
                large_gap_count = (diffs > 1000).sum()  # Very large gaps are suspicious
                
                checks['reasonable_gaps'] = large_gap_count == 0
                if large_gap_count > 0:
                    warnings.append(f"Found {large_gap_count} very large update_id gaps (>1000)")
                
                if gap_count > 0:
                    warnings.append(f"Found {gap_count} update_id gaps")
        
        return {
            'checks': checks,
            'errors': errors,
            'warnings': warnings
        }
    
    def validate_date_continuity(self, 
                                file_paths: List[Path],
                                expected_start: datetime,
                                expected_end: datetime) -> ValidationResult:
        """Validate that files provide continuous coverage over a date range.
        
        Args:
            file_paths: List of file paths to check
            expected_start: Expected start date
            expected_end: Expected end date
            
        Returns:
            ValidationResult for date continuity
        """
        checks = {}
        errors = []
        warnings = []
        metadata = {}
        
        if not file_paths:
            errors.append("No files provided for continuity check")
            return ValidationResult(Path("multiple"), False, checks, errors, warnings, metadata)
        
        # Extract dates from file paths
        file_dates = []
        for path in file_paths:
            date = self._extract_date_from_path(path)
            if date:
                file_dates.append(date)
        
        if not file_dates:
            errors.append("Could not extract dates from any file paths")
            return ValidationResult(Path("multiple"), False, checks, errors, warnings, metadata)
        
        file_dates.sort()
        
        # Check coverage
        coverage_start = min(file_dates)
        coverage_end = max(file_dates)
        
        checks['covers_start'] = coverage_start <= expected_start
        checks['covers_end'] = coverage_end >= expected_end
        
        if not checks['covers_start']:
            errors.append(f"Coverage starts {coverage_start}, expected {expected_start}")
        
        if not checks['covers_end']:
            errors.append(f"Coverage ends {coverage_end}, expected {expected_end}")
        
        # Check for gaps
        expected_days = (expected_end - expected_start).days + 1
        unique_dates = set(file_dates)
        
        checks['no_missing_days'] = len(unique_dates) >= expected_days * 0.95  # Allow 5% missing
        
        metadata['coverage_start'] = str(coverage_start)
        metadata['coverage_end'] = str(coverage_end)
        metadata['unique_dates'] = len(unique_dates)
        metadata['expected_days'] = expected_days
        
        passed = all(checks.values())
        
        return ValidationResult(Path("multiple"), passed, checks, errors, warnings, metadata)
    
    def _extract_date_from_path(self, path: Path) -> Optional[datetime]:
        """Extract date from file path."""
        import re
        
        path_str = str(path)
        
        # Look for YYYY-MM-DD pattern
        date_pattern = r'(\d{4})-(\d{2})-(\d{2})'
        match = re.search(date_pattern, path_str)
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                pass
        
        # Look for YYYY/MM/DD pattern
        date_pattern = r'(\d{4})/(\d{2})/(\d{2})'
        match = re.search(date_pattern, path_str)
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                pass
                
        return None