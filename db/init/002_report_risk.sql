-- Phase 3: a report's greenwashing risk, from its claims' verdicts.
--
-- risk = 100 x (prominence of vague + unsupported claims) / (prominence of all claims)
--
-- A claim in Section B (director's statement, headline commitments) has prominence 1.5,
-- others 1.0, so a vague headline claim moves the score more than a vague footnote.
CREATE OR REPLACE VIEW report_risk AS
SELECT r.id                                                   AS report_id,
       r.company,
       r.fiscal_year,
       count(c.id)                                            AS claims,
       count(*) FILTER (WHERE v.label = 'substantiated')      AS substantiated,
       count(*) FILTER (WHERE v.label = 'vague')              AS vague,
       count(*) FILTER (WHERE v.label = 'unsupported')        AS unsupported,
       round((100 * coalesce(sum(c.prominence) FILTER (WHERE v.label <> 'substantiated'), 0)
              / nullif(sum(c.prominence), 0))::numeric, 1)    AS risk_score
FROM reports r
JOIN claims c   ON c.report_id = r.id
JOIN verdicts v ON v.claim_id = c.id
GROUP BY r.id, r.company, r.fiscal_year;
