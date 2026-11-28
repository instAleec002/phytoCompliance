"""Document corpus processing: files to normalized blocks to chunks, every stage swappable by configuration.
See README.md in this folder for the design and the swap points."""
from .config import PipelineConfig, load_config
from .model import Block, Cell, Chunk, MarkdownDocument, NormalizedDocument
from .pipeline import Pipeline, Result

__all__ = ["Block", "Cell", "Chunk", "MarkdownDocument", "NormalizedDocument", "Pipeline", "PipelineConfig", "Result",
           "load_config"]
