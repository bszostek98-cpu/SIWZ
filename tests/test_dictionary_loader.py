"""Tests for dictionary loader."""

import pytest
from pathlib import Path
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.io import DictionaryLoader, DictionaryLoadError
from siwz_mapper.io.dictionary_loader import load_dictionary
from siwz_mapper.models import ServiceEntry


class TestDictionaryLoader:
    """Tests for DictionaryLoader class."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Get fixtures directory."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.fixture
    def loader(self):
        """Create DictionaryLoader instance."""
        return DictionaryLoader(strict_validation=True)
    
    def test_load_valid_csv(self, loader, fixtures_dir):
        """Test loading valid CSV file."""
        csv_path = fixtures_dir / "services_v1.0.csv"
        services, version = loader.load(csv_path)
        
        assert len(services) == 10
        assert version == "1.0"
        assert all(isinstance(s, ServiceEntry) for s in services)
    
    def test_service_fields(self, loader, fixtures_dir):
        """Test that service fields are correctly loaded."""
        csv_path = fixtures_dir / "services_v1.0.csv"
        services, _ = loader.load(csv_path)
        
        # Check first service
        kar001 = next(s for s in services if s.code == "KAR001")
        assert kar001.name == "Konsultacja kardiologiczna"
        assert kar001.category == "Kardiologia"
        assert kar001.subcategory == "Konsultacje"
        assert "wizyta kardiologiczna" in kar001.synonyms
        assert "badanie kardiologiczne" in kar001.synonyms
    
    def test_synonyms_parsing(self, loader, fixtures_dir):
        """Test synonyms parsing with different separators."""
        csv_path = fixtures_dir / "services_v1.0.csv"
        services, _ = loader.load(csv_path)
        
        kar002 = next(s for s in services if s.code == "KAR002")
        assert len(kar002.synonyms) == 3
        assert "echokardiografia" in kar002.synonyms
        assert "echo serca" in kar002.synonyms
    
    def test_version_detection_from_filename(self, loader, fixtures_dir):
        """Test version detection from filename."""
        csv_path = fixtures_dir / "services_v1.0.csv"
        _, version = loader.load(csv_path)
        assert version == "1.0"
    
    def test_explicit_version(self, loader, fixtures_dir):
        """Test explicit version override."""
        csv_path = fixtures_dir / "services_v1.0.csv"
        _, version = loader.load(csv_path, version="2.5")
        assert version == "2.5"
    
    def test_whitespace_trimming(self, loader, fixtures_dir):
        """Test that whitespace is trimmed."""
        csv_path = fixtures_dir / "services_with_issues.csv"
        
        # Use non-strict mode to handle other issues
        loader_non_strict = DictionaryLoader(strict_validation=False)
        services, _ = loader_non_strict.load(csv_path)
        
        kar003 = next((s for s in services if s.code == "KAR003"), None)
        if kar003:
            assert kar003.code == "KAR003"
            assert kar003.name == "EKG spoczynkowe"
            assert kar003.category == "Kardiologia"
    
    def test_duplicate_codes_strict(self, loader, fixtures_dir):
        """Test duplicate code detection in strict mode."""
        csv_path = fixtures_dir / "services_with_issues.csv"
        
        with pytest.raises(DictionaryLoadError) as exc_info:
            loader.load(csv_path)
        
        assert "duplicate" in str(exc_info.value).lower()
    
    def test_duplicate_codes_non_strict(self, fixtures_dir):
        """Test duplicate handling in non-strict mode."""
        csv_path = fixtures_dir / "services_with_issues.csv"
        loader_non_strict = DictionaryLoader(strict_validation=False)
        
        services, _ = loader_non_strict.load(csv_path)
        
        # Should keep only first occurrence of KAR001
        kar001_entries = [s for s in services if s.code == "KAR001"]
        assert len(kar001_entries) == 1
        assert kar001_entries[0].name == "Konsultacja kardiologiczna"
    
    def test_missing_required_fields(self, fixtures_dir):
        """Test handling of missing required fields."""
        csv_path = fixtures_dir / "services_with_issues.csv"
        loader_non_strict = DictionaryLoader(strict_validation=False)
        
        services, _ = loader_non_strict.load(csv_path)
        
        # Should skip rows with missing code or name
        codes = [s.code for s in services]
        assert "" not in codes
        
        names = [s.name for s in services]
        assert "" not in names
    
    def test_semicolon_separator(self, loader, fixtures_dir):
        """Test CSV with semicolon separator."""
        csv_path = fixtures_dir / "services_semicolon.csv"
        services, _ = loader.load(csv_path)
        
        assert len(services) == 2
        assert services[0].code == "KAR001"
    
    def test_file_not_found(self, loader):
        """Test error when file doesn't exist."""
        with pytest.raises(DictionaryLoadError) as exc_info:
            loader.load(Path("nonexistent.csv"))
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_unsupported_format(self, loader, tmp_path):
        """Test error for unsupported file format."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("some data")
        
        with pytest.raises(DictionaryLoadError) as exc_info:
            loader.load(txt_file)
        
        assert "unsupported" in str(exc_info.value).lower()
    
    def test_get_stats(self, loader, fixtures_dir):
        """Test loading statistics."""
        csv_path = fixtures_dir / "services_v1.0.csv"
        services, version = loader.load(csv_path)
        
        stats = loader.get_stats()
        assert stats['valid_services'] == len(services)
        assert stats['version'] == version
        assert 'source_file' in stats
    
    def test_load_from_dataframe(self, loader):
        """Test loading from DataFrame."""
        df = pd.DataFrame([
            {
                'code': 'TEST001',
                'name': 'Test Service',
                'category': 'Testing',
                'subcategory': 'Unit Tests',
                'synonyms': 'test,testing'
            },
            {
                'code': 'TEST002',
                'name': 'Another Test',
                'category': 'Testing',
                'subcategory': '',
                'synonyms': ''
            }
        ])
        
        services, version = loader.load_from_dataframe(df, version="test")
        
        assert len(services) == 2
        assert version == "test"
        assert services[0].code == "TEST001"
        assert len(services[0].synonyms) == 2
    
    def test_optional_subcategory(self, loader):
        """Test that subcategory is optional."""
        df = pd.DataFrame([
            {
                'code': 'TEST001',
                'name': 'Test Service',
                'category': 'Testing'
            }
        ])
        
        services, _ = loader.load_from_dataframe(df)
        
        assert len(services) == 1
        assert services[0].subcategory is None
    
    def test_to_search_text(self, loader, fixtures_dir):
        """Test that loaded services have working to_search_text method."""
        csv_path = fixtures_dir / "services_v1.0.csv"
        services, _ = loader.load(csv_path)
        
        service = services[0]
        search_text = service.to_search_text()
        
        assert service.code in search_text
        assert service.name in search_text
        assert service.category in search_text


class TestConvenienceFunction:
    """Tests for load_dictionary convenience function."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Get fixtures directory."""
        return Path(__file__).parent / "fixtures"
    
    def test_load_dictionary(self, fixtures_dir):
        """Test convenience function."""
        csv_path = fixtures_dir / "services_v1.0.csv"
        services, version = load_dictionary(csv_path)
        
        assert len(services) == 10
        assert version == "1.0"
    
    def test_load_dictionary_non_strict(self, fixtures_dir):
        """Test convenience function with non-strict mode."""
        csv_path = fixtures_dir / "services_with_issues.csv"
        services, version = load_dictionary(csv_path, strict=False)
        
        assert len(services) > 0
        # Should have removed invalid entries
        assert len(services) < 7  # Original has 7 rows


class TestColumnMapping:
    """Tests for custom column mapping."""
    
    def test_custom_column_names(self, tmp_path):
        """Test loading with custom column names."""
        # Create CSV with Polish column names
        csv_file = tmp_path / "services_pl.csv"
        csv_file.write_text(
            "kod,nazwa,kategoria,podkategoria,synonimy\n"
            "KAR001,Konsultacja,Kardiologia,Konsultacje,wizyta\n",
            encoding='utf-8'
        )
        
        loader = DictionaryLoader()
        services, _ = loader.load(csv_file)
        
        assert len(services) == 1
        assert services[0].code == "KAR001"
        assert services[0].name == "Konsultacja"
    
    def test_missing_required_column(self, tmp_path):
        """Test error when required column is missing."""
        csv_file = tmp_path / "invalid.csv"
        csv_file.write_text(
            "some_col,another_col\n"
            "value1,value2\n"
        )
        
        loader = DictionaryLoader()
        with pytest.raises(DictionaryLoadError) as exc_info:
            loader.load(csv_file)
        
        assert "missing" in str(exc_info.value).lower()


class TestVersionDetection:
    """Tests for version detection."""
    
    def test_version_patterns(self):
        """Test various version patterns in filenames."""
        loader = DictionaryLoader()
        
        test_cases = [
            ("services_v1.0.csv", "1.0"),
            ("services_v2.5.1.csv", "2.5.1"),
            ("services_1.2.csv", "1.2"),
            ("dict_v3.csv", "3"),
            ("services.csv", "1.0"),  # Default
        ]
        
        for filename, expected_version in test_cases:
            file_path = Path(filename)
            detected = loader._detect_version(file_path)
            assert detected == expected_version, f"Failed for {filename}"


class TestLargeDataset:
    """Tests for handling large datasets."""
    
    def test_load_many_rows(self, tmp_path):
        """Test loading thousands of rows efficiently."""
        # Create CSV with 5000 rows
        csv_file = tmp_path / "large_services.csv"
        
        with open(csv_file, 'w', encoding='utf-8') as f:
            f.write("code,name,category,subcategory,synonyms\n")
            for i in range(5000):
                f.write(f"SVC{i:05d},Service {i},Category {i % 10},Subcat,synonym{i}\n")
        
        loader = DictionaryLoader()
        services, _ = loader.load(csv_file)
        
        assert len(services) == 5000
        assert services[0].code == "SVC00000"
        assert services[-1].code == "SVC04999"
    
    def test_memory_efficiency(self, tmp_path):
        """Test that loading is memory efficient (no duplicate storage)."""
        csv_file = tmp_path / "services.csv"
        csv_file.write_text(
            "code,name,category\n"
            "SVC001,Service 1,Cat1\n"
            "SVC002,Service 2,Cat2\n"
        )
        
        loader = DictionaryLoader()
        services, _ = loader.load(csv_file)
        
        # Verify each service is a separate object
        assert id(services[0]) != id(services[1])
        
        # Verify we can access all services
        codes = [s.code for s in services]
        assert codes == ["SVC001", "SVC002"]

