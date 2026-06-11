from __future__ import annotations

import gzip
from pathlib import Path
import tempfile

from app.core.parse_activity import parse_activity
from app.core.parse_tcx import parse_tcx_text

SAMPLE_TCX = """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
  xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Running">
      <Name>Morning Run</Name>
      <Id>2020-01-01T10:00:00.000Z</Id>
      <Lap StartTime="2020-01-01T10:00:00.000Z">
        <Track>
          <Trackpoint>
            <Time>2020-01-01T10:00:00.000Z</Time>
            <Position>
              <LatitudeDegrees>40.0</LatitudeDegrees>
              <LongitudeDegrees>-75.0</LongitudeDegrees>
            </Position>
          </Trackpoint>
          <Trackpoint>
            <Time>2020-01-01T10:05:00.000Z</Time>
            <Position>
              <LatitudeDegrees>40.001</LatitudeDegrees>
              <LongitudeDegrees>-75.001</LongitudeDegrees>
            </Position>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""


def test_parse_tcx_text_extracts_track():
    track = parse_tcx_text(SAMPLE_TCX)
    assert track is not None
    assert track.name == "Morning Run"
    assert track.activity_type == "run"
    assert len(track.coordinates) == 2
    assert track.coordinates[0] == (-75.0, 40.0)
    assert track.duration_sec == 300
    assert track.distance_m > 0


def test_parse_activity_handles_tcx_gz():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "run.tcx.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(SAMPLE_TCX)
        track, source = parse_activity(path)
        assert source == "TCX"
        assert track is not None
        assert track.activity_type == "run"
