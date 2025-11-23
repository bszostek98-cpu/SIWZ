"""
Dictionary loader for medical services.

Loads services dictionary from CSV/XLSX files into List[ServiceEntry].
Supports versioning, validation, and efficient loading of large datasets.
"""

import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import logging

import pandas as pd
from pydantic import ValidationError

from ..models import ServiceEntry

logger = logging.getLogger(__name__)


class DictionaryLoadError(Exception):
    """Exception raised when dictionary loading fails."""
    pass


class DictionaryLoader:
    """
    Loader for medical services dictionary.
    
    Supports:
    - CSV and XLSX formats
    - Efficient loading of thousands of rows
    - Version detection from filename or column
    - Validation: duplicate codes, required fields, whitespace trimming
    """
    
    # Default column mappings (case-insensitive)
    DEFAULT_COLUMN_MAPPING = {
        'code': ['code', 'service_code', 'kod', 'kod_uslugi'],
        'name': ['name', 'service_name', 'nazwa', 'nazwa_uslugi'],
        'category': ['category', 'kategoria', 'cat'],
        'subcategory': ['subcategory', 'podkategoria', 'subcat', 'sub_category'],
        'synonyms': ['synonyms', 'synonimy', 'aliases', 'alternative_names'],
    }
    
    # Version detection pattern from filename
    VERSION_PATTERN = re.compile(r'[_v](\d+\.?\d*\.?\d*)(?:\.|_|$)', re.IGNORECASE)
    
    def __init__(
        self,
        column_mapping: Optional[Dict[str, List[str]]] = None,
        strict_validation: bool = True
    ):
        """
        Initialize dictionary loader.
        
        Args:
            column_mapping: Custom column name mappings (optional)
            strict_validation: If True, raise errors on validation issues
        """
        self.column_mapping = column_mapping or self.DEFAULT_COLUMN_MAPPING
        self.strict_validation = strict_validation
        self.stats: Dict[str, Any] = {}
    
    def load(
        self,
        file_path: Path,
        encoding: str = 'utf-8',
        version: Optional[str] = None
    ) -> Tuple[List[ServiceEntry], str]:
        """
        Load services dictionary from file.
        
        Args:
            file_path: Path to CSV or XLSX file
            encoding: File encoding (for CSV)
            version: Explicit version string (overrides auto-detection)
            
        Returns:
            Tuple of (services list, version string)
            
        Raises:
            DictionaryLoadError: If loading or validation fails
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise DictionaryLoadError(f"File not found: {file_path}")
        
        logger.info(f"Loading dictionary from: {file_path}")
        
        # Detect version
        detected_version = version or self._detect_version(file_path)
        logger.info(f"Dictionary version: {detected_version}")
        
        # Load data
        try:
            df = self._load_dataframe(file_path, encoding)
        except Exception as e:
            raise DictionaryLoadError(f"Failed to load file: {e}")
        
        # Map columns
        df = self._map_columns(df)
        
        # Validate and clean
        df = self._validate_and_clean(df)
        
        # Convert to ServiceEntry objects
        services = self._convert_to_services(df)
        
        # Final validation
        self._validate_services(services)
        
        # Store stats
        self.stats = {
            'total_rows': len(df),
            'valid_services': len(services),
            'version': detected_version,
            'source_file': str(file_path),
        }
        
        logger.info(f"Loaded {len(services)} services (version: {detected_version})")
        
        return services, detected_version
    
    def load_from_dataframe(
        self,
        df: pd.DataFrame,
        version: str = "unknown"
    ) -> Tuple[List[ServiceEntry], str]:
        """
        Load services from an existing DataFrame.
        
        Args:
            df: DataFrame with services data
            version: Version string
            
        Returns:
            Tuple of (services list, version string)
        """
        logger.info(f"Loading dictionary from DataFrame ({len(df)} rows)")
        
        # Map columns
        df = self._map_columns(df)
        
        # Validate and clean
        df = self._validate_and_clean(df)
        
        # Convert to ServiceEntry objects
        services = self._convert_to_services(df)
        
        # Final validation
        self._validate_services(services)
        
        logger.info(f"Loaded {len(services)} services")
        
        return services, version
    
    def _load_dataframe(self, file_path: Path, encoding: str) -> pd.DataFrame:
        """Load DataFrame from CSV or XLSX."""
        suffix = file_path.suffix.lower()
        
        if suffix == '.csv':
            # Try different separators
            for sep in [',', ';', '\t', '|']:
                try:
                    df = pd.read_csv(file_path, sep=sep, encoding=encoding)
                    if len(df.columns) > 1:  # Valid separator found
                        logger.debug(f"Loaded CSV with separator '{sep}'")
                        break
                except Exception:
                    continue
            else:
                raise DictionaryLoadError("Could not parse CSV file with any separator")
        
        elif suffix in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path, engine='openpyxl' if suffix == '.xlsx' else None)
        
        else:
            raise DictionaryLoadError(f"Unsupported file format: {suffix}")
        
        if df.empty:
            raise DictionaryLoadError("File contains no data")
        
        logger.debug(f"Loaded DataFrame: {len(df)} rows, {len(df.columns)} columns")
        return df
    
    def _map_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map DataFrame columns to standard names."""
        # Normalize column names
        df.columns = df.columns.str.strip().str.lower()
        
        logger.debug(f"Normalized columns: {list(df.columns)}")
        
        # Create mapping from CSV columns to standard names
        col_to_standard = {}
        for standard_name, possible_names in self.column_mapping.items():
            possible_lower = [name.lower() for name in possible_names]
            for col in df.columns:
                if col in possible_lower:
                    col_to_standard[col] = standard_name
                    logger.debug(f"Mapped '{col}' -> '{standard_name}'")
                    break
        
        # Check required fields
        required = ['code', 'name', 'category']
        missing = []
        for req in required:
            if req not in col_to_standard.values():
                missing.append(req)
        
        if missing:
            available = list(df.columns)
            raise DictionaryLoadError(
                f"Missing required columns: {missing}. "
                f"Available columns: {available}. "
                f"Mapped: {col_to_standard}"
            )
        
        # Rename columns to standard names
        df = df.rename(columns=col_to_standard)
        
        # Select only standard columns that exist
        available_cols = [col for col in ['code', 'name', 'category', 'subcategory', 'synonyms'] 
                         if col in df.columns]
        df = df[available_cols]
        
        logger.debug(f"Final columns after mapping: {list(df.columns)}")
        return df
    
    def _validate_and_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and clean data."""
        original_len = len(df)
        
        # Remove completely empty rows
        df = df.dropna(how='all')
        
        # Trim whitespace from string columns
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.strip()
        
        # Fill NaN in optional fields first
        optional_cols = ['subcategory', 'synonyms']
        for col in optional_cols:
            if col in df.columns:
                df[col] = df[col].fillna('')
        
        # Check required fields
        required_cols = ['code', 'name', 'category']
        for col in required_cols:
            if col in df.columns:
                # Remove rows with empty required fields
                before = len(df)
                df = df[df[col].notna() & (df[col] != '')]
                after = len(df)
                if after < before:
                    logger.warning(f"Removed {before - after} rows with empty '{col}'")
        
        # Check for duplicate codes
        if 'code' in df.columns:
            duplicates = df[df['code'].duplicated(keep=False)]
            if not duplicates.empty:
                dup_codes = duplicates['code'].unique().tolist()
                error_msg = f"Found {len(dup_codes)} duplicate codes: {dup_codes[:5]}"
                if self.strict_validation:
                    raise DictionaryLoadError(error_msg)
                else:
                    logger.warning(error_msg)
                    # Keep first occurrence
                    df = df.drop_duplicates(subset=['code'], keep='first')
        
        # Fill NaN in optional fields with empty string (before validation)
        optional_cols = ['subcategory', 'synonyms']
        for col in optional_cols:
            if col in df.columns:
                df[col] = df[col].fillna('')
        
        cleaned_count = len(df)
        removed_count = original_len - cleaned_count
        
        if removed_count > 0:
            logger.info(f"Removed {removed_count} invalid rows ({cleaned_count} remaining)")
        
        # Ensure empty strings for optional fields (not None)
        for col in optional_cols:
            if col in df.columns:
                df[col] = df[col].replace('', pd.NA).fillna('')
        
        return df
    
    def _convert_to_services(self, df: pd.DataFrame) -> List[ServiceEntry]:
        """Convert DataFrame rows to ServiceEntry objects."""
        services = []
        errors = []
        
        logger.debug(f"Converting {len(df)} rows to ServiceEntry objects")
        logger.debug(f"DataFrame columns: {list(df.columns)}")
        
        for idx, row in df.iterrows():
            try:
                # Parse synonyms
                synonyms = []
                if 'synonyms' in row and row['synonyms']:
                    syn_str = str(row['synonyms'])
                    # Split by common separators
                    for sep in [',', ';', '|', '\n']:
                        if sep in syn_str:
                            synonyms = [s.strip() for s in syn_str.split(sep) if s.strip()]
                            break
                    else:
                        # No separator found, treat as single synonym
                        if syn_str.strip():
                            synonyms = [syn_str.strip()]
                
                # Create ServiceEntry
                service_data = {
                    'code': str(row['code']).strip(),
                    'name': str(row['name']).strip(),
                    'category': str(row['category']).strip(),
                    'subcategory': str(row.get('subcategory', '')).strip() or None,
                    'synonyms': synonyms
                }
                logger.debug(f"Row {idx}: Creating ServiceEntry with data: {service_data}")
                service = ServiceEntry(**service_data)
                services.append(service)
                logger.debug(f"Row {idx}: Successfully created service {service.code}")
                
            except ValidationError as e:
                error_msg = f"Row {idx}: {e}"
                errors.append(error_msg)
                if self.strict_validation:
                    raise DictionaryLoadError(error_msg)
                else:
                    logger.warning(error_msg)
            except Exception as e:
                error_msg = f"Row {idx}: Unexpected error: {e}"
                errors.append(error_msg)
                if self.strict_validation:
                    raise DictionaryLoadError(error_msg)
                else:
                    logger.warning(error_msg)
        
        if errors and not self.strict_validation:
            logger.warning(f"Encountered {len(errors)} errors during conversion")
        
        return services
    
    def _validate_services(self, services: List[ServiceEntry]):
        """Final validation of loaded services."""
        if not services:
            raise DictionaryLoadError("No valid services loaded")
        
        # Check for duplicate codes (should not happen after cleaning, but double-check)
        codes = [s.code for s in services]
        unique_codes = set(codes)
        
        if len(codes) != len(unique_codes):
            duplicates = [code for code in unique_codes if codes.count(code) > 1]
            raise DictionaryLoadError(f"Duplicate codes found: {duplicates}")
        
        logger.debug(f"Validated {len(services)} unique services")
    
    def _detect_version(self, file_path: Path) -> str:
        """Detect version from filename."""
        filename = file_path.stem
        
        # Try to extract version from filename
        match = self.VERSION_PATTERN.search(filename)
        if match:
            version = match.group(1)
            return version
        
        # Default version
        return "1.0"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get loading statistics."""
        return self.stats.copy()


def load_dictionary(
    file_path: Path,
    encoding: str = 'utf-8',
    version: Optional[str] = None,
    strict: bool = True
) -> Tuple[List[ServiceEntry], str]:
    """
    Convenience function to load services dictionary.
    
    Args:
        file_path: Path to CSV or XLSX file
        encoding: File encoding (for CSV)
        version: Explicit version string
        strict: Enable strict validation
        
    Returns:
        Tuple of (services list, version string)
        
    Example:
        >>> services, version = load_dictionary("data/services_v1.2.csv")
        >>> print(f"Loaded {len(services)} services (version {version})")
        Loaded 1500 services (version 1.2)
    """
    loader = DictionaryLoader(strict_validation=strict)
    return loader.load(file_path, encoding=encoding, version=version)

