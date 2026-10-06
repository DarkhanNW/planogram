# Recognition is a two-stage pipeline (detect, then match), not a vision LLM

Recognising Products in a Shelf Photo uses two stages behind one swappable interface: a product detector that boxes every Facing and finds the Shelf lines, then image-embedding similarity that matches each crop against the Product Catalogue, with matches below a threshold becoming Unknown Products. We chose this over sending the photo and reference images to a vision LLM because the Annotated Photo needs precise boxes, results must be repeatable so Compliance Scores are comparable over time, and passing ~100+ reference images per request is slow and costly.

## Consequences

The interface ("Shelf Photo in, recognised Facings with boxes out") is the seam: Extraction and the Compliance Check depend only on it, so a vision LLM can later be added for low-confidence matches without touching them.
