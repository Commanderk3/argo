import xarray as xr

file_path = r"./test/R7902251_001.nc"
ds = xr.open_dataset(file_path)

print("=== GLOBAL ATTRIBUTES ===")
for attr in ds.attrs:
    print(attr)

print("\n=== VARIABLE ATTRIBUTES (with dimensions) ===")
for var in ds.variables:
    print(f"{var}: {ds[var].dims}")

ds.close()
