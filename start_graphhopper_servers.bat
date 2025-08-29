@echo off
echo Starting GraphHopper servers for all states...
echo.

echo Starting PA server on port 8989...
start "GraphHopper PA" cmd /k "cd graphhopper && java -Xms4g -Xmx8g -jar map-matching.jar server config_PA.yaml"

echo Starting NY server on port 8988...
start "GraphHopper NY" cmd /k "cd graphhopper && java -Xms4g -Xmx8g -jar map-matching.jar server config_NY.yaml"

echo Starting NJ server on port 8987...
start "GraphHopper NJ" cmd /k "cd graphhopper && java -Xms4g -Xmx8g -jar map-matching.jar server config_NJ.yaml"

echo Starting FL server on port 8986...
start "GraphHopper FL" cmd /k "cd graphhopper && java -Xms4g -Xmx8g -jar map-matching.jar server config_FL.yaml"

echo.
echo All GraphHopper servers started!
echo PA: http://localhost:8989
echo NY: http://localhost:8988
echo NJ: http://localhost:8987
echo FL: http://localhost:8986
echo.
echo The backend will automatically detect the state and route to the correct server.
pause
