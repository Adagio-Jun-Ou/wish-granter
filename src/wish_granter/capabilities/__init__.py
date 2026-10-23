"""Capability modules for WishGranter."""

from wish_granter.capabilities.base import Capability,CapabilityResult
from wish_granter.capabilities.web_search import WebSearchCapability
from wish_granter.capabilities.code_gen import CodeGenCapability
from wish_granter.capabilities.file_io import FileIOCapability
from wish_granter.capabilities.data_analysis import DataAnalysisCapability
from wish_granter.capabilities.web_scraper import WebScraperCapability
from wish_granter.capabilities.shell import ShellCapability
from wish_granter.capabilities.knowledge import KnowledgeCapability

__all__ = [
    "Capability", "CapabilityResult",
    "WebSearchCapability", "CodeGenCapability", "FileIOCapability",
    "DataAnalysisCapability", "WebScraperCapability", "ShellCapability",
    "KnowledgeCapability",
]