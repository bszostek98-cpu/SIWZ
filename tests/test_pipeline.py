from pathlib import Path
import json
import pytest

from siwz_mapper.pipeline import (
    PDFExtractor,
    ServiceMapper,
    Pipeline,
    VariantAggregator,
)
from siwz_mapper.config import Config
from siwz_mapper.models import ServiceEntry, VariantResult, DocumentResult


# -----------------------
# Fixtures (local)
# -----------------------

@pytest.fixture
def config():
    return Config()


@pytest.fixture
def services():
    return [
        ServiceEntry(
            code="SVC001",
            name="Konsultacja kardiologiczna",
            category="Kardiologia",
            subcategory=None,
            synonyms=[]
        ),
        ServiceEntry(
            code="SVC002",
            name="USG serca",
            category="Kardiologia",
            subcategory=None,
            synonyms=[]
        ),
    ]


# -----------------------
# Tests
# -----------------------

class TestPDFExtractor:
    def test_extract_stub(self):
        """PDFExtractor should return a list of PdfSegments even if file is missing."""
        extractor = PDFExtractor()
        segs = extractor.extract(Path("dummy.pdf"))

        assert isinstance(segs, list)
        assert len(segs) >= 1
        assert hasattr(segs[0], "segment_id")
        assert hasattr(segs[0], "text")


class TestServiceMapper:
    def test_initialization(self, services):
        mapper = ServiceMapper(
            services=services,
            top_k=5
        )
        assert len(mapper.services) == 2
        assert mapper.top_k == 5

    def test_map_variants_stub(self, services):
        mapper = ServiceMapper(
            services=services
        )

        variant = VariantResult(
            variant_id="v1",
            core_codes=["SVC001"],
            prophylaxis_codes=[],
            mappings=[]
        )

        out = mapper.map_variants([variant])
        assert out == [variant]


class TestPipeline:
    def test_initialization(self, config, services):
        pipeline = Pipeline(config=config, services=services)

        assert pipeline.config is not None
        assert len(pipeline.services) == 2
        assert pipeline.pdf_extractor is not None
        assert pipeline.variant_aggregator is not None
        assert pipeline.service_mapper is not None

    def test_process_stub(self, config, services, tmp_path):
        pipeline = Pipeline(config=config, services=services)

        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"dummy")  # niepoprawny PDF -> extractor zwróci stub

        output_path = tmp_path / "output.json"

        result = pipeline.process(
            pdf_path=pdf_path,
            output_path=output_path
        )

        assert isinstance(result, DocumentResult)
        assert output_path.exists()

        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["doc_id"] == "test"
