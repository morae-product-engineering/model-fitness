-- Golden database for query_correctness, v0.
--
-- A small legal-domain schema: matters and their associated documents.
-- Used as the SQL execution target for the `query_correctness` evaluator's
-- v0.1 reference Tier-2 dimension. Hermetic — no external dependencies,
-- no random data, no time-sensitive values.

CREATE TABLE matters (
    id          INTEGER PRIMARY KEY,
    client      TEXT NOT NULL,
    practice    TEXT NOT NULL,
    opened_on   TEXT NOT NULL
);

CREATE TABLE documents (
    id          INTEGER PRIMARY KEY,
    matter_id   INTEGER NOT NULL REFERENCES matters(id),
    kind        TEXT NOT NULL,
    pages       INTEGER NOT NULL
);

INSERT INTO matters (id, client, practice, opened_on) VALUES
    (1, 'Acme Ltd',     'corporate',  '2026-01-04'),
    (2, 'Globex Inc',   'litigation', '2026-02-11'),
    (3, 'Initech LLC',  'corporate',  '2026-02-18'),
    (4, 'Soylent Ltd',  'employment', '2026-03-02'),
    (5, 'Umbrella Co',  'litigation', '2026-03-15');

INSERT INTO documents (id, matter_id, kind, pages) VALUES
    (1, 1, 'contract',    24),
    (2, 1, 'memo',         3),
    (3, 2, 'pleading',    18),
    (4, 2, 'evidence',    62),
    (5, 3, 'contract',    11),
    (6, 4, 'policy',      12),
    (7, 4, 'memo',         5),
    (8, 5, 'pleading',    32),
    (9, 5, 'evidence',    47),
    (10, 5, 'memo',        2);
