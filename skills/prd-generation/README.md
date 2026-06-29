# PRD Generation Complete Skill

This folder is the reusable PRD Generation skill package.

## Contents

```text
prd-generation/
  SKILL.md
  README.md
  agents/
    openai.yaml
  scripts/
    requirements.txt
    prd_flow/
      __main__.py
      main.py
      ...
```

`SKILL.md` defines the Root and Derive workflows. `scripts/prd_flow/` is the
bundled deterministic backend for Derive mode, so the skill can be copied
without the original repository.

## Derive Mode

From this `prd-generation/` directory:

```powershell
$env:PYTHONPATH = "scripts"
python -m prd_flow `
  --parent-prd <parent_prd.md> `
  --parent-architecture <parent_architecture.yaml> `
  --target-module <module_name> `
  --output <output_prd.md>
```

The backend prefers PyYAML when available and falls back to a small built-in YAML
subset parser for the current PRD/architecture formats.
