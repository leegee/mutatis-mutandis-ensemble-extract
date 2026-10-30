from pathlib import Path
import pyarrow.parquet as pq

path = Path("D:/") / "temp" / "output-passages"

print("File:", path)
print("Exists:", path.exists())
print("Size:", path.stat().st_size if path.exists() else None)

try:
    parquet = pq.ParquetFile(path)

    print("Rows:", parquet.metadata.num_rows)
    print("Row groups:", parquet.metadata.num_row_groups)
    print("Schema:")
    print(parquet.schema)

    for i in range(parquet.metadata.num_row_groups):
        print(f"Reading row group {i}...")
        table = parquet.read_row_group(i)
        print("  Rows read:", table.num_rows)

    print("Full file read successfully.")

except Exception as e:
    print(type(e).__name__, str(e))
    