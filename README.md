# DemRoadCalculator Plugin
### Calculate slope and aspect along road lines using DEM

The module calculates slope and aspect values for roads, using the DEM. The tool is designed to work with roads in forestry and open-data DEM. You should not use it on roads with engineering structures if you do not have access to high-precision terrain data.

### Input Data

- Raster DEM layer with coordinate reference system which use meters as units and its channel.
- Linear vector layer with road infrastructure.
- The algorithm used to determine the values of perpendicular gradients in the slope formula.
- The distance in meters through which the values are calculated.

### Output Data

- Point vector layer where points located along the baselines with a measurement step. Every point contains attributes with calculated values of DEM height, slope and aspect.
- Line vector layer, where lines are baselines, splitted by points of measure. Every line contains attributes with calculated values of DEM height, slope and aspect at the start and end points.
