# Shelf Photos are blurred on arrival and never leave the service whole

People in Shelf Photos are detected and blurred before anything is stored, and the original is never kept; no whole Shelf Photo is ever sent to a third-party API, so any future external model (for example an LLM for low-confidence matches) may receive only product crops. Shelf Photos are deleted after six months, or earlier on request, while Planograms and Compliance Check results are kept. The service stores only the host's opaque user IDs, never names or emails. Photos from in-store cameras routinely capture customers and staff, recognition needs only the products, and these rules keep identifiable personal data out of the service entirely rather than having to govern it.

## Consequences

These constraints are not visible in the recognition code but limit future choices: a "just send it to a vision LLM" improvement is ruled out unless it works on crops.
