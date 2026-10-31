# Vendored HaspelSync calculation resources

Source: the locally preserved `linked-stack/haspelsync` tree, package version `1.3.4-local.1`.

This package contains only `src/calculation.js`, `public/shared.js`, and the upstream `LICENSE`. The relative import in calculation.js is adjusted from `../public/shared.js` to `./shared.js` to make this package resource closure relocatable. No service, settings, logs, credentials, npm packages, or databases are copied. Re-run `python scripts/sync_haspel_calculation_resources.py` before packaging after changing the linked source.

Source calculation SHA-256: `f4f56ff29fa73327a1f2c883cf782bfbe0667407ca6533305944f96ac6d2734d`

Packaged calculation SHA-256: `f51b14d498da8740164f9c91dd513d0473023fdf55b781825b2b65d72dfefb57`

Shared source/package SHA-256: `be542b172214d1541baddc4efdaf114cf2eae0cb6dbd23b23d63cfb150103bb1`
