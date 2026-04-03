import os

css_path = 'web/src/App.css'
with open(css_path, 'r', encoding='utf-8') as f:
    css = f.read()

# 0. Client history sticky fix (which was lost during checkout)
css = css.replace(
    '.latest-month-table th.col-client {\n  position: sticky;',
    '.latest-month-table th.col-client,\n.client-history-table th.col-month {\n  position: sticky;'
)
css = css.replace(
    '.latest-month-table td.cell-name {\n  position: sticky;',
    '.latest-month-table td.cell-name,\n.client-history-table td.cell-name {\n  position: sticky;'
)
css = css.replace(
    '.latest-month-table tbody td.cell-name {\n  text-align: left;\n}',
    '.latest-month-table tbody td.cell-name,\n.client-history-table tbody td.cell-name {\n  text-align: left;\n}'
)
css = css.replace(
    '.latest-month-table tbody tr:nth-child(even) td.cell-name {\n  background-color: #fff;\n}',
    '.latest-month-table tbody tr:nth-child(even) td.cell-name,\n.client-history-table tbody tr:nth-child(even) td.cell-name {\n  background-color: #fff;\n}'
)
css = css.replace(
    '.latest-month-table tbody tr:hover td.cell-name {\n  background-color: var(--bg-page);\n}',
    '.latest-month-table tbody tr:hover td.cell-name,\n.client-history-table tbody tr:hover td.cell-name {\n  background-color: var(--bg-page);\n}'
)
css = css.replace(
    '.latest-month-table tbody tr.is-selected td.cell-name {\n  background: #eff6ff;\n}',
    '.latest-month-table tbody tr.is-selected td.cell-name,\n.client-history-table tbody tr.is-selected td.cell-name {\n  background: #eff6ff;\n}'
)

# 1. Merge the final override declarations
css = css.replace(
    '.table-wrapper {\n  background: white;\n  border-radius: var(--radius-lg);\n  box-shadow: var(--shadow-sm);\n  border: 1px solid var(--border-strong);\n  flex: 0 1 auto;\n  /* Fix: Shrink to content to avoid huge whitespace */\n  min-height: 0;\n  width: 100%;\n  display: flex;\n  flex-direction: column;\n  overflow: hidden;\n  margin-bottom: 2rem;\n}',
    '.table-wrapper {\n  background: white;\n  border-radius: var(--radius-lg);\n  box-shadow: var(--shadow-sm);\n  border: 1px solid var(--border-strong);\n  flex: 0 1 auto;\n  min-height: 0;\n  width: 100%;\n  display: flex;\n  flex-direction: column;\n  overflow: hidden;\n  margin-bottom: 2rem;\n  height: fit-content;\n}'
)
css = css.replace(
    '.data-table th {\n  background: var(--bg-page);\n  padding: 1rem 1.5rem;\n  text-align: left;\n  font-weight: 800;\n  color: var(--text-secondary);\n  border-bottom: 1px solid var(--border-strong);\n  border-right: none !important;\n  /* Remove separator line as requested */\n  border-left: none !important;',
    '.data-table th {\n  background: var(--bg-page);\n  padding: 1rem 1.5rem;\n  text-align: left;\n  font-weight: 800;\n  color: var(--text-main);\n  border-bottom: 1px solid var(--border-strong);\n  border-right: none;\n  border-left: none;'
)
css = css.replace(
    '.data-table td {\n  padding: 1rem 1.5rem;\n  border-bottom: 1px solid var(--border-subtle);\n  border-right: none !important;\n  /* Remove separator line as requested */\n  border-left: none !important;',
    '.data-table td {\n  padding: 1rem 1.5rem;\n  border-bottom: 1px solid var(--border-subtle);\n  border-right: none;\n  border-left: none;'
)

# Clients-table rules from bottom
clients_rules = '''
.clients-table th:nth-child(1),
.clients-table td:nth-child(1) {
  width: 25%;
}

.clients-table th:nth-child(2),
.clients-table td:nth-child(2) {
  width: 15%;
}

.clients-table th:nth-child(3),
.clients-table td:nth-child(3) {
  width: auto;
  min-width: 300px;
}

.clients-table th:nth-child(4),
.clients-table td:nth-child(4) {
  width: 120px;
  white-space: nowrap;
}
'''
css = css.replace(
    '.clients-table {\n  min-width: 1320px;\n}',
    '.clients-table {\n  min-width: 1320px;\n}' + clients_rules
)

# Adjust tab-content
css = css.replace(
    '.tab-content {\n  flex: 1;\n  display: flex;\n  flex-direction: column;\n  justify-content: flex-start;\n  align-items: stretch;\n  position: relative;\n  overflow-y: auto;\n  overflow-x: hidden;\n  padding: 2rem 2.5rem;\n}',
    '.tab-content {\n  justify-content: flex-start;\n  align-items: stretch;\n  flex: 1;\n  display: flex;\n  flex-direction: column;\n  position: relative;\n  overflow-y: auto;\n  overflow-x: hidden;\n  padding: 2rem 2.5rem;\n}'
)

# 2. Chop off the Final UI Refinements block
idx = css.find('/* --- Final UI Refinements & Overrides --- */')
if idx != -1:
    css = css[:idx]

# 3. Append ClientTrendModal.css
with open('web/src/ClientTrendModal.css', 'r', encoding='utf-8') as f2:
    trend_css = f2.read()

css += '\n/* --- Trend Modal Additions --- */\n' + trend_css

with open(css_path, 'w', encoding='utf-8') as f:
    f.write(css)

print("App.css modification completed.")
