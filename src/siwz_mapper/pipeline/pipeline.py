from pathlib import Path
from typing import Optional, List
import logging
import json

from ..config import Config
from ..models import DocumentResult, VariantResult, ServiceEntry
from .pdf_extractor import PDFExtractor
from .service_mapper import ServiceMapper
from .variant_detector import VariantDetector

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: Optional[Config] = None, services: Optional[List[ServiceEntry]] = None):
        self.config = config or Config()
        self.services = services or []

        self.pdf_extractor = PDFExtractor(
            extract_bboxes=getattr(self.config.pipeline, "extract_bboxes", True)
        )
        self.variant_detector = VariantDetector(llm_client=None)   # NEW
        self.service_mapper = ServiceMapper(
            llm_client=None,
            services=self.services,
            top_k=getattr(self.config.pipeline, "top_k_candidates", 10)
        )

    def process(self, pdf_path: Path, output_path: Optional[Path] = None) -> DocumentResult:
        segments = self.pdf_extractor.extract(pdf_path)

        result = DocumentResult(
            doc_id=pdf_path.stem,
            variants=[],
            metadata={
                "pipeline_version": "0.1.0-stub",
                "num_segments": len(segments),
            },
        )

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result.model_dump(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

        return result


    def run(self, pdf_path: str) -> DocumentResult:
        return self.process(Path(pdf_path))
