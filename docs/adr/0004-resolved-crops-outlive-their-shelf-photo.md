# Reference images cropped from a Shelf Photo belong to the Product Catalogue and outlive the photo

When a Manager resolves an Unknown Product, the crop of its Facing becomes a reference image of a Product. That crop is Product Catalogue data. It is kept when its Shelf Photo is deleted, whether by the six-month sweep or by a Manager, and it does not record which photo it came from. ADR 0003's deletion of a Shelf Photo covers the photo and its Annotated Photos only. The crop comes from the already-blurred photo and shows only the product, which is the same material ADR 0003 allows to be sent to third-party models. Deleting the crop would silently remove the reference image that lets the Product be recognised. A Product with no reference images left could then no longer be matched.

## Considered Options

- Deleting crops along with their Shelf Photo: rejected. Each reference image would need to record its source photo. Deleting a photo could also leave a Product with no reference images, and we would have to decide what to do with that Product. All this cost would buy no privacy, because the crop holds no personal data.
