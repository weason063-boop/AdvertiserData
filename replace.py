import re

with open('web/src/App.css', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix .data-table
content = re.sub(
    r'\.data-table\s*\{\s*min-width:\s*100%;\s*width:\s*max-content;\s*border-spacing:\s*0;\s*\}',
    '.data-table {\n  min-width: 100%;\n  width: 100%;\n  border-spacing: 0;\n  table-layout: auto;\n}',
    content
)

# Fix .data-table th
content = re.sub(
    r'\.data-table th\s*\{[^}]*?font-weight:\s*800;[^}]*?\}',
    '.data-table th {\n  background: var(--bg-page);\n  padding: 1rem 1.5rem;\n  text-align: left;\n  font-weight: 800 !important;\n  color: var(--text-main) !important;\n  border-bottom: 1px solid var(--border-strong);\n  font-size: 0.85rem !important;\n  text-transform: uppercase;\n  letter-spacing: 0.05em;\n  white-space: nowrap;\n  position: sticky;\n  top: 0;\n  z-index: 10;\n}',
    content
)

# Fix padding for table td
content = re.sub(
    r'\.data-table td\s*\{\s*padding:\s*1rem 1\.5rem;([^}]*?)\}',
    r'.data-table td {\n  padding: 0.85rem 1.5rem;\1}',
    content
)

clients_table_css = '''
.clients-table th:nth-child(1), .clients-table td:nth-child(1) { width: 25%; }
.clients-table th:nth-child(2), .clients-table td:nth-child(2) { width: 15%; }
.clients-table th:nth-child(3), .clients-table td:nth-child(3) { width: auto; min-width: 300px; }
.clients-table th:nth-child(4), .clients-table td:nth-child(4) { width: 120px; white-space: nowrap; }
'''
if '.clients-table th:nth-child' not in content:
    content += clients_table_css

with open('web/src/App.css', 'w', encoding='utf-8') as f:
    f.write(content)

print("Styles updated successfully!")
