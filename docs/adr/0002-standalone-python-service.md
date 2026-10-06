# Planogram is a standalone Python service integrated through the host's UI

Planogram runs as its own FastAPI service with its own storage (SQLite for the MVP behind a repository interface; local image storage behind a storage interface), and the host product integrates it only by calling its HTTP API from the host's React UI. The host uses a different backend architecture, so a separate service avoids coupling to it, and Python is where the computer-vision tooling the recognition pipeline needs (detectors, embedding models, OpenCV) lives.

## Considered Options

- Shipping a React component package as the integration surface: deferred; reusable components may be extracted from this repo's development UI later.
- Running recognition in the browser against an AI API: rejected, as it exposes API keys and puts matching logic in the client.
