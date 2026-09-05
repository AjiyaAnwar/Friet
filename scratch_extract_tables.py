import re
import os

files = ['team_1_backend_architect.md', 'team_2_commercial_backend.md', 'team_3_operations_finance_backend.md']
tables_in_md = set()

for f in files:
    if os.path.exists(f):
        content = open(f, encoding='utf-8').read()
        # Look for table definitions in SQL or SQLAlchemy models
        tables = re.findall(r'__tablename__\s*=\s*["\']([a-zA-Z0-9_]+)["\']', content)
        sql_tables = re.findall(r'CREATE TABLE (?:IF NOT EXISTS )?([a-zA-Z0-9_]+)', content, re.IGNORECASE)
        tables_in_md.update(tables)
        tables_in_md.update(sql_tables)

print("MD Tables:", sorted(list(tables_in_md)))
