# Sample Product Catalogue

A sample Product Catalogue for the mock-up grocery Fixture in
`service/tests/fixtures/mockup/source/`: 61 Products, every product in those photos whose
label can be read. It uses the bulk import format (`sku`, `name`, `images` with file names
separated by `;`).

Each reference image is a single Facing cropped from `full.jpeg`. Fifteen Products also have
a second image (`*-2.jpg`) cropped from `partial.jpeg`. The seven Products in the smoke-test
catalogue (`service/tests/fixtures/mockup/catalogue.csv`) keep the same SKUs and first images.

Products left out because their labels are illegible or cut off at the edge of the photo:
the green-label Ben's Original Korma, the Chinese sauce cans, the red Aromat, the Centra
ketchup, the small Chef jars, Chef Chilli sauce, the third Hellmann's squeezy, Hellmann's
Chilli and Napolina Tomato Tomatoes. They should come out as Unknown Products.

Import it from the development UI, or with curl against a running service:

```sh
cd samples/catalogue
curl -X POST http://localhost:8000/products/import \
  -H "X-API-Key: dev-key" -H "X-User-Id: dev" -H "X-User-Role: Manager" \
  -F csv=@catalogue.csv $(for f in images/*.jpg; do printf -- '-F images=@%s ' "$f"; done)
```
