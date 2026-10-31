# Bounded GEBCO preparation for MarineVerse Objective 2

The retained genuine GEBCO ZIP is a **regional** extract, not a global
bathymetry dataset. The original grid may exceed the existing two-million
cell import safety limit.

The new preview-first command reads the ZIP without extracting arbitrary
archive paths, validates the NetCDF units/dimensions, and calculates an
explicit grid stride that yields at most 1.8 million original grid points.

Preview (no persistent file changes):

```powershell
python -m backend.marine_data.platform.prepare_gebco
```

Prepare only (creates a new local NetCDF, retains ZIP unchanged):

```powershell
python -m backend.marine_data.platform.prepare_gebco --execute
```

Prepare **and** publish regional Bronze/Silver/three Gold products:

```powershell
python -m backend.marine_data.platform.prepare_gebco --execute --publish
```

The product is **lower-resolution sampling**: it selects real original grid
points at every Nth latitude/longitude position. It does not interpolate,
estimate missing depths, produce navigation charts, or claim full spatial
resolution. The selected stride, grid point count, bounds and coverage
limitation are recorded explicitly. Land elevation remains positive upward;
water depth is only derived for negative elevations, not chart datum.

This enables a practical verified regional bathymetry demonstration without
loading a full 13.8-million-cell raster into the current per-record Gold
pipeline. True worldwide GEBCO coverage requires separately licensed/obtained
global source tiles and deliberate storage/cost planning. Never fabricate
or describe this bounded regional sample as full-world coverage.

The command never uses AWS, modifies frozen PostGIS migrations, changes shared
API contracts or re-enables Task Scheduler. Source and generated files stay in
ignored local data directories.
