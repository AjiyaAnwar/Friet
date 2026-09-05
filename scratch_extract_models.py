import os, re

tables = set()
for root, dirs, files in os.walk('backend/app/db/models'):
    for f in files:
        if f.endswith('.py'):
            content = open(os.path.join(root, f), 'r', encoding='utf-8').read()
            matches = re.findall(r'__tablename__\s*=\s*["\'](.*?)["\']', content)
            tables.update(matches)

print("SQLAlchemy Models defined in code:")
print(sorted(tables))
