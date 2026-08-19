"""Geospatially explicit DEM loading and deterministic terrain derivatives."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import numpy as np
import rasterio

@dataclass(frozen=True)
class DEMData:
    path: str
    elevation_m: np.ndarray
    valid_mask: np.ndarray
    transform: rasterio.Affine
    crs_wkt: str
    x_resolution_m: float
    y_resolution_m: float
    nodata: float | None
    sha256: str

@dataclass(frozen=True)
class TerrainDerivatives:
    gradient_x: np.ndarray
    gradient_y: np.ndarray
    gradient_magnitude: np.ndarray
    slope_degrees: np.ndarray
    aspect_degrees: np.ndarray
    hillshade: np.ndarray
    local_relief_m: np.ndarray
    valid_mask: np.ndarray

@lru_cache(maxsize=8)
def load_dem(path: str) -> DEMData:
    """Load a one-band projected DEM whose horizontal and vertical units are metres.

    Nodata remains masked and is never replaced with elevation zero. Geographic or
    missing CRS is rejected because raw angular/pixel spacing cannot be treated as metres.
    """
    import hashlib
    resolved=Path(path).resolve()
    if not resolved.exists(): raise FileNotFoundError(path)
    try:
        with rasterio.open(resolved) as src:
            if src.count != 1: raise ValueError("DEM must contain exactly one elevation band")
            if src.crs is None or not src.crs.is_projected: raise ValueError("DEM requires a projected CRS with metre units")
            units=(src.crs.linear_units or "").lower()
            if "met" not in units: raise ValueError("DEM projected CRS horizontal units must be metres")
            data=src.read(1,masked=True).astype(np.float64)
            values=np.asarray(data.data,dtype=np.float64)
            valid=~np.ma.getmaskarray(data) & np.isfinite(values)
            if values.ndim!=2 or min(values.shape)<2: raise ValueError("DEM dimensions are invalid")
            xres,yres=abs(float(src.transform.a)),abs(float(src.transform.e))
            if xres<=0 or yres<=0: raise ValueError("DEM pixel resolution must be positive")
            transform,crs,nodata=src.transform,src.crs.to_wkt(),src.nodata
    except rasterio.errors.RasterioIOError as exc: raise ValueError("DEM could not be decoded") from exc
    return DEMData(str(resolved),values,valid,transform,crs,xres,yres,nodata,hashlib.sha256(resolved.read_bytes()).hexdigest())

def clear_dem_cache()->None: load_dem.cache_clear()

def _masked_fill(values:np.ndarray,valid:np.ndarray)->np.ndarray:
    if not valid.any(): return np.zeros_like(values,dtype=float)
    fill=float(np.nanmedian(values[valid])); return np.where(valid,values,fill)

def terrain_derivatives(dem:DEMData,relief_window:int=5,azimuth_deg:float=315,altitude_deg:float=45)->TerrainDerivatives:
    """Compute slope/aspect/hillshade/relief using explicit metre pixel spacing.

    Hillshade uses a configured visualization light, not acquisition illumination.
    It must not be interpreted as observed shading without acquisition metadata.
    """
    from scipy.ndimage import maximum_filter,minimum_filter,binary_erosion
    z=_masked_fill(dem.elevation_m,dem.valid_mask)
    gy,gx=np.gradient(z,dem.y_resolution_m,dem.x_resolution_m)
    stable=binary_erosion(dem.valid_mask,structure=np.ones((3,3)),border_value=0)
    magnitude=np.hypot(gx,gy); slope=np.degrees(np.arctan(magnitude))
    aspect=(np.degrees(np.arctan2(-gx,gy))+360)%360
    az=np.radians(azimuth_deg); alt=np.radians(altitude_deg); slope_r=np.arctan(magnitude); aspect_r=np.radians(aspect)
    shaded=np.sin(alt)*np.cos(slope_r)+np.cos(alt)*np.sin(slope_r)*np.cos(az-aspect_r)
    hillshade=np.clip((shaded+1)/2,0,1)
    relief=maximum_filter(z,size=relief_window,mode='nearest')-minimum_filter(z,size=relief_window,mode='nearest')
    nan=np.full(z.shape,np.nan)
    return TerrainDerivatives(np.where(stable,gx,nan),np.where(stable,gy,nan),np.where(stable,magnitude,nan),
        np.where(stable,slope,nan),np.where(stable,aspect,nan),np.where(stable,hillshade,nan),np.where(stable,relief,nan),stable)

def extract_patch(array:np.ndarray,bbox:tuple[int,int,int,int])->np.ndarray:
    """Extract clipped pixel bbox x,y,width,height; raises on no overlap."""
    x,y,w,h=bbox; x0=max(0,int(np.floor(x)));y0=max(0,int(np.floor(y)));x1=min(array.shape[1],int(np.ceil(x+w)));y1=min(array.shape[0],int(np.ceil(y+h)))
    if x1<=x0 or y1<=y0: raise ValueError("NO_OVERLAP")
    return array[y0:y1,x0:x1]
