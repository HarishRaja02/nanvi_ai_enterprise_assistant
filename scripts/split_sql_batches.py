from pathlib import Path

sql_file = Path('deploy/supabase_migration_and_seed.sql')
with open(sql_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

batch_dir = Path('deploy/batches')
batch_dir.mkdir(parents=True, exist_ok=True)

batches = [
    ('part1_remainder_transactions.sql', 1000, 2132),
    ('part2_customers.sql', 2133, 3884),
    ('part3_contracts_and_projects.sql', 3885, 5188),
    ('part4_tasks.sql', 5189, 6390),
    ('part5_employees_departments_invoices.sql', 6391, 7412),
]

for name, start_line, end_line in batches:
    out = batch_dir / name
    chunk = lines[start_line-1:end_line]
    with open(out, 'w', encoding='utf-8') as f:
        f.write('BEGIN;\n' + ''.join(chunk) + '\nCOMMIT;\n')
    print(f'Wrote {name}: {len(chunk)} lines')
