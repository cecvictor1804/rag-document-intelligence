"""Core contract shared by the backend API and the ingestion pipeline.

`models` holds the data transfer objects; `interfaces` holds the swappable
provider Protocols. Both halves of the system import from here so there is a
single definition of `Chunk`, `EmbeddingProvider`, `VectorStore`, etc.
"""
