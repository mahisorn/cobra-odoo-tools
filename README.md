# cobra-odoo-tools

Tools for the cdrone Odoo instance (Cobra drone business).

- `material-costs/`: sync Cobra's SAP standard material costs into Odoo products ([README](material-costs/README.md))
- `insee-bom/`: INSEE wing shipset test structure (skin → wing → shipset) on cdrone-test ([README](insee-bom/README.md))
- `sim-line/`: simulated drone line, demo BoMs and a 1-week order run on cdrone-test ([README](sim-line/README.md))
- `sap-loadtest/`: load all ~258k SAP materials into the cdrone-test db and time Odoo with them ([README](sap-loadtest/README.md))
- `merops-parts/`: sync the Merops RJ2 part list (with in-cell images) into Odoo products ([README](merops-parts/README.md))

Secrets go in environment variables only (`COBRA_DRONE_ODOO_API_KEY`). Never commit them, the source xlsx files, or run outputs.
