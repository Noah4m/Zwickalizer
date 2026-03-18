-- ── Schema ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS test_results (
    id            SERIAL PRIMARY KEY,
    material_name VARCHAR(100) NOT NULL,
    machine_id    VARCHAR(50)  NOT NULL,
    site          VARCHAR(100),
    operator      VARCHAR(100),
    property_name VARCHAR(100) NOT NULL,  -- e.g. tensile_strength, elongation
    value         NUMERIC(12, 4) NOT NULL,
    unit          VARCHAR(20),
    tested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mat_prop ON test_results (material_name, property_name);
CREATE INDEX IF NOT EXISTS idx_tested_at ON test_results (tested_at);

-- ── Seed data: Fancyplast 42, two machines, ~12 months ──────────────────────
-- Machine A: tensile strength slightly declining trend
INSERT INTO test_results (material_name, machine_id, site, operator, property_name, value, unit, tested_at)
SELECT
    'Fancyplast 42',
    'Machine_A',
    'Site_Zurich',
    'op_1',
    'tensile_strength',
    -- start ~52 MPa, drift to ~47 over 12 months + noise
    52.0 - (n * 0.04) + (RANDOM() * 3 - 1.5),
    'MPa',
    NOW() - INTERVAL '365 days' + (n || ' days')::INTERVAL
FROM generate_series(0, 180, 2) AS n;

-- Machine B: tensile strength stable ~50 MPa
INSERT INTO test_results (material_name, machine_id, site, operator, property_name, value, unit, tested_at)
SELECT
    'Fancyplast 42',
    'Machine_B',
    'Site_Basel',
    'op_2',
    'tensile_strength',
    50.0 + (RANDOM() * 3 - 1.5),
    'MPa',
    NOW() - INTERVAL '365 days' + (n || ' days')::INTERVAL
FROM generate_series(0, 180, 2) AS n;

-- Machine A: elongation
INSERT INTO test_results (material_name, machine_id, site, operator, property_name, value, unit, tested_at)
SELECT
    'Fancyplast 42',
    'Machine_A',
    'Site_Zurich',
    'op_1',
    'elongation',
    28.0 + (RANDOM() * 4 - 2),
    '%',
    NOW() - INTERVAL '365 days' + (n || ' days')::INTERVAL
FROM generate_series(0, 180, 2) AS n;

-- Machine A: temperature during test (correlates negatively with elongation)
INSERT INTO test_results (material_name, machine_id, site, operator, property_name, value, unit, tested_at)
SELECT
    'Fancyplast 42',
    'Machine_A',
    'Site_Zurich',
    'op_1',
    'test_temperature',
    23.0 + (RANDOM() * 6),
    '°C',
    NOW() - INTERVAL '365 days' + (n || ' days')::INTERVAL
FROM generate_series(0, 180, 2) AS n;

-- Second material: Rigidex 100
INSERT INTO test_results (material_name, machine_id, site, operator, property_name, value, unit, tested_at)
SELECT
    'Rigidex 100',
    'Machine_A',
    'Site_Zurich',
    'op_3',
    'tensile_strength',
    72.0 + (RANDOM() * 4 - 2),
    'MPa',
    NOW() - INTERVAL '180 days' + (n || ' days')::INTERVAL
FROM generate_series(0, 90, 3) AS n;
