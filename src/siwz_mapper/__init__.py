"""
SIWZ Medical Service Mapper

System do mapowania wzmianek o usługach medycznych w PDFach SIWZ
na wewnętrzne kody usług z wykorzystaniem GPT API.
"""

__version__ = "0.1.0"

# Core models - convenient imports
from .models import (
    ServiceEntry,
    PdfSegment,
    DetectedEntity,
    CandidateService,
    EntityMapping,
    VariantResult,
    DocumentResult,
    ValidationHelper,
)

# I/O utilities
from .io import DictionaryLoader, DictionaryLoadError, PDFLoader, PDFLoadError
from .io.dictionary_loader import load_dictionary
from .io.pdf_loader import load_pdf

__all__ = [
    # Models
    "ServiceEntry",
    "PdfSegment",
    "DetectedEntity",
    "CandidateService",
    "EntityMapping",
    "VariantResult",
    "DocumentResult",
    "ValidationHelper",
    # I/O
    "DictionaryLoader",
    "DictionaryLoadError",
    "load_dictionary",
    "PDFLoader",
    "PDFLoadError",
    "load_pdf",
]

