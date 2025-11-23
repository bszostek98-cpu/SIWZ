from pathlib import Path
import json
import pytest

from siwz_mapper.pipeline import (
    PDFExtractor,
    VariantDetector,
    ServiceMapper,
    Pipeline,
)
from siwz_mapper.llm.client import LLMClient
from siwz_mapper.config import Config
from siwz_mapper.llm.classify_segments import SegmentClassification
from siwz_mapper.models import ServiceEntry, VariantResult, DocumentResult


# -----------------------
# Fixtures (local)
# -----------------------

@pytest.fixture
def llm_client():
    # LLMClient is a stub anyway, so empty config is fine
    cfg = Config()
    return LLMClient(cfg.llm)


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


class TestVariantDetector:
    def test_initialization(self, llm_client):
        detector = VariantDetector(llm_client)
        assert detector is not None

    def test_detect_stub(self, llm_client):
        detector = VariantDetector(llm_client)

        classifications = [
            SegmentClassification(
                segment_id="seg1",
                label="variant_header",
                variant_hint="1",
                is_prophylaxis=False,
                confidence=0.9,
                rationale="test"
            ),
            SegmentClassification(
                segment_id="seg2",
                label="variant_body",
                variant_hint=None,
                is_prophylaxis=False,
                confidence=0.9,
                rationale="test"
            ),
        ]

        variants = detector.detect(classifications)
        assert isinstance(variants, list)
        assert len(variants) >= 1


class TestServiceMapper:
    def test_initialization(self, llm_client, services):
        mapper = ServiceMapper(
            llm_client=llm_client,
            services=services,
            top_k=5
        )
        assert len(mapper.services) == 2
        assert mapper.top_k == 5
        assert len(mapper.service_index) == 2

    def test_map_variants_stub(self, llm_client, services):
        mapper = ServiceMapper(
            llm_client=llm_client,
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
        assert pipeline.variant_detector is not None
        assert pipeline.service_mapper is not None

    def test_process_stub(self, config, services, tmp_path):
        pipeline = Pipeline(config=config, services=services)

        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"dummy")

        output_path = tmp_path / "output.json"

        result = pipeline.process(
            pdf_path=pdf_path,
            output_path=output_path
        )

        assert isinstance(result, DocumentResult)
        assert output_path.exists()

        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["doc_id"] == "test"
