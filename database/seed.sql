-- Seed the skill registry with initial skills
INSERT INTO skills (skill_id, version, intent, output_format, region_code, security_level)
VALUES
  ('triage-basic',     '1.0.0', 'medical triage',                   'text',     'OM',     'high'),
  ('dev-assist',       '1.0.0', 'software development assistance',   'text',     'GLOBAL', 'standard'),
  ('enterprise-query', '1.0.0', 'enterprise data query',             'json',     'GLOBAL', 'high')
ON CONFLICT (skill_id) DO NOTHING;
