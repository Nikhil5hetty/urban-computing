"""Explainable Swiss public-transport assistant built on fuzzy linguistic summaries.

Package map (see docs/PROJECT.md for the architecture):
    data        raw Ist-Daten -> validated Parquet -> arrivals / connections tables
    fuzzy       vocabulary (membership functions), truth engine, quality measures, miner
    assistant   question/answer contract, fuzzy decision engine, crisp baseline
    llm         LLM runner (UBELIX), claim parser, crisp and fuzzy checkers
    evaluation  experiments for SRQ1-3 and the project-level runner (`make eval`)
"""

__version__ = "0.1.0"
