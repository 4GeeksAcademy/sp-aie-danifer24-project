"""
Safe snippet for basic pandas cleaning. Copy and adapt for your dataset.
Run: python pandas_clean.py  (ensure pandas is installed)
"""
import sys

import pandas as pd

# Load (adjust path and kwargs as needed)
try:
	df = pd.read_csv("data.csv")  # or read_json, read_excel
except FileNotFoundError:
	print("Error: no se encontró data.csv.", file=sys.stderr)
	raise SystemExit(1)
except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as error:
	print(f"Error: no se pudo leer data.csv ({type(error).__name__}).", file=sys.stderr)
	raise SystemExit(1)

if df.empty or not len(df.columns):
	print("Error: data.csv no contiene registros con encabezados.", file=sys.stderr)
	raise SystemExit(1)

print("df_shape", df.shape)
print("df_dtype_counts", df.dtypes.astype(str).value_counts().to_dict())

# Drop fully null columns
df = df.dropna(axis=1, how="all")
print("df_shape_after_drop_all_null_cols", df.shape)

# Fill or drop nulls in key columns (customise columns)
# df = df.dropna(subset=["required_col"])
# df["optional_col"] = df["optional_col"].fillna(0)

# Normalise column names (optional)
df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
print("df_column_count", len(df.columns))

# Deduplicate (optional)
before = len(df)
df = df.drop_duplicates()
print("rows_dropped_duplicates", before - len(df))

# Avoid printing sample rows because input datasets may contain personal data.
