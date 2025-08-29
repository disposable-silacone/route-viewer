# Map-Matching Improvements

This document summarizes the improvements made to the route-viewer map-matching functionality to reduce side-street detours and improve overall matching quality.

## Improvements Implemented

### 1. Enhanced GPX Generation with Timestamps

**Problem**: GraphHopper's Viterbi algorithm was only using coordinate information, missing valuable speed and heading data from timestamps.

**Solution**: 
- Modified `ParsedTrack` dataclass to include per-point timestamps
- Updated GPX/FIT parsing to collect timestamps during ingest
- Enhanced GeoJSON storage to include timestamp metadata
- Modified map-matching to extract timestamps and include them in GPX sent to GraphHopper

**Files Modified**:
- `backend/app/core/parse_gpx.py` - Added timestamp collection
- `backend/app/core/parse_fit.py` - Added timestamp collection  
- `backend/app/core/geojson.py` - Enhanced to store timestamps
- `backend/app/api/routes_ingest.py` - Updated to use enhanced GeoJSON writer
- `backend/app/api/routes_mapmatch.py` - Added timestamp extraction and GPX generation

### 2. Activity-Type-Based GPS Accuracy Defaults

**Problem**: GPS accuracy was manually set or defaulted to a single value, not accounting for different activity types and device characteristics.

**Solution**:
- Added `_get_default_gps_accuracy()` function with activity-type-specific defaults:
  - Run/Walk/Hike: 5m (foot activities typically have better GPS)
  - Ride/Bike/Cycling: 8m (bike activities may have slightly lower accuracy)
  - Swim: 10m (water activities often have poor GPS)
  - Default: 8m for unknown types
- Updated frontend to show precision level (High/Medium/Low) based on GPS accuracy value
- Auto-populate GPS accuracy field when activity type is selected

**Files Modified**:
- `backend/app/api/routes_mapmatch.py` - Added GPS accuracy defaults
- `frontend/src/pages/MapPage.tsx` - Enhanced GPS accuracy UI

### 3. Post-Processing Cleanup for Short Excursions

**Problem**: Map-matching sometimes creates brief detours down side streets that don't add meaningful distance to the route.

**Solution**:
- Added `_cleanup_short_excursions()` function that:
  - Detects points that create short perpendicular excursions
  - Calculates if the excursion adds minimal distance
  - Removes points that create excursions ≤50m from the main route
  - Preserves route topology while eliminating noise
- Applied cleanup after GraphHopper matching but before saving results

**Files Modified**:
- `backend/app/api/routes_mapmatch.py` - Added excursion cleanup

### 4. Enhanced Logging and Monitoring

**Problem**: Limited visibility into map-matching performance and debugging issues.

**Solution**:
- Added comprehensive logging for map-matching operations:
  - Activity ID, point count, profile, and GPS accuracy used
  - Number of excursion points removed during cleanup
  - Success/failure status with error details
- Logs help with debugging and performance monitoring

**Files Modified**:
- `backend/app/api/routes_mapmatch.py` - Added logging throughout

## Technical Details

### GPS Accuracy Values

The system now uses these default GPS accuracy values based on activity type:

| Activity Type | GPS Accuracy | Precision Level |
|---------------|--------------|-----------------|
| Run/Walk/Hike | 5m | High |
| Ride/Bike/Cycling | 8m | Medium |
| Swim | 10m | Low |
| Unknown/Other | 8m | Medium |

### Excursion Cleanup Algorithm

The cleanup function works by:

1. **Point-to-Line Distance**: Calculates perpendicular distance from each point to the line segment between its neighbors
2. **Excursion Detection**: Identifies points that create excursions >50m from the main route
3. **Distance Analysis**: Compares total excursion distance vs. direct distance
4. **Point Removal**: Removes points that create short, unnecessary detours

### Timestamp Integration

Timestamps are now:
- Collected during GPX/FIT parsing
- Stored in GeoJSON as additional Point features with timestamp properties
- Extracted during map-matching
- Included in GPX sent to GraphHopper as `<time>` elements

## Expected Improvements

These changes should result in:

1. **Better Route Following**: Timestamps help GraphHopper understand speed and direction changes
2. **Reduced Side-Street Detours**: GPS accuracy defaults and excursion cleanup eliminate unnecessary diversions
3. **More Consistent Results**: Activity-type-specific defaults provide appropriate constraints
4. **Better Debugging**: Enhanced logging helps identify and resolve issues

## Testing

All improvements have been tested with:
- GPS accuracy defaults for all activity types
- Excursion cleanup with sample coordinates
- GPX generation with and without timestamps
- All tests pass successfully

## Future Enhancements

Potential next steps:
1. **Custom Model Tuning**: Adjust GraphHopper custom models to favor through-roads
2. **Corridor-Constrained Matching**: Pre-compute mainline corridors to reject perpendicular side streets
3. **Speed-Based Filtering**: Use speed data to identify and remove GPS noise
4. **Reverse Geocoding**: Add start location city/state for better activity organization

## Multi-State GraphHopper Setup

The system now supports hot-swapping between different states (PA, NY, NJ, FL) for map-matching:

### Architecture
- **Multiple GraphHopper Servers**: Each state runs on its own port
  - PA: `http://localhost:8989` (default)
  - NY: `http://localhost:8988`
  - NJ: `http://localhost:8987`
  - FL: `http://localhost:8986`

### State Detection
- **Automatic Detection**: The backend analyzes activity coordinates to determine which state the activity is in
- **Bounding Box Logic**: Uses approximate bounding boxes for each state:
  - PA: ~-80.5 to -75, ~39.7 to 42.3
  - NY: ~-79.8 to -71.8, ~40.5 to 45.1
  - NJ: ~-75.6 to -73.9, ~38.9 to 41.4
  - FL: ~-87.6 to -80, ~24.4 to 31.0

### Starting the Servers
Use the provided batch script to start all servers:
```bash
start_graphhopper_servers.bat
```

Or start them manually:
```bash
# Terminal 1 - PA
cd graphhopper
java -Xms4g -Xmx8g -jar map-matching.jar server config_PA.yaml

# Terminal 2 - NY
cd graphhopper
java -Xms4g -Xmx8g -jar map-matching.jar server config_NY.yaml

# Terminal 3 - NJ
cd graphhopper
java -Xms4g -Xmx8g -jar map-matching.jar server config_NJ.yaml

# Terminal 4 - FL
cd graphhopper
java -Xms4g -Xmx8g -jar map-matching.jar server config_FL.yaml
```

### Benefits
- **Automatic Routing**: No manual state selection needed
- **Optimal Matching**: Each activity uses the most appropriate road network
- **Scalable**: Easy to add more states by adding new configs and servers
- **Transparent**: Users don't need to know which state their activities are in
