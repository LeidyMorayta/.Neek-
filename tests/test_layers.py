"""Offline raster checks: holes, missing observations and API isolation."""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import Polygon, box

from fieldshift.layers import normalized_difference, read_grid, pack


def test_index_masks_nodata_and_zero_denominator():
    result = normalized_difference(np.array([.6, 0, np.nan, -.1]), np.array([.2, 0, .3, .2]))
    assert result[0] == pytest.approx(.5)
    assert np.isnan(result[1:]).all()


def test_raster_preserves_holes_and_nodata(tmp_path):
    geom = Polygon([(0,0),(.01,0),(.01,.01),(0,.01)],
                   holes=[[(.003,.003),(.007,.003),(.007,.007),(.003,.007)]])
    path = tmp_path/'soil.tif'
    values = np.full((10,10), 7, dtype='float32')
    values[0,0] = -9999
    with rasterio.open(path, 'w', driver='GTiff', width=10, height=10, count=1,
                       dtype='float32', crs='EPSG:4326', transform=from_bounds(0,0,.01,.01,10,10), nodata=-9999) as ds:
        ds.write(values, 1)
    grid, resolution = read_grid(path, geom, 112)
    assert np.isnan(grid[4:6,4:6]).all()
    assert np.isnan(grid[0,0])
    assert np.nanmax(grid) == 7
    packed = pack(grid, geom, resolution)
    assert packed['values'][0][0] is None


def test_no_observation_does_not_generate_overlay():
    with pytest.raises(ValueError, match='píxeles válidos'):
        pack(np.full((2,2),np.nan), box(0,0,1,1), 250)


def test_layer_api_validates_polygon_without_network(monkeypatch):
    from fastapi.testclient import TestClient
    import api
    import fieldshift.layers as layers
    def unexpected(*args):
        pytest.fail('Invalid parcel must not contact providers')
    monkeypatch.setattr(layers, 'get_layer', unexpected)
    client = TestClient(api.app)
    assert client.post('/capas/vegetation', json={'puntos':[[0,0],[1,0],[1,1]]}).status_code == 422
    assert client.post('/capas/unknown', json={'puntos':[[0,0],[1,0],[1,1]]}).status_code == 422


def test_removed_erosion_layer_is_rejected():
    from fieldshift.layers import get_layer
    with pytest.raises(ValueError, match='Capa no reconocida'):
        get_layer(box(-89.62,20.828,-89.618,20.830), 'erosion')


def test_vegetation_change_uses_only_pixels_valid_in_both_scenes(monkeypatch):
    import fieldshift.layers as layers
    latest={'values':[[.8,None],[.3,.5]],'resolution_m':10,'source':'test','date':'2026-11-01','scene':'recent'}
    previous=dict(latest,values=[[.4,.5],[None,.7]],date='2026-09-29',scene='prior')
    monkeypatch.setattr(layers,'get_layer',lambda *args:latest)
    seen=[]
    def earlier(geom,layer,before=None):
        seen.append(before)
        return previous
    monkeypatch.setattr(layers,'sentinel_layer',earlier)
    result=layers.vegetation_change(box(-89.62,20.828,-89.618,20.830),30)
    assert result['values']==[[.4,None],[None,-.2]]
    assert result['valid_pixels']==2
    assert result['previous_date']=='2026-09-29'
    assert str(seen[0])=='2026-10-02'
